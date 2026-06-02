# PyPSA-Isolated

Generic power system optimization framework built on [PyPSA](https://pypsa.org/), designed for isolated or weakly interconnected regions. Includes electricity, heat, battery storage, hydrogen (electrolyzer, fuel cell, H2 turbine), and underground hydrogen storage (UHS).

## Case studies

| Case | Description |
|---|---|
| New Zealand | Large islanded-style power system analysis with high renewable penetration and long-term expansion planning. |
| Punta Arenas | Urban-scale isolated system planning with emphasis on sector coupling and future demand evolution. |
| Magallanes | Integrated power system planning focused on energy security under a 100% renewable scenario. |
| Rapa Nui | Electricity and energy system decarbonization with a multisector emissions mitigation perspective. |
| Juan Fernandez Archipelago | Island energy decarbonization comparing local production/electrification pathways versus imported fuels. |

## Features

- **Generic API** — `run_case()` / `run_case_multiple_years()` work for any case study
- **CSV-driven configuration** — nodes, generators, storage, hydrogen assets, costs, and interconnections defined in CSV files
- **Folder-based cases** — each case lives in its own `input_*/` folder
- **Optional hydrogen chain** — electrolyzer, H2 tank, fuel cell, H2 turbine, and UHS via CSV
- **Optional heat sector** — gas boiler and heat pump coupling
- **ERA5 weather cutouts** — automatic download via `atlite` (handled internally by `config.py`)
- **Multi-year optimization** — with inter-year capacity linking
- **Automatic input validation** — `validate_inputs()` checks consistency before solving
- **Automatic solver fallback** — tries Gurobi first, falls back to HiGHS

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

If you already created the environment and only want to refresh it after changes, use:

```bash
conda env update -f environment.yml --prune
```

### 3. Install dependencies

The environment file already includes the core Python packages used by the project, including `pypsa`, `atlite`, `numpy`, `pandas`, `xarray`, `matplotlib`, `folium`, `jupyter`, `openpyxl`, and `highspy`.

If you have a Gurobi license, also install:

```bash
conda install -c gurobi gurobi -y
```

If you prefer manual installation instead of `environment.yml`, you can still install the packages with `conda install` and `pip install` as before.

### 4. Configure CDS API (for ERA5 cutouts)

To download weather data with `atlite`, you need a [CDS API](https://cds.climate.copernicus.eu/) account. Create `~/.cdsapirc` with your key:

```
url: https://cds.climate.copernicus.eu/api
key: <YOUR_UID>:<YOUR_API_KEY>
```

---

## Quick start

### Run a case (single year)

```python
from config import run_case, get_case_paths

paths = get_case_paths("input_punta_arenas")

result = run_case(
    year=2050,
    weather_year=2019,
    case_name="punta_arenas",
    solver_name="gurobi",   # falls back to HiGHS if unavailable
    enable_hydrogen=True,
    **paths,
)

print(f"Total cost: €{result['objective']:,.0f}")
```

### Run multiple years with capacity linking

```python
from config import run_case_multiple_years, get_case_paths

paths = get_case_paths("input_punta_arenas")

all_results = run_case_multiple_years(
    years=[2040, 2050],
    weather_year=2019,
    case_name="punta_arenas",
    solver_name="gurobi",
    enable_year_linking=True,
    enable_hydrogen=True,
    co2_cap_tons={2050: 0},
    **paths,
)
```

### Validate inputs before running

```python
from config import validate_inputs, get_case_paths

paths = get_case_paths("input_punta_arenas")
validate_inputs(**paths, strict=True)
```

### Analyze results interactively

Open `case_analysis.ipynb` in Jupyter or VS Code. The notebook produces:

- Demand, wind, and solar capacity factor profiles
- Aggregate dispatch by technology vs. total demand
- Weekly dispatch zoom (winter / summer)
- Installed capacity evolution across years (by technology and zone)
- CO2 emissions (annual and monthly)
- BESS charge/discharge and state of charge
- Hydrogen/UHS operation: production, reconversion, and inventory
- Heat sector: gas boiler vs. heat pump supply
- System topology diagram per zone
- Georeferenced map with capacities and interconnection flows

---

## Demand scenarios

`build_demand_scenarios.py` generates future demand profiles from a base year. It creates one `demand_profiles_{scenario}.csv` file per scenario (containing all years together), which `run_case` loads automatically by filtering the requested timestamp range.

### Workflow

**1. Configure** `input_punta_arenas/config_demand_scenarios.csv`

**2. Run:**
```bash
python build_demand_scenarios.py \
  --input-case input_punta_arenas \
  --base-demand-csv input_punta_arenas/demand_profiles.csv \
  --config-csv input_punta_arenas/config_demand_scenarios.csv \
  --base-year 2025 \
  --years 2030 2040 2050
```

**3. Files generated in `input_punta_arenas/`:**

| Archivo | Contenido |
|---|---|
| `demand_profiles_{scenario}.csv` | Aggregated profile (timestamp, zone, demand_type, demand_mw) |
| `demand_components_{scenario}.csv` | Component-level breakdown |
| `demand_scenario_summary.csv` | Annual summary by component (energy, max, min, mean) |

**4. Use in the model:**
```python
paths = get_case_paths("input_punta_arenas")
result = run_case(year=2030, case_name="punta_arenas",
                  csv_demand="input_punta_arenas/demand_profiles_reference.csv",
                  **paths)
```

---

### `config_demand_scenarios.csv` — columns

| Column | Description |
|---|---|
| `scenario` | Scenario name (e.g. `reference`, `high_growth`) |
| `year` | Target year (e.g. 2030, 2040, 2050) |
| `zone` | Node zone (must exist in `nodes.csv`) |
| `component` | See supported components below |
| `enabled` | `True`/`False` — row is skipped if False |
| `growth_factor` | Multiplicative factor over the base profile (only `base_load`) |
| `annual_energy_mwh` | Total annual energy to distribute (MWh) |
| `unit_count` | Number of units (alternative to `annual_energy_mwh`) |
| `energy_per_unit_kwh_per_year` | Energy per unit (kWh/year) |
| `profile_type` | Hourly shape to use (see below) |
| `demand_type` | Demand type (`electricity`, `heat`, etc.) |

Annual energy can be defined in two ways (first available is used):
- **Direct:** `annual_energy_mwh`
- **Activity-based:** `unit_count × energy_per_unit_kwh_per_year / 1000`

---

### Supported components

| `component` | Description |
|---|---|
| `base_load` | Historical 2025 profile scaled by `growth_factor` |
| `ev` | Electric vehicle charging load |
| `heating` | Electric heating load |
| `cooking` | Electric cooking load |
| `process_electrification` | Industrial electrification load |
| `ptx_export` | PtX export demand |

---

### Default hourly profiles

When `profile_type` matches the component name, a synthetic profile defined in code is used. All profiles are normalized so their annual sum equals 1 before energy is distributed.

#### `base_load`
Uses the real base-year curve (`demand_profiles.csv`) mapped to the target year. For non-leap to leap-year transitions, the 24 hours of February 28 are replicated on February 29.

#### `ev` — electric vehicles
- Evening peak centered at **20:00** (σ = 2.5h), representing charging after arriving home
- Minimum baseline at 25% of peak during the rest of the day
- **+10% on weekends** (higher time at home)
- Formula: `0.25 + 1.75 · exp(−0.5·((h−20)/2.5)²) × weekend_factor`

#### `heating` — electric heating
- **Seasonal factor** (southern hemisphere):
  - Winter (May-September): ×1.8
  - Summer (October-April): ×0.6
- Two daily peaks: **morning ~7:00** (σ = 3.0h, amplitude 0.45) and **evening ~20:00** (σ = 3.5h, amplitude 0.35)
- Constant baseline of 0.55
- Formula: `seasonal_factor × (0.55 + 0.45·exp(−((h−7)/3)²/2) + 0.35·exp(−((h−20)/3.5)²/2))`

#### `cooking` — electric cooking
- Three daily peaks:
  - **Breakfast ~8:00** (σ = 1.5h, amplitude 0.8)
  - **Lunch ~13:00** (σ = 1.5h, amplitude 0.7)
  - **Dinner ~20:00** (σ = 1.8h, amplitude 1.2) — highest peak
- Minimum baseline of 0.10
- No seasonal or weekday variation

#### `process_electrification` — industry
- **Working hours (7:00-19:00):** factor 1.0 (`0.45 + 0.55 = 1.0`)
- **Off-hours:** factor 0.45
- **Weekends:** ×0.7 applied to all values
- Represents industrial processes with reduced nighttime and weekend operation

#### `ptx_export` — export (PtX / H2)
- Fully flat profile (equivalent to `constant`)
- Distributes annual energy uniformly across all hours

#### `constant`
- Flat profile. Useful for loads that operate 24/7 without variation (e.g. continuous hydrogen plants).

---

### Custom profiles (optional)

To replace any synthetic profile with real data, create a CSV with one column per profile and pass it with `--profiles-csv`:

```
timestamp,ev,heating
2025-01-01 00:00,0.12,0.30
2025-01-01 01:00,0.09,0.28
...
```

The column name must match the `profile_type` in the config. The script automatically normalizes each profile before use.

---

## Project structure

```
PyPSA-Isolated/
├── config.py                      # Core API (run_case, run_case_multiple_years, etc.)
├── build_demand.py                # Demand profile construction
├── build_demand_scenarios.py      # Demand scenario generator (future years)
├── case_analysis.ipynb            # Results visualization notebook
│
├── input_punta_arenas/            # Example case: Punta Arenas
│   ├── nodes.csv                  # Zones, demand, coordinates
│   ├── generators_capacity.csv    # Generator capacities
│   ├── storage_capacity.csv       # BESS parameters
│   ├── hydrogen_assets.csv        # H2/UHS assets (optional)
│   ├── interlinks.csv             # Interconnections between zones
│   ├── costs.csv                  # Technology costs
│   ├── demand_profiles.csv        # Hourly demand profiles
│   ├── general.csv                # General parameters
│   └── nodes_template.csv         # Template for new cases
│
├── input_<other_case>/            # Additional cases (same structure)
│
├── data/                          # Shared weather cutouts (.nc)
│   └── magallanes_2019.nc
│
└── README.md
```

---

## Creating a new case study

**1. Copy an existing case folder:**
```bash
cp -r input_punta_arenas input_my_case
```

**2. Edit the CSV files with your data:**
- `nodes.csv` — zones, annual mean demand, coordinates
- `generators_capacity.csv` — installed capacities by technology and zone
- `interlinks.csv` — interconnections
- `storage_capacity.csv` — battery storage
- `hydrogen_assets.csv` — hydrogen chain assets (optional)
- `costs.csv` — annualized costs per technology

**3. Validate:**
```python
from config import validate_inputs, get_case_paths

paths = get_case_paths("input_my_case")
validate_inputs(**paths)
```

**4. Run:**
```python
from config import run_case, get_case_paths

paths = get_case_paths("input_my_case")
result = run_case(year=2030, case_name="my_case", **paths)
```

---

## Switching between cases

```python
from config import run_case, get_case_paths

# Change only this line:
CASE = "input_punta_arenas"  # or "input_magallanes", "input_my_case", etc.

paths = get_case_paths(CASE)
result = run_case(
    year=2030,
    case_name=CASE.replace("input_", ""),
    **paths,
)
```

---

## CSV format reference

### `nodes.csv` (required)

| Column           | Type  | Description                    | Required |
|------------------|-------|--------------------------------|----------|
| zone             | str   | Unique node name               | yes      |
| annual_mean_mw   | float | Annual mean demand (MW)        | yes      |
| lat              | float | Latitude (for VRE profiles)    | recommended |
| lon              | float | Longitude (for VRE profiles)   | recommended |
| enabled          | bool  | Include this node              | no       |

### `generators_capacity.csv`

| Column              | Type  | Description                      |
|---------------------|-------|----------------------------------|
| generator           | str   | Technology (wind, solar, ocgt)   |
| zone                | str   | Generator zone                   |
| installed_capacity  | float | Base installed capacity (MW)     |
| capital_cost        | float | $/MW/year                        |
| marginal_cost       | float | $/MWh                            |
| efficiency          | float | 0–1                              |
| p_min_mw            | float | Minimum technical output (MW)    |

### `interlinks.csv`

| Column         | Type  | Description             |
|----------------|-------|-------------------------|
| from_zone      | str   | Origin zone             |
| to_zone        | str   | Destination zone        |
| capacity_mw    | float | Capacity (MW)           |
| loss_fraction  | float | Losses (0–1)            |
| enabled        | bool  | Enable interconnection  |

### `storage_capacity.csv`

| Column                | Type  | Description                    |
|-----------------------|-------|--------------------------------|
| zone                  | str   | Zone                           |
| installed_power_mw    | float | Installed power (MW)           |
| max_hours             | float | Maximum duration (hours)       |
| capital_cost          | float | $/MW/year                      |
| marginal_cost         | float | $/MWh                          |
| efficiency_store      | float | Charging efficiency (0–1)      |
| efficiency_dispatch   | float | Discharging efficiency (0–1)   |
| standing_loss         | float | Self-discharge per hour (0–1)  |

### `costs.csv` (optional, recommended)

Fill in missing technology values and define year-aware projections:

| Column                      | Type  | Description                                      |
|-----------------------------|-------|--------------------------------------------------|
| technology                  | str   | wind, solar, ocgt, bess, natural_gas, etc.      |
| year                        | int   | Optional row year (one or more rows per tech)    |
| base_year                   | int   | Optional projection anchor year                   |
| capital_cost                | float | $/MW/year                                         |
| marginal_cost               | float | $/MWh                                             |
| efficiency                  | float | 0-1 (or COP for heat_pump)                        |
| co2_emissions               | float | tCO2/MWh                                          |
| annual_change               | float | Generic annual rate (decimal or %)                |
| capital_cost_annual_change  | float | Annual rate for capital_cost                      |
| marginal_cost_annual_change | float | Annual rate for marginal_cost                     |
| co2_emissions_annual_change | float | Annual rate for co2_emissions                     |

Selection rules by technology when running a model year:
- Exact `year` match first
- If no exact match, latest available year before target
- If still missing, earliest year after target
- If `year` is omitted, row is treated as static

Projection rule:
- If annual rates are provided, values are projected with compound growth:
    value_target = value_base * (1 + rate)^(target_year - base_year)

### `general.csv` (optional)

Global scenario settings only (for example `slack_cost_per_mwh`).
Technology-specific costs and emissions should be in `costs.csv`.

### `hydrogen_assets.csv` (optional)

Models a full H2 chain per zone (electrolyzer, tank, fuel cell, H2 turbine, UHS).

| Column                 | Type  | Description                                                       |
|------------------------|-------|-------------------------------------------------------------------|
| zone                   | str   | Asset zone                                                        |
| asset_type             | str   | `electrolyzer`, `h2_store_tank`, `h2_fuel_cell`, `h2_turbine`     |
| installed_capacity_mw  | float | Initial link capacity (MW). Use `0` for endogenous investment     |
| installed_energy_mwh   | float | Initial store capacity (MWh). Use `0` for endogenous investment   |
| capital_cost           | float | Annualized cost                                                   |
| marginal_cost          | float | Variable cost                                                     |
| efficiency             | float | Efficiency (links)                                                |
| standing_loss          | float | Hourly loss (store)                                               |
| available_from_year    | int   | Earliest year of availability                                     |
| enabled                | bool  | Include asset                                                     |

> **Tip:** To let the optimizer decide whether to build H2 assets, set `installed_capacity_mw` and `installed_energy_mwh` to `0` with `enabled=True`.

---

## Advanced API

### Multi-year simulation with capacity linking

```python
from config import run_case_multiple_years, get_case_paths

paths = get_case_paths("input_punta_arenas")

results = run_case_multiple_years(
    years=[2030, 2040, 2050],
    weather_year=2019,
    case_name="punta_arenas",
    enable_year_linking=True,   # each year constrains the next
    enable_hydrogen=True,
    co2_cap_tons={2050: 0},     # net-zero by 2050
    **paths,
)
```

---

## Troubleshooting

### `Objective: inf`

If the output shows `status=ok`, `condition=time_limit` and `objective=inf`, it usually means the solver hit the time limit before finding a feasible MIP solution.

Recommendations:

- Increase `time_limit` (e.g. 1800 or 3600 seconds).
- Relax `mip_gap` (e.g. 0.05 or 0.1).
- Try fewer years or temporarily disable `enable_year_linking`.
- HiGHS may need more time than Gurobi on large MIP instances.

### Specifying bounds manually (without nodes.csv)

```python
result = run_case(
    year=2030,
    case_name="custom",
    cutout_bounds=(-76, -66, -56, -50),  # lon_min, lon_max, lat_min, lat_max
    ...
)
```

---

## Supported solvers

| Solver   | License      | Notes                                    |
|----------|-------------|------------------------------------------|
| **Gurobi** | Commercial  | Recommended; free academic license available |
| **HiGHS**  | Open-source | Automatic fallback if Gurobi unavailable |

Other PyPSA-compatible solvers (CPLEX, GLPK, etc.) can also be used.

---

## References

- [PyPSA Documentation](https://pypsa.org/)
- [Atlite Documentation](https://atlite.readthedocs.io/)
- [ERA5 / CDS](https://cds.climate.copernicus.eu/)
