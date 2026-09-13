"""Verify a checkout of this snapshot: checksums match MANIFEST.json, the dataset contains none of the
excluded market-derivative questions (by key list AND by rule), and the rev-3 value-level invariants hold
(every row has a PMF, no unscoreable or inconsistent-multiway question remains). Run from anywhere:
    python scripts/verify.py"""
import gzip, hashlib, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); SNAP = os.path.dirname(HERE)
m = json.load(open(f"{SNAP}/MANIFEST.json")); bad = 0
def fail(msg):
    global bad; bad += 1; print("FAIL", msg)
def keylist(name):
    p = f"{SNAP}/provenance/{name}"
    return {l.split("\t", 1)[0] for i, l in enumerate(open(p)) if i and l.strip()} if os.path.exists(p) else set()
for rel, d in m["files"].items():
    p = f"{SNAP}/data/{rel}"
    if not os.path.exists(p): fail(f"missing {rel}"); continue
    if hashlib.sha256(open(p, "rb").read()).hexdigest() != d["sha256"]: fail(f"checksum {rel}")
excl = keylist("excluded_market_derivative_questions.tsv")
removed = keylist("unscoreable_questions.tsv") | keylist("inconsistent_multiway_questions.tsv")  # rev 3: absent from the CLEAN set only
rule = re.compile(r"kalshi|polymarket", re.I); gen = ("Sooth_QGen", "qgen")
qkeys = set(); meta = {}; n_rule = 0
for l in gzip.open(f"{SNAP}/data/questions.jsonl.gz", "rt"):
    r = json.loads(l); qkeys.add(r["_key"])
    meta[r["_key"]] = (r.get("Status"), str(r.get("Resolution")), bool(r.get("Outcome Kind")), r.get("Outcome Status"))
    if r["_key"].startswith(gen) and rule.search(r.get("Question") or ""): n_rule += 1
if qkeys & excl: fail(f"{len(qkeys & excl)} excluded keys present in questions.jsonl.gz")
if n_rule: fail(f"{n_rule} generated questions in questions.jsonl.gz still name Kalshi/Polymarket")
for f in ("forecast_rows_clean.tsv.gz", "forecast_rows_all.tsv.gz"):
    hit = sum(1 for l in gzip.open(f"{SNAP}/data/{f}", "rt") if l.rstrip("\n").split("\t", 2)[2] in excl)
    if hit: fail(f"{hit} rows on excluded questions in {f}")
clean = {l.rstrip("\n").replace("\t", "#") for l in gzip.open(f"{SNAP}/data/forecast_rows_clean.tsv.gz", "rt")}
clean_q = {k.split("#", 2)[2] for k in clean}
if clean_q & removed: fail(f"{len(clean_q & removed)} rev-3-removed questions still in forecast_rows_clean.tsv.gz")
# rule-based (not just list-based): every clean question must be scoreable
unsc = [q for q in clean_q if q not in meta or meta[q][0] == "voided"
        or (meta[q][2] and meta[q][3] == "void") or (not meta[q][2] and meta[q][1] not in ("0", "0.0", "1", "1.0"))]
if unsc: fail(f"{len(unsc)} clean questions are voided / lack a 0-1 resolution (e.g. {unsc[:3]})")
try:
    import pyarrow.parquet as pq
    vals = set(); n_null = n_nonpmf = 0
    for f in sorted(os.listdir(f"{SNAP}/data/values")):
        t = pq.read_table(f"{SNAP}/data/values/{f}", columns=["row_key", "question_key", "forecast_form", "forecast_value"])
        vals |= set(t.column("row_key").to_pylist())
        qs = t.column("question_key").to_pylist()
        hit = sum(1 for q in qs if q in excl)
        if hit: fail(f"{hit} rows on excluded questions in values/{f}")
        hit = sum(1 for q in qs if q in removed)
        if hit: fail(f"{hit} rows on rev-3-removed questions in values/{f}")
        n_null += t.column("forecast_value").null_count
        n_nonpmf += sum(1 for x in t.column("forecast_form").to_pylist() if x != "pmf")
    if vals != clean: fail(f"values rows ({len(vals)}) != clean row list ({len(clean)})")
    if n_null: fail(f"{n_null} values rows have no forecast_value")
    if n_nonpmf: fail(f"{n_nonpmf} values rows are not in pmf form")
except ImportError:
    print("note: pyarrow not installed, values/ not checked")
c = m["counts"]["clean"]
print(f"snapshot {m['snapshot']} rev {m.get('revision', 1)}: {c['questions']:,} questions / {c['rows']:,} rows; "
      f"{len(excl):,} market-derivative questions excluded; {len(removed):,} unscoreable/inconsistent questions removed")
print("OK" if not bad else f"{bad} problem(s)"); sys.exit(1 if bad else 0)
