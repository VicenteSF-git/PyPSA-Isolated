from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def make_load_profile_8760(
    snapshots: pd.DatetimeIndex,
    annual_mean_mw: float,
    daily_amp: float = 0.12,
    weekly_amp: float = 0.06,
    seasonal_amp: float = 0.10,
    noise_amp: float = 0.02,
    seed: int = 0,
) -> pd.Series:
    """Generate synthetic hourly load profile with diurnal, weekly and seasonal variation."""
    rng = np.random.default_rng(seed)

    h = snapshots.hour.values
    dow = snapshots.dayofweek.values
    doy = snapshots.dayofyear.values

    diurnal = 1 + daily_amp * np.sin(2 * np.pi * (h - 19) / 24)
    weekend = np.where(dow >= 5, 1 - weekly_amp, 1.0)
    seasonal = 1 + seasonal_amp * np.cos(2 * np.pi * (doy - 200) / 365)
    noise = 1 + noise_amp * rng.standard_normal(len(snapshots))

    profile = diurnal * weekend * seasonal * noise
    profile = profile / profile.mean()

    return pd.Series(annual_mean_mw * profile, index=snapshots, name="load_mw")


def _safe_float(value, default: float) -> float:
    try:
        val = float(value)
        if np.isnan(val):
            return default
        return val
    except (TypeError, ValueError):
        return default


def _infer_case_folder_from_nodes_csv(csv_nodes: str) -> Path:
    p = Path(csv_nodes)
    if not p.is_absolute():
        p = PROJECT_DIR / p
    return p.resolve().parent


def _resolve_case_relative_path(case_folder: Path, path_value: str) -> Path:
    p = Path(path_value)
    if p.is_absolute():
        return p

    # Avoid duplicated paths like input_case/input_case/file.csv
    if p.parts and p.parts[0] == case_folder.name:
        return case_folder.parent / p

    return case_folder / p


def _resolve_demand_csv(case_folder: Path, demand_csv: Optional[str]) -> Path:
    if demand_csv is None or str(demand_csv).strip() == "":
        return case_folder / "demand_profiles.csv"

    return _resolve_case_relative_path(case_folder, str(demand_csv))


def _normalize_timestamps_to_snapshots(ts: pd.Series, snapshots: pd.DatetimeIndex) -> pd.DatetimeIndex:
    try:
        idx = pd.DatetimeIndex(pd.to_datetime(ts, errors="raise"))
    except Exception as exc:
        raise ValueError(f"Invalid timestamp values in demand CSV: {exc}") from exc

    if idx.tz is not None:
        idx = idx.tz_convert(None)

    return idx


def _expand_8760_profile_to_leap_year(
    series: pd.Series,
    snapshots: pd.DatetimeIndex,
) -> pd.Series:
    """Expand a non-leap annual profile to a leap-year snapshot index.

    The 29 February hours are filled using the same hour from 28 February.
    """
    if len(snapshots) != 8784:
        return series

    leap_day_mask = (snapshots.month == 2) & (snapshots.day == 29)
    if leap_day_mask.sum() != 24:
        return series

    base_index = snapshots[~leap_day_mask]
    if len(series) != len(base_index):
        return series

    aligned = pd.Series(series.values, index=base_index, name=series.name)
    leap_day = pd.date_range(
        f"{snapshots[0].year}-02-29 00:00",
        f"{snapshots[0].year}-02-29 23:00",
        freq="h",
    )
    feb_28 = pd.date_range(
        f"{snapshots[0].year}-02-28 00:00",
        f"{snapshots[0].year}-02-28 23:00",
        freq="h",
    )
    leap_values = aligned.reindex(feb_28).values
    if len(leap_values) != 24 or pd.isna(leap_values).any():
        return series

    leap_series = pd.Series(leap_values, index=leap_day, name=series.name)
    expanded = pd.concat([aligned, leap_series]).sort_index()
    return expanded


