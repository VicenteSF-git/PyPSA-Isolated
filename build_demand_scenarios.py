from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

import numpy as np
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent
REQUIRED_CONFIG_COLUMNS = [
    "scenario",
    "year",
    "zone",
    "component",
    "enabled",
    "growth_factor",
    "annual_energy_mwh",
    "unit_count",
    "energy_per_unit_kwh_per_year",
    "profile_type",
    "demand_type",
]

COMPONENTS_SUPPORTED = {
    "base_load",
    "ev",
    "heating",
    "cooking",
    "process_electrification",
    "ptx_export",
}


def _resolve_path(path_value: str | Path, base_folder: Optional[Path] = None) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    if base_folder is not None:
        return (base_folder / path).resolve()
    return (PROJECT_DIR / path).resolve()


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "t", "yes", "y"}


def _to_float_or_nan(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def read_base_demand(base_demand_csv: str | Path, base_year: Optional[int] = None) -> pd.DataFrame:
    """Read and validate base demand CSV in long format.

    If base_year is given, only rows whose timestamp falls within that calendar
    year are kept.  This allows the input CSV to contain multiple years (e.g. a
    multi-year demand_profiles.csv produced by the model run) without causing
    profile-length errors downstream.
    """
    path = _resolve_path(base_demand_csv)
    if not path.exists():
        raise FileNotFoundError(f"Base demand CSV not found: {path}")

    df = pd.read_csv(path, comment="#")
    required = ["timestamp", "zone", "demand_type", "demand_mw"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in base demand CSV {path}: {missing}")

    out = df[required].copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="raise")
    if getattr(out["timestamp"].dt, "tz", None) is not None:
        out["timestamp"] = out["timestamp"].dt.tz_convert(None)

    if base_year is not None:
        mask = out["timestamp"].dt.year == int(base_year)
        if not mask.any():
            raise ValueError(
                f"No rows found for base_year={base_year} in {path}. "
                f"Years present: {sorted(out['timestamp'].dt.year.unique().tolist())}"
            )
        out = out[mask].copy()

    out["zone"] = out["zone"].astype(str).str.strip()
    out["demand_type"] = out["demand_type"].astype(str).str.strip().str.lower()
    out["demand_mw"] = pd.to_numeric(out["demand_mw"], errors="coerce")

    if out["demand_mw"].isna().any():
        count = int(out["demand_mw"].isna().sum())
        raise ValueError(f"Base demand contains non-numeric demand_mw values: {count}")

    if (out["demand_mw"] < 0).any():
        count = int((out["demand_mw"] < 0).sum())
        raise ValueError(f"Base demand contains negative demand values: {count}")

    return out.sort_values("timestamp").reset_index(drop=True)


def read_config(config_csv: str | Path) -> pd.DataFrame:
    """Read scenario assumptions and validate required structure."""
    path = _resolve_path(config_csv)
    if not path.exists():
        raise FileNotFoundError(f"Config CSV not found: {path}")

    cfg = pd.read_csv(path, comment="#")
    missing = [c for c in REQUIRED_CONFIG_COLUMNS if c not in cfg.columns]
    if missing:
        raise ValueError(f"Missing columns in config CSV {path}: {missing}")

    out = cfg.copy()
    out["scenario"] = out["scenario"].astype(str).str.strip()
    out["zone"] = out["zone"].astype(str).str.strip()
    out["component"] = out["component"].astype(str).str.strip().str.lower()
    out["demand_type"] = out["demand_type"].astype(str).str.strip().str.lower()
    out["profile_type"] = out["profile_type"].astype(str).str.strip().str.lower()
    out["enabled"] = out["enabled"].map(_to_bool)
    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype("Int64")

    numeric_cols = [
        "growth_factor",
        "annual_energy_mwh",
        "unit_count",
        "energy_per_unit_kwh_per_year",
    ]
    for col in numeric_cols:
        out[col] = out[col].map(_to_float_or_nan)

    if out["year"].isna().any():
        raise ValueError("Config has invalid year values.")

    unknown_components = sorted(set(out["component"]) - COMPONENTS_SUPPORTED)
    if unknown_components:
        raise ValueError(f"Unsupported component values in config: {unknown_components}")

    enabled = out[out["enabled"]].copy()
    if enabled.empty:
        raise ValueError("No enabled rows found in config.")

    missing_info_rows = []
    for idx, row in enabled.iterrows():
        component = row["component"]
        annual = row["annual_energy_mwh"]
        units = row["unit_count"]
        energy_per_unit = row["energy_per_unit_kwh_per_year"]
        growth = row["growth_factor"]

        if component == "base_load":
            if pd.isna(growth):
                missing_info_rows.append(int(idx))
            continue

        has_direct = pd.notna(annual)
        has_activity = pd.notna(units) and pd.notna(energy_per_unit)
        if not (has_direct or has_activity):
            missing_info_rows.append(int(idx))

    if missing_info_rows:
        raise ValueError(
            "Enabled config rows missing demand definition (annual_energy_mwh or "
            "unit_count + energy_per_unit_kwh_per_year, or growth_factor for base_load). "
            f"Rows: {missing_info_rows}"
        )

    return out


def make_snapshots_for_year(year: int) -> pd.DatetimeIndex:
    """Create hourly snapshots for a full year (8760 or 8784 for leap years)."""
    snapshots = pd.date_range(
        f"{int(year)}-01-01 00:00",
        f"{int(year)}-12-31 23:00",
        freq="h",
    )
    return snapshots


def map_profile_to_year(profile: pd.Series, target_snapshots: pd.DatetimeIndex) -> pd.Series:
    """Map an hourly single-year profile to target year snapshots with leap-year handling."""
    if profile.empty:
        raise ValueError("Cannot map an empty profile.")

    s = pd.Series(pd.to_numeric(profile.values, errors="coerce"), index=profile.index).dropna()
    if len(s) not in (8760, 8784):
        raise ValueError(f"Profile length must be 8760 or 8784 hours, got {len(s)}")

    s = s.sort_index().reset_index(drop=True)
    target_is_leap = len(target_snapshots) == 8784

    if len(s) == 8760 and target_is_leap:
        feb28_start = 24 * (31 + 27)
        feb28 = s.iloc[feb28_start : feb28_start + 24].copy()
        mapped = pd.concat(
            [s.iloc[: feb28_start + 24], feb28, s.iloc[feb28_start + 24 :]],
            ignore_index=True,
        )
    elif len(s) == 8784 and not target_is_leap:
        feb29_start = 24 * (31 + 28)
        mapped = pd.concat(
            [s.iloc[:feb29_start], s.iloc[feb29_start + 24 :]],
            ignore_index=True,
        )
    else:
        mapped = s

    if len(mapped) != len(target_snapshots):
        raise ValueError(
            f"Mapped profile length mismatch: {len(mapped)} vs {len(target_snapshots)}"
        )

    return pd.Series(mapped.values.astype(float), index=target_snapshots)


def normalize_profile(profile: pd.Series) -> pd.Series:
    """Normalize profile so annual sum equals 1."""
    s = pd.to_numeric(profile, errors="coerce").astype(float)
    if s.isna().any():
        raise ValueError("Profile contains NaN values.")
    if (s < 0).any():
        raise ValueError("Profile contains negative values.")

    total = float(s.sum())
    if total <= 0:
        raise ValueError("Profile sum must be positive for normalization.")
    return s / total


def _read_optional_profiles(profiles_csv: Optional[str | Path]) -> Dict[str, pd.Series]:
    if profiles_csv is None or str(profiles_csv).strip() == "":
        return {}

    path = _resolve_path(profiles_csv)
    if not path.exists():
        raise FileNotFoundError(f"Profiles CSV not found: {path}")

    df = pd.read_csv(path, comment="#")
    if "timestamp" not in df.columns:
        raise ValueError("Profiles CSV must contain a timestamp column.")

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="raise")

    profiles: Dict[str, pd.Series] = {}

    if {"profile_type", "value"}.issubset(df.columns):
        narrow = df[["timestamp", "profile_type", "value"]].copy()
        narrow["profile_type"] = narrow["profile_type"].astype(str).str.strip().str.lower()
        narrow["value"] = pd.to_numeric(narrow["value"], errors="coerce")
        if narrow["value"].isna().any():
            raise ValueError("Profiles CSV contains non-numeric profile values.")
        for ptype, group in narrow.groupby("profile_type"):
            s = group.sort_values("timestamp").set_index("timestamp")["value"]
            profiles[ptype] = s
        return profiles

    value_columns = [c for c in df.columns if c != "timestamp"]
    if not value_columns:
        raise ValueError("Profiles CSV has no profile value columns.")

    for col in value_columns:
        values = pd.to_numeric(df[col], errors="coerce")
        if values.isna().any():
            raise ValueError(f"Profiles CSV contains non-numeric values in column: {col}")
        profiles[str(col).strip().lower()] = pd.Series(values.values, index=df["timestamp"])

    return profiles


