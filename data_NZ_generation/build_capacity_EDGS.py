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
SHEET_NAME = "Generation Stack"
DEFAULT_REFERENCE_SCENARIO = "Reference"
CSV_FLOAT_FORMAT = "%.6f"


def weighted_average(group: pd.DataFrame, value_col: str, weight_col: str = "Capacity (MW)") -> float:
	values = group[value_col]
	weights = group[weight_col]
	valid = values.notna() & weights.notna()

	if valid.sum() == 0:
		return np.nan

	if float(weights[valid].abs().sum()) == 0.0:
		return float(values[valid].mean())

	return float(np.average(values[valid], weights=weights[valid]))


def slugify(value: str) -> str:
	text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
	text = text.lower().strip()
	for old, new in [("&", " and "), ("/", " "), ("-", " "), ("'", ""), (",", " ")]:
		text = text.replace(old, new)
	text = "_".join(text.split())
	return text


def build_pypsa_output(aggregated: pd.DataFrame) -> pd.DataFrame:
	out = aggregated.copy()

	heat_rate = pd.to_numeric(out["Heat Rate (GJ/GWh)"], errors="coerce")
	fuel_cost = pd.to_numeric(out["Fuel delivery costs (NZD/GJ)"], errors="coerce")
	variable_cost = pd.to_numeric(out["Variable operating costs (NZD/MWh)"], errors="coerce").fillna(0.0)
	capital_cost_kw = pd.to_numeric(out["Capital cost (NZD/kW)"], errors="coerce")

	fuel_component_per_mwh = (fuel_cost * heat_rate / 1000.0).fillna(0.0)
	efficiency = (3600.0 / heat_rate).replace([np.inf, -np.inf], np.nan)
	efficiency = efficiency.clip(lower=0.0, upper=1.0).fillna(1.0)

	zone = out["Region"].map(slugify)
	tech_slug = out["Tech"].map(slugify)

	out_pypsa = pd.DataFrame(
		{
			"scenario": out["Scenario"],
			"generator": tech_slug,
			"zone": zone,
			"technology": tech_slug,
			"capital_cost": capital_cost_kw * 1000.0,
			"marginal_cost": variable_cost + fuel_component_per_mwh,
			"efficiency": efficiency,
			"installed_capacity": pd.to_numeric(out["Capacity (MW)"], errors="coerce").fillna(0.0),
			"p_min_mw": 0.0,
			"available_from_year": pd.to_numeric(out["Earliest Commissioning Year"], errors="coerce"),
			"earliest_commissioning_year": pd.to_numeric(out["Earliest Commissioning Year"], errors="coerce"),
			"fixed_commissioning_year": pd.to_numeric(out["Fixed Commissioning Year"], errors="coerce"),
			"commissioning_type": np.where(
				pd.to_numeric(out["Fixed Commissioning Year"], errors="coerce").notna(),
				"fixed",
				"flexible",
			),
			"tech": out["Tech"],
			"tech_name": out["TechName"],
			"region": out["Region"],
			"fixed_operating_cost_nzd_per_kw_year": pd.to_numeric(
				out["Fixed operating costs (NZD/kW/year)"], errors="coerce"
			),
			"fuel_delivery_cost_nzd_per_gj": fuel_cost,
			"heat_rate_gj_per_gwh": heat_rate,
			"connection_cost_nzd_m": pd.to_numeric(out["Connection cost (NZD $m)"], errors="coerce"),
			"total_capital_costs_nzd_m": pd.to_numeric(out["Total Capital costs (NZD $m)"], errors="coerce"),
			"plants_grouped": pd.to_numeric(out["Plants grouped"], errors="coerce"),
		}
	)

	out_pypsa["available_from_year"] = (
		out_pypsa["available_from_year"].fillna(out_pypsa["fixed_commissioning_year"]).round(0).astype("Int64")
	)
	out_pypsa["earliest_commissioning_year"] = out_pypsa["earliest_commissioning_year"].round(0).astype("Int64")
	out_pypsa["fixed_commissioning_year"] = out_pypsa["fixed_commissioning_year"].round(0).astype("Int64")

	out_pypsa = out_pypsa.sort_values(["scenario", "zone", "generator"]).reset_index(drop=True)
	return out_pypsa


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