def _validate_series(
    series_df: pd.DataFrame,
    demand_type: str,
    zone: str,
    snapshots: pd.DatetimeIndex,
) -> Tuple[pd.Series, Dict[str, str]]:
    details: Dict[str, str] = {}

    if series_df.empty:
        raise ValueError(f"Empty demand series for demand_type='{demand_type}', zone='{zone}'")

    series_df = series_df.sort_values("timestamp")
    if series_df["timestamp"].duplicated().any():
        raise ValueError(
            f"Duplicate timestamps in demand series for demand_type='{demand_type}', zone='{zone}'"
        )

    ts_index = _normalize_timestamps_to_snapshots(series_df["timestamp"], snapshots)
    values = pd.to_numeric(series_df["demand_mw"], errors="coerce").astype(float)

    nan_count = int(values.isna().sum())
    if nan_count > 0:
        raise ValueError(
            f"NaN/non-numeric demand_mw ({nan_count} rows) for demand_type='{demand_type}', zone='{zone}'"
        )

    if (values < 0).any():
        neg_count = int((values < 0).sum())
        raise ValueError(
            f"Negative demand_mw ({neg_count} rows) for demand_type='{demand_type}', zone='{zone}'"
        )

    s = pd.Series(values.values.astype(float), index=ts_index, name=zone).sort_index()

    if not s.index.equals(snapshots):
        expanded = _expand_8760_profile_to_leap_year(s, snapshots)
        if not expanded.index.equals(snapshots):
            missing = snapshots.difference(s.index)
            extra = s.index.difference(snapshots)
            raise ValueError(
                "Demand timestamps must match snapshots exactly for "
                f"demand_type='{demand_type}', zone='{zone}'. "
                f"Missing={len(missing)}, Extra={len(extra)}"
            )
        s = expanded

    details["status"] = "ok"
    details["rows"] = str(len(s))
    return s, details


def _build_fallback_demand(
    snapshots: pd.DatetimeIndex,
    nodes_df: pd.DataFrame,
    demand_type: str,
    seed_start: int,
) -> pd.DataFrame:
    out = pd.DataFrame(index=snapshots, dtype=float)

    if demand_type == "electricity":
        if "annual_mean_mw" not in nodes_df.columns:
            raise ValueError("nodes_df missing 'annual_mean_mw' required for electricity fallback")
        for i, row in nodes_df.reset_index(drop=True).iterrows():
            zone = str(row["zone"])
            annual_mean_mw = _safe_float(row.get("annual_mean_mw", 0.0), 0.0)
            if annual_mean_mw <= 0:
                annual_mean_mw = 0.0
            out[zone] = make_load_profile_8760(snapshots, annual_mean_mw, seed=seed_start + i)
        return out

    if demand_type == "heat":
        if "annual_heat_mean_mw" not in nodes_df.columns:
            return out
        for i, row in nodes_df.reset_index(drop=True).iterrows():
            zone = str(row["zone"])
            annual_mean_mw = _safe_float(row.get("annual_heat_mean_mw", 0.0), 0.0)
            if annual_mean_mw <= 0:
                continue
            out[zone] = make_load_profile_8760(
                snapshots,
                annual_mean_mw,
                daily_amp=0.10,
                weekly_amp=0.04,
                seasonal_amp=0.35,
                noise_amp=0.015,
                seed=seed_start + i,
            )
        return out

    return out


