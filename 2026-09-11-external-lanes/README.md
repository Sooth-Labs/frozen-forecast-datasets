# 2026-09-11 · external-model forecasts on Kalshi, Polymarket, Sooth_QGen and QGen Calendar questions

Snapshot of `forecast_reports_v2` / `forecast_questions_v2` taken **2026-09-11 ~19:05 UTC** (revision 2, 2026-09-12: market-derivative QGen questions removed, see step 8; revision 3, 2026-09-13: value-level cleaning, steps 9–12). Extends the 2026-09-10 venue-only freeze (monorepo `docs/agent/2026-09-10-venue-forecast-dataset/`) to the two Sooth-generated question spaces, with the same lane rule and the same two leakage filters.

## Definition

1. **Question spaces**: keys starting `Kalshi#`, `Polymarket#`, `Sooth_QGen#` (+ `Sooth_QGen_v2#`, `qgen#`), `Sooth_QGen_Calendar#` (+ `_v2`). `User#` questions excluded.
2. **Forecast rows**: `forecast_reports_v2` row keys `panel_<lane>#<fire_ts>#<question_key>`, `fire_ts` = `YYYYMMDD_HHMMSS` UTC. One row = one model × one question × one panel pass.
3. **Lanes: external models only.** Every roster lane with no `type:` (a single external LLM on the standard panel prompt, incl. retired models, `_w2` wave-2 deliberation twins, `_noweb` ablations, `gpt_5_5_min`, and the horizon/category-tagged `_t<N>_<cat>` twins, which fold onto their base lane) plus the two `cli_harness` lanes `claude_code` and `codex`. **Excluded as Sooth-internal**: `panel_sooth_*` (forecast engines, Snap, Tendril, Mirabilis, deep/DS harnesses, continual blenders, big router, reinforcer), `rp_ensemble*`, `openharness`, `v11_*`, `v21_*`, `reflector_*`, `ormolu*`, `meta*`, `dromedary_imitation_1`. Rule: `scripts/lanes.py`; per-lane detail: `data/lanes.json`.
4. **Resolved** = question meta `Status == resolved`, or a recorded `Resolution`, or present in `gs://sooth-panel/pool_v2_resolved.jsonl` at snapshot time.
5. **Clean step 1**: drop every question whose resolve timestamp (`Resolve Date` → `Sooth_Resolved_At` → pool `resolved_at`) precedes our first forecast on it.
6. **Clean step 2**: drop every row fired at or after the question's `End Date` or its resolve timestamp.
7. **Multi-outcome** = question meta `Outcome Kind` present (`categorical` or `numeric`). Calendar multiway questions use plain keys, not `#f_`; the key prefix alone undercounts them.
8. **Removed (rev 2)**: 5,518 QGen questions whose text names Kalshi or Polymarket — all of the form *"Will the Kalshi YES mid-market price for X land in the 80–90¢ bucket at game start"* / *"… YES price be ≥ 20¢ at …"*. They forecast a venue price, not a world event. The exclusion is a **rule in `count.py`** (generated question whose text matches `kalshi|polymarket`), so a rebuild drops them by construction; the keys + text are written to `provenance/excluded_market_derivative_questions.tsv` for audit only — nothing under `data/` contains them. 71,456 external-lane rows went with them. `python scripts/verify.py` checks this on any checkout.
9. **Rows without a forecast dropped (rev 3)**: 9,303 rows (1.6%) where `prediction` and `forecast_value` were both null — the model call failed and the panel wrote an empty row (mostly Qwen 3.5+ and DeepSeek V4 Pro, May–June 2026). Revision 2 kept them so counts matched the store; revision 3 removes them from both the key list and the values.
10. **Unscoreable questions dropped (rev 3)**: 258 questions / 7,620 rows with no usable label — 88 Kalshi binaries whose `Resolution` is `scalar` (ties, postponements), 56 Polymarket binaries with `Status == voided`, 91 legacy Polymarket `#s_` binaries with no `Resolution` recorded anywhere, and 23 Kalshi multiway families with `Outcome Status == void`. Rule: a binary question must have `Resolution` ∈ {0, 1} and no question may be voided. List: `provenance/unscoreable_questions.tsv`.
11. **Gaussian submissions projected to PMFs (rev 3)**: 322 rows on 88 numeric questions where the model returned `{"form": "gaussian", "mean", "sd"}` instead of a PMF. They are projected onto the question's bin grid with a port of `sooth_scoring.distributions.project_gaussian` (CDF differences at `binning.edges`; open tails absorb their mass exactly; a closed end conditions on the support; the vector is divided by its raw sum). The original is kept as `submitted_representation` inside `forecast_value`, and the new column `submitted_form` says what the model returned (`pmf` / `gaussian`). Every `forecast_value` is now a PMF.
12. **Inconsistent multiway questions dropped (rev 3)**: 33 Kalshi families / 865 rows whose outcome space is not identical on every forecast row (15 — the venue added or removed legs mid-life, so PMF lengths differ across fires) or whose recorded `Outcome Index` falls outside the PMF the models saw (18). List: `provenance/inconsistent_multiway_questions.tsv`.

