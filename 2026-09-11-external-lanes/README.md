# 2026-09-11 · external-model forecasts on Kalshi, Polymarket, Sooth_QGen and QGen Calendar questions

Snapshot of `forecast_reports_v2` / `forecast_questions_v2` taken **2026-09-11 ~19:05 UTC** (revision 2, 2026-09-12: market-derivative QGen questions removed, see step 8). Extends the 2026-09-10 venue-only freeze (monorepo `docs/agent/2026-09-10-venue-forecast-dataset/`) to the two Sooth-generated question spaces, with the same lane rule and the same two leakage filters.

## Definition

1. **Question spaces**: keys starting `Kalshi#`, `Polymarket#`, `Sooth_QGen#` (+ `Sooth_QGen_v2#`, `qgen#`), `Sooth_QGen_Calendar#` (+ `_v2`). `User#` questions excluded.
2. **Forecast rows**: `forecast_reports_v2` row keys `panel_<lane>#<fire_ts>#<question_key>`, `fire_ts` = `YYYYMMDD_HHMMSS` UTC. One row = one model × one question × one panel pass.
3. **Lanes: external models only.** Every roster lane with no `type:` (a single external LLM on the standard panel prompt, incl. retired models, `_w2` wave-2 deliberation twins, `_noweb` ablations, `gpt_5_5_min`, and the horizon/category-tagged `_t<N>_<cat>` twins, which fold onto their base lane) plus the two `cli_harness` lanes `claude_code` and `codex`. **Excluded as Sooth-internal**: `panel_sooth_*` (forecast engines, Snap, Tendril, Mirabilis, deep/DS harnesses, continual blenders, big router, reinforcer), `rp_ensemble*`, `openharness`, `v11_*`, `v21_*`, `reflector_*`, `ormolu*`, `meta*`, `dromedary_imitation_1`. Rule: `scripts/lanes.py`; per-lane detail: `data/lanes.json`.
4. **Resolved** = question meta `Status == resolved`, or a recorded `Resolution`, or present in `gs://sooth-panel/pool_v2_resolved.jsonl` at snapshot time.
5. **Clean step 1**: drop every question whose resolve timestamp (`Resolve Date` → `Sooth_Resolved_At` → pool `resolved_at`) precedes our first forecast on it.
6. **Clean step 2**: drop every row fired at or after the question's `End Date` or its resolve timestamp.
7. **Multi-outcome** = question meta `Outcome Kind` present (`categorical` or `numeric`). Calendar multiway questions use plain keys, not `#f_`; the key prefix alone undercounts them.
8. **Removed (rev 2)**: 5,518 QGen questions whose text names Kalshi or Polymarket — all of the form *"Will the Kalshi YES mid-market price for X land in the 80–90¢ bucket at game start"* / *"… YES price be ≥ 20¢ at …"*. They forecast a venue price, not a world event. Keys + text in `data/excluded_market_derivative_questions.tsv`; `count.py` reads that file. 71,456 external-lane rows went with them.

## Counts

| Set | Questions | Forecast rows | Fires | Base models (lane keys) |
|---|---|---|---|---|
| **Resolved + cleaned** (`forecast_rows_clean.tsv.gz`) | **27,430** | **590,932** | **71,631** | 38 (210) |
| Resolved, before cleaning | 29,122 | 672,984 | 84,541 | 38 (210) |
| All questions incl. still-open (`forecast_rows_all.tsv.gz`) | 62,192 | 940,439 | 132,890 | 39 (211) |

Resolved + cleaned, by space:

| Space | Questions | Binary | Multi-outcome | Rows | Fires | YES / NO among binary |
|---|---|---|---|---|---|---|
| Kalshi | 12,246 | 10,506 | 1,740 | 240,937 | 26,405 | 5,655 / 4,763 (+88 tie/scalar) |
| Polymarket | 7,828 | 7,806 | 22 | 213,060 | 25,582 | 2,734 / 4,925 (+56 voided, 91 no value) |
| Sooth_QGen | 3,885 | 3,877 | 8 | 116,636 | 13,255 | 1,627 / 2,250 |
| Sooth_QGen_Calendar | 3,471 | 2,215 | 1,256 | 20,299 | 6,389 | 1,077 / 1,138 |

Cleaning removed 1,267 leak-suspect questions (12,845 rows) and 69,207 late rows (425 further questions emptied). 687,046 rows from 148 internal lanes were excluded, and 5,518 market-derivative QGen questions (71,456 rows) were removed in revision 2. Fires span 2026-03-29 → 2026-09-11 18:17 UTC. 124 question keys have forecast rows but no question row (47 Calendar, 40 Polymarket, 37 QGen). Calendar is mostly still open (22.5k open questions in the live pool; 10,223 of the 26,233 Calendar questions with forecasts are multiway).

## Files

`data/`