def build_demands(
    snapshots: pd.DatetimeIndex,
    nodes_df: pd.DataFrame,
    csv_nodes: str,
    demand_csv: Optional[str] = None,
    fallback_to_synthetic: bool = True,
    summary_output_csv: Optional[str] = None,
    seed_start_by_type: Optional[Dict[str, int]] = None,
    demand_round_decimals: Optional[int] = None,
) -> Tuple[Dict[str, pd.DataFrame], pd.DataFrame]:
    """
    Build demand profiles by type from CSV input with validation and synthetic fallback.

    Standard CSV format:
    - timestamp: hourly timestamps matching snapshots exactly
    - zone: node/zone identifier (must exist in nodes_df.zone)
    - demand_type: e.g. electricity, heat, hydrogen, others
    - demand_mw: non-negative demand in MW
    """
    if "zone" not in nodes_df.columns:
        raise ValueError("nodes_df must contain 'zone' column")

    if demand_round_decimals is not None:
        try:
            demand_round_decimals = int(demand_round_decimals)
        except (TypeError, ValueError) as exc:
            raise ValueError("demand_round_decimals must be an integer or None") from exc
        if demand_round_decimals < 0:
            raise ValueError("demand_round_decimals must be >= 0")

    case_folder = _infer_case_folder_from_nodes_csv(csv_nodes)
    demand_csv_path = _resolve_demand_csv(case_folder, demand_csv)

    seeds = {"electricity": 10, "heat": 1010}
    if seed_start_by_type:
        seeds.update(seed_start_by_type)

    zones = set(nodes_df["zone"].astype(str).tolist())
    demand_by_type: Dict[str, pd.DataFrame] = {}
    summary_rows = []

    if demand_csv_path.exists():
        df = pd.read_csv(demand_csv_path, comment="#")
        required_cols = ["timestamp", "zone", "demand_type", "demand_mw"]
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing columns in {demand_csv_path}: {missing_cols}")

        df = df.copy()
        df["zone"] = df["zone"].astype(str)
        df["demand_type"] = df["demand_type"].astype(str).str.strip().str.lower()

        unknown_zones = sorted(set(df["zone"].unique()) - zones)
        if unknown_zones:
            raise ValueError(
                f"Demand CSV contains unknown zones not present in nodes.csv: {unknown_zones}"
            )

        for demand_type in sorted(df["demand_type"].unique()):
            subset_type = df[df["demand_type"] == demand_type]
            out = pd.DataFrame(index=snapshots)

            for zone in sorted(subset_type["zone"].unique()):
                zone_df = subset_type[subset_type["zone"] == zone].copy()
                # If the CSV contains multiple scenario years, keep only rows that fall
                # within the current snapshot range, then drop any duplicate timestamps
                # that may exist as block-separator artefacts.
                try:
                    ts_parsed = pd.to_datetime(zone_df["timestamp"], errors="coerce")
                    mask = ts_parsed.between(snapshots.min(), snapshots.max())
                    if mask.any():
                        zone_df = zone_df[mask].copy()
                    # Drop duplicate timestamps, keeping first occurrence
                    zone_df = zone_df.drop_duplicates(subset=["timestamp"], keep="first")
                except Exception:
                    pass
                series, _ = _validate_series(zone_df, demand_type, zone, snapshots)
                out[zone] = series.values

            if demand_round_decimals is not None:
                out = out.round(demand_round_decimals)

            demand_by_type[demand_type] = out

            for zone in out.columns:
                s = out[zone]
                monthly_total_mwh = s.resample("ME").sum().sum()
                summary_rows.append(
                    {
                        "demand_type": demand_type,
                        "zone": str(zone),
                        "source": "csv",
                        "rows": int(len(s)),
                        "annual_total_mwh": float(s.sum()),
                        "monthly_total_mwh_sum": float(monthly_total_mwh),
                        "mean_mw": float(s.mean()),
                        "min_mw": float(s.min()),
                        "max_mw": float(s.max()),
                    }
                )

    elif not fallback_to_synthetic:
        raise FileNotFoundError(
            f"Demand CSV not found and fallback disabled: {demand_csv_path}"
        )

    # Only electricity gets a synthetic fallback; heat requires explicit CSV data
    if "electricity" not in demand_by_type:
        if fallback_to_synthetic:
            logger.warning(
                "Electricity demand CSV not found at %s; generating synthetic fallback demand for zones: %s",
                demand_csv_path,
                ", ".join(sorted(zones)),
            )
            seed = int(seeds.get("electricity", 10))
            fallback_df = _build_fallback_demand(
                snapshots=snapshots,
                nodes_df=nodes_df,
                demand_type="electricity",
                seed_start=seed,
            )
            demand_by_type["electricity"] = fallback_df
            for zone in fallback_df.columns:
                s = fallback_df[zone]
                monthly_total_mwh = s.resample("ME").sum().sum()
                summary_rows.append(
                    {
                        "demand_type": "electricity",
                        "zone": str(zone),
                        "source": "synthetic_fallback",
                        "rows": int(len(s)),
                        "annual_total_mwh": float(s.sum()),
                        "monthly_total_mwh_sum": float(monthly_total_mwh),
                        "mean_mw": float(s.mean()),
                        "min_mw": float(s.min()),
                        "max_mw": float(s.max()),
                    }
                )
        else:
            demand_by_type["electricity"] = pd.DataFrame(index=snapshots)

    summary_df = pd.DataFrame(summary_rows)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(["demand_type", "zone"]).reset_index(drop=True)

    if summary_output_csv:
        out_path = _resolve_case_relative_path(case_folder, str(summary_output_csv))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        summary_df.to_csv(out_path, index=False)

    return demand_by_type, summary_df