def _default_profile_for_component(
    component: str,
    snapshots: pd.DatetimeIndex,
) -> pd.Series:
    h = snapshots.hour.values
    dow = snapshots.dayofweek.values
    month = snapshots.month.values

    if component == "ev":
        evening_peak = np.exp(-0.5 * ((h - 20) / 2.5) ** 2)
        weekend_shift = np.where(dow >= 5, 1.10, 1.00)
        values = 0.25 + 1.75 * evening_peak
        return pd.Series(values * weekend_shift, index=snapshots)

    if component == "heating":
        winter_factor = np.where(np.isin(month, [5, 6, 7, 8, 9]), 1.8, 0.6)
        daily_shape = 0.55 + 0.45 * np.exp(-0.5 * ((h - 7) / 3.0) ** 2) + 0.35 * np.exp(
            -0.5 * ((h - 20) / 3.5) ** 2
        )
        return pd.Series(winter_factor * daily_shape, index=snapshots)

    if component == "cooking":
        breakfast = np.exp(-0.5 * ((h - 8) / 1.5) ** 2)
        lunch = np.exp(-0.5 * ((h - 13) / 1.5) ** 2)
        dinner = np.exp(-0.5 * ((h - 20) / 1.8) ** 2)
        values = 0.10 + 0.8 * breakfast + 0.7 * lunch + 1.2 * dinner
        return pd.Series(values, index=snapshots)

    if component == "process_electrification":
        business_hours = ((h >= 7) & (h <= 19)).astype(float)
        weekday = np.where(dow < 5, 1.0, 0.7)
        values = 0.45 + 0.55 * business_hours
        return pd.Series(values * weekday, index=snapshots)

    if component == "ptx_export":
        return pd.Series(np.ones(len(snapshots)), index=snapshots)

    return pd.Series(np.ones(len(snapshots)), index=snapshots)


