"""Tests for the Part D pipeline: class mapping and share SQL on a tiny table with known answers.
Run: python -m pytest -q
"""
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from analyse_partd import CLASS_SQL  # noqa: E402

ROWS = pd.DataFrame([
    # generic name, claims, year  -> expected class
    ("Dapagliflozin", 100, 2022), ("Empagliflozin", 100, 2022),   # SGLT2 200
    ("Semaglutide", 50, 2022), ("Dulaglutide", 50, 2022),          # GLP-1 100
    ("Sitagliptin", 100, 2022),                                    # DPP-4 100
    ("Metformin Hcl", 600, 2022),                                  # Metformin 600
    ("Insulin Glargine", 100, 2022),                               # Other 100
], columns=["Gnrc_Name", "claims", "year"])


def _con():
    con = duckdb.connect()
    con.register("t", ROWS)
    con.execute(f"CREATE TABLE rx AS SELECT {CLASS_SQL} AS drug_class, claims, year FROM t")
    return con


def test_class_mapping():
    got = _con().execute("SELECT drug_class, sum(claims) c FROM rx GROUP BY 1 ORDER BY 1").df()
    assert dict(zip(got.drug_class, got.c)) == {"DPP-4": 100, "GLP-1": 100, "Metformin": 600,
                                                "Other": 100, "SGLT2": 200}


def test_shares_sum_to_100():
    q = """SELECT drug_class,
                  100.0 * sum(claims) / sum(sum(claims)) OVER (PARTITION BY year) AS share
           FROM rx GROUP BY year, drug_class"""
    got = _con().execute(q).df()
    assert abs(got["share"].sum() - 100) < 1e-9
    # SGLT2 = 200 / 1100
    assert abs(got.set_index("drug_class").loc["SGLT2", "share"] - 200 / 1100 * 100) < 1e-9


def test_new_class_share():
    q = """SELECT 100.0 * sum(claims) FILTER (WHERE drug_class IN ('SGLT2','GLP-1')) / sum(claims) FROM rx"""
    assert abs(_con().execute(q).fetchone()[0] - 300 / 1100 * 100) < 1e-9


def test_fixture_respects_cms_suppression():
    """CMS does not publish rows under 11 claims and blanks beneficiary counts under 11."""
    files = sorted((Path(__file__).resolve().parents[1] / "data/fixture").glob("*.csv"))
    if not files:
        return
    df = pd.read_csv(files[-1])
    assert df["Tot_Clms"].min() >= 11
    assert df.loc[df["Tot_Benes"].notna(), "Tot_Benes"].min() >= 11
