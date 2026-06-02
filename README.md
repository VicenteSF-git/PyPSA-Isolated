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

`build_demand_scenarios.py` genera perfiles de demanda futuros a partir de un año base. Produce un archivo `demand_profiles_{scenario}.csv` por escenario (con todos los años juntos), que `run_case` carga automáticamente filtrando por rango de timestamps.

### Flujo de trabajo

**1. Configurar** `input_punta_arenas/config_demand_scenarios.csv`

**2. Ejecutar:**
```bash
python build_demand_scenarios.py \
  --input-case input_punta_arenas \
  --base-demand-csv input_punta_arenas/demand_profiles.csv \
  --config-csv input_punta_arenas/config_demand_scenarios.csv \
  --base-year 2025 \
  --years 2030 2040 2050
```

**3. Archivos generados en `input_punta_arenas/`:**

| Archivo | Contenido |
|---|---|
| `demand_profiles_{scenario}.csv` | Perfil agregado (timestamp, zone, demand_type, demand_mw) |
| `demand_components_{scenario}.csv` | Desglose por componente |
| `demand_scenario_summary.csv` | Resumen anual por componente (energía, max, min, mean) |

**4. Usar en el modelo:**
```python
paths = get_case_paths("input_punta_arenas")
result = run_case(year=2030, case_name="punta_arenas",
                  csv_demand="input_punta_arenas/demand_profiles_reference.csv",
                  **paths)
```

---

### `config_demand_scenarios.csv` — columnas

| Columna | Descripción |
|---|---|
| `scenario` | Nombre del escenario (e.g. `reference`, `high_growth`) |
| `year` | Año objetivo (e.g. 2030, 2040, 2050) |
| `zone` | Zona del nodo (debe existir en `nodes.csv`) |
| `component` | Ver componentes más abajo |
| `enabled` | `True`/`False` — omite la fila si es False |
| `growth_factor` | Factor multiplicador sobre el perfil base (solo `base_load`) |
| `annual_energy_mwh` | Energía anual total a distribuir (MWh) |
| `unit_count` | Cantidad de unidades (alternativa a `annual_energy_mwh`) |
| `energy_per_unit_kwh_per_year` | Energía por unidad (kWh/año) |
| `profile_type` | Forma horaria a usar (ver más abajo) |
| `demand_type` | Tipo de demanda (`electricity`, `heat`, etc.) |

La energía anual se puede definir de dos formas (se usa la primera disponible):
- **Directa:** `annual_energy_mwh`
- **Por actividad:** `unit_count × energy_per_unit_kwh_per_year / 1000`

---

### Componentes soportados

| `component` | Descripción |
|---|---|
| `base_load` | Perfil histórico 2025 escalado por `growth_factor` |
| `ev` | Carga de vehículos eléctricos |
| `heating` | Calefacción eléctrica |
| `cooking` | Cocina eléctrica |
| `process_electrification` | Electrificación industrial |
| `ptx_export` | Demanda de exportación (PtX) |

---

### Perfiles horarios por defecto

Cuando `profile_type` coincide con el nombre del componente, se usa un perfil sintético definido en el código. Todos se normalizan para que su suma anual sea 1 antes de distribuir la energía.

#### `base_load`
Usa directamente la curva real del año base (`demand_profiles.csv`) mapeada al año objetivo. La transición entre año no-bisiesto y bisiesto replica las 24h del 28 de febrero en el 29 de febrero.

#### `ev` — vehículos eléctricos
- Pico nocturno centrado en **20:00** (σ = 2.5h), que simula recarga al llegar a casa
- Base mínima del 25% del pico en el resto del día
- **+10% los fines de semana** (mayor permanencia en el hogar)
- Fórmula: `0.25 + 1.75 · exp(−0.5·((h−20)/2.5)²) × factor_fin_de_semana`

#### `heating` — calefacción eléctrica
- **Factor estacional** (hemisferio sur):
  - Invierno (mayo–septiembre): ×1.8
  - Verano (octubre–abril): ×0.6
- Dos peaks diarios: **mañana ~7:00** (σ = 3.0h, amplitud 0.45) y **noche ~20:00** (σ = 3.5h, amplitud 0.35)
- Base constante de 0.55
- Fórmula: `factor_estacional × (0.55 + 0.45·exp(−((h−7)/3)²/2) + 0.35·exp(−((h−20)/3.5)²/2))`

#### `cooking` — cocina eléctrica
- Tres peaks diarios:
  - **Desayuno ~8:00** (σ = 1.5h, amplitud 0.8)
  - **Almuerzo ~13:00** (σ = 1.5h, amplitud 0.7)
  - **Cena ~20:00** (σ = 1.8h, amplitud 1.2) — el más alto
- Base mínima de 0.10
- Sin variación estacional ni de día de semana

#### `process_electrification` — industria
- **Horario laboral (7:00–19:00):** factor 1.0 (`0.45 + 0.55 = 1.0`)
- **Fuera de horario:** factor 0.45
- **Fines de semana:** ×0.7 sobre todos los valores
- Simula procesos industriales con operación reducida nocturna y en fines de semana

#### `ptx_export` — exportación (PtX / H₂)
- Perfil completamente plano (equivalente a `constant`)
- Distribuye la energía anual uniformemente en todas las horas

#### `constant`
- Perfil plano. Útil para cargas que operan 24/7 sin variación (e.g. plantas de hidrógeno continuas).

---

### Perfiles personalizados (opcional)

Para reemplazar cualquier perfil sintético con datos reales, crea un CSV con una columna por perfil y pásalo con `--profiles-csv`:

```
timestamp,ev,heating
2025-01-01 00:00,0.12,0.30
2025-01-01 01:00,0.09,0.28
...
```

El nombre de la columna debe coincidir con el `profile_type` en el config. El script normaliza automáticamente cada perfil antes de usarlo.

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
