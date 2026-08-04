# PyPSA-Isolated

`PyPSA-Isolated` is a CSV-driven power and energy system optimisation framework built on [PyPSA](https://pypsa.org/). It is designed for isolated or weakly interconnected systems where renewable expansion, storage, sector coupling, hydrogen, underground hydrogen storage (UHS), export-oriented Power-to-X (PtX) production, and security-of-supply constraints need to be assessed consistently.

The model is case-agnostic: each case study is defined through an `input_*/` folder, while the core API in `config.py` builds and solves the PyPSA network.

---

## Case studies

| Case | Description |
|---|---|
| `input_punta_arenas` | Urban-scale isolated system planning for Punta Arenas, including demand evolution, electrification, PtX exports, BESS, hydrogen, and UHS. |
| `input_magallanes` | Regional isolated-system analysis for Magallanes, with emphasis on renewable integration and energy security. |
| `input_rapa_nui` | Island decarbonisation with local production, storage, and multisector mitigation options. |
| `input_juan_fernandez` | Island energy decarbonisation comparing local electrification and fuel import pathways. |
| `input_new_zealand` | Larger islanded-style system analysis for high renewable penetration and long-term expansion planning. |

Additional cases can be added by copying an existing `input_*/` folder and editing the CSV files.

---

## Main capabilities

- **Case-agnostic API**: `run_case()`, `run_case_multiple_years()`, and `export_results_to_csv()`.
- **CSV-driven configuration**: nodes, generators, storage, hydrogen assets, costs, interconnections, demand profiles, and general settings are defined in CSV files.
- **Multi-node network representation**: each zone is represented by an electricity bus, with optional heat, gas, hydrogen, and UHS buses.
- **Variable renewable energy profiles**: wind and solar profiles from ERA5 cutouts using either a simple meteorological proxy or `atlite` technology conversion.
- **Multi-year capacity linking**: capacities built in earlier model years can be carried forward as lower bounds in later years.
- **Technology commissioning logic**: assets can be fixed/existing, committed, flexible/candidate, or retired depending on CSV metadata.
- **Battery storage**: multiple BESS assets and durations can be represented through `storage_capacity.csv`.
- **Hydrogen chain**: electrolyzers, hydrogen tanks, fuel cells, hydrogen turbines, UHS injection, UHS withdrawal, and UHS stores.
- **PtX export module**: optional ammonia and methanol export chains through ASU, DAC, synthesis, product storage, and monthly export constraints.
- **UHS operation**: UHS can be represented as separate injection/withdrawal/store assets or through one combined `uhs` row. UHS inventory is constrained to start and end the modelling year at 50% of optimized/fixed energy capacity.
- **Seasonal UHS windows**: optional injection and withdrawal windows can be enforced through `continuous_operation` and seasonal columns.
- **Heat sector**: optional heat demand, gas boilers, and heat pumps.
- **Transmission/interlinks**: fixed, expandable, bidirectional, and modular/discrete interconnection expansion.
- **Monthly product delivery**: PtX products can be required as monthly export totals, allowing flexible intra-month production and delivery while avoiding unrealistic annual-only aggregation.
- **CO2 cap**: optional annual CO2 constraint by model year.
- **Slack generation**: high-cost unmet-demand proxy for feasibility diagnostics.
- **Automatic solver fallback**: can try Gurobi first and fall back to HiGHS.
- **Standardized result export**: solver summary, capacities, dispatch, link capacities/flows, UHS/store capacities, demand, CO2 emissions, and PtX production/export summaries.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/VicenteSF-git/PyPSA-Isolated.git
cd PyPSA-Isolated
```

### 2. Create the conda environment

```bash
conda env create -f environment.yml
conda activate pypsa-isolated
```

To update an existing environment:

```bash
conda env update -f environment.yml --prune
```

### 3. Optional: install Gurobi

HiGHS can be used as an open-source solver. Gurobi is recommended for larger MILP cases, especially when discrete transmission expansion or unit commitment constraints are enabled.

```bash
conda install -c gurobi gurobi -y
```

### 4. Configure the CDS API

ERA5 cutouts are downloaded through `atlite`, which requires a Copernicus Climate Data Store account. Create `~/.cdsapirc` with:

```text
url: https://cds.climate.copernicus.eu/api
key: <YOUR_UID>:<YOUR_API_KEY>
```

---

## Quick start

### Validate a case

```python
from config import get_case_paths, validate_inputs

paths = get_case_paths("input_punta_arenas")
validate_inputs(**paths, enable_hydrogen=True, enable_ptx=True, strict=True)
```

### Run one model year

```python
from config import get_case_paths, run_case

paths = get_case_paths("input_punta_arenas")

result = run_case(
    year=2050,
    weather_year=2019,
    case_name="punta_arenas",
    solver_name="gurobi",
    fallback_to_highs=True,
    enable_hydrogen=True,
    enable_heat=True,
    **paths,
)

print(result["status"], result["condition"])
print(f"Objective: {result['objective']:,.0f}")
```

### Run a demand scenario by shortcut name

Scenario demand files are preferentially resolved from:

```text
input_punta_arenas/demand_profiles_scenarios/
```

For example, if this file exists:

```text
input_punta_arenas/demand_profiles_scenarios/demand_profiles_RH_full_ptx.csv
```

it can be loaded with:

```python
result = run_case(
    year=2050,
    weather_year=2019,
    case_name="punta_arenas",
    csv_demand="RH_full_ptx",
    enable_hydrogen=True,
    **paths,
)
```

This avoids accidentally using stale `demand_profiles_*.csv` files stored in the case-folder root.

### Run with PtX exports

PtX exports are controlled separately from the hourly electricity/heat demand scenarios. Keep `csv_demand` for local electricity and heat demand, and use `csv_ptx_assets` plus `csv_ptx_monthly_demand` for ammonia/methanol export chains.

```python
from config import get_case_paths, run_case

paths = get_case_paths("input_punta_arenas")

result = run_case(
    year=2050,
    weather_year=2019,
    case_name="punta_arenas",
    csv_demand="RH_full",                 # local electricity/heat scenario
    csv_ptx_assets="input_punta_arenas/ptx_assets.csv",
    csv_ptx_monthly_demand="input_punta_arenas/ptx_monthly_demand.csv",
    enable_hydrogen=True,
    enable_ptx=True,
    enable_heat=True,
    solver_name="gurobi",
    **paths,
)
```

### Run multiple years with capacity linking

```python
from config import get_case_paths, run_case_multiple_years, export_results_to_csv

paths = get_case_paths("input_punta_arenas")

all_results = run_case_multiple_years(
    years=[2025, 2030, 2040, 2050],
    weather_year=2019,
    case_name="punta_arenas",
    solver_name="gurobi",
    enable_year_linking=True,
    enable_hydrogen=True,
    enable_ptx=True,
    enable_heat=True,
    co2_cap_tons={2050: 0},
    time_limit=3600,
    mip_gap=0.05,
    **paths,
)

output_folder = export_results_to_csv(
    all_results,
    case_name="punta_arenas",
    scenario_name="RH_full_ptx",
    output_base_dir="output",
)
print(output_folder)
```

---

## Demand scenarios

`build_demand_scenarios.py` creates future hourly demand profiles from a base-year profile and a scenario configuration file.

### Workflow

1. Edit:

```text
input_punta_arenas/config_demand_scenarios.csv
```

2. Run:

```bash
python build_demand_scenarios.py \
  --input-case input_punta_arenas \
  --base-demand-csv input_punta_arenas/demand_profiles.csv \
  --config-csv input_punta_arenas/config_demand_scenarios.csv \
  --base-year 2025 \
  --years 2030 2040 2050
```

3. Recommended output location:

```text
input_punta_arenas/demand_profiles_scenarios/
```

4. Use a scenario in the model:

```python
paths = get_case_paths("input_punta_arenas")

result = run_case(
    year=2050,
    weather_year=2019,
    case_name="punta_arenas",
    csv_demand="RH_full_ptx",
    enable_hydrogen=True,
    **paths,
)
```

### Demand scenario columns

| Column | Description |
|---|---|
| `scenario` | Scenario name, e.g. `BAU_base`, `RH_full`, `RH_full_ptx`. |
| `year` | Target model year. |
| `zone` | Model zone; must match `nodes.csv`. |
| `component` | Demand component, e.g. `base_load`, `ev`, `heating`, `cooking`, `process_electrification`, `ptx_export`. |
| `enabled` | `True`/`False`; disabled rows are skipped. |
| `growth_factor` | Multiplicative factor over the base profile, mainly for `base_load`. |
| `annual_energy_mwh` | Annual energy assigned to the component. |
| `unit_count` | Number of units, used with `energy_per_unit_kwh_per_year`. |
| `energy_per_unit_kwh_per_year` | Annual energy per unit. |
| `profile_type` | Hourly shape to use. |
| `demand_type` | Demand carrier, e.g. `electricity`, `heat`, or hydrogen-related demand. |

Annual energy can be provided directly with `annual_energy_mwh` or derived from:

```text
unit_count × energy_per_unit_kwh_per_year / 1000
```

### Default hourly profile types

| Profile | Description |
|---|---|
| `base_load` | Historical base-year hourly profile mapped to the target year. |
| `ev` | Evening-biased charging profile with higher weekend demand. |
| `heating` | Southern-hemisphere seasonal heating profile with morning and evening peaks. |
| `cooking` | Breakfast, lunch, and dinner peaks. |
| `process_electrification` | Higher demand during working hours, reduced overnight and on weekends. |
| `ptx_export` | Legacy flat 24/7 PtX demand profile. For NH3/CH3OH exports, prefer `ptx_monthly_demand.csv`. |
| `constant` | Flat profile for continuous loads. |

Custom profiles can be provided with `--profiles-csv`, with one column per `profile_type`. Profiles are normalized internally before annual energy is distributed.

---


## PtX export module

The PtX module is optional and is enabled only when both `enable_hydrogen=True` and `enable_ptx=True`. It is intentionally separated from `hydrogen_assets.csv` so that the hydrogen backbone and the export product chains can be configured independently.

### Conceptual topology

```text
electricity → electrolyzer → H2 bus

Electricity → ASU → N2 bus
Electricity → DAC → CO2 bus

H2 + N2  → ammonia synthesis → NH3 bus   → NH3 storage   → monthly NH3 export
H2 + CO2 → methanol synthesis → CH3OH bus → MeOH storage  → monthly CH3OH export

H2 bus ↔ H2 tank / UHS injection → UHS store → UHS withdrawal ↔ H2 bus
```

The hydrogen system can therefore be valuable either for local power balancing or because export-oriented PtX production creates a large hydrogen flow that may benefit from short-term tanks and/or seasonal UHS.

### Products and feedstocks

Supported products:

| Product aliases | Internal product | Product bus | Feedstock |
|---|---|---|---|
| `ammonia`, `nh3`, `amoniaco` | `ammonia` | `nh3_<zone>` | `nitrogen` / `n2_<zone>` |
| `methanol`, `ch3oh`, `meoh`, `metanol` | `methanol` | `ch3oh_<zone>` | `co2` / `co2_<zone>` |

Default stoichiometric/intensity assumptions used when CSV columns are not specified:

| Product | H2 input | Feedstock input |
|---|---:|---:|
| Ammonia | 5.90 MWh_H2/tNH3 | 0.824 tN2/tNH3 |
| Methanol | 6.25 MWh_H2/tCH3OH | 1.375 tCO2/tCH3OH |

These values are practical modelling defaults. Final scenarios should document the chosen assumptions and sensitivity ranges.

### Monthly export requirements

`ptx_monthly_demand.csv` imposes product delivery as monthly equality constraints:

```text
sum(export_product_t over month m) = monthly demand_tons
```

This avoids a purely annual target that could be satisfied unrealistically in a few high-renewable periods, while still allowing flexibility within each month. Product storage can decouple synthesis timing from export timing.

`export_flexibility_factor` controls the maximum hourly export rate inside the month:

| Value | Interpretation |
|---:|---|
| `1.0` | Export link capacity equals the monthly average export rate. |
| `2.0` | Exports can be concentrated up to twice the monthly average rate. |
| `>2.0` | More flexible intra-month delivery. |

---

## Project structure

```text
PyPSA-Isolated/
├── config.py                         # Core model API and PyPSA network builder
├── build_demand.py                   # Demand loader and demand validation logic
├── build_demand_scenarios.py         # Future demand scenario generator
├── case_analysis.ipynb               # Interactive result analysis notebook
│
├── input_punta_arenas/               # Example case folder
│   ├── nodes.csv
│   ├── generators_capacity.csv
│   ├── storage_capacity.csv
│   ├── hydrogen_assets.csv
│   ├── ptx_assets.csv
│   ├── ptx_monthly_demand.csv
│   ├── interlinks.csv
│   ├── costs.csv
│   ├── general.csv
│   ├── demand_profiles.csv
│   ├── demand_profiles_scenarios/
│   │   └── demand_profiles_<scenario>.csv
│   └── nodes_template.csv
│
├── input_<other_case>/               # Additional cases with the same structure
│
├── data/                             # ERA5 cutouts (.nc)
│   └── <case_name>_<weather_year>.nc
│
├── output/                           # Recommended result export location
└── README.md
```

---

## Input CSV reference

### `nodes.csv`

Required columns:

| Column | Description |
|---|---|
| `zone` | Unique model zone. |
| `annual_mean_mw` | Annual mean electricity demand used for synthetic fallback demand. |

Recommended columns:

| Column | Description |
|---|---|
| `lat`, `lon` | Coordinates used to extract wind and solar profiles. |
| `enabled` | Include or exclude the node. |

Optional heat-sector columns:

| Column | Description |
|---|---|
| `annual_heat_mean_mw` | Annual mean heat demand, if heat demand is generated from node metadata. |
| `existing_gas_boiler_mw` | Existing gas boiler capacity. |
| `installed_heat_pump_mw` | Existing heat pump capacity. |
| `allow_heat_pump` | Whether heat pump expansion is allowed. |
| `heat_pump_available_from_year` | First model year when heat pumps can expand. |
| `heat_pump_cop` | Heat pump coefficient of performance. |
| `gas_boiler_efficiency` | Gas boiler efficiency. |
| `natural_gas_marginal_cost` | Gas supply marginal cost. |

---

### `generators_capacity.csv`

Required columns:

| Column | Description |
|---|---|
| `generator` | Asset or candidate name. |
| `zone` | Model zone. |
| `installed_capacity` | For fixed assets: installed capacity. For flexible assets: cumulative upper bound in the model year. |

Recommended columns:

| Column | Description |
|---|---|
| `asset_id` | Unique PyPSA generator ID. If omitted, `generator_zone` is used. |
| `technology` | Physical technology/carrier, e.g. `wind`, `solar`, `gas`, `diesel`, `hydro`. |
| `capital_cost` | Annualized capital cost. |
| `marginal_cost` | Variable cost. |
| `efficiency` | Conversion efficiency. |
| `enabled` | Include or exclude the row. |

Commissioning and availability columns:

| Column | Description |
|---|---|
| `commissioning_type` | `fixed`, `existing`, `committed`, `flexible`, `candidate`, `expandable`, or `retired`. |
| `available_from_year` | First model year when a flexible candidate can be built. |
| `earliest_commissioning_year` | Alias/alternative for candidate availability. |
| `fixed_commissioning_year` | First year when a fixed/committed asset exists. |
| `p_min_mw` | Minimum technical output for committable fixed units. |
| `capacity_factor` / `availability_factor` | Fixed capacity factor for hydro-like assets. |

Technology labels are normalized internally. Wind and solar-like technologies receive hourly VRE availability profiles when coordinates and cutouts are available.

---

### `storage_capacity.csv`

Required columns:

| Column | Description |
|---|---|
| `zone` | Model zone. |
| `installed_power_mw` | Existing/fixed power capacity, or initial/minimum capacity for flexible storage. |
| `max_hours` | Energy-to-power duration. |

Recommended/optional columns:

| Column | Description |
|---|---|
| `asset_id` | Unique StorageUnit ID. |
| `storage` | Storage asset name, e.g. `bess_4h`, `bess_8h`. |
| `technology` | Carrier label, usually `bess`. |
| `max_power_mw`, `p_nom_max_mw`, `installed_power_max_mw` | Upper bound for flexible storage expansion. |
| `capital_cost` | Annualized cost per MW. |
| `marginal_cost` | Variable cost per MWh. |
| `efficiency_store` | Charging efficiency. |
| `efficiency_dispatch` | Discharging efficiency. |
| `standing_loss` | Hourly self-discharge. |
| `commissioning_type`, `available_from_year`, `earliest_commissioning_year`, `fixed_commissioning_year`, `enabled` | Same commissioning logic as generators. |

---

### `interlinks.csv`

Required columns:

| Column | Description |
|---|---|
| `from_zone` | Source zone. |
| `to_zone` | Sink zone. |
| `capacity_mw` | Existing/fixed transfer capacity. |
| `loss_fraction` | Link losses, from 0 to less than 1. |

Optional columns:

| Column | Description |
|---|---|
| `asset_id` | Unique interlink ID. |
| `enabled` | Include/exclude the interlink. |
| `expandable` | Allow capacity expansion. |
| `discrete_expansion` | Enforce modular/integer expansion. |
| `module_capacity_mw` | Capacity per module when modular expansion is used. |
| `min_modules`, `max_modules` | Minimum and maximum number of modules. |
| `max_capacity_mw` | Continuous expansion upper bound. |
| `capital_cost` | Annualized transmission capacity cost. |
| `marginal_cost` | Flow cost. |
| `bidirectional` | If true, the corridor is represented as two directed links sharing the same optimized capacity. |

Bidirectional interlinks are not represented through negative flows. They are implemented as two non-negative directed links with a shared-capacity constraint, avoiding artificial negative objective contributions.

---

### `hydrogen_assets.csv`

Required columns:

| Column | Description |
|---|---|
| `zone` | Model zone. |
| `asset_type` | Hydrogen or UHS component type. |

Supported `asset_type` values include:

| Asset type | Description |
|---|---|
| `electrolyzer` | Electricity to hydrogen conversion. |
| `h2_store_tank`, `h2_tank`, `tank` | Above-ground hydrogen storage. |
| `h2_fuel_cell` | Hydrogen to electricity through fuel cell. |
| `h2_turbine` | Hydrogen to electricity through turbine. |
| `uhs_injection`, `dgr_injection` | Injection link from hydrogen bus to UHS bus. |
| `uhs_withdrawal`, `dgr_withdrawal` | Withdrawal link from UHS bus to hydrogen bus. |
| `uhs_store`, `dgr_store` | Underground hydrogen store. |
| `uhs`, `dgr`, `h2_uhs`, `h2_store_uhs` | Combined UHS row that creates injection, withdrawal, and store components. |

Common columns:

| Column | Description |
|---|---|
| `asset_id` | Unique base asset ID. |
| `technology` | Carrier/technology label. |
| `installed_capacity_mw` | Existing/fixed power capacity for Link assets. |
| `installed_energy_mwh` | Existing/fixed energy capacity for Store assets. |
| `p_nom_max_mw`, `max_capacity_mw`, `installed_capacity_max_mw` | Upper bound for flexible Link assets. |
| `e_nom_max_mwh`, `max_energy_mwh`, `installed_energy_max_mwh` | Upper bound for flexible Store assets. |
| `capital_cost`, `marginal_cost`, `efficiency`, `standing_loss` | Generic cost and performance attributes. |
| `commissioning_type`, `available_from_year`, `earliest_commissioning_year`, `fixed_commissioning_year`, `enabled` | Commissioning logic. |

Additional columns for a combined `uhs` row:

| Column | Description |
|---|---|
| `injection_capacity_mw` | Initial/minimum injection capacity. |
| `withdrawal_capacity_mw` | Initial/minimum withdrawal capacity. |
| `injection_p_nom_max_mw` | Upper bound for injection capacity. |
| `withdrawal_p_nom_max_mw` | Upper bound for withdrawal capacity. |
| `injection_efficiency`, `withdrawal_efficiency` | Direction-specific efficiencies. |
| `injection_capital_cost`, `withdrawal_capital_cost`, `storage_capital_cost` | Component-specific capital costs. |
| `injection_marginal_cost`, `withdrawal_marginal_cost`, `storage_marginal_cost` | Component-specific marginal costs. |

Seasonal UHS columns:

| Column | Description |
|---|---|
| `continuous_operation` | If `1`, seasonal injection/withdrawal masks are enforced as hard availability windows. If `0`, operation is flexible. |
| `injection_season_start` | Day-of-year when injection window starts. |
| `injection_season_days` | Injection window length in days. |
| `withdrawal_season_start` | Day-of-year when withdrawal window starts. |
| `withdrawal_season_days` | Withdrawal window length in days. |

By default, UHS stores are constrained to begin and end the simulated year at 50% of their optimized or fixed energy capacity.

---


### `ptx_assets.csv`

`ptx_assets.csv` defines optional Power-to-X conversion, feedstock, synthesis, product storage, and export-related assets. It is separate from `hydrogen_assets.csv`, which remains focused on the H2 backbone, H2-to-power, tanks, and UHS.

Required columns:

| Column | Description |
|---|---|
| `zone` | Model zone. |
| `asset_type` | PtX component type. |

Supported `asset_type` values include:

| Asset type | Description |
|---|---|
| `asu`, `air_separation_unit`, `n2_production` | Electricity to nitrogen feedstock. |
| `dac`, `direct_air_capture`, `co2_capture` | Electricity to CO2 feedstock. |
| `ammonia_synthesis`, `nh3_synthesis`, `haber_bosch` | H2 + N2 to ammonia. |
| `methanol_synthesis`, `ch3oh_synthesis`, `meoh_synthesis` | H2 + CO2 to methanol. |
| `ammonia_store`, `nh3_store` | Ammonia product storage. |
| `methanol_store`, `ch3oh_store`, `meoh_store` | Methanol product storage. |

Useful columns:

| Column | Description |
|---|---|
| `asset_id` | Unique component ID. |
| `technology` | Carrier/technology label, e.g. `asu`, `dac`, `ammonia_synthesis`. |
| `product` | Product associated with synthesis or storage, e.g. `ammonia` or `methanol`. |
| `installed_capacity_mw` | Initial/minimum Link input capacity. For ASU/DAC this is MW_e; for synthesis this is MW_H2. |
| `p_nom_max_mw`, `max_capacity_mw`, `installed_capacity_max_mw` | Upper bound for flexible Link expansion. |
| `installed_energy_tons` | Initial/minimum product storage capacity. |
| `e_nom_max_tons`, `max_energy_tons`, `installed_energy_max_tons` | Upper bound for flexible product storage capacity. |
| `electricity_mwh_per_t` | Electricity intensity for ASU/DAC, expressed as MWh/t feedstock. |
| `h2_mwh_per_t_product` | H2 input intensity for synthesis, expressed as MWh_H2/t product. |
| `feedstock_t_per_t_product` | N2 or CO2 input per tonne of product. |
| `capital_cost`, `marginal_cost`, `efficiency`, `standing_loss` | Cost and performance attributes. |
| `commissioning_type`, `available_from_year`, `earliest_commissioning_year`, `fixed_commissioning_year`, `enabled` | Same commissioning logic as generators and hydrogen assets. |

Unit convention:

| Component | Capacity unit | Flow interpretation |
|---|---|---|
| ASU/DAC | MW_e input | Output is feedstock in t/h through the conversion efficiency or inverse intensity. |
| NH3/MeOH synthesis | MW_H2 input | Output is product in t/h; secondary input is feedstock consumption. |
| Product storage | tonnes | Store energy variable is interpreted as tonnes of NH3 or CH3OH. |

---

### `ptx_monthly_demand.csv`

`ptx_monthly_demand.csv` defines monthly export requirements for ammonia and methanol.

Required columns:

| Column | Description |
|---|---|
| `zone` | Zone where product export is imposed. |
| `product` | `ammonia`/`nh3` or `methanol`/`ch3oh`/`meoh`. |
| `month` | Month number from 1 to 12. |
| `demand_tons` | Monthly export requirement in tonnes of product. |

Optional columns:

| Column | Description |
|---|---|
| `year` | If provided, rows are filtered to the current model year. |
| `scenario` | Scenario label for bookkeeping, e.g. `S8`, `S9`, or `S10`. |
| `export_flexibility_factor` | Maximum hourly export rate relative to the monthly average. Minimum is 1.0. |
| `enabled` | Include or exclude the row. |

Example:

```csv
year,zone,product,month,demand_tons,export_flexibility_factor,enabled,scenario
2050,punta_arenas_2,ammonia,1,10000,1.5,True,S8
2050,punta_arenas_2,methanol,1,5000,2.0,True,S8
```

---

### `costs.csv`

`costs.csv` provides technology-level defaults and year-aware cost projections.

| Column | Description |
|---|---|
| `technology` | Technology/carrier label. |
| `year` | Optional year-specific row. |
| `base_year` | Optional projection anchor year. |
| `capital_cost` | Annualized capital cost. |
| `marginal_cost` | Variable cost. |
| `efficiency` | Efficiency or COP. |
| `co2_emissions` | Emissions factor in tCO2/MWh of carrier. |
| `annual_change` | Generic annual compound rate. |
| `capital_cost_annual_change` | Annual rate for capital cost. |
| `marginal_cost_annual_change` | Annual rate for marginal cost. |
| `co2_emissions_annual_change` | Annual rate for emissions factor. |
| `max_hours`, `efficiency_store`, `efficiency_dispatch`, `standing_loss` | Storage defaults when applicable. |

Cost selection for a model year follows this priority:

1. Exact `year` match.
2. Latest available year before the target.
3. Earliest available year after the target.
4. Static row without `year`.

Projection rule:

```text
value_target = value_base × (1 + annual_rate)^(target_year − base_year)
```

Rates can be provided either as decimals (`-0.05`) or percentages (`-5`).

---

### `general.csv`

`general.csv` stores global scenario settings.

| Parameter | Description |
|---|---|
| `slack_cost_per_mwh` | Penalty cost for unmet electricity demand. |
| `hydro_capacity_factor` | Default fixed capacity factor for hydro-like technologies. |

Rows can include an `enabled` column. Disabled rows are ignored.

Technology-specific costs and emissions should generally be placed in `costs.csv`, not `general.csv`. PtX technologies such as `asu`, `dac`, `ammonia_synthesis`, `methanol_synthesis`, `ammonia_storage`, and `methanol_storage` can be added to `costs.csv` and will be used as defaults when row-level values are omitted.

---

## Weather and VRE profiles

ERA5 cutouts are created or loaded through:

```python
get_case_cutout(
    year=2019,
    case_name="punta_arenas",
    nodes_df=nodes_df,
    base_dir="data",
)
```

The model supports two VRE profile methods:

| Method | Description |
|---|---|
| `simple` | Uses ERA5 wind speed and irradiance proxies. |
| `atlite_technology` | Uses `atlite` technology conversion for wind turbines and PV panels. |

Example:

```python
result = run_case(
    year=2050,
    weather_year=2016,
    case_name="punta_arenas",
    vre_profile_method="atlite_technology",
    wind_turbine="Vestas_V112_3MW",
    solar_panel="CSi",
    solar_orientation="latitude_optimal",
    **paths,
)
```

Historical weather profiles are mapped to the model year while handling leap-year differences.

---

## Capacity linking across years

When `enable_year_linking=True`, each model year receives the previous optimized network. The model then uses already-built capacities as lower bounds in the next model year.

This affects:

- Generators
- Storage units
- Hydrogen links
- Hydrogen and UHS stores
- PtX synthesis links and product stores
- Heat pumps

Example:

```python
all_results = run_case_multiple_years(
    years=[2025, 2030, 2040, 2050],
    weather_year=2019,
    case_name="punta_arenas",
    enable_year_linking=True,
    **paths,
)
```

---

## CO2 constraints

A scalar CO2 cap applies the same cap to all years:

```python
run_case(co2_cap_tons=0, **paths)
```

A dictionary applies year-specific caps:

```python
run_case_multiple_years(
    years=[2030, 2040, 2050],
    co2_cap_tons={2030: 50000, 2040: 10000, 2050: 0},
    **paths,
)
```

The cap is implemented as a PyPSA `GlobalConstraint` using carrier-level `co2_emissions`.

---

## Exported results

Use:

```python
from config import export_results_to_csv

folder = export_results_to_csv(
    all_results,
    case_name="punta_arenas",
    scenario_name="RH_full_ptx",
    output_base_dir="output",
)
```

The export folder follows:

```text
output_<case_name>_<scenario_name>_YYYY_MM_DD_<counter>/
```

Files created:

| File | Description |
|---|---|
| `<case>_solver_summary.csv` | Solver, status, condition, and objective by year. |
| `<case>_capacity_by_year.csv` | Generator and StorageUnit power capacity by year. |
| `<case>_links_by_year.csv` | Transmission, heat, and hydrogen Link capacities by year. |
| `<case>_stores_by_year.csv` | Store energy capacities, including UHS. |
| `<case>_dispatch_by_year.csv` | Annual generation, storage discharge, and link input energy by carrier. |
| `<case>_demand_by_year.csv` | Annual electricity demand and peak demand by zone. |
| `<case>_co2_by_year.csv` | Annual CO2 emissions by carrier. |
| `<case>_ptx_summary_by_year.csv` | Annual PtX feedstock production, synthesis, and product export summary. |
| `link_flows/<case>_link_flows_<year>.csv` | Hourly link flows for each model year. |

---

## Result analysis

Open `case_analysis.ipynb` in Jupyter or VS Code to inspect:

- Demand profiles by year, zone, and component
- Wind and solar capacity factor profiles
- Installed capacity by technology and zone
- Dispatch by technology
- Weekly winter and summer dispatch
- BESS charge/discharge and state of charge
- Hydrogen production, storage, reconversion, and UHS inventory
- PtX feedstock production, NH3/CH3OH synthesis, product storage, and monthly exports
- Heat sector supply
- Transmission/interlink flows
- CO2 emissions
- Curtailment and renewable surplus diagnostics
- System topology and georeferenced maps

---

## Creating a new case study

1. Copy an existing case folder:

```bash
cp -r input_punta_arenas input_my_case
```

2. Edit the input files:

```text
nodes.csv
generators_capacity.csv
storage_capacity.csv
hydrogen_assets.csv
ptx_assets.csv
ptx_monthly_demand.csv
interlinks.csv
costs.csv
general.csv
demand_profiles.csv
```

3. Validate inputs:

```python
from config import get_case_paths, validate_inputs

paths = get_case_paths("input_my_case")
validate_inputs(**paths, enable_hydrogen=True, enable_ptx=True, strict=True)
```

4. Run:

```python
from config import get_case_paths, run_case

paths = get_case_paths("input_my_case")

result = run_case(
    year=2030,
    weather_year=2019,
    case_name="my_case",
    **paths,
)
```

---

## Troubleshooting

### Synthetic fallback demand was used

If the model prints a warning about `synthetic_fallback`, the demand CSV did not provide a complete profile for the requested year, zone, and demand type. Check:

- `csv_demand` points to the intended file or scenario shortcut.
- The demand file includes the requested year.
- Zone names match `nodes.csv`.
- `demand_type` is correctly set.

### `Objective: inf`

If the solver returns `status=ok`, `condition=time_limit`, and `objective=inf`, it likely reached the time limit before finding a feasible MIP solution.

Possible fixes:

- Increase `time_limit`.
- Relax `mip_gap`.
- Reduce the number of model years.
- Temporarily disable discrete expansion or unit commitment.
- Use Gurobi if available.

### Unexpected slack generation

Slack generation means demand was not fully supplied by normal technologies. Check:

- Renewable and backup capacity bounds.
- Storage and transmission limits.
- Demand profiles, especially heating and PtX demand.
- CO2 cap feasibility.
- Whether `slack_cost_per_mwh` is high enough for diagnostics but not so high that it creates numerical issues.

### Negative or suspicious objective values

Check whether any interlink is represented with negative flows and positive marginal costs. The current implementation avoids this by representing bidirectional corridors as two non-negative directed links with shared capacity.

### UHS starts at the wrong inventory level

The current custom constraint fixes UHS stores to start and end at 50% of energy capacity. Confirm that the relevant store has carrier `uhs_storage` and that it is represented as a PyPSA `Store`.

### PtX monthly demand is infeasible

Monthly NH3/CH3OH export constraints are hard equality constraints. Check:

- `ptx_monthly_demand.csv` uses the intended year, zone, product, and month.
- `enable_hydrogen=True` and `enable_ptx=True` are both set.
- `ptx_assets.csv` includes the required ASU/DAC, synthesis, and product storage assets.
- Electrolyzer, H2 storage/UHS, feedstock production, synthesis, and renewable capacities have sufficient upper bounds.
- `export_flexibility_factor` is not too restrictive for the required monthly export profile.

### PtX appears but UHS does not

This can be a valid least-cost result. UHS competes with flexible synthesis operation, product storage, H2 tanks, renewable overbuild, BESS, and curtailment. Useful sensitivities include UHS cost, product storage cost, export flexibility, renewable land constraints, BESS limits, and monthly demand seasonality.

### Gurobi unavailable

Set:

```python
solver_name="highs"
```

or keep:

```python
solver_name="gurobi"
fallback_to_highs=True
```

---

## Notes for reproducibility

Recommended information to record for each experiment:

- Git commit hash
- `CONFIG_VERSION`
- Case folder and scenario name
- Model years and weather year
- VRE profile method
- Solver and solver options
- CO2 cap assumptions
- Demand scenario file
- PtX asset file and monthly export-demand file, if used
- Cost file version
- Whether year-linking, hydrogen, PtX, heat, UHS, and discrete transmission were enabled

---

## References

- [PyPSA Documentation](https://pypsa.org/)
- [Atlite Documentation](https://atlite.readthedocs.io/)
- [Copernicus Climate Data Store / ERA5](https://cds.climate.copernicus.eu/)

## S8–S10 PtX export scenarios

The PtX export scenarios are defined as an extension of the existing local-demand scenarios. Local electricity/heat demand remains in the usual `demand_profiles_scenarios/` files, while product export obligations are read separately from `ptx_monthly_demand.csv`.

| Paper ID | Scenario code | Local demand profile reused | Additional export module | Purpose |
|---|---|---|---|---|
| S8 | `PTX_base` | `demand_profiles_RH_base.csv` (S5) | Monthly NH3 + CH3OH export | Test PtX export under base local demand. |
| S9 | `PTX_partial` | `demand_profiles_RH_partial.csv` (S6) | Monthly NH3 + CH3OH export | Test PtX export with partial electrification. |
| S10 | `PTX_full` | `demand_profiles_RH_full.csv` (S7) | Monthly NH3 + CH3OH export | Test PtX export with full electrification and seasonal local demand. |

This separation is intentional: S8–S10 do not need separate electricity-demand CSVs if the intended local demand is identical to S5–S7. The notebook filters `ptx_monthly_demand.csv` by the `scenario` column before passing the demand table to `run_case_multiple_years(...)`, so rows for S8, S9 and S10 are not summed together.

A starter `ptx_monthly_demand.csv` is provided with an editable export scale of 70 ktNH3/year and 30 ktCH3OH/year by 2050, ramping up from 2030 to 2040 and 2050. The monthly shape is weighted toward European winter / austral summer demand: January, February and December are higher, while June–August are lower. These values are placeholders for scenario exploration and should be replaced or cited before final paper results.
