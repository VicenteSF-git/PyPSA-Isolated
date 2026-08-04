import argparse
from pathlib import Path
import unicodedata

import numpy as np
import pandas as pd


INPUT_XLSX = Path("data_NZ/electricity-demand-generation-scenarios-2024-assumptions (1).xlsx")
OUTPUT_CSV = Path("data_NZ/generators_capacity.csv")
OUTPUT_PYPSA_ALL_CSV = Path("data_NZ/generators_capacity_pypsa_all_scenarios.csv")
OUTPUT_PYPSA_REFERENCE_CSV = Path("data_NZ/generators_capacity_reference.csv")
OUTPUT_PYPSA_REFERENCE_GROUPED_CSV = Path("data_NZ/generators_capacity_reference_grouped.csv")
OUTPUT_PYPSA_SELECTED_CSV = Path("data_NZ/generators_capacity_selected.csv")
OUTPUT_PYPSA_SELECTED_GROUPED_CSV = Path("data_NZ/generators_capacity_selected_grouped.csv")
OUTPUT_SELECTED_BY_SCENARIO_DIR = Path("data_NZ/generators_capacity_by_scenario")
OUTPUT_YEAR_ASSUMPTIONS_CSV = Path("data_NZ/generators_capacity_commissioning_year_assumptions.csv")
SHEET_NAME = "Generation Stack"
DEFAULT_REFERENCE_SCENARIO = "Reference"
CSV_FLOAT_FORMAT = "%.6f"

# Default rules for EDGS rows that have no explicit commissioning year.
# These are modelling assumptions, not EDGS data. They are written explicitly
# to commissioning_year_assumption/source columns and exported to an audit CSV.
STATUS_WITHOUT_YEAR_RULES = {
    "under construction": {"type": "fixed", "year": 2025, "source": "assumed_from_status_under_construction"},
    "fully consented": {"type": "flexible", "year": 2030, "source": "assumed_from_status_fully_consented"},
    "applied for consent": {"type": "flexible", "year": 2030, "source": "assumed_from_status_applied_for_consent"},
    "announced": {"type": "flexible", "year": 2035, "source": "assumed_from_status_announced"},
    "generic": {"type": "flexible", "year": 2035, "source": "assumed_from_status_generic"},
    "potential": {"type": "flexible", "year": 2040, "source": "assumed_from_status_potential"},
    "early stages": {"type": "flexible", "year": 2040, "source": "assumed_from_status_early_stages"},
    "consent lapsed": {"type": "flexible", "year": 2040, "source": "assumed_from_status_consent_lapsed"},
}


def weighted_average(group: pd.DataFrame, value_col: str, weight_col: str = "installed_capacity") -> float:
    values = pd.to_numeric(group[value_col], errors="coerce")
    weights = pd.to_numeric(group[weight_col], errors="coerce")
    valid = values.notna() & weights.notna()
    if valid.sum() == 0:
        return np.nan
    if float(weights[valid].abs().sum()) == 0.0:
        return float(values[valid].mean())
    return float(np.average(values[valid], weights=weights[valid]))


def slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    for old, new in [("&", " and "), ("/", " "), ("-", " "), ("'", ""), (",", " "), ("(", " "), (")", " "), (":", " ")]:
        text = text.replace(old, new)
    return "_".join(text.split())


def grouped_family(tech: str) -> str:
    tech_map = {
        "hydpk": "hydro",
        "hydrr": "hydro",
        "hydsc": "hydro",
        "gaspkr": "gas",
        "ocgt": "gas",
        "ccgt": "gas",
        "gascog": "gas",
        "dslpkr": "diesel",
        "othcog": "thermal_other",
        "biorecip": "thermal_other",
    }
    return tech_map.get(str(tech).lower(), str(tech).lower())


