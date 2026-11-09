"""make_fixture.py: build a SYNTHETIC Part D file with the exact CMS schema.

Why: the analysis and the dashboard must be testable without a multi-GB download, and the repo
must stay small. The fixture reproduces the CMS column names, dtypes, suppression rule (counts
below 11 are blanked) and a plausible class-switch pattern, so every SQL query and every chart
in this repo runs end to end. The numbers are NOT real and every output built from them is
labelled "SYNTHETIC FIXTURE".

Usage: python src/make_fixture.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RNG = np.random.default_rng(20261110)
YEARS = [2019, 2020, 2021, 2022, 2023]
# CMS column names from the "by Provider and Drug" data dictionary
COLUMNS = ["PRSCRBR_NPI", "Prscrbr_Last_Org_Name", "Prscrbr_First_Name", "Prscrbr_City", "Prscrbr_State_Abrvtn",
           "Prscrbr_Type", "Brnd_Name", "Gnrc_Name", "Tot_Clms", "Tot_30day_Fills", "Tot_Day_Suply",
           "Tot_Drug_Cst", "Tot_Benes", "GE65_Sprsn_Flag", "GE65_Tot_Clms", "Year"]
DRUGS = [  # brand, generic, class, launch-era weight
    ("JANUVIA", "Sitagliptin", "DPP-4", 0.55), ("TRADJENTA", "Linagliptin", "DPP-4", 0.3),
    ("FARXIGA", "Dapagliflozin", "SGLT2", 0.35), ("JARDIANCE", "Empagliflozin", "SGLT2", 0.42),
    ("INVOKANA", "Canagliflozin", "SGLT2", 0.12),
    ("OZEMPIC", "Semaglutide", "GLP-1", 0.38), ("TRULICITY", "Dulaglutide", "GLP-1", 0.26),
    ("GLUCOPHAGE", "Metformin Hcl", "Metformin", 4.5),
]
SPECIALTIES = [("Internal Medicine", .34), ("Family Practice", .30), ("Nurse Practitioner", .14),
               ("Endocrinology", .07), ("Physician Assistant", .09), ("Cardiology", .06)]
STATES = ["CA", "TX", "FL", "NY", "PA", "IL", "OH", "GA", "NC", "MI", "NJ", "VA", "WA", "AZ", "MA"]
N_PRESCRIBERS = 1200


def class_growth(cls: str, year: int) -> float:
    """Simple adoption curves: SGLT2/GLP-1 grow, DPP-4 flat, metformin slowly down."""
    t = year - 2019
    return {"SGLT2": 1.0 + 0.42 * t, "GLP-1": 1.0 + 0.55 * t, "DPP-4": 1.0 - 0.04 * t,
            "Metformin": 1.0 - 0.03 * t}[cls]


def main() -> None:
    spec_names = [s for s, _ in SPECIALTIES]
    spec_p = np.array([p for _, p in SPECIALTIES]); spec_p = spec_p / spec_p.sum()
    npi = 1_000_000_000 + RNG.permutation(10_000_000)[:N_PRESCRIBERS] * 97  # unique 10-digit ids
    spec = RNG.choice(spec_names, N_PRESCRIBERS, p=spec_p)
    state = RNG.choice(STATES, N_PRESCRIBERS)
    size = RNG.lognormal(3.2, 0.9, N_PRESCRIBERS)              # practice volume
    adopter = RNG.beta(1.6, 4.0, N_PRESCRIBERS)                # willingness to use newer classes
    adopter = np.clip(adopter + (spec == "Endocrinology") * 0.35, 0, 1)

    rows = []
    for year in YEARS:
        for i in range(N_PRESCRIBERS):
            for brand, gen, cls, w in DRUGS:
                pref = w * class_growth(cls, year)
                if cls in ("SGLT2", "GLP-1"):
                    pref *= 0.25 + 1.6 * adopter[i]
                lam = size[i] * pref * 0.55
                clms = RNG.poisson(lam)
                if clms == 0:
                    continue
                fills = int(clms * RNG.uniform(1.0, 1.35))
                supply = int(fills * 30 * RNG.uniform(0.95, 1.05))
                unit = {"SGLT2": 17.5, "GLP-1": 31.0, "DPP-4": 16.0, "Metformin": 0.25}[cls]
                cost = round(supply * unit * RNG.uniform(0.85, 1.15), 2)
                benes = max(1, int(clms / RNG.uniform(2.0, 6.0)))
                rows.append([npi[i], f"PROVIDER{i:04d}", f"F{i:04d}", "CITY", state[i], spec[i],
                             brand, gen, clms, fills, supply, cost, benes, "", "", year])
    df = pd.DataFrame(rows, columns=COLUMNS)
    # CMS suppression: beneficiary counts 1-10 are blanked; claims below 11 are not published at all
    df = df[df["Tot_Clms"] >= 11].copy()
    df.loc[df["Tot_Benes"] < 11, "Tot_Benes"] = pd.NA
    df["GE65_Sprsn_Flag"] = np.where(df["Tot_Benes"].isna(), "*", "")
    out = Path("data/fixture"); out.mkdir(parents=True, exist_ok=True)
    for year, g in df.groupby("Year"):
        g.drop(columns="Year").to_csv(out / f"partd_npi_{year}_SYNTHETIC.csv", index=False)
    print(df.groupby(["Year"]).agg(rows=("Tot_Clms", "size"), claims=("Tot_Clms", "sum")).to_string())
    print(f"\nWrote {len(df):,} synthetic rows to {out}/ (schema-identical to CMS, values are not real)")


if __name__ == "__main__":
    main()
