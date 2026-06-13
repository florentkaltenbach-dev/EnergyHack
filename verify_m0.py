"""M0 verification: one inverter, one day, P_AC from DuckDB."""
import sys
sys.path.insert(0, ".")
from db.db import run_query
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

INV = "INV 01.01.001"
DAY = "2019-07-15"

df = run_query(f"""
    SELECT fp.ts, fp.p_ac_kw, pl.irradiation_wm2
    FROM fact_power fp
    JOIN fact_plant pl ON pl.ts = fp.ts
    WHERE fp.inverter_id = '{INV}'
      AND fp.ts::DATE = '{DAY}'
    ORDER BY fp.ts
""")

print(f"{INV} on {DAY}: {len(df)} rows, max={df.p_ac_kw.max():.1f} kW")

fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(df.ts, df.p_ac_kw, label="P_AC (kW)")
ax.set_title(f"{INV} — {DAY}")
ax.set_ylabel("kW")
ax.legend()
fig.tight_layout()
fig.savefig("m0_check.png", dpi=100)
print("Plot saved: m0_check.png")
