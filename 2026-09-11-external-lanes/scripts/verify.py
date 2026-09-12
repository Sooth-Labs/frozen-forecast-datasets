"""Verify a checkout of this snapshot: checksums match MANIFEST.json and the dataset contains none of the
excluded market-derivative questions (by key list AND by rule). Run from anywhere:  python scripts/verify.py"""
import gzip, hashlib, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); SNAP = os.path.dirname(HERE)
m = json.load(open(f"{SNAP}/MANIFEST.json")); bad = 0
def fail(msg):
    global bad; bad += 1; print("FAIL", msg)
for rel, d in m["files"].items():
    p = f"{SNAP}/data/{rel}"
    if not os.path.exists(p): fail(f"missing {rel}"); continue
    if hashlib.sha256(open(p, "rb").read()).hexdigest() != d["sha256"]: fail(f"checksum {rel}")
excl = {l.split("\t", 1)[0] for i, l in enumerate(open(f"{SNAP}/provenance/excluded_market_derivative_questions.tsv")) if i and l.strip()}
rule = re.compile(r"kalshi|polymarket", re.I); gen = ("Sooth_QGen", "qgen")
qkeys = set(); n_rule = 0
for l in gzip.open(f"{SNAP}/data/questions.jsonl.gz", "rt"):
    r = json.loads(l); qkeys.add(r["_key"])
    if r["_key"].startswith(gen) and rule.search(r.get("Question") or ""): n_rule += 1
if qkeys & excl: fail(f"{len(qkeys & excl)} excluded keys present in questions.jsonl.gz")
if n_rule: fail(f"{n_rule} generated questions in questions.jsonl.gz still name Kalshi/Polymarket")
for f in ("forecast_rows_clean.tsv.gz", "forecast_rows_all.tsv.gz"):
    hit = sum(1 for l in gzip.open(f"{SNAP}/data/{f}", "rt") if l.rstrip("\n").split("\t", 2)[2] in excl)
    if hit: fail(f"{hit} rows on excluded questions in {f}")
try:
    import pyarrow.parquet as pq
    clean = {l.rstrip("\n").replace("\t", "#") for l in gzip.open(f"{SNAP}/data/forecast_rows_clean.tsv.gz", "rt")}
    vals = set()
    for f in sorted(os.listdir(f"{SNAP}/data/values")):
        t = pq.read_table(f"{SNAP}/data/values/{f}", columns=["row_key", "question_key"])
        vals |= set(t.column("row_key").to_pylist())
        hit = sum(1 for q in t.column("question_key").to_pylist() if q in excl)
        if hit: fail(f"{hit} rows on excluded questions in values/{f}")
    if vals != clean: fail(f"values rows ({len(vals)}) != clean row list ({len(clean)})")
except ImportError:
    print("note: pyarrow not installed, values/ not checked")
c = m["counts"]["clean"]
print(f"snapshot {m['snapshot']} rev {m.get('revision', 1)}: {c['questions']:,} questions / {c['rows']:,} rows; {len(excl):,} market-derivative questions excluded")
print("OK" if not bad else f"{bad} problem(s)"); sys.exit(1 if bad else 0)
