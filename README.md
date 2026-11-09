# pharma-partd-commercial

A commercial-analytics pipeline for US Medicare Part D prescribing in type-2 diabetes: class share and trend, growth decomposition, geography, specialty mix, k-means prescriber segmentation with a recommended action per segment, and a dashboard.

> ⚠️ **The outputs committed here were produced from a SYNTHETIC FIXTURE, not real CMS data.** The machine this was built on could not reach `data.cms.gov` (the host refuses the connection), so the pipeline was validated on a generated file that copies the CMS schema exactly — same column names, same dtypes, same suppression rules. Every figure and the dashboard carry a visible "SYNTHETIC FIXTURE" banner. One command switches to real data; see below. Nothing in this repo should be quoted as a real Medicare finding.

> Path: Commercial analytics (the most entry-level-friendly lane) · SQL (DuckDB) + Python + dashboard

## Run it on real CMS data

```bash
pip install -r requirements.txt
python src/fetch_cms.py --level geo --years 2019 2020 2021 2022 2023   # small files, state level
# or, for prescriber-level segmentation (several GB per year):
python src/fetch_cms.py --level npi --years 2023
python src/analyse_partd.py --source cms                               # real data, no banner
```
`fetch_cms.py` reads the CMS `data.json` catalogue and picks the newest release of each data year, so it keeps working when CMS republishes. Source: [Medicare Part D Prescribers](https://data.cms.gov/provider-summary-by-type-of-service/medicare-part-d-prescribers).

## Run it on the fixture (what is committed)

```bash
python src/make_fixture.py        # writes data/fixture/partd_npi_<year>_SYNTHETIC.csv
python -m pytest -q               # 4 tests: class mapping, share SQL, suppression rules
python src/analyse_partd.py       # tables, figures, dashboard (labelled SYNTHETIC)
```

## What the pipeline computes

| Output | What it answers |
|---|---|
| `class_share_by_year.csv` | How claims and spend split across metformin / DPP-4 / SGLT2 / GLP-1, year by year |
| `growth_decomposition.csv` | Is a class growing because **more prescribers** write it, or because the same prescribers write **more of it**? These need different commercial responses |
| `state_new_class_share.csv` | Where the newer classes are adopted fastest (targeting and field-force sizing) |
| `specialty_mix.csv` | Who prescribes: endocrinology vs primary care vs NP/PA |
| `prescriber_segments.csv` | 4 k-means segments on volume, new-class share and growth, each with a recommended action |
| `dashboard.html` | Self-contained page: KPI tiles, charts, segment table |

Drug classes are derived from the generic name by stem (`-gliflozin` → SGLT2, `-glutide` → GLP-1, `-gliptin` → DPP-4), which is robust to new molecules entering the file.

### Segment logic

Segments are named from their own profile rather than from the cluster number: segments are split into high/low volume, then into adopters/traditionalists **within** each volume tier, so the four names are always distinct and always mean what they say. The commercially interesting one is **high-volume traditionalists** — large diabetes panels with little SGLT2/GLP-1 use. That is where detailing on cardiovascular and renal outcomes has the most to work with.

## Why this project

The medical-rep role at Orient Pharma was HCP targeting done by hand: which doctors to visit, with which message. This is the same job done with data — and Part D is the largest public prescriber-level dataset in the world, so the SQL and the segmentation logic transfer directly to IQVIA Xponent/LAAD work in an MNC commercial team.

## Limitations

1. **The committed numbers are synthetic.** They are only there to prove the pipeline runs end to end.
2. Real Part D covers Medicare only (65+ and disabled), so it is not the whole US market.
3. CMS suppresses prescriber–drug rows under 11 claims; low-volume prescribers are therefore under-counted. The fixture reproduces this so the code handles it.
4. Claims are not patients: one patient can produce many claims.
5. Segmentation uses three features. A production version would add payer mix, panel size from the companion "by Provider" file, and Open Payments data.

## CV bullets

> Replace the bracketed numbers after you run it on the real CMS files.

- EN: Built a Medicare Part D commercial-analytics pipeline in SQL (DuckDB) and Python — class share, growth decomposition, geography and specialty mix — with a tested schema-identical fixture so the whole pipeline runs without the multi-GB download.
- EN: Segmented prescribers into 4 targeting groups (k-means on volume, new-class share and growth) and produced a dashboard with a recommended commercial action per segment.
- VI: Xây dựng quy trình phân tích thương mại trên dữ liệu Medicare Part D bằng SQL (DuckDB) và Python: thị phần theo nhóm thuốc, phân tách nguồn tăng trưởng, phân bố theo bang và chuyên khoa, kèm bộ dữ liệu mô phỏng đúng cấu trúc để chạy thử toàn bộ quy trình.
- VI: Phân khúc bác sĩ kê đơn thành 4 nhóm mục tiêu (k-means theo sản lượng, tỷ trọng nhóm thuốc mới và tốc độ tăng trưởng) và xây dựng dashboard kèm đề xuất hành động cho từng nhóm.
