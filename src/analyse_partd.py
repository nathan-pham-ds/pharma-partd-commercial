"""analyse_partd.py: commercial analysis of Medicare Part D prescribing for type-2 diabetes.

Runs the same SQL whether the input is the real CMS files or the synthetic fixture:
  --source fixture  (default) data/fixture/partd_npi_*_SYNTHETIC.csv   -> outputs are labelled SYNTHETIC
  --source cms                data/raw/partd_npi_*.csv                 -> real CMS data

Produces: class share by year, growth decomposition (new prescribers vs deeper use), state map table,
specialty mix, k-means prescriber segmentation with a recommended action per segment, and a dashboard.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent))
import pharmakit as pk  # noqa: E402

pk.mpl_theme()
CLASS_SQL = """
    CASE
      WHEN lower(Gnrc_Name) LIKE '%gliflozin%' THEN 'SGLT2'
      WHEN lower(Gnrc_Name) LIKE '%glutide%' OR lower(Gnrc_Name) LIKE '%tirzepatide%' THEN 'GLP-1'
      WHEN lower(Gnrc_Name) LIKE '%gliptin%' THEN 'DPP-4'
      WHEN lower(Gnrc_Name) LIKE '%metformin%' THEN 'Metformin'
      ELSE 'Other'
    END"""


def load(con: duckdb.DuckDBPyConnection, pattern: str) -> None:
    files = sorted(glob.glob(pattern))
    if not files:
        raise SystemExit(f"no files matching {pattern}")
    parts = []
    for f in files:
        year = "".join(c for c in Path(f).stem if c.isdigit())[-4:]
        parts.append(f"SELECT *, {year} AS Year FROM read_csv('{f}', header=true, "
                     f"all_varchar=true, ignore_errors=true)")
    con.execute("CREATE OR REPLACE TABLE raw AS " + " UNION ALL BY NAME ".join(parts))
    con.execute(f"""
        CREATE OR REPLACE TABLE rx AS
        SELECT PRSCRBR_NPI AS npi, Prscrbr_State_Abrvtn AS state, Prscrbr_Type AS specialty,
               Brnd_Name AS brand, Gnrc_Name AS generic, {CLASS_SQL} AS drug_class,
               TRY_CAST(Tot_Clms AS BIGINT) AS claims,
               TRY_CAST(Tot_Drug_Cst AS DOUBLE) AS cost,
               TRY_CAST(Tot_Benes AS BIGINT) AS benes, Year AS year
        FROM raw WHERE TRY_CAST(Tot_Clms AS BIGINT) IS NOT NULL""")
    print(f"{len(files)} file(s), {con.execute('SELECT count(*) FROM rx').fetchone()[0]:,} rows")


def main(source: str, out_dir: Path) -> None:
    synthetic = source == "fixture"
    pattern = "data/fixture/partd_npi_*_SYNTHETIC.csv" if synthetic else "data/raw/partd_npi_*.csv"
    tag = "SYNTHETIC FIXTURE - not real CMS data" if synthetic else "CMS Medicare Part D"
    (out_dir / "tables").mkdir(parents=True, exist_ok=True)
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    load(con, pattern)

    # 1) class share by year
    share = con.execute("""
        SELECT year, drug_class, sum(claims) AS claims, sum(cost) AS cost,
               100.0 * sum(claims) / sum(sum(claims)) OVER (PARTITION BY year) AS claims_share_pct,
               100.0 * sum(cost)   / sum(sum(cost))   OVER (PARTITION BY year) AS cost_share_pct
        FROM rx GROUP BY 1, 2 ORDER BY 1, 3 DESC""").df()
    share.to_csv(out_dir / "tables/class_share_by_year.csv", index=False)

    # 2) growth decomposition for the newer classes: more prescribers vs more per prescriber
    decomp = con.execute("""
        WITH y AS (
          SELECT year, drug_class, count(DISTINCT npi) AS prescribers, sum(claims) AS claims
          FROM rx WHERE drug_class IN ('SGLT2','GLP-1') GROUP BY 1,2)
        SELECT drug_class, year, prescribers, claims, claims::DOUBLE / prescribers AS claims_per_prescriber,
               100.0 * (prescribers - first_value(prescribers) OVER w) / first_value(prescribers) OVER w AS prescriber_growth_pct,
               100.0 * (claims::DOUBLE/prescribers - first_value(claims::DOUBLE/prescribers) OVER w)
                     / first_value(claims::DOUBLE/prescribers) OVER w AS depth_growth_pct
        FROM y WINDOW w AS (PARTITION BY drug_class ORDER BY year) ORDER BY drug_class, year""").df()
    decomp.to_csv(out_dir / "tables/growth_decomposition.csv", index=False)

    # 3) geography and specialty
    geo = con.execute("""
        SELECT state, sum(claims) FILTER (WHERE drug_class IN ('SGLT2','GLP-1')) AS new_class_claims,
               sum(claims) AS total_claims,
               100.0 * sum(claims) FILTER (WHERE drug_class IN ('SGLT2','GLP-1')) / sum(claims) AS new_class_share_pct
        FROM rx WHERE year = (SELECT max(year) FROM rx) GROUP BY 1 ORDER BY 4 DESC""").df()
    geo.to_csv(out_dir / "tables/state_new_class_share.csv", index=False)
    spec = con.execute("""
        SELECT specialty, count(DISTINCT npi) AS prescribers, sum(claims) AS claims,
               100.0 * sum(claims) FILTER (WHERE drug_class IN ('SGLT2','GLP-1')) / sum(claims) AS new_class_share_pct,
               sum(claims)::DOUBLE / count(DISTINCT npi) AS claims_per_prescriber
        FROM rx WHERE year = (SELECT max(year) FROM rx) GROUP BY 1 ORDER BY 3 DESC""").df()
    spec.to_csv(out_dir / "tables/specialty_mix.csv", index=False)

    # 4) prescriber segmentation (latest year): volume, new-class share, growth
    feat = con.execute("""
        WITH last2 AS (SELECT max(year) AS y1, max(year) - 1 AS y0 FROM rx),
        agg AS (
          SELECT npi, state, any_value(specialty) AS specialty,
                 sum(claims) FILTER (WHERE year = (SELECT y1 FROM last2)) AS claims_now,
                 sum(claims) FILTER (WHERE year = (SELECT y0 FROM last2)) AS claims_prev,
                 sum(claims) FILTER (WHERE year = (SELECT y1 FROM last2) AND drug_class IN ('SGLT2','GLP-1')) AS new_now
          FROM rx GROUP BY npi, state)
        SELECT npi, state, specialty, claims_now, coalesce(claims_prev, 0) AS claims_prev,
               coalesce(new_now, 0) AS new_now,
               100.0 * coalesce(new_now, 0) / nullif(claims_now, 0) AS new_class_share_pct,
               100.0 * (claims_now - coalesce(claims_prev, 0)) / nullif(claims_prev, 0) AS growth_pct
        FROM agg WHERE claims_now IS NOT NULL AND claims_now > 0""").df()
    feat["growth_pct"] = feat["growth_pct"].fillna(0).clip(-100, 300)
    X = StandardScaler().fit_transform(
        np.column_stack([np.log1p(feat["claims_now"]), feat["new_class_share_pct"].fillna(0), feat["growth_pct"]]))
    k = 4
    feat["segment_id"] = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(X)
    prof = feat.groupby("segment_id").agg(prescribers=("npi", "size"), median_claims=("claims_now", "median"),
                                          median_new_share=("new_class_share_pct", "median"),
                                          median_growth=("growth_pct", "median")).reset_index()
    # name segments from their profile, not from a hard-coded order
    # Name segments from their own profile: split on volume, then on adoption WITHIN each
    # volume tier, so the four names are always distinct and always mean what they say.
    vol_rank = prof["median_claims"].rank(ascending=False, method="first")
    hi_vol = vol_rank <= len(prof) / 2
    hi_new = pd.Series(False, index=prof.index)
    for tier in (True, False):
        idx = prof.index[hi_vol == tier]
        r = prof.loc[idx, "median_new_share"].rank(ascending=False, method="first")
        hi_new.loc[idx] = r <= len(idx) / 2
    names, actions = [], []
    for v, n in zip(hi_vol, hi_new):
        if v and n:
            names.append("High-volume adopters"); actions.append("Protect: peer-to-peer programmes, outcomes data, first for new indications")
        elif v and not n:
            names.append("High-volume traditionalists"); actions.append("Biggest opportunity: targeted detailing on guideline change and CV/renal outcomes")
        elif not v and n:
            names.append("Low-volume adopters"); actions.append("Low cost to serve: digital/email, samples, let them grow their panel")
        else:
            names.append("Low-volume traditionalists"); actions.append("Do not detail in person: newsletter and pharmacy-channel support only")
    prof["segment"] = names
    prof["recommended_action"] = actions
    prof = prof.sort_values("median_claims", ascending=False)
    prof.to_csv(out_dir / "tables/prescriber_segments.csv", index=False)
    feat.merge(prof[["segment_id", "segment"]], on="segment_id").to_csv(
        out_dir / "tables/prescriber_level_segments.csv", index=False)

    # 5) figures
    wide = share.pivot(index="year", columns="drug_class", values="claims_share_pct").fillna(0)
    order = [c for c in ["Metformin", "DPP-4", "SGLT2", "GLP-1", "Other"] if c in wide.columns]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    axes[0].stackplot(wide.index, [wide[c] for c in order], labels=order,
                      colors=[pk.PALETTE["sage"], pk.PALETTE["grey"], pk.PALETTE["teal"], pk.PALETTE["coral"], pk.PALETTE["line"]][:len(order)])
    axes[0].set_title("Share of diabetes claims by class"); axes[0].set_ylabel("% of claims")
    axes[0].set_xticks(list(wide.index)); axes[0].legend(fontsize=8, loc="center left")
    for cls, c in [("SGLT2", pk.PALETTE["teal"]), ("GLP-1", pk.PALETTE["coral"])]:
        d = decomp[decomp["drug_class"] == cls]
        axes[1].plot(d["year"], d["prescriber_growth_pct"], marker="o", color=c, label=f"{cls}: more prescribers")
        axes[1].plot(d["year"], d["depth_growth_pct"], marker="s", ls="--", color=c, label=f"{cls}: more per prescriber")
    axes[1].axhline(0, color=pk.PALETTE["grey"], lw=.8)
    axes[1].set_title("Where the growth comes from"); axes[1].set_ylabel("% change vs first year")
    axes[1].set_xticks(list(wide.index)); axes[1].legend(fontsize=7.5)
    fig.suptitle(tag, fontsize=9, color=pk.PALETTE["coral"] if synthetic else pk.PALETTE["grey"], y=1.02)
    fig.tight_layout(); fig.savefig(out_dir / "figures/share_and_growth.png", bbox_inches="tight"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.8, 4.4))
    m = feat.merge(prof[["segment_id", "segment"]], on="segment_id")
    cols = {s: c for s, c in zip(prof["segment"], [pk.PALETTE["coral"], pk.PALETTE["teal"], pk.PALETTE["amber"], pk.PALETTE["grey"]])}
    for s, g in m.groupby("segment"):
        ax.scatter(g["claims_now"], g["new_class_share_pct"], s=12, alpha=.65, color=cols[s], label=s, edgecolor="none")
    ax.set_xscale("log")
    ax.set_xlabel("Diabetes claims, latest year (log)"); ax.set_ylabel("% of claims in SGLT2 / GLP-1")
    ax.set_title(f"Prescriber segments (k-means, k={k})")
    ax.legend(fontsize=7.5, loc="upper left")
    fig.text(0.01, -0.02, tag, fontsize=8, color=pk.PALETTE["coral"] if synthetic else pk.PALETTE["grey"])
    fig.tight_layout(); fig.savefig(out_dir / "figures/segments.png", bbox_inches="tight"); plt.close(fig)

    key = dict(source=tag, synthetic=synthetic, years=sorted(int(y) for y in share["year"].unique()),
               n_prescribers=int(feat["npi"].nunique()), n_rows=int(con.execute("SELECT count(*) FROM rx").fetchone()[0]),
               share_first=wide.iloc[0].round(1).to_dict(), share_last=wide.iloc[-1].round(1).to_dict(),
               new_class_shift_pts=round(float(wide.iloc[-1].get("SGLT2", 0) + wide.iloc[-1].get("GLP-1", 0)
                                               - wide.iloc[0].get("SGLT2", 0) - wide.iloc[0].get("GLP-1", 0)), 1),
               segments=prof.round(1).to_dict("records"),
               top_states=geo.head(5).round(1).to_dict("records"),
               specialty=spec.round(1).to_dict("records"))
    (out_dir / "key_numbers.json").write_text(json.dumps(key, indent=1, default=float))

    banner = ('<div style="background:#FBDDD3;color:#E4572E;padding:10px 14px;border-radius:8px;'
              'font-weight:600;margin-bottom:16px">SYNTHETIC FIXTURE — the numbers on this page are generated '
              'test data with the CMS schema, not real Medicare prescribing. Run with --source cms for real data.</div>'
              if synthetic else "")
    seg_rows = "".join(f'<tr><td>{r.segment}</td><td class="num">{r.prescribers}</td>'
                       f'<td class="num">{r.median_claims:,.0f}</td><td class="num">{r.median_new_share:.0f}%</td>'
                       f'<td class="num">{r.median_growth:.0f}%</td><td>{r.recommended_action}</td></tr>'
                       for r in prof.itertuples())
    P = pk.PALETTE
    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Part D diabetes commercial dashboard</title>
<style>body{{margin:0;font-family:Inter,'Segoe UI',system-ui,sans-serif;background:{P['bg']};color:{P['ink']}}}
.wrap{{max-width:1040px;margin:0 auto;padding:24px 20px 40px}} h1{{margin:4px 0 2px;font-size:25px}}
.sub{{color:{P['grey']};margin-bottom:16px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:18px}}
.tile{{background:#fff;border:1px solid {P['line']};border-radius:10px;padding:12px 14px}}
.tile .v{{font-size:23px;font-weight:700;color:{P['teal']}}} .tile .l{{font-size:11.5px;color:{P['grey']}}}
.card{{background:#fff;border:1px solid {P['line']};border-radius:10px;padding:16px 18px;margin-bottom:16px}}
h2{{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:{P['teal']};margin:0 0 10px}}
table{{border-collapse:collapse;width:100%;font-size:12.5px}}
th{{background:{P['teal']};color:#fff;text-align:left;padding:7px 9px}} th.num,td.num{{text-align:right}}
td{{border-bottom:1px solid {P['line']};padding:6px 9px}} img{{width:100%;border:1px solid {P['line']};border-radius:8px}}
</style></head><body><div class="wrap">
<h1>Medicare Part D: type-2 diabetes commercial view</h1>
<div class="sub">{tag} · {key['years'][0]}–{key['years'][-1]} · {key['n_prescribers']:,} prescribers</div>
{banner}
<div class="tiles">
 <div class="tile"><div class="v">{key['new_class_shift_pts']:+.1f} pts</div><div class="l">share shift to SGLT2 + GLP-1</div></div>
 <div class="tile"><div class="v">{key['n_prescribers']:,}</div><div class="l">prescribers analysed</div></div>
 <div class="tile"><div class="v">{len(prof)}</div><div class="l">targeting segments</div></div>
 <div class="tile"><div class="v">{key['top_states'][0]['state']}</div><div class="l">highest new-class share ({key['top_states'][0]['new_class_share_pct']:.0f}%)</div></div>
</div>
<div class="card"><h2>Class share and growth</h2><img src="figures/share_and_growth.png" alt="share and growth"></div>
<div class="card"><h2>Prescriber segments and recommended actions</h2>
<table><thead><tr><th>Segment</th><th class="num">Prescribers</th><th class="num">Median claims</th>
<th class="num">New-class share</th><th class="num">Growth</th><th>Recommended action</th></tr></thead>
<tbody>{seg_rows}</tbody></table></div>
<div class="card"><h2>Segment map</h2><img src="figures/segments.png" alt="segments"></div>
</div></body></html>"""
    (out_dir / "dashboard.html").write_text(html, encoding="utf-8")
    print(share.to_string(index=False)); print(); print(prof.to_string(index=False)); print(); print(geo.head().to_string(index=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["fixture", "cms"], default="fixture")
    ap.add_argument("--out", default="outputs")
    a = ap.parse_args()
    main(a.source, Path(a.out))