def _get_base_series(
    base_demand_df: pd.DataFrame,
    zone: str,
    demand_type: str,
) -> pd.Series:
    subset = base_demand_df[
        (base_demand_df["zone"] == zone)
        & (base_demand_df["demand_type"] == demand_type)
    ].copy()
    if subset.empty:
        raise ValueError(
            f"No base demand data found for zone='{zone}', demand_type='{demand_type}'."
        )

    subset = subset.groupby("timestamp", as_index=False)["demand_mw"].sum().sort_values("timestamp")
    out = subset.set_index("timestamp")["demand_mw"]
    if len(out) not in (8760, 8784):
        raise ValueError(
            f"Base demand for zone='{zone}', demand_type='{demand_type}' must have 8760/8784 rows; "
            f"got {len(out)}"
        )
    return out


def _annual_energy_mwh_from_row(row: pd.Series) -> float:
    direct = row["annual_energy_mwh"]
    if pd.notna(direct):
        return float(direct)

    units = row["unit_count"]
    energy_unit = row["energy_per_unit_kwh_per_year"]
    if pd.notna(units) and pd.notna(energy_unit):
        return float(units) * float(energy_unit) / 1000.0

    raise ValueError(
        "Cannot compute annual energy. Provide annual_energy_mwh or "
        "unit_count and energy_per_unit_kwh_per_year."
    )


