
"""
Process the 12 monthly 2025 Grid_export files for the New Zealand case.

Run from the model root directory:

    python build_nz_demand.py

Expected structure:

model/
├─ build_nz_demand_2025.py
├─ data_nz_demand/
│  └─ input/
│     ├─ 202501_Grid_export.csv
│     ├─ ...
│     ├─ 202512_Grid_export.csv
│     ├─ NetworkSupplyPointsTable....csv   # opcional
│     └─ poc_to_zone_overrides.csv        # opcional
└─ input_new_zealand/
   └─ nodes.csv

Outputs:

model/input_new_zealand/demand_profiles.csv
model/input_new_zealand/demand_profiles_2025_wide.csv
model/input_new_zealand/demand_validation_2025.csv
model/data_nz_demand/input/poc_zone_mapping_2025.csv
model/data_nz_demand/input/poc_zone_summary_2025.csv
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


# =============================================================================
# PATHS
# =============================================================================

MODEL_DIR = Path(__file__).resolve().parent

YEAR = 2025

RAW_INPUT_DIR = MODEL_DIR / "data_nz_demand" / "input"
CASE_INPUT_DIR = MODEL_DIR / "input_new_zealand"

NODES_FILE = CASE_INPUT_DIR / "nodes.csv"

OUTPUT_LONG = CASE_INPUT_DIR / "demand_profiles.csv"
OUTPUT_WIDE = CASE_INPUT_DIR / "demand_profiles_2025_wide.csv"
OUTPUT_SUMMARY = CASE_INPUT_DIR / "demand_validation_2025.csv"

OUTPUT_MAPPING = RAW_INPUT_DIR / "poc_zone_mapping_2025.csv"
OUTPUT_POC_SUMMARY = RAW_INPUT_DIR / "poc_zone_summary_2025.csv"
OUTPUT_UNMAPPED = RAW_INPUT_DIR / "unmapped_grid_export_2025.csv"

OVERRIDES_FILE = RAW_INPUT_DIR / "poc_to_zone_overrides.csv"

NODES_BACKUP = CASE_INPUT_DIR / "nodes_before_2025_grid_export.csv"

NSP_LOCAL_PATTERNS = (
    "*NetworkSupplyPointsTable*.csv",
    "*network_supply_points*.csv",
    "*Network_supply_points*.csv",
    "nsp_table.csv",
)

NSP_REPORT_URL = (
    "https://www.emi.ea.govt.nz/All/Download/DataReport/CSV/R_NSPL_DR"
)

UPDATE_NODES_ANNUAL_MEAN = True
STRICT_ZONE_COVERAGE = True


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _normalise_column(name: str) -> str:
    text = re.sub(r"[^0-9A-Za-z]+", "_", str(name).strip())
    return text.strip("_").lower()


def _normalise_zone(name: str) -> str:
    text = str(name).strip().lower().replace("&", "and")
    text = re.sub(r"[^0-9a-z]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _as_bool(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .isin({"1", "true", "t", "yes", "y"})
    )


def _parse_dates(series: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(
            series,
            format="mixed",
            dayfirst=True,
            errors="coerce",
        )
    except TypeError:
        return pd.to_datetime(
            series,
            dayfirst=True,
            errors="coerce",
        )


def _find_column(
    columns: Iterable[str],
    candidates: Iterable[str],
) -> str:
    available = set(columns)

    for candidate in candidates:
        if candidate in available:
            return candidate

    raise KeyError(
        f"Could not find ninguna de las columnas esperadas "
        f"{list(candidates)}. Available columns: {sorted(available)}"
    )


def _clean_code(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper()


# =============================================================================
# MODEL NODES
# =============================================================================

def load_nodes_and_active_zones() -> tuple[pd.DataFrame, list[str]]:
    if not NODES_FILE.exists():
        raise FileNotFoundError(
            f"Could not find {NODES_FILE}."
        )

    nodes_full = pd.read_csv(NODES_FILE, comment="#")

    if "zone" not in nodes_full.columns:
        raise ValueError(
            f"{NODES_FILE} must contain the column 'zone'."
        )

    if "annual_mean_mw" not in nodes_full.columns:
        raise ValueError(
            f"{NODES_FILE} must contain the column 'annual_mean_mw'."
        )

    nodes_active = nodes_full.copy()

    if "enabled" in nodes_active.columns:
        nodes_active = nodes_active.loc[
            _as_bool(nodes_active["enabled"])
        ].copy()

    nodes_active["zone"] = nodes_active["zone"].map(
        _normalise_zone
    )

    zones = nodes_active["zone"].drop_duplicates().tolist()

    if not zones:
        raise ValueError(
            f"No enabled nodes were found in {NODES_FILE}."
        )

    return nodes_full, zones


# =============================================================================
# GRID_EXPORT FILES
# =============================================================================

def find_monthly_grid_export_files() -> list[Path]:
    pattern = re.compile(
        rf"^{YEAR}(0[1-9]|1[0-2])_Grid_export\.csv$",
        re.IGNORECASE,
    )

    files_by_month: dict[int, Path] = {}

    for path in RAW_INPUT_DIR.glob("*_Grid_export.csv"):
        match = pattern.match(path.name)

        if match:
            month = int(match.group(1))
            files_by_month[month] = path

    missing = sorted(
        set(range(1, 13)) - set(files_by_month)
    )

    if missing:
        missing_text = ", ".join(
            f"{YEAR}{month:02d}"
            for month in missing
        )

        raise FileNotFoundError(
            f"Missing Grid_export files for: {missing_text}. "
            f"Expected folder: {RAW_INPUT_DIR}"
        )

    return [
        files_by_month[month]
        for month in range(1, 13)
    ]


def load_grid_export(files: list[Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    required = {
        "POC",
        "Nwk_Code",
        "Generation_Type",
        "Trader",
        "Unit_Measure",
        "Flow_Direction",
        "Status",
        "Trading_Date",
    }

    for path in files:
        frame = pd.read_csv(path, low_memory=False)

        missing = required - set(frame.columns)

        if missing:
            raise ValueError(
                f"{path.name} is missing columns: "
                f"{sorted(missing)}"
            )

        frame["source_file"] = path.name
        frames.append(frame)

    data = pd.concat(
        frames,
        ignore_index=True,
    )

    data["Trading_Date"] = _parse_dates(
        data["Trading_Date"]
    )

    invalid_dates = data["Trading_Date"].isna()

    if invalid_dates.any():
        bad_files = sorted(
            data.loc[invalid_dates, "source_file"].unique()
        )

        raise ValueError(
            f"Invalid dates found in: {bad_files}"
        )

    data = data.loc[
        data["Trading_Date"].dt.year.eq(YEAR)
    ].copy()

    data = data.loc[
        _clean_code(data["Flow_Direction"]).eq("X")
    ].copy()

    data = data.loc[
        _clean_code(data["Status"]).eq("F")
    ].copy()

    units = set(
        data["Unit_Measure"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.lower()
    )

    if units != {"kwh"}:
        raise ValueError(
            f"Expected kWh only. "
            f"Units found: {sorted(units)}"
        )

    for column in (
        "POC",
        "Nwk_Code",
        "Generation_Type",
        "Trader",
    ):
        data[column] = _clean_code(data[column])

    dates = pd.DatetimeIndex(
        sorted(data["Trading_Date"].unique())
    )

    expected = pd.date_range(
        f"{YEAR}-01-01",
        f"{YEAR}-12-31",
        freq="D",
    )

    missing_dates = expected.difference(dates)
    extra_dates = dates.difference(expected)

    if len(missing_dates) or len(extra_dates):
        raise ValueError(
            "The files do not contain a complete calendar year. "
            f"Missing dates: "
            f"{missing_dates.strftime('%Y-%m-%d').tolist()[:10]}; "
            f"extra dates: "
            f"{extra_dates.strftime('%Y-%m-%d').tolist()[:10]}"
        )

    return data


# =============================================================================
# NETWORK SUPPLY POINTS
# =============================================================================

def load_network_supply_points() -> pd.DataFrame:
    local_file: Path | None = None

    for pattern in NSP_LOCAL_PATTERNS:
        candidates = sorted(
            RAW_INPUT_DIR.glob(pattern)
        )

        if candidates:
            local_file = candidates[-1]
            break

    if local_file is not None:
        print(
            f"Using local Network Supply Points file: "
            f"{local_file.name}"
        )

        nsp = pd.read_csv(
            local_file,
            low_memory=False,
        )

    else:
        print(
            "Downloading Network Supply Points from EMI..."
        )

        try:
            nsp = pd.read_csv(
                NSP_REPORT_URL,
                low_memory=False,
            )

        except Exception as exc:
            raise RuntimeError(
                "Could not download Network Supply Points. "
                "Download the CSV manually from EMI and save it "
                f"en {RAW_INPUT_DIR}."
            ) from exc

    nsp.columns = [
        _normalise_column(column)
        for column in nsp.columns
    ]

    aliases = {
        "poc": (
            "poc_code",
            "poc",
        ),
        "network": (
            "network_participant",
            "nwk_code",
            "network",
        ),
        "reconciliation": (
            "reconciliation_type",
            "generation_type",
            "recon_type",
        ),
        "nrr_id": (
            "network_reporting_region_id",
            "network_region_id",
            "region_id",
        ),
        "nrr_name": (
            "network_reporting_region",
            "network_region",
            "region",
        ),
    }

    selected = {
        name: _find_column(
            nsp.columns,
            candidates,
        )
        for name, candidates in aliases.items()
    }

    rename = {
        selected["poc"]: "POC",
        selected["network"]: "Nwk_Code",
        selected["reconciliation"]: "Generation_Type",
        selected["nrr_id"]: "nrr_id",
        selected["nrr_name"]: "nrr_name",
    }

    for optional in (
        "start_date",
        "end_date",
        "x_flow",
    ):
        if optional in nsp.columns:
            rename[optional] = optional

    nsp = nsp.rename(columns=rename)

    keep = [
        "POC",
        "Nwk_Code",
        "Generation_Type",
        "nrr_id",
        "nrr_name",
    ]

    keep += [
        column
        for column in (
            "start_date",
            "end_date",
            "x_flow",
        )
        if column in nsp.columns
    ]

    nsp = nsp[keep].copy()

    for column in (
        "POC",
        "Nwk_Code",
        "Generation_Type",
    ):
        nsp[column] = _clean_code(nsp[column])

    nsp["nrr_id"] = pd.to_numeric(
        nsp["nrr_id"],
        errors="coerce",
    ).astype("Int64")

    nsp["nrr_name"] = (
        nsp["nrr_name"]
        .astype(str)
        .str.strip()
    )

    if "start_date" in nsp.columns:
        nsp["start_date"] = _parse_dates(
            nsp["start_date"]
        )
    else:
        nsp["start_date"] = pd.Timestamp(
            "1900-01-01"
        )

    if "end_date" in nsp.columns:
        nsp["end_date"] = _parse_dates(
            nsp["end_date"]
        )
    else:
        nsp["end_date"] = pd.NaT

    if "x_flow" in nsp.columns:
        x_flow = pd.to_numeric(
            nsp["x_flow"],
            errors="coerce",
        )

        nsp = nsp.loc[
            x_flow.fillna(1).ne(0)
        ].copy()

    return nsp.drop_duplicates()


# =============================================================================
# MAP NZ REPORTING REGIONS TO MODEL ZONES
# =============================================================================

def nrr_to_model_zone(
    nrr_id: object,
    active_zones: set[str],
) -> str | None:
    if pd.isna(nrr_id):
        return None

    region = int(nrr_id)

    mapping = {
        1: "northland",
        2: "northland",
        3: "auckland",
        4: "auckland",
        5: "auckland",
        6: "waikato",
        7: "waikato",
        8: "waikato",
        9: "waikato",
        10: "bay_of_plenty",
        11: "bay_of_plenty",
        12: "bay_of_plenty",
        13: "waikato",
        14: (
            "gisborne"
            if "gisborne" in active_zones
            else "hawkes_bay"
        ),
        15: "hawkes_bay",
        16: "hawkes_bay",
        17: "hawkes_bay",
        18: "wellington",
        19: "taranaki",
        20: "manawatu_whanganui",
        21: "manawatu_whanganui",
        22: "wellington",
        23: "wellington",
        24: "nelson",
        25: (
            "tasman"
            if "tasman" in active_zones
            else "nelson"
        ),
        26: "marlborough",
        27: "west_coast",
        28: "west_coast",
        29: "canterbury",
        30: "canterbury",
        31: "canterbury",
        32: "canterbury",
        33: "otago",
        34: "otago",
        35: "otago",
        36: "otago",
        37: "otago",
        38: "southland",
        39: "southland",
        40: "otago",
    }

    zone = mapping.get(region)

    return (
        zone
        if zone in active_zones
        else None
    )


def apply_manual_overrides(
    daily_map: pd.DataFrame,
    active_zones: set[str],
) -> pd.DataFrame:
    if not OVERRIDES_FILE.exists():
        return daily_map

    overrides = pd.read_csv(
        OVERRIDES_FILE,
        comment="#",
    )

    if overrides.empty:
        return daily_map

    required = {"POC", "zone"}

    if not required.issubset(overrides.columns):
        raise ValueError(
            f"{OVERRIDES_FILE} debe contener "
            f"las columnas POC y zone."
        )

    overrides["POC"] = _clean_code(
        overrides["POC"]
    )

    overrides["zone"] = overrides["zone"].map(
        _normalise_zone
    )

    invalid_zones = sorted(
        set(overrides["zone"]) - active_zones
    )

    if invalid_zones:
        raise ValueError(
            f"The override zones do not exist in nodes.csv: "
            f"{invalid_zones}"
        )

    optional_keys = [
        column
        for column in (
            "Nwk_Code",
            "Generation_Type",
        )
        if column in overrides.columns
    ]

    merge_keys = ["POC", *optional_keys]

    for column in optional_keys:
        overrides[column] = _clean_code(
            overrides[column]
        )

    overrides = (
        overrides[
            merge_keys + ["zone"]
        ]
        .drop_duplicates(
            merge_keys,
            keep="last",
        )
        .rename(
            columns={"zone": "zone_override"}
        )
    )

    result = daily_map.merge(
        overrides,
        on=merge_keys,
        how="left",
    )

    result["zone"] = (
        result["zone_override"]
        .combine_first(result["zone"])
    )

    return result.drop(
        columns="zone_override"
    )


def build_daily_poc_mapping(
    grid_export: pd.DataFrame,
    nsp: pd.DataFrame,
    active_zones: list[str],
) -> pd.DataFrame:
    key_columns = [
        "Trading_Date",
        "POC",
        "Nwk_Code",
        "Generation_Type",
    ]

    keys = (
        grid_export[key_columns]
        .drop_duplicates()
        .copy()
    )

    keys["_row_id"] = np.arange(
        len(keys),
        dtype=np.int64,
    )

    candidates = keys.merge(
        nsp,
        on=[
            "POC",
            "Nwk_Code",
            "Generation_Type",
        ],
        how="left",
    )

    active = (
        candidates["start_date"].isna()
        | candidates["Trading_Date"].ge(
            candidates["start_date"]
        )
    ) & (
        candidates["end_date"].isna()
        | candidates["Trading_Date"].le(
            candidates["end_date"]
        )
    )

    selected = (
        candidates.loc[active]
        .sort_values(
            ["_row_id", "start_date"],
            na_position="first",
        )
        .drop_duplicates(
            "_row_id",
            keep="last",
        )
    )

    daily_map = keys.merge(
        selected[
            [
                "_row_id",
                "nrr_id",
                "nrr_name",
            ]
        ],
        on="_row_id",
        how="left",
    )

    active_zone_set = set(active_zones)

    daily_map["zone"] = daily_map["nrr_id"].map(
        lambda value: nrr_to_model_zone(
            value,
            active_zone_set,
        )
    )

    daily_map = apply_manual_overrides(
        daily_map,
        active_zone_set,
    )

    unmapped = daily_map.loc[
        daily_map["zone"].isna()
    ].copy()

    if not unmapped.empty:
        unmapped.drop(
            columns="_row_id"
        ).to_csv(
            OUTPUT_UNMAPPED,
            index=False,
        )

        raise ValueError(
            f"{len(unmapped):,} POC records could not be mapped. "
            f"Review {OUTPUT_UNMAPPED} and add corrections in "
            f"{OVERRIDES_FILE}."
        )

    output = daily_map.drop(
        columns="_row_id"
    )

    output.to_csv(
        OUTPUT_MAPPING,
        index=False,
    )

    return output


# =============================================================================
# HALF-HOURLY TO HOURLY CONVERSION
# =============================================================================

def grid_export_to_hourly_demand(
    grid_export: pd.DataFrame,
    daily_mapping: pd.DataFrame,
    active_zones: list[str],
) -> pd.DataFrame:
    tp_columns = sorted(
        [
            column
            for column in grid_export.columns
            if re.fullmatch(
                r"TP\d+",
                str(column),
            )
        ],
        key=lambda column: int(
            str(column)[2:]
        ),
    )

    if not tp_columns:
        raise ValueError(
            "No TP1...TP50 columns were found."
        )

    id_columns = [
        "Trading_Date",
        "POC",
        "Nwk_Code",
        "Generation_Type",
        "Trader",
    ]

    long = grid_export.melt(
        id_vars=id_columns,
        value_vars=tp_columns,
        var_name="trading_period",
        value_name="energy_kwh",
    )

    long["tp_number"] = (
        long["trading_period"]
        .astype(str)
        .str.extract(
            r"(\d+)",
            expand=False,
        )
        .astype(int)
    )

    long["energy_kwh"] = pd.to_numeric(
        long["energy_kwh"],
        errors="coerce",
    )

    long = long.loc[
        long["energy_kwh"].notna()
    ].copy()

    poc_half_hour = (
        long.groupby(
            [
                "Trading_Date",
                "tp_number",
                "POC",
                "Nwk_Code",
                "Generation_Type",
            ],
            as_index=False,
            observed=True,
        )["energy_kwh"]
        .sum()
    )

    poc_half_hour = poc_half_hour.merge(
        daily_mapping,
        on=[
            "Trading_Date",
            "POC",
            "Nwk_Code",
            "Generation_Type",
        ],
        how="left",
        validate="many_to_one",
    )

    if poc_half_hour["zone"].isna().any():
        raise RuntimeError(
            "The zone mapping was lost during the merge."
        )

    poc_summary = (
        poc_half_hour.groupby(
            [
                "POC",
                "Nwk_Code",
                "Generation_Type",
                "zone",
            ],
            as_index=False,
            observed=True,
        )["energy_kwh"]
        .sum()
    )

    poc_summary["annual_energy_gwh"] = (
        poc_summary["energy_kwh"]
        / 1_000_000
    )

    poc_summary = poc_summary.drop(
        columns="energy_kwh"
    )

    poc_summary.to_csv(
        OUTPUT_POC_SUMMARY,
        index=False,
        float_format="%.6f",
    )

    zone_half_hour = (
        poc_half_hour.groupby(
            [
                "Trading_Date",
                "tp_number",
                "zone",
            ],
            as_index=False,
            observed=True,
        )["energy_kwh"]
        .sum()
    )

    slots = (
        zone_half_hour[
            [
                "Trading_Date",
                "tp_number",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            [
                "Trading_Date",
                "tp_number",
            ]
        )
        .reset_index(drop=True)
    )

    slots["half_hour_id"] = np.arange(
        len(slots),
        dtype=np.int64,
    )

    expected_half_hours = 365 * 48

    if len(slots) != expected_half_hours:
        daily_counts = (
            slots.groupby(
                "Trading_Date"
            )["tp_number"]
            .size()
            .value_counts()
            .sort_index()
            .to_dict()
        )

        raise ValueError(
            f"Expected {expected_half_hours:,} medias horas, "
            f"pero se encontraron {len(slots):,}. "
            f"Daily distribution: {daily_counts}"
        )

    zone_half_hour = zone_half_hour.merge(
        slots,
        on=[
            "Trading_Date",
            "tp_number",
        ],
        how="left",
        validate="many_to_one",
    )

    half_hour_wide = (
        zone_half_hour.pivot_table(
            index="half_hour_id",
            columns="zone",
            values="energy_kwh",
            aggfunc="sum",
        )
        .sort_index()
        .reindex(columns=active_zones)
    )

    absent_zones = [
        zone
        for zone in active_zones
        if half_hour_wide[zone].isna().all()
    ]

    if absent_zones and STRICT_ZONE_COVERAGE:
        raise ValueError(
            f"No Grid_export demand was assigned to: "
            f"{absent_zones}"
        )

    half_hour_wide = half_hour_wide.fillna(0.0)

    values = half_hour_wide.to_numpy(
        dtype=float
    )

    hourly_values = (
        values[0::2]
        + values[1::2]
    ) / 1000.0

    hourly_index = pd.date_range(
        f"{YEAR}-01-01 00:00:00",
        periods=365 * 24,
        freq="h",
    )

    hourly = pd.DataFrame(
        hourly_values,
        index=hourly_index,
        columns=active_zones,
    )

    hourly.index.name = "timestamp"

    raw_total_gwh = float(
        long["energy_kwh"].sum()
        / 1_000_000
    )

    hourly_total_gwh = float(
        hourly.to_numpy().sum()
        / 1000
    )

    if not np.isclose(
        raw_total_gwh,
        hourly_total_gwh,
        rtol=0,
        atol=1e-6,
    ):
        raise RuntimeError(
            "Energy was not conserved during conversion: "
            f"raw={raw_total_gwh:.6f} GWh, "
            f"hourly={hourly_total_gwh:.6f} GWh."
        )

    return hourly


# =============================================================================
# OUTPUTS
# =============================================================================

def build_summary(
    hourly: pd.DataFrame,
) -> pd.DataFrame:
    rows = []

    for zone in hourly.columns:
        series = hourly[zone]

        rows.append(
            {
                "zone": zone,
                "year": YEAR,
                "annual_energy_gwh": float(
                    series.sum() / 1000
                ),
                "annual_mean_mw": float(
                    series.mean()
                ),
                "peak_load_mw": float(
                    series.max()
                ),
                "minimum_load_mw": float(
                    series.min()
                ),
                "hours": int(
                    series.size
                ),
                "source": (
                    "Electricity Authority Grid_export"
                ),
            }
        )

    return pd.DataFrame(rows)


def update_nodes_annual_mean(
    nodes_full: pd.DataFrame,
    summary: pd.DataFrame,
) -> None:
    nodes = nodes_full.copy()

    nodes["_zone_normalised"] = nodes["zone"].map(
        _normalise_zone
    )

    means = summary.set_index(
        "zone"
    )["annual_mean_mw"]

    matched = nodes["_zone_normalised"].isin(
        means.index
    )

    if not matched.any():
        raise ValueError(
            "No calculated zone matches nodes.csv."
        )

    if not NODES_BACKUP.exists():
        shutil.copy2(
            NODES_FILE,
            NODES_BACKUP,
        )

    nodes.loc[
        matched,
        "annual_mean_mw",
    ] = (
        nodes.loc[
            matched,
            "_zone_normalised",
        ]
        .map(means)
    )

    nodes = nodes.drop(
        columns="_zone_normalised"
    )

    nodes.to_csv(
        NODES_FILE,
        index=False,
        float_format="%.6f",
    )


def write_outputs(
    hourly: pd.DataFrame,
    nodes_full: pd.DataFrame,
) -> pd.DataFrame:
    CASE_INPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    RAW_INPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    hourly.reset_index().to_csv(
        OUTPUT_WIDE,
        index=False,
        float_format="%.6f",
    )

    long = (
        hourly.rename_axis("timestamp")
        .reset_index()
        .melt(
            id_vars="timestamp",
            var_name="zone",
            value_name="demand_mw",
        )
    )

    long.insert(
        2,
        "demand_type",
        "electricity",
    )

    long.to_csv(
        OUTPUT_LONG,
        index=False,
        float_format="%.6f",
    )

    summary = build_summary(hourly)

    summary.to_csv(
        OUTPUT_SUMMARY,
        index=False,
        float_format="%.6f",
    )

    if UPDATE_NODES_ANNUAL_MEAN:
        update_nodes_annual_mean(
            nodes_full,
            summary,
        )

    return summary


# =============================================================================
# EXECUTION
# =============================================================================

def main() -> None:
    RAW_INPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    CASE_INPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    nodes_full, active_zones = (
        load_nodes_and_active_zones()
    )

    files = find_monthly_grid_export_files()

    print(
        f"Reading {len(files)} Grid_export files from:"
    )
    print(f"  {RAW_INPUT_DIR}")

    print(
        f"\nEnabled zones ({len(active_zones)}):"
    )
    print(active_zones)

    grid_export = load_grid_export(files)

    nsp = load_network_supply_points()

    daily_mapping = build_daily_poc_mapping(
        grid_export=grid_export,
        nsp=nsp,
        active_zones=active_zones,
    )

    hourly = grid_export_to_hourly_demand(
        grid_export=grid_export,
        daily_mapping=daily_mapping,
        active_zones=active_zones,
    )

    summary = write_outputs(
        hourly=hourly,
        nodes_full=nodes_full,
    )

    national_gwh = float(
        summary["annual_energy_gwh"].sum()
    )

    national_mean_mw = float(
        hourly.sum(axis=1).mean()
    )

    national_peak_mw = float(
        hourly.sum(axis=1).max()
    )

    print("\n" + "=" * 72)
    print("NZ 2025 DEMAND CREATED FROM GRID_EXPORT")
    print("=" * 72)

    print(
        f"Hours:                    {len(hourly):,}"
    )
    print(
        f"National annual demand:   {national_gwh:,.2f} GWh"
    )
    print(
        f"National mean demand:   {national_mean_mw:,.2f} MW"
    )
    print(
        f"National peak demand:  {national_peak_mw:,.2f} MW"
    )

    print("\nGenerated files:")

    for path in (
        OUTPUT_LONG,
        OUTPUT_WIDE,
        OUTPUT_SUMMARY,
        OUTPUT_MAPPING,
        OUTPUT_POC_SUMMARY,
    ):
        print(f"  {path.relative_to(MODEL_DIR)}")

    if UPDATE_NODES_ANNUAL_MEAN:
        print(
            f"  {NODES_FILE.relative_to(MODEL_DIR)} "
            "(updated)"
        )
        print(
            f"  {NODES_BACKUP.relative_to(MODEL_DIR)} "
            "(backup)"
        )


if __name__ == "__main__":
    main()