def _commissioning_from_row(row: pd.Series) -> tuple[str, float, float, str, float]:
    """Return type, earliest_year, fixed_year, source, assumption_year."""
    status_norm = str(row.get("Status", "")).strip().lower()
    earliest_year = pd.to_numeric(row.get("Earliest Commissioning Year"), errors="coerce")
    fixed_year = pd.to_numeric(row.get("Fixed Commissioning Year"), errors="coerce")

    if status_norm == "current":
        return "existing", np.nan, np.nan, "edgs_status_current", np.nan

    if pd.notna(fixed_year):
        return "fixed", np.nan, float(fixed_year), "edgs_fixed_commissioning_year", np.nan

    if pd.notna(earliest_year):
        return "flexible", float(earliest_year), np.nan, "edgs_earliest_commissioning_year", np.nan

    rule = STATUS_WITHOUT_YEAR_RULES.get(status_norm)
    if rule is None:
        return "candidate_without_year", np.nan, np.nan, "missing_no_rule", np.nan

    assumed_year = float(rule["year"])
    if rule["type"] == "fixed":
        return "fixed", np.nan, assumed_year, rule["source"], assumed_year
    return "flexible", assumed_year, np.nan, rule["source"], assumed_year


def build_pypsa_plant_level_output(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()

    heat_rate = pd.to_numeric(data["Heat Rate (GJ/GWh)"], errors="coerce")
    fuel_cost = pd.to_numeric(data["Fuel delivery costs (NZD/GJ)"], errors="coerce")
    variable_cost = pd.to_numeric(data["Variable operating costs (NZD/MWh)"], errors="coerce").fillna(0.0)
    capital_cost_kw = pd.to_numeric(data["Capital cost (NZD/kW)"], errors="coerce")

    fuel_component_per_mwh = (fuel_cost * heat_rate / 1000.0).fillna(0.0)
    efficiency = (3600.0 / heat_rate).replace([np.inf, -np.inf], np.nan)
    efficiency = efficiency.clip(lower=0.0, upper=1.0).fillna(1.0)

    commissioning = data.apply(_commissioning_from_row, axis=1, result_type="expand")
    commissioning.columns = [
        "commissioning_type",
        "earliest_commissioning_year",
        "fixed_commissioning_year",
        "commissioning_year_source",
        "commissioning_year_assumption",
    ]

    out = pd.DataFrame({
        "scenario": data["Scenario"],
        "asset_id": None,
        "generator": data["Tech"].map(slugify),  # technology/carrier used by config.py and VRE profiles
        "zone": data["Region"].map(slugify),
        "technology": data["Tech"].map(slugify),
        "capital_cost": capital_cost_kw * 1000.0,
        "marginal_cost": variable_cost + fuel_component_per_mwh,
        "efficiency": efficiency,
        "installed_capacity": pd.to_numeric(data["Capacity (MW)"], errors="coerce").fillna(0.0),
        "p_min_mw": 0.0,
        "available_from_year": np.nan,
        "earliest_commissioning_year": commissioning["earliest_commissioning_year"],
        "fixed_commissioning_year": commissioning["fixed_commissioning_year"],
        "commissioning_type": commissioning["commissioning_type"],
        "commissioning_year_source": commissioning["commissioning_year_source"],
        "commissioning_year_assumption": commissioning["commissioning_year_assumption"],
        "status": data["Status"],
        "plant": data["Plant"],
        "plant_slug": data["Plant"].map(slugify),
        "tech": data["Tech"],
        "tech_name": data["TechName"],
        "plant_type": data["PlantType"],
        "substation": data["Substation"],
        "region": data["Region"],
        "fixed_operating_cost_nzd_per_kw_year": pd.to_numeric(data["Fixed operating costs (NZD/kW/year)"], errors="coerce"),
        "fuel_delivery_cost_nzd_per_gj": fuel_cost,
        "heat_rate_gj_per_gwh": heat_rate,
        "connection_cost_nzd_m": pd.to_numeric(data["Connection cost (NZD $m)"], errors="coerce"),
        "total_capital_costs_nzd_m": pd.to_numeric(data["Total Capital costs (NZD $m)"], errors="coerce"),
        "plants_grouped": 1,
    })

    out.loc[out["commissioning_type"].eq("flexible"), "available_from_year"] = out.loc[
        out["commissioning_type"].eq("flexible"), "earliest_commissioning_year"
    ]
    out.loc[out["commissioning_type"].eq("fixed"), "available_from_year"] = out.loc[
        out["commissioning_type"].eq("fixed"), "fixed_commissioning_year"
    ]

    for year_col in [
        "available_from_year",
        "earliest_commissioning_year",
        "fixed_commissioning_year",
        "commissioning_year_assumption",
    ]:
        out[year_col] = pd.to_numeric(out[year_col], errors="coerce").round(0).astype("Int64")

    # Unique id for PyPSA component names. Keep generator as technology/carrier.
    out["asset_id"] = (
        out["generator"].astype(str)
        + "_"
        + out["zone"].astype(str)
        + "_"
        + out["plant_slug"].astype(str)
    )

    # Guard against duplicated plant slugs in the same scenario.
    duplicate_mask = out.duplicated(["scenario", "asset_id"], keep=False)
    if duplicate_mask.any():
        out["_dup_no"] = out.groupby(["scenario", "asset_id"]).cumcount() + 1
        out.loc[duplicate_mask, "asset_id"] = out.loc[duplicate_mask, "asset_id"] + "_" + out.loc[duplicate_mask, "_dup_no"].astype(str)
        out = out.drop(columns=["_dup_no"])

    out = out.sort_values(["scenario", "zone", "generator", "asset_id"]).reset_index(drop=True)
    return out


def build_grouped_selected_output(pypsa_selected: pd.DataFrame) -> pd.DataFrame:
    grouped = pypsa_selected.copy()
    grouped["family"] = grouped["generator"].map(grouped_family)

    # Keep the grouped file as a reporting summary, not the preferred model input.
    # Include availability year/source in the grouping to avoid mixing assets that
    # become available in different model years.
    group_cols = [
        "zone",
        "family",
        "commissioning_type",
        "available_from_year",
        "commissioning_year_source",
    ]
    include_scenario = "scenario" in grouped.columns
    if include_scenario:
        group_cols = ["scenario"] + group_cols

    rows: list[dict] = []
    for keys, group in grouped.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)

        if include_scenario:
            scenario_key = keys[0]
            zone_key, family_key, commissioning_key, available_year_key, source_key = keys[1:]
        else:
            scenario_key = None
            zone_key, family_key, commissioning_key, available_year_key, source_key = keys

        generator_key = f"{family_key}_{commissioning_key}_{'na' if pd.isna(available_year_key) else int(available_year_key)}"
        row = {
            "generator": generator_key,
            "zone": zone_key,
            "technology": generator_key,
            "family": family_key,
            "capital_cost": weighted_average(group, "capital_cost"),
            "marginal_cost": weighted_average(group, "marginal_cost"),
            "efficiency": weighted_average(group, "efficiency"),
            "installed_capacity": float(pd.to_numeric(group["installed_capacity"], errors="coerce").sum(min_count=1)),
            "p_min_mw": float(pd.to_numeric(group["p_min_mw"], errors="coerce").sum(min_count=1)),
            "available_from_year": available_year_key,
            "earliest_commissioning_year": pd.to_numeric(group["earliest_commissioning_year"], errors="coerce").min(),
            "fixed_commissioning_year": pd.to_numeric(group["fixed_commissioning_year"], errors="coerce").min(),
            "commissioning_type": commissioning_key,
            "commissioning_year_source": source_key,
            "status_list": "; ".join(sorted(group["status"].dropna().astype(str).unique())),
            "source_plant_count": int(group["plant"].nunique()),
            "source_tech_count": int(group["tech"].nunique()),
        }
        if include_scenario:
            row["scenario"] = scenario_key
        rows.append(row)

    sort_cols = ["zone", "generator"]
    if include_scenario:
        sort_cols = ["scenario"] + sort_cols
    out = pd.DataFrame(rows).sort_values(sort_cols).reset_index(drop=True)
    for year_col in ["available_from_year", "earliest_commissioning_year", "fixed_commissioning_year"]:
        out[year_col] = pd.to_numeric(out[year_col], errors="coerce").round(0).astype("Int64")
    return out