| File | Rows | What |
|---|---|---|
| `forecast_rows_clean.tsv.gz` | 590,932 | `lane \t fire_ts \t question_key` — the resolved + cleaned set. Bigtable row key = `lane#fire_ts#question_key`. |
| `forecast_rows_all.tsv.gz` | 940,439 | same, every external-lane row on the four spaces (resolved and open, uncleaned) |
| `questions.jsonl.gz` | 62,068 | one JSON object per question: `_key`, `Platform`, `Category`, `Sooth_Category`, `Question`, `Start Date`, `End Date`, `First Observed At`, `Resolve Date` / `Sooth_Resolved_At` / `Resolution Date`, `Resolution` (`1.0`/`0.0`), `Status`, `Sooth_Resolution_Status`, `Outcome Kind` / `Outcome Status` / `Outcome Index` (multiway), `Num Markets in Event`, `Event ID`, `Volume_USD` |
| `lanes.json` | 359 lanes | `external` / `internal` → `base_lane`, `display_name`, `model` (OpenRouter id), `roster_type`, `rows_total`, `spaces`, notes |
| `lane_space_counts.json` | | every lane × space row count from the full `panel_` scan (1,736,425 rows incl. `User#`) |
| `count_printout.txt` | | full output of `count.py` incl. the external / internal lane lists |
| `values/forecasts_clean_{Kalshi,Polymarket,Sooth_QGen,Sooth_QGen_Calendar}.parquet` | 590,932 | hydrated values for the cleaned set (see below) |
| `excluded_market_derivative_questions.tsv` | 5,518 | QGen questions removed in rev 2 (key, text) |
| `MANIFEST.json` | | snapshot timestamp, revision log, counts, sha256 of each data file |

`data/values/` — **the hydrated values for the cleaned set, one parquet per space** (`forecasts_clean_<space>.parquet`, 590,932 rows, 42 MB total, produced by `hydrate.py` at snapshot time). Columns are the values-only hydrate output listed below; no explanation text. Load with `pd.read_parquet("data/values")` (pandas reads the directory). **9,303 rows (1.6%) have no forecast** — `prediction` and `forecast_value` both null: the model call failed and the panel wrote an empty row (mostly Qwen 3.5+ and DeepSeek V4 Pro, May–June 2026). Filter with `forecast_value.notna()` for scoring; the key lists keep them so counts match the store.

`scripts/` — `hydrate.py` (pull full rows for any key list → parquet / jsonl.gz), and the rebuild recipe `dump_all_rows.py` → `fetch_meta_all.py` → `count.py` (`lanes.py` = the lane rule; expects `pool_v2_resolved.jsonl` from `gs://sooth-panel/` in the working dir; ~5 min total).

## Hydrating

```bash
pip install -r scripts/requirements.txt
gcloud auth application-default login        # needs roles/bigtable.reader on sooth-events-database
cd scripts
python hydrate.py --rows ../data/forecast_rows_clean.tsv.gz --out forecasts_clean.parquet
python hydrate.py --rows ../data/forecast_rows_clean.tsv.gz --out gemini_kalshi.parquet --spaces Kalshi --lanes gemini_3_7_flash,gemini
python hydrate.py --rows ../data/forecast_rows_clean.tsv.gz --out sample_with_text.parquet --limit 5000 --content
```

Output columns (values only): `row_key, lane, base_lane, fire_ts, question_key, space, model_name, prediction, forecast_form, forecast_value, cost_usd, cost_source, input_tokens, output_tokens, processing_s, queue_delay_s, start_timestamp, end_timestamp, horizon, category, serving_providers, resolution_ruling, final_turn_gate_fired`. `--content` adds `explanation, prompt, raw_message, self_prior_digest_*` (~40 KB/row; the full cleaned set is ≈25 GB with content).

- `prediction` = P(YES) for binary questions; **null on multi-outcome rows**. `forecast_value` is the JSON `{"outcome_space": …, "representation": {"form": "pmf", "mass": [...]}}` for every row; on binary rows (`outcome_space.kind == "boolean"`) `mass` is `[P(NO), P(YES)]`, so `mass[1] == prediction` (verified on a 3,192-row sample, 0 mismatches).
- Multi-outcome truth = question meta `Outcome Index` into the `forecast_value.outcome_space` labels / bins, **not** `Resolution`.
- `cost_usd` and token columns are null on the earliest (March–April) rows.
- Market price at fire time is not in these rows; it lives in `forecast_questions_v2` `preds:Community Predictions` (see the 09-10 folder's `fetch_crowd.py` in the monorepo).

## Gotchas

- Do not compare raw Brier across months: the pool mix shifted toward 50/50 sports over the summer, so market Brier itself moved 0.09 → 0.15.
- The roster changed over the window; no model covers every question, and multi-outcome questions were forecast only by the post-July roster.
- 79 Kalshi binaries settled to ties/scalars and 56 Polymarket binaries were voided; drop them from accuracy work.
- Rows written during the 2026-09-10 OpenRouter harness-key outage affect only internal (Mirabilis) lanes, which are excluded here.