def build_base_component(
    row: pd.Series,
    base_demand_df: pd.DataFrame,
    snapshots: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Build base_load component by scaling mapped base year profile by growth_factor."""
    growth = row["growth_factor"]
    if pd.isna(growth):
        raise ValueError("base_load requires growth_factor.")
    growth = float(growth)
    if growth < 0:
        raise ValueError("growth_factor must be non-negative.")

    base_series = _get_base_series(
        base_demand_df=base_demand_df,
        zone=row["zone"],
        demand_type=row["demand_type"],
    )
    mapped = map_profile_to_year(base_series, snapshots)
    demand = mapped * growth

    out = pd.DataFrame(
        {
            "timestamp": snapshots,
            "zone": row["zone"],
            "scenario": row["scenario"],
            "year": int(row["year"]),
            "component": row["component"],
            "demand_type": row["demand_type"],
            "demand_mw": demand.values,
        }
    )
    return out


def build_synthetic_component(
    row: pd.Series,
    snapshots: pd.DatetimeIndex,
    profile_library: Dict[str, pd.Series],
    base_demand_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build synthetic component from annual energy and normalized profile."""
    annual_energy_mwh = _annual_energy_mwh_from_row(row)
    if annual_energy_mwh < 0:
        raise ValueError("annual energy must be non-negative.")

    profile_type = row["profile_type"]
    component = row["component"]

    if profile_type == "constant":
        profile = pd.Series(np.ones(len(snapshots)), index=snapshots)
    elif profile_type == "base_2025":
        base_series = _get_base_series(
            base_demand_df=base_demand_df,
            zone=row["zone"],
            demand_type=row["demand_type"],
        )
        profile = map_profile_to_year(base_series, snapshots)
    elif profile_type in profile_library:
        profile = map_profile_to_year(profile_library[profile_type], snapshots)
    else:
        profile = _default_profile_for_component(component=component, snapshots=snapshots)

    normalized = normalize_profile(profile)
    demand = normalized * annual_energy_mwh

    out = pd.DataFrame(
        {
            "timestamp": snapshots,
            "zone": row["zone"],
            "scenario": row["scenario"],
            "year": int(row["year"]),
            "component": row["component"],
            "demand_type": row["demand_type"],
            "demand_mw": demand.values,
        }
    )
    return out


def _validate_component_output(
    component_df: pd.DataFrame,
    snapshots: pd.DatetimeIndex,
    scenario: str,
    year: int,
) -> None:
    if component_df.empty:
        raise ValueError(f"No component output generated for scenario={scenario}, year={year}")

    if (component_df["demand_mw"] < 0).any():
        count = int((component_df["demand_mw"] < 0).sum())
        raise ValueError(
            f"Negative demand found in scenario={scenario}, year={year}: {count} rows"
        )

    for (zone, component, demand_type), group in component_df.groupby(
        ["zone", "component", "demand_type"], dropna=False
    ):
        idx = pd.DatetimeIndex(group["timestamp"]).sort_values()
        if not idx.equals(snapshots):
            raise ValueError(
                "Output snapshots mismatch for "
                f"scenario={scenario}, year={year}, zone={zone}, component={component}, "
                f"demand_type={demand_type}"
            )


def build_scenario(
    scenario_cfg: pd.DataFrame,
    base_demand_df: pd.DataFrame,
    profile_library: Dict[str, pd.Series],
    base_year: Optional[int] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build component-level and aggregated scenario demand outputs."""
    if scenario_cfg.empty:
        raise ValueError("Scenario configuration is empty.")

    scenario = str(scenario_cfg["scenario"].iloc[0])
    year = int(scenario_cfg["year"].iloc[0])
    snapshots = make_snapshots_for_year(year)

    components = []
    for _, row in scenario_cfg.iterrows():
        component = row["component"]
        if component == "base_load":
            comp_df = build_base_component(
                row=row,
                base_demand_df=base_demand_df,
                snapshots=snapshots,
            )
        else:
            comp_df = build_synthetic_component(
                row=row,
                snapshots=snapshots,
                profile_library=profile_library,
                base_demand_df=base_demand_df,
            )
        components.append(comp_df)

    component_df = pd.concat(components, ignore_index=True)
    _validate_component_output(component_df, snapshots, scenario=scenario, year=year)

    aggregated = (
        component_df.groupby(["timestamp", "zone", "demand_type"], as_index=False)["demand_mw"]
        .sum()
        .sort_values(["timestamp", "zone", "demand_type"])
        .reset_index(drop=True)
    )

    summary = (
        component_df.groupby(
            ["scenario", "year", "zone", "component", "demand_type"], as_index=False
        )["demand_mw"]
        .agg(
            annual_energy_mwh="sum",
            mean_mw="mean",
            max_mw="max",
            min_mw="min",
        )
        .sort_values(["scenario", "year", "zone", "component", "demand_type"])
        .reset_index(drop=True)
    )

    return aggregated, component_df, summary


def write_scenario_outputs(
    input_case_folder: str | Path,
    scenario: str,
    aggregated_df: pd.DataFrame,
    component_df: pd.DataFrame,
) -> Tuple[Path, Path]:
    """Write demand_profiles_{scenario}.csv and demand_components_{scenario}.csv.

    All years for the scenario are written together in a single file each.
    The existing build_demands() loader in build_demand.py filters by timestamp
    range automatically, so each run_case(year=...) call picks up only the
    relevant year from the combined file.
    """
    case_folder = _resolve_path(input_case_folder)

    demand_profiles_path = case_folder / f"demand_profiles_{scenario}.csv"
    demand_components_path = case_folder / f"demand_components_{scenario}.csv"

    aggregated_df = (
        aggregated_df[["timestamp", "zone", "demand_type", "demand_mw"]]
        .sort_values(["timestamp", "zone", "demand_type"])
        .reset_index(drop=True)
    )
    component_df = (
        component_df[["timestamp", "zone", "scenario", "year", "component", "demand_type", "demand_mw"]]
        .sort_values(["timestamp", "zone", "component"])
        .reset_index(drop=True)
    )

    aggregated_df.to_csv(demand_profiles_path, index=False)
    component_df.to_csv(demand_components_path, index=False)
    return demand_profiles_path, demand_components_path


def write_summary(input_case_folder: str | Path, summary_df: pd.DataFrame) -> Path:
    """Write global scenario summary under input_case folder."""
    case_folder = _resolve_path(input_case_folder)
    out_path = case_folder / "demand_scenario_summary.csv"
    summary_df = summary_df[
        [
            "scenario",
            "year",
            "zone",
            "component",
            "demand_type",
            "annual_energy_mwh",
            "mean_mw",
            "max_mw",
            "min_mw",
        ]
    ].copy()
    summary_df.to_csv(out_path, index=False)
    return out_path


def _iter_scenario_groups(config_df: pd.DataFrame) -> Iterable[Tuple[Tuple[str, int], pd.DataFrame]]:
    enabled = config_df[config_df["enabled"]].copy()
    if enabled.empty:
        return []

    grouped = []
    for (scenario, year), group in enabled.groupby(["scenario", "year"], dropna=False):
        grouped.append(((str(scenario), int(year)), group.reset_index(drop=True)))
    grouped.sort(key=lambda x: (x[0][1], x[0][0]))
    return grouped


def _filter_years(config_df: pd.DataFrame, years: Optional[list[int]]) -> pd.DataFrame:
    if not years:
        return config_df
    year_set = {int(y) for y in years}
    out = config_df[config_df["year"].astype(int).isin(year_set)].copy()
    if out.empty:
        raise ValueError(f"No config rows found for requested years: {sorted(year_set)}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build scenario-year demand CSVs for PyPSA isolated model."
    )
    parser.add_argument(
        "--input-case",
        default="input_punta_arenas",
        help="Case folder where scenarios output will be written.",
    )
    parser.add_argument(
        "--base-demand-csv",
        default="input_punta_arenas/demand_profiles.csv",
        help="Base demand CSV (2025 profile) in standard long format.",
    )
    parser.add_argument(
        "--config-csv",
        default="input_punta_arenas/config_demand_scenarios.csv",
        help="Scenario assumptions CSV.",
    )
    parser.add_argument(
        "--profiles-csv",
        default="",
        help="Optional normalized profile CSV for synthetic components.",
    )
    parser.add_argument(
        "--base-year",
        type=int,
        default=2025,
        help="Calendar year to use from the base demand CSV as the reference profile (default: 2025).",
    )
    parser.add_argument(
        "--years",
        nargs="*",
        type=int,
        default=[2030, 2040, 2050],
        help="Scenario years to generate. Defaults: 2030 2040 2050",
    )
    args = parser.parse_args()

    base_demand_df = read_base_demand(args.base_demand_csv, base_year=args.base_year)
    config_df = read_config(args.config_csv)
    config_df = _filter_years(config_df, args.years)
    profile_library = _read_optional_profiles(args.profiles_csv)

    # Accumulate all years per scenario before writing
    agg_by_scenario: Dict[str, list] = {}
    comp_by_scenario: Dict[str, list] = {}
    all_summary = []

    for (scenario, year), cfg_group in _iter_scenario_groups(config_df):
        aggregated_df, component_df, summary_df = build_scenario(
            scenario_cfg=cfg_group,
            base_demand_df=base_demand_df,
            profile_library=profile_library,
            base_year=args.base_year,
        )
        agg_by_scenario.setdefault(scenario, []).append(aggregated_df)
        comp_by_scenario.setdefault(scenario, []).append(component_df)
        all_summary.append(summary_df)

    # Write one file per scenario (all years combined)
    for scenario in agg_by_scenario:
        all_agg = pd.concat(agg_by_scenario[scenario], ignore_index=True)
        all_comp = pd.concat(comp_by_scenario[scenario], ignore_index=True)
        profiles_path, components_path = write_scenario_outputs(
            input_case_folder=args.input_case,
            scenario=scenario,
            aggregated_df=all_agg,
            component_df=all_comp,
        )
        print(f"  {profiles_path.name}")
        print(f"  {components_path.name}")

    if all_summary:
        summary_all_df = pd.concat(all_summary, ignore_index=True)
        summary_path = write_summary(args.input_case, summary_all_df)
        print(f"  {summary_path.name}")


if __name__ == "__main__":
    main()