def _resolve_selected_scenarios(available: list[str], requested: list[str] | None) -> list[str]:
    if not available:
        raise ValueError("No scenarios found in input data.")
    available_map = {str(s).casefold(): str(s) for s in available}
    if not requested:
        default_key = DEFAULT_REFERENCE_SCENARIO.casefold()
        return [available_map[default_key]] if default_key in available_map else [available[0]]

    requested_flat: list[str] = []
    for item in requested:
        requested_flat.extend([part.strip() for part in str(item).split(",") if part.strip()])
    if any(token.casefold() == "all" for token in requested_flat):
        return available

    selected, missing = [], []
    for token in requested_flat:
        key = token.casefold()
        if key in available_map:
            selected.append(available_map[key])
        else:
            missing.append(token)
    if missing:
        raise ValueError("Unknown scenario(s): " + ", ".join(missing) + ". Available: " + ", ".join(available))

    seen, unique_selected = set(), []
    for s in selected:
        if s not in seen:
            seen.add(s)
            unique_selected.append(s)
    return unique_selected


def _prompt_selected_scenarios(available: list[str]) -> list[str]:
    print("\nAvailable scenarios:")
    for i, s in enumerate(available, start=1):
        print(f"  {i}. {s}")
    default_choice = DEFAULT_REFERENCE_SCENARIO
    if default_choice.casefold() not in {s.casefold() for s in available}:
        default_choice = available[0]
    print("\nChoose scenario(s):")
    print("  - One: Reference")
    print("  - Multiple: Reference, High Electrification")
    print("  - All: ALL")
    print(f"  - Enter (empty): default = {default_choice}")
    while True:
        user_input = input("Scenario(s): ").strip()
        if not user_input:
            return _resolve_selected_scenarios(available, [default_choice])
        try:
            return _resolve_selected_scenarios(available, [user_input])
        except ValueError as exc:
            print(f"Invalid selection: {exc}")
            print("Try again using names exactly as listed, comma-separated, or ALL.")


