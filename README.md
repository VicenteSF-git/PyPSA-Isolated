# PyPSA-Isolated

Generic power system optimization framework built on [PyPSA](https://pypsa.org/), designed for isolated or weakly interconnected regions. Includes electricity, heat, battery storage, hydrogen (electrolyzer, fuel cell, H2 turbine), and underground hydrogen storage (UHS).

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
conda create -n pypsa-isolated python=3.11 -y
conda activate pypsa-isolated
```

### 3. Install dependencies

```bash
conda install -c conda-forge pypsa atlite numpy pandas xarray matplotlib folium jupyter -y
pip install highspy
```

If you have a Gurobi license, also install:

```bash
conda install -c gurobi gurobi -y
```

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

## Project structure

```
PyPSA-Isolated/
├── config.py                      # Core API (run_case, run_case_multiple_years, etc.)
├── build_demand.py                # Demand profile construction
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
