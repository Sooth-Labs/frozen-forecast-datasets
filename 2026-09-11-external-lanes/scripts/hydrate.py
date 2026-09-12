"""Hydrate frozen forecast row keys from Bigtable into a parquet (or jsonl.gz) table.

    python hydrate.py --rows ../data/forecast_rows_clean.tsv.gz --out forecasts.parquet
    python hydrate.py --rows ../data/forecast_rows_clean.tsv.gz --out sample.parquet --limit 2000 --content

Needs roles/bigtable.reader on instance sooth-events-database in project data-ingestion-v1
(ADC: `gcloud auth application-default login`). Values (probability / PMF, cost, tokens, latency)
come from the `meta` column family; `--content` adds the explanation, prompt and raw model message
(~40 KB/row — the full cleaned set is ~25 GB with content, ~150 MB without).
"""
import argparse, gzip, json, re, sys, time
from google.cloud import bigtable
from google.cloud.bigtable.row_filters import CellsColumnLimitFilter, FamilyNameRegexFilter, RowFilterChain
from google.cloud.bigtable.row_set import RowRange, RowSet

PROJECT, INSTANCE, TABLE = "data-ingestion-v1", "sooth-events-database", "forecast_reports_v2"
META_COLS = ["model_name", "prediction", "forecast_form", "forecast_value", "cost_usd", "cost_source", "input_tokens",
             "output_tokens", "processing_s", "queue_delay_s", "start_timestamp", "end_timestamp", "horizon",
             "category", "serving_providers", "resolution_ruling", "final_turn_gate_fired"]
CONTENT_COLS = ["explanation", "prompt", "raw_message", "self_prior_digest_prompt", "self_prior_digest_response",
                "self_prior_digest_raw_message"]
FLOAT = {"prediction", "cost_usd"}
INT = {"input_tokens", "output_tokens", "processing_s", "queue_delay_s"}


def base_lane(lane: str) -> str:
    """Fold horizon/category-tagged twins (`panel_gpt_t4_sports`) onto their base lane (`gpt`)."""
    return re.sub(r"_t\d+_[a-z]+$", "", lane[len("panel_"):])


def load_keys(path, spaces=None, lanes=None, limit=None):
    """Read (lane, fire_ts, question_key) rows and return the Bigtable row keys to fetch."""
    keys = []
    opener = gzip.open if path.endswith(".gz") else open
    for line in opener(path, "rt"):
        lane, ts, q = line.rstrip("\n").split("\t", 2)
        if spaces and q.split("#", 1)[0] not in spaces: continue
        if lanes and lane not in lanes and base_lane(lane) not in lanes: continue
        keys.append(f"{lane}#{ts}#{q}")
        if limit and len(keys) >= limit: break
    return keys


def cast(col, v):
    """Convert a Bigtable string cell to the column's declared type."""
    if col in FLOAT:
        try: return float(v)
        except ValueError: return None
    if col in INT:
        try: return int(float(v))
        except ValueError: return None
    return v


def to_record(row, content):
    """Flatten one Bigtable row into a dict with key parts plus the selected columns."""
    k = row.row_key.decode()
    lane, ts, q = k.split("#", 2)
    d = {"row_key": k, "lane": lane, "base_lane": base_lane(lane), "fire_ts": ts, "question_key": q,
         "space": q.split("#", 1)[0]}
    for col in META_COLS: d[col] = None
    for col, cells in row.cells.get("meta", {}).items():
        c = col.decode()
        if c in META_COLS: d[c] = cast(c, cells[0].value.decode("utf-8", "replace"))
    if content:
        for col in CONTENT_COLS: d[col] = None
        for col, cells in row.cells.get("content", {}).items():
            c = col.decode()
            if c in CONTENT_COLS: d[c] = cells[0].value.decode("utf-8", "replace")
    return d


def fetch(keys, content, progress=True):
    """Yield records for the given row keys: batched point reads under 100k keys, else one range scan."""
    table = bigtable.Client(project=PROJECT, admin=False).instance(INSTANCE).table(TABLE)
    fams = "meta|content" if content else "meta"
    flt = RowFilterChain(filters=[FamilyNameRegexFilter(fams), CellsColumnLimitFilter(1)])
    want = set(keys); t0 = time.time(); n = 0
    if len(keys) < 100_000:
        for i in range(0, len(keys), 1000):
            rs = RowSet()
            for k in keys[i:i + 1000]: rs.add_row_key(k.encode())
            for row in table.read_rows(row_set=rs, filter_=flt):
                n += 1; yield to_record(row, content)
            if progress: print(f"  {min(i + 1000, len(keys))}/{len(keys)} keys, {n} rows, {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
    else:
        rs = RowSet(); rs.add_row_range(RowRange(start_key=b"panel_", end_key=b"panel`"))
        scanned = 0
        for row in table.read_rows(row_set=rs, filter_=flt):
            scanned += 1
            if progress and scanned % 200_000 == 0: print(f"  scanned {scanned}, matched {n}, {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
            if row.row_key.decode() in want:
                n += 1; yield to_record(row, content)
    print(f"hydrated {n}/{len(keys)} rows in {time.time() - t0:.0f}s", file=sys.stderr)


def main():
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", required=True, help="forecast_rows_*.tsv.gz (lane, fire_ts, question_key)")
    ap.add_argument("--out", required=True, help="output path: .parquet or .jsonl.gz")
    ap.add_argument("--content", action="store_true", help="also pull explanation/prompt/raw_message (~40 KB/row)")
    ap.add_argument("--spaces", help="comma list, e.g. Kalshi,Polymarket,Sooth_QGen,Sooth_QGen_Calendar")
    ap.add_argument("--lanes", help="comma list of lane keys or base lanes, e.g. panel_gpt_5_6,gemini_3_7_flash")
    ap.add_argument("--limit", type=int, help="stop after N keys (for smoke tests)")
    a = ap.parse_args()
    keys = load_keys(a.rows, a.spaces.split(",") if a.spaces else None, set(a.lanes.split(",")) if a.lanes else None, a.limit)
    print(f"{len(keys)} keys to hydrate", file=sys.stderr)
    recs = fetch(keys, a.content)
    if a.out.endswith(".parquet"):
        import pyarrow as pa, pyarrow.parquet as pq
        cols = ["row_key", "lane", "base_lane", "fire_ts", "question_key", "space"] + META_COLS + (CONTENT_COLS if a.content else [])
        schema = pa.schema([(c, pa.float64() if c in FLOAT else pa.int64() if c in INT else pa.string()) for c in cols])
        writer = pq.ParquetWriter(a.out, schema, compression="zstd"); buf = []
        def flush():
            if buf: writer.write_table(pa.Table.from_pylist(buf, schema=schema)); buf.clear()
        for r in recs:
            buf.append(r)
            if len(buf) >= 20_000: flush()
        flush()
        writer.close()
    else:
        with gzip.open(a.out, "wt") as g:
            for r in recs: g.write(json.dumps(r) + "\n")
    print("wrote", a.out, file=sys.stderr)


if __name__ == "__main__":
    main()