def build_grouped_selected_output(pypsa_selected: pd.DataFrame) -> pd.DataFrame:
	grouped = pypsa_selected.copy()
	grouped["family"] = grouped["generator"].map(grouped_family)
	grouped["commissioning_type"] = grouped["commissioning_type"].fillna("flexible")
	grouped["generator"] = grouped["family"] + "_" + grouped["commissioning_type"]
	grouped["technology"] = grouped["generator"]

	group_cols = ["zone", "generator", "technology", "commissioning_type"]
	include_scenario = "scenario" in grouped.columns
	if include_scenario:
		group_cols = ["scenario"] + group_cols

	rows: list[dict] = []
	for keys, group in grouped.groupby(group_cols, dropna=False):
		if not isinstance(keys, tuple):
			keys = (keys,)

		if include_scenario:
			scenario_key = keys[0]
			zone_key, generator_key, technology_key, commissioning_key = keys[1], keys[2], keys[3], keys[4]
		else:
			scenario_key = None
			zone_key, generator_key, technology_key, commissioning_key = keys[0], keys[1], keys[2], keys[3]

		row = {
			"generator": generator_key,
			"zone": zone_key,
			"technology": technology_key,
			"capital_cost": weighted_average(group, "capital_cost", "installed_capacity"),
			"marginal_cost": weighted_average(group, "marginal_cost", "installed_capacity"),
			"efficiency": weighted_average(group, "efficiency", "installed_capacity"),
			"installed_capacity": float(pd.to_numeric(group["installed_capacity"], errors="coerce").sum(min_count=1)),
			"p_min_mw": float(pd.to_numeric(group["p_min_mw"], errors="coerce").sum(min_count=1)),
			"available_from_year": pd.to_numeric(group["available_from_year"], errors="coerce").min(),
			"earliest_commissioning_year": pd.to_numeric(group["earliest_commissioning_year"], errors="coerce").min(),
			"fixed_commissioning_year": pd.to_numeric(group["fixed_commissioning_year"], errors="coerce").min(),
			"commissioning_type": commissioning_key,
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
		if default_key in available_map:
			return [available_map[default_key]]
		return [available[0]]

	requested_flat: list[str] = []
	for item in requested:
		requested_flat.extend([part.strip() for part in str(item).split(",") if part.strip()])

	if any(token.casefold() == "all" for token in requested_flat):
		return available

	selected: list[str] = []
	missing: list[str] = []
	for token in requested_flat:
		key = token.casefold()
		if key in available_map:
			selected.append(available_map[key])
		else:
			missing.append(token)

	if missing:
		raise ValueError(
			"Unknown scenario(s): "
			+ ", ".join(missing)
			+ ". Available: "
			+ ", ".join(available)
		)

	# Keep order and remove duplicates
	seen = set()
	unique_selected = []
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

	# Keep fixed and flexible assets separate through aggregation.
	df["_commissioning_type"] = np.where(
		pd.to_numeric(df["Fixed Commissioning Year"], errors="coerce").notna(),
		"fixed",
		"flexible",
	)

	grouping_columns = ["Scenario", "Region", "Tech", "_commissioning_type"]
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

	rows: list[dict] = []
	for keys, group in df.groupby(grouping_columns, dropna=False):
		row = {
			"Scenario": keys[0],
			"Region": keys[1],
			"Tech": keys[2],
			"TechName": group["TechName"].mode().iat[0] if group["TechName"].notna().any() else np.nan,
			"Capacity (MW)": float(group["Capacity (MW)"].sum(min_count=1)),
			"Heat Rate (GJ/GWh)": weighted_average(group, "Heat Rate (GJ/GWh)"),
			"Variable operating costs (NZD/MWh)": weighted_average(group, "Variable operating costs (NZD/MWh)"),
			"Fixed operating costs (NZD/kW/year)": weighted_average(group, "Fixed operating costs (NZD/kW/year)"),
			"Fuel delivery costs (NZD/GJ)": weighted_average(group, "Fuel delivery costs (NZD/GJ)"),
			"Capital cost (NZD/kW)": weighted_average(group, "Capital cost (NZD/kW)"),
			"Connection cost (NZD $m)": float(group["Connection cost (NZD $m)"].sum(min_count=1)),
			"Total Capital costs (NZD $m)": float(group["Total Capital costs (NZD $m)"].sum(min_count=1)),
			"Earliest Commissioning Year": float(group["Earliest Commissioning Year"].min())
			if group["Earliest Commissioning Year"].notna().any()
			else np.nan,
			"Fixed Commissioning Year": float(group["Fixed Commissioning Year"].min())
			if group["Fixed Commissioning Year"].notna().any()
			else np.nan,
			"Plants grouped": int(len(group)),
		}
		rows.append(row)

	output = pd.DataFrame(rows).sort_values(["Scenario", "Region", "Tech"]).reset_index(drop=True)

	for year_col in ["Earliest Commissioning Year", "Fixed Commissioning Year"]:
		output[year_col] = output[year_col].round(0).astype("Int64")

	output.to_csv(OUTPUT_CSV, index=False, float_format=CSV_FLOAT_FORMAT)

	pypsa_output = build_pypsa_output(output)
	pypsa_output.to_csv(OUTPUT_PYPSA_ALL_CSV, index=False, float_format=CSV_FLOAT_FORMAT)

	available_scenarios = sorted(pypsa_output["scenario"].dropna().astype(str).unique().tolist())
	if list_scenarios_only:
		print("Available scenarios:")
		for s in available_scenarios:
			print(f"  - {s}")
		return

	if selected_scenarios is None:
		selected_scenarios = _prompt_selected_scenarios(available_scenarios)

	selected = _resolve_selected_scenarios(available_scenarios, selected_scenarios)
	selected_keys = {s.casefold() for s in selected}
	selected_mask = pypsa_output["scenario"].astype(str).str.casefold().isin(selected_keys)
	pypsa_selected = pypsa_output.loc[selected_mask].reset_index(drop=True)
	pypsa_selected.to_csv(OUTPUT_PYPSA_SELECTED_CSV, index=False, float_format=CSV_FLOAT_FORMAT)

	pypsa_selected_grouped = build_grouped_selected_output(pypsa_selected)
	pypsa_selected_grouped.to_csv(
		OUTPUT_PYPSA_SELECTED_GROUPED_CSV,
		index=False,
		float_format=CSV_FLOAT_FORMAT,
	)

	# Explicit per-scenario files for easy inspection when multiple scenarios are selected.
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

	# Backward-compatible single-scenario outputs used by downstream workflow.
	# If one scenario is selected, expose it in the legacy reference file names.
	pypsa_reference = pypsa_selected.copy()
	if len(selected) == 1:
		pypsa_reference = pypsa_reference.drop(columns=["scenario"], errors="ignore")
	pypsa_reference.to_csv(OUTPUT_PYPSA_REFERENCE_CSV, index=False, float_format=CSV_FLOAT_FORMAT)

	pypsa_reference_grouped = build_grouped_selected_output(pypsa_reference)
	pypsa_reference_grouped.to_csv(
		OUTPUT_PYPSA_REFERENCE_GROUPED_CSV,
		index=False,
		float_format=CSV_FLOAT_FORMAT,
	)

	print(f"Output written to: {OUTPUT_CSV}")
	print(f"PyPSA all scenarios written to: {OUTPUT_PYPSA_ALL_CSV}")
	print(f"Selected scenarios: {', '.join(selected)}")
	print(f"PyPSA selected written to: {OUTPUT_PYPSA_SELECTED_CSV}")
	print(f"PyPSA selected grouped written to: {OUTPUT_PYPSA_SELECTED_GROUPED_CSV}")
	print(f"Per-scenario outputs written to: {OUTPUT_SELECTED_BY_SCENARIO_DIR}")
	print(f"PyPSA reference written to: {OUTPUT_PYPSA_REFERENCE_CSV}")
	print(f"PyPSA reference grouped written to: {OUTPUT_PYPSA_REFERENCE_GROUPED_CSV}")
	print(f"Rows: {len(output)}")
	print(f"Scenarios: {output['Scenario'].nunique()}")
	print(f"Regions: {output['Region'].nunique()}")
	print(f"Selected rows: {len(pypsa_selected)}")
	print(f"Selected grouped rows: {len(pypsa_selected_grouped)}")
	print(f"Reference rows: {len(pypsa_reference)}")
	print(f"Reference grouped rows: {len(pypsa_reference_grouped)}")


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
