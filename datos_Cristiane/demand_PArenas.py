import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path


def remove_isolated_spikes(
    series: pd.Series,
    ratio_threshold: float = 8.0,
    abs_min_threshold: float = 100.0,
) -> tuple[pd.Series, list[pd.Timestamp]]:
    """Replace isolated one-hour spikes using neighbor median.

    This targets artefacts such as aggregated period totals (e.g., semestral totals)
    accidentally appearing as a single hourly value.
    """
    s = pd.to_numeric(series, errors="coerce").copy()
    flagged_idx: list[pd.Timestamp] = []

    if len(s) < 3:
        return s, flagged_idx

    for i in range(1, len(s) - 1):
        prev_v = s.iloc[i - 1]
        cur_v = s.iloc[i]
        next_v = s.iloc[i + 1]

        if pd.isna(prev_v) or pd.isna(cur_v) or pd.isna(next_v):
            continue

        neighborhood_med = float(np.median([prev_v, next_v]))
        local_floor = max(abs_min_threshold, ratio_threshold * max(neighborhood_med, 1e-9))

        if cur_v > local_floor:
            s.iloc[i] = neighborhood_med
            flagged_idx.append(s.index[i])

    return s, flagged_idx

output_dir = Path(__file__).parent

# %% Read raw data from Excel
filepath = output_dir / "Energia-Potencia 2024.xlsx"
df = pd.read_excel(filepath, sheet_name="Energia 2024", header=0)

# %% Clean rows: keep only rows where first column is a valid datetime
first_col = df.columns[0]
df[first_col] = pd.to_datetime(df[first_col], errors="coerce")
df = df.dropna(subset=[first_col]).reset_index(drop=True)

# %% Clean columns: drop all-NaN and unnamed spacer columns
df = df.dropna(axis=1, how="all")
df = df.loc[:, ~df.columns.str.startswith("Unnamed")]

# %% Keep only datetime + .1 columns (energy per interval, not meter readings)
df = df.rename(columns={first_col: "datetime"})
cols_dot1 = [c for c in df.columns if c.endswith(".1")]
df = df[["datetime"] + cols_dot1].copy()
df.columns = [c.removesuffix(".1") for c in df.columns]

# %% Convert feeder columns to numeric
feeder_cols = [c for c in df.columns if c != "datetime"]
for col in feeder_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# %% Export 15-min data
df.to_csv(output_dir / "demand_15min.csv", index=False)
print("15-min data:", df.shape)

# %% Resample to hourly (sum of 4 x 15-min intervals) and add total column
df_h = df.set_index("datetime").resample("1h").sum()
df_h["Total"] = df_h.sum(axis=1)
df_h = df_h.reset_index()

# %% Export hourly data
df_h.to_csv(output_dir / "demand_hourly.csv", index=False)
print("Hourly data:", df_h.shape)

# %% Remove isolated spikes in total demand (e.g., semestral totals loaded as one hour)
df_h = df_h.sort_values("datetime").reset_index(drop=True)
total_clean, flagged_timestamps = remove_isolated_spikes(df_h.set_index("datetime")["Total"])
df_h["Total"] = total_clean.values

if flagged_timestamps:
    print(f"Removed {len(flagged_timestamps)} isolated spike(s) in hourly Total demand:")
    for ts in flagged_timestamps:
        print(f"  - {ts}")
else:
    print("No isolated spikes found in hourly Total demand.")

# %% ==================== PLOTS ====================
months_es = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
             7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"}

df_h["month"] = df_h["datetime"].dt.month
df_h["hour"] = df_h["datetime"].dt.hour

fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle("Demanda Eléctrica Punta Arenas 2024", fontsize=14, fontweight="bold")

# --- (a) Curva de demanda horaria promedio por mes ---
ax = axes[0, 0]
for m in sorted(df_h["month"].unique()):
    subset = df_h[df_h["month"] == m]
    hourly_avg = subset.groupby("hour")["Total"].mean()
    ax.plot(hourly_avg.index, hourly_avg.values, label=months_es.get(m, m))
