# frozen-forecast-datasets

Frozen, reproducible snapshots of Sooth's panel forecast data, published as **references to the live Bigtable rows** plus the exact recipe that produced them. Each snapshot is a dated directory; the row-key lists and question metadata are committed, and `scripts/hydrate.py` pulls the full rows (probabilities, PMFs, cost, explanations) from Bigtable for anyone with reader access.

| Snapshot | Scope | Questions | Forecast rows |
|---|---|---|---|
| [`2026-09-11-external-lanes/`](2026-09-11-external-lanes/) | Kalshi + Polymarket + Sooth_QGen + QGen Calendar × external models only (no Sooth-internal lanes, no QGen questions about venue prices); resolved + leakage-cleaned | 27,430 | 590,932 |

## Access

Each snapshot also commits the hydrated **values** (probability / PMF, cost, tokens, latency per forecast row) as parquet under `data/values/`, so scoring work needs no Bigtable access at all. The row keys and question metadata are likewise usable on their own (question text, categories, dates, resolutions, which model forecast what when). The forecasts themselves live in Bigtable:

- project `data-ingestion-v1`, instance `sooth-events-database`, tables `forecast_reports_v2` (forecasts) and `forecast_questions_v2` (questions)
- you need `roles/bigtable.reader` on that instance and Application Default Credentials (`gcloud auth application-default login`)

```bash
pip install -r 2026-09-11-external-lanes/scripts/requirements.txt
cd 2026-09-11-external-lanes/scripts
python hydrate.py --rows ../data/forecast_rows_all.tsv.gz --out forecasts_all.parquet            # values for the uncleaned/open set too, ~4 min
python hydrate.py --rows ../data/forecast_rows_clean.tsv.gz --out sample.parquet --limit 5000 --content   # with explanations
```

## Verifying a checkout

```bash
python 2026-09-11-external-lanes/scripts/verify.py   # checksums + no excluded question present → OK
```

## Adding a snapshot

Copy the previous snapshot's `scripts/`, change the definition in its `lanes.py` / `count.py`, run `dump_all_rows.py` → `fetch_meta_all.py` → `count.py`, and commit the resulting `data/` with a `README.md` data card and `MANIFEST.json` (sha256 of every data file). Never edit a published snapshot's data files; add a new dated directory instead.

Internal to Sooth Labs. Kalshi and Polymarket question text and prices are venue data; do not redistribute outside the company without checking their terms.