Steps 9–12 are `scripts/clean_values.py`, which runs on the hydrated parquets after `hydrate.py` and is idempotent.

## Counts

| Set | Questions | Forecast rows | Fires | Base models (lane keys) |
|---|---|---|---|---|
| **Resolved + cleaned, rev 3** (`forecast_rows_clean.tsv.gz`) | **27,139** | **573,144** | **70,059** | 38 (206) |
| Resolved + cleaned, rev 2 (steps 1–8 only) | 27,430 | 590,932 | 71,631 | 38 (210) |
| Resolved, before cleaning | 29,122 | 672,984 | 84,541 | 38 (210) |
| All questions incl. still-open (`forecast_rows_all.tsv.gz`) | 62,192 | 940,439 | 132,890 | 39 (211) |

Resolved + cleaned, by space:

| Space | Questions | Binary | Multi-outcome | Rows | Fires | YES / NO among binary |
|---|---|---|---|---|---|---|
| Kalshi | 12,102 | 10,418 | 1,684 | 234,378 | 26,052 | 5,655 / 4,763 |
| Polymarket | 7,681 | 7,659 | 22 | 203,986 | 24,368 | 2,734 / 4,925 |
| Sooth_QGen | 3,885 | 3,877 | 8 | 114,509 | 13,250 | 1,627 / 2,250 |
| Sooth_QGen_Calendar | 3,471 | 2,215 | 1,256 | 20,271 | 6,389 | 1,077 / 1,138 |

Every binary question resolves 0 or 1 and every multiway question has a resolved `Outcome Index` inside its PMF; every row carries a PMF.

Cleaning removed 1,267 leak-suspect questions (12,845 rows) and 69,207 late rows (425 further questions emptied). 687,046 rows from 148 internal lanes were excluded, and 5,518 market-derivative QGen questions (71,456 rows) were removed in revision 2. Revision 3 removed 9,303 rows without a forecast, 258 unscoreable questions (7,620 rows) and 33 inconsistent multiway questions (865 rows), and projected 322 gaussian rows to PMFs (`data/clean_values_printout.txt`). Fires span 2026-03-29 → 2026-09-11 18:17 UTC. 124 question keys have forecast rows but no question row (47 Calendar, 40 Polymarket, 37 QGen). Calendar is mostly still open (22.5k open questions in the live pool; 10,223 of the 26,233 Calendar questions with forecasts are multiway).

## Files

`data/`

| File | Rows | What |
|---|---|---|
| `forecast_rows_clean.tsv.gz` | 573,144 | `lane \t fire_ts \t question_key` — the resolved + cleaned set. Bigtable row key = `lane#fire_ts#question_key`. |
| `forecast_rows_all.tsv.gz` | 940,439 | same, every external-lane row on the four spaces (resolved and open, uncleaned) |
| `questions.jsonl.gz` | 62,068 | one JSON object per question: `_key`, `Platform`, `Category`, `Sooth_Category`, `Question`, `Start Date`, `End Date`, `First Observed At`, `Resolve Date` / `Sooth_Resolved_At` / `Resolution Date`, `Resolution` (`1.0`/`0.0`), `Status`, `Sooth_Resolution_Status`, `Outcome Kind` / `Outcome Status` / `Outcome Index` (multiway), `Num Markets in Event`, `Event ID`, `Volume_USD` |
| `lanes.json` | 359 lanes | `external` / `internal` → `base_lane`, `display_name`, `model` (OpenRouter id), `roster_type`, `rows_total`, `spaces`, notes |
| `lane_space_counts.json` | | every lane × space row count from the full `panel_` scan (1,736,425 rows incl. `User#`) |
| `count_printout.txt` | | full output of `count.py` incl. the external / internal lane lists |
| `clean_values_printout.txt` | | full output of `clean_values.py` (rev 3: what steps 9–12 removed, by space / lane / reason) |
| `values/forecasts_clean_{Kalshi,Polymarket,Sooth_QGen,Sooth_QGen_Calendar}.parquet` | 573,144 | hydrated values for the cleaned set (see below) |
| `MANIFEST.json` | | snapshot timestamp, revision log, counts, sha256 of each data file |