ax.set_xlabel("Hora del día [h]")
ax.set_ylabel("Energía [kWh/h]")
ax.set_title("(a) Curva horaria promedio por mes")
ax.set_xlim(0, 23)
ax.set_xticks(range(0, 24, 3))
ax.legend(fontsize=7, ncol=3)
ax.grid(True, alpha=0.3)

# --- (b) Demanda total diaria a lo largo del año ---
ax = axes[0, 1]
daily = df_h.set_index("datetime")["Total"].resample("1D").sum()
ax.plot(daily.index, daily.values, linewidth=0.8)
ax.set_xlabel("Fecha [2024]")
ax.set_ylabel("Energía diaria [kWh/día]")
ax.set_title("(b) Demanda total diaria")
ax.grid(True, alpha=0.3)

# --- (c) Demanda mensual por alimentador (stacked bar) ---
ax = axes[1, 0]
monthly_by_feeder = df_h.groupby("month")[feeder_cols].sum()
monthly_by_feeder.index = [months_es.get(m, m) for m in monthly_by_feeder.index]
monthly_by_feeder.plot(kind="bar", stacked=True, ax=ax, legend=False, width=0.8)
ax.set_xlabel("Mes [2024]")
ax.set_ylabel("Energía mensual [kWh/mes]")
ax.set_title("(c) Demanda mensual por alimentador")
ax.legend(fontsize=5, ncol=3, loc="upper right")
ax.tick_params(axis="x", rotation=45)
ax.grid(True, alpha=0.3, axis="y")

# --- (d) Boxplot de demanda horaria total por mes ---
ax = axes[1, 1]
data_box = [df_h[df_h["month"] == m]["Total"].values for m in sorted(df_h["month"].unique())]
labels_box = [months_es.get(m, m) for m in sorted(df_h["month"].unique())]
ax.boxplot(data_box, labels=labels_box, showfliers=False)
ax.set_xlabel("Mes [2024]")
ax.set_ylabel("Energía horaria [kWh/h]")
ax.set_title("(d) Distribución demanda horaria por mes")
ax.tick_params(axis="x", rotation=45)
ax.grid(True, alpha=0.3, axis="y")

plt.tight_layout()
plt.savefig(output_dir / "demand_analysis.png", dpi=150)
plt.show()
print("Gráfico guardado: demand_analysis.png")

# %% ==================== EXPORT demand_profiles.csv ====================
# Format required by build_demand.py: timestamp, zone, demand_type, demand_mw
# Convert kWh/h -> MW (÷1000), assign to zone punta_arenas_1
# Replicate for years 2025, 2030, 2040, 2050 (same demand profile)

df_base = df_h[["datetime", "Total"]].copy()
df_base["demand_mw"] = df_base["Total"] / 1000  # kWh/h -> MW
df_base = df_base.drop_duplicates(subset=["datetime"], keep="first")

# Source is 2024 (leap year, 8784h). For non-leap years (8760h), drop Feb 29.
target_years = [2025, 2030, 2040, 2050]
frames = []

for year in target_years:
    df_year = df_base[["datetime", "demand_mw"]].copy()
    # Replace year in timestamps
    df_year["timestamp"] = df_year["datetime"].apply(
        lambda dt: dt.replace(year=year) if not (dt.month == 2 and dt.day == 29) else None
    )
    # Drop Feb 29 rows for non-leap years
    df_year = df_year.dropna(subset=["timestamp"])
    df_year["zone"] = "punta_arenas_1"
    df_year["demand_type"] = "electricity"
    frames.append(df_year[["timestamp", "zone", "demand_type", "demand_mw"]])

    n_hours = len(pd.date_range(f"{year}-01-01", f"{year}-12-31 23:00", freq="1h"))
    print(f"  {year}: {len(df_year)} hours (expected {n_hours})")

df_profile = pd.concat(frames, ignore_index=True)
df_profile["timestamp"] = pd.to_datetime(df_profile["timestamp"]).dt.strftime("%Y-%m-%d %H:%M")

output_path = output_dir / "demand_profiles.csv"
df_profile.to_csv(output_path, index=False)
print(f"demand_profiles.csv exportado: {output_path}")
print(f"  Filas totales: {len(df_profile)}, Media: {df_profile['demand_mw'].astype(float).mean():.2f} MW")