def main(selected_scenarios: list[str] | None = None, list_scenarios_only: bool = False) -> None:
    df = pd.read_excel(INPUT_XLSX, sheet_name=SHEET_NAME)

    numeric_columns = [
        "Capacity (MW)",
        "Heat Rate (GJ/GWh)",
        "Variable operating costs (NZD/MWh)",
        "Fixed operating costs (NZD/kW/year)",
        "Fuel delivery costs (NZD/GJ)",
        "Capital cost (NZD/kW)",
        "Connection cost (NZD $m)",
        "Total Capital costs (NZD $m)",
        "Earliest Commissioning Year",
        "Fixed Commissioning Year",
    ]
    df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors="coerce")

    pypsa_output = build_pypsa_plant_level_output(df)
    pypsa_output.to_csv(OUTPUT_PYPSA_ALL_CSV, index=False, float_format=CSV_FLOAT_FORMAT)

    # Keep a raw-ish output for backward inspection. This is now plant-level, not aggregated.
    pypsa_output.to_csv(OUTPUT_CSV, index=False, float_format=CSV_FLOAT_FORMAT)

    assumed = pypsa_output[pypsa_output["commissioning_year_assumption"].notna()].copy()
    assumed.to_csv(OUTPUT_YEAR_ASSUMPTIONS_CSV, index=False, float_format=CSV_FLOAT_FORMAT)

    unresolved = pypsa_output[pypsa_output["commissioning_type"].eq("candidate_without_year")].copy()
    if not unresolved.empty:
        print(
            f"Warning: {len(unresolved)} assets still have no commissioning year/rule. "
            "They will be excluded from model-ready outputs."
        )

    pypsa_model_ready = pypsa_output[~pypsa_output["commissioning_type"].eq("candidate_without_year")].copy()

    available_scenarios = sorted(pypsa_model_ready["scenario"].dropna().astype(str).unique().tolist())
    if list_scenarios_only:
        print("Available scenarios:")
        for s in available_scenarios:
            print(f"  - {s}")
        return

    if selected_scenarios is None:
        selected_scenarios = _prompt_selected_scenarios(available_scenarios)

    selected = _resolve_selected_scenarios(available_scenarios, selected_scenarios)
    selected_keys = {s.casefold() for s in selected}
    selected_mask = pypsa_model_ready["scenario"].astype(str).str.casefold().isin(selected_keys)
    pypsa_selected = pypsa_model_ready.loc[selected_mask].reset_index(drop=True)
    pypsa_selected.to_csv(OUTPUT_PYPSA_SELECTED_CSV, index=False, float_format=CSV_FLOAT_FORMAT)

    pypsa_selected_grouped = build_grouped_selected_output(pypsa_selected)
    pypsa_selected_grouped.to_csv(OUTPUT_PYPSA_SELECTED_GROUPED_CSV, index=False, float_format=CSV_FLOAT_FORMAT)

    OUTPUT_SELECTED_BY_SCENARIO_DIR.mkdir(parents=True, exist_ok=True)
    for scenario_name in selected:
        scenario_mask = pypsa_selected["scenario"].astype(str).str.casefold() == scenario_name.casefold()
        scenario_df = pypsa_selected.loc[scenario_mask].reset_index(drop=True)
        scenario_slug = slugify(scenario_name)

        scenario_df_no_scenario = scenario_df.drop(columns=["scenario"], errors="ignore")
        scenario_csv = OUTPUT_SELECTED_BY_SCENARIO_DIR / f"generators_capacity_{scenario_slug}.csv"
        scenario_df_no_scenario.to_csv(scenario_csv, index=False, float_format=CSV_FLOAT_FORMAT)

        scenario_grouped = build_grouped_selected_output(scenario_df_no_scenario)
        scenario_grouped_csv = OUTPUT_SELECTED_BY_SCENARIO_DIR / f"generators_capacity_{scenario_slug}_grouped.csv"
        scenario_grouped.to_csv(scenario_grouped_csv, index=False, float_format=CSV_FLOAT_FORMAT)

    pypsa_reference = pypsa_selected.copy()
    if len(selected) == 1:
        pypsa_reference = pypsa_reference.drop(columns=["scenario"], errors="ignore")
    pypsa_reference.to_csv(OUTPUT_PYPSA_REFERENCE_CSV, index=False, float_format=CSV_FLOAT_FORMAT)

    pypsa_reference_grouped = build_grouped_selected_output(pypsa_reference)
    pypsa_reference_grouped.to_csv(OUTPUT_PYPSA_REFERENCE_GROUPED_CSV, index=False, float_format=CSV_FLOAT_FORMAT)

    print(f"Output written to: {OUTPUT_CSV}")
    print(f"PyPSA all scenarios written to: {OUTPUT_PYPSA_ALL_CSV}")
    print(f"Selected scenarios: {', '.join(selected)}")
    print(f"PyPSA selected written to: {OUTPUT_PYPSA_SELECTED_CSV}")
    print(f"PyPSA selected grouped written to: {OUTPUT_PYPSA_SELECTED_GROUPED_CSV}")
    print(f"Per-scenario outputs written to: {OUTPUT_SELECTED_BY_SCENARIO_DIR}")
    print(f"PyPSA reference written to: {OUTPUT_PYPSA_REFERENCE_CSV}")
    print(f"PyPSA reference grouped written to: {OUTPUT_PYPSA_REFERENCE_GROUPED_CSV}")
    print(f"Commissioning-year assumptions written to: {OUTPUT_YEAR_ASSUMPTIONS_CSV}")
    print(f"Rows all scenarios: {len(pypsa_output)}")
    print(f"Selected rows: {len(pypsa_selected)}")
    print(f"Selected grouped rows: {len(pypsa_selected_grouped)}")
    print(f"Reference rows: {len(pypsa_reference)}")
    print(f"Reference grouped rows: {len(pypsa_reference_grouped)}")
    print(f"Rows with assumed commissioning year: {len(assumed)}")
    print(f"Rows unresolved without year: {len(unresolved)}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build NZ generator-capacity CSVs from EDGS input.")
    parser.add_argument(
        "--scenarios",
        nargs="+",
        help="Scenario name(s) to export (case-insensitive). Use ALL to include all scenarios.",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="List scenarios discovered in the input and exit.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    main(selected_scenarios=args.scenarios, list_scenarios_only=args.list_scenarios)
