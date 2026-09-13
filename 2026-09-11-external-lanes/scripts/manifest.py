"""Refresh MANIFEST.json after a data change: sha256/bytes/lines for every file under data/, and the
`counts.clean` block recomputed from data/values. Revision metadata is passed on the command line:

    python manifest.py --rev 3 --note "..."        # bumps revision, appends to the revision log
    python manifest.py                             # checksums + counts only
"""
import argparse, datetime as dt, gzip, hashlib, json, os, re

import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__)); SNAP = os.path.dirname(HERE); DATA = f"{SNAP}/data"


def file_entry(path):
    """sha256 + size (+ line count for text/tsv/jsonl files)."""
    b = open(path, "rb").read(); e = {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}
    if path.endswith((".gz", ".tsv", ".jsonl", ".txt")) and not path.endswith(".parquet"):
        e["lines"] = sum(1 for _ in (gzip.open(path, "rt") if path.endswith(".gz") else open(path)))
    return e


def main():
    """Rewrite MANIFEST.json in place."""
    ap = argparse.ArgumentParser(); ap.add_argument("--rev", type=int); ap.add_argument("--note"); a = ap.parse_args()
    m = json.load(open(f"{SNAP}/MANIFEST.json"))
    files = {}
    for root, _, names in os.walk(DATA):
        for n in sorted(names):
            p = os.path.join(root, n); files[os.path.relpath(p, DATA)] = file_entry(p)
    m["files"] = dict(sorted(files.items()))
    rows = 0; qs, fires, bases, lanes = set(), set(), set(), set(); no_fc = 0
    for f in sorted(os.listdir(f"{DATA}/values")):
        t = pq.read_table(f"{DATA}/values/{f}", columns=["question_key", "fire_ts", "base_lane", "lane", "forecast_value"]).to_pydict()
        rows += len(t["question_key"]); qs |= set(t["question_key"]); fires |= set(zip(t["question_key"], t["fire_ts"]))
        bases |= set(t["base_lane"]); lanes |= set(t["lane"]); no_fc += sum(1 for v in t["forecast_value"] if v is None)
    m["counts"]["clean"] = {"questions": len(qs), "rows": rows, "fires": len(fires), "base_models": len(bases), "lane_keys": len(lanes), "rows_without_forecast": no_fc}
    m["values"]["rows"] = rows
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:00Z")
    if a.rev:
        m["revision"] = a.rev; m["revision_utc"] = now
        m.setdefault("revisions", []).append({"rev": a.rev, "utc": now, "note": a.note or ""})
    json.dump(m, open(f"{SNAP}/MANIFEST.json", "w"), indent=1); print(json.dumps(m["counts"]["clean"]), "| files:", len(files))


if __name__ == "__main__":
    main()
