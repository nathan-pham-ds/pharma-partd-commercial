"""fetch_cms.py: download the CMS Medicare Part D Prescribers files you need.

Two CMS datasets are used:
  * "by Provider and Drug"   - one row per prescriber x drug x year (NPI level). Large (GBs/year).
  * "by Geography and Drug"  - the same totals rolled up to state/national. Small, good for trends.

CMS serves them from data.cms.gov. The distribution URLs change with each release year, so this
script reads the data.json catalogue and picks the newest distribution for each data year.

Usage:
  python src/fetch_cms.py --level geo   --years 2019 2020 2021 2022 2023
  python src/fetch_cms.py --level npi   --years 2023            # big download
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import requests

CATALOG = "https://data.cms.gov/data.json"
TITLES = {"geo": "Medicare Part D Prescribers - by Geography and Drug",
          "npi": "Medicare Part D Prescribers - by Provider and Drug"}


def distributions(level: str) -> dict[int, str]:
    j = requests.get(CATALOG, timeout=120).json()
    out: dict[int, tuple[str, str]] = {}
    for ds in j["dataset"]:
        if ds.get("title") != TITLES[level]:
            continue
        for d in ds.get("distribution", []):
            url = d.get("downloadURL", "")
            if d.get("mediaType") != "text/csv" or not url.endswith(".csv"):
                continue
            m = re.search(r"_DY(\d\d)_", url)          # data year
            ry = re.search(r"_RY(\d\d)_", url)          # release year
            if not m:
                continue
            year, rel = 2000 + int(m.group(1)), int(ry.group(1)) if ry else 0
            if year not in out or rel > out[year][0]:
                out[year] = (rel, url)
    return {y: u for y, (_, u) in sorted(out.items())}


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"skip {dest.name} (exists)")
        return
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk); done += len(chunk)
                if total:
                    print(f"\r{dest.name}: {done / total:6.1%}", end="")
    print(f"\r{dest.name}: done ({done / 1e6:.0f} MB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", choices=["geo", "npi"], default="geo")
    ap.add_argument("--years", nargs="+", type=int, default=[2019, 2020, 2021, 2022, 2023])
    a = ap.parse_args()
    dist = distributions(a.level)
    print("available years:", ", ".join(map(str, dist)))
    for y in a.years:
        if y in dist:
            download(dist[y], Path(f"data/raw/partd_{a.level}_{y}.csv"))
        else:
            print(f"{y}: not published")