`data/values/` — **the hydrated values for the cleaned set, one parquet per space** (`forecasts_clean_<space>.parquet`, 573,144 rows, 41 MB total, produced by `hydrate.py` at snapshot time and then cleaned in place by `clean_values.py`). Columns are the values-only hydrate output listed below plus `submitted_form`; no explanation text. Load with `pd.read_parquet("data/values")` (pandas reads the directory). Every row has a `forecast_value` PMF; nothing needs filtering before scoring.

`provenance/` — audit lists, not part of the dataset: `excluded_market_derivative_questions.tsv` (5,518 QGen venue-price questions, step 8), `unscoreable_questions.tsv` (258 questions, step 10, with reason), `inconsistent_multiway_questions.tsv` (33 questions, step 12, with reason). Step-10/12 questions still appear in `questions.jsonl.gz` and `forecast_rows_all.tsv.gz` (they are real questions with real forecasts, just not scoreable); step-8 questions appear nowhere under `data/`.

`scripts/` — `verify.py` (checksums, no excluded question present, rev-3 invariants), `hydrate.py` (pull full rows for any key list → parquet / jsonl.gz), `clean_values.py` (steps 9–12 on the hydrated parquets, in place, idempotent), `manifest.py` (refresh checksums + counts, bump the revision log), and the rebuild recipe `dump_all_rows.py` → `fetch_meta_all.py` → `count.py` (`lanes.py` = the lane rule; expects `pool_v2_resolved.jsonl` from `gs://sooth-panel/` in the working dir; ~5 min total).

## Hydrating

```bash
pip install -r scripts/requirements.txt
gcloud auth application-default login        # needs roles/bigtable.reader on sooth-events-database
cd scripts
python hydrate.py --rows ../data/forecast_rows_clean.tsv.gz --out forecasts_clean.parquet
python hydrate.py --rows ../data/forecast_rows_clean.tsv.gz --out gemini_kalshi.parquet --spaces Kalshi --lanes gemini_3_7_flash,gemini
python hydrate.py --rows ../data/forecast_rows_clean.tsv.gz --out sample_with_text.parquet --limit 5000 --content
```

`hydrate.py` returns the rows **as stored**: a fresh hydrate of `forecast_rows_clean.tsv.gz` still contains the 322 gaussian-form rows (the key list keeps them; step 11 rewrites, not removes). To reproduce `data/values/` exactly, hydrate into `data/values/forecasts_clean_<space>.parquet` and run `python clean_values.py`.

Output columns (values only): `row_key, lane, base_lane, fire_ts, question_key, space, model_name, prediction, forecast_form, forecast_value, cost_usd, cost_source, input_tokens, output_tokens, processing_s, queue_delay_s, start_timestamp, end_timestamp, horizon, category, serving_providers, resolution_ruling, final_turn_gate_fired`, plus `submitted_form` in the committed parquets (added by `clean_values.py`). `--content` adds `explanation, prompt, raw_message, self_prior_digest_*` (~40 KB/row; the full cleaned set is ≈25 GB with content).

- `prediction` = P(YES) for binary questions; **null on multi-outcome rows**. `forecast_value` is the JSON `{"outcome_space": …, "representation": {"form": "pmf", "mass": [...]}}` for every row; on binary rows (`outcome_space.kind == "boolean"`) `mass` is `[P(NO), P(YES)]`, so `mass[1] == prediction` (verified on a 3,192-row sample, 0 mismatches). On categorical spaces with `allow_other: true`, `mass` has one more slot than `labels` (the OTHER bucket, last). Rows with `submitted_form == "gaussian"` additionally carry `submitted_representation: {"form": "gaussian", "mean", "sd"}` — the model's original report; `sooth_scoring` treats the submitted form as a stratification axis, so keep it separate when comparing numeric forecasts across models.
- Multi-outcome truth = question meta `Outcome Index` into the `forecast_value.outcome_space` labels / bins, **not** `Resolution`.
- `cost_usd` and token columns are null on the earliest (March–April) rows.
- Market price at fire time is not in these rows; it lives in `forecast_questions_v2` `preds:Community Predictions` (see the 09-10 folder's `fetch_crowd.py` in the monorepo).

## Gotchas

- Do not compare raw Brier across months: the pool mix shifted toward 50/50 sports over the summer, so market Brier itself moved 0.09 → 0.15.
- The roster changed over the window; no model covers every question, and multi-outcome questions were forecast only by the post-July roster.
- Polymarket stores `Resolution` as `"0"`/`"1"` for most questions and `"0.0"`/`"1.0"` for some; Kalshi and the generated spaces use `"0.0"`/`"1.0"`. Compare as floats.
- Rows written during the 2026-09-10 OpenRouter harness-key outage affect only internal (Mirabilis) lanes, which are excluded here.
