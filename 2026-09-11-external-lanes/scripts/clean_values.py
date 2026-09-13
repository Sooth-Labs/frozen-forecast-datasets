"""Revision-3 value-level cleaning of the frozen set (runs on the hydrated parquets, in place).

    python clean_values.py            # from scripts/; rewrites ../data/values/*.parquet and ../data/forecast_rows_clean.tsv.gz

count.py works on row keys and question metadata; the four rules below need the hydrated values, so they
run after hydrate.py. Idempotent: a second run removes nothing.

1. Drop rows with no forecast (`forecast_value` null — the model call failed and the panel wrote an empty row).
2. Drop questions that cannot be scored: `Status == voided`, multiway `Outcome Status == void`, or a binary
   question whose `Resolution` is not 0/1 (Kalshi "scalar" settlements, legacy Polymarket `#s_` keys with no
   recorded resolution). Listed in ../provenance/unscoreable_questions.tsv.
3. Project `gaussian` submissions onto the question's bin grid so every `forecast_value` is a PMF. The
   projection is a line-for-line port of `sooth_scoring.distributions.project_gaussian` (CDF differences at
   `binning.edges`, open tails absorb their mass exactly, closed ends condition on the support, always divided
   by the raw sum). The original `{mean, sd}` is kept under `submitted_representation` inside the JSON and the
   new column `submitted_form` records what the model actually returned ("pmf" or "gaussian").
4. Drop multi-outcome questions whose outcome space is not the same on every forecast row (the venue added or
   removed legs mid-life, so the PMFs are not comparable) or whose `Outcome Index` falls outside the PMF.
   Listed in ../provenance/inconsistent_multiway_questions.tsv.
"""
import collections, gzip, json, math, os, sys

import pyarrow as pa
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__)); SNAP = os.path.dirname(HERE)
DATA, PROV = f"{SNAP}/data", f"{SNAP}/provenance"
SPACES = {"Kalshi": "Kalshi", "Polymarket": "Polymarket", "Sooth_QGen": "QGen", "Sooth_QGen_v2": "QGen", "qgen": "QGen",
          "Sooth_QGen_Calendar": "Calendar", "Sooth_QGen_Calendar_v2": "Calendar"}
FILES = {"Kalshi": "Kalshi", "Polymarket": "Polymarket", "QGen": "Sooth_QGen", "Calendar": "Sooth_QGen_Calendar"}
BINARY_RESOLUTIONS = {"0", "0.0", "1", "1.0"}

# ---- gaussian → PMF, ported from sooth_scoring.distributions (keep in sync with that module) ----
_SQRT2 = math.sqrt(2.0); _INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi); MIDPOINT_Z_WIDTH = 1e-6


def normal_cdf(z):
    """Standard-normal CDF via erfc so the small-z tail keeps full precision."""
    return 0.5 * math.erfc(-z / _SQRT2)


def standard_bin_mass(za, zb):
    """P(za <= Z <= zb) for a standard normal, without cancellation (four regimes, see sooth_scoring)."""
    if zb <= za: return 0.0
    if zb - za < MIDPOINT_Z_WIDTH: return math.exp(-0.5 * (0.5 * (za + zb)) ** 2) * _INV_SQRT_2PI * (zb - za)
    if zb <= 0.0: return 0.5 * (math.erfc(-zb / _SQRT2) - math.erfc(-za / _SQRT2))
    if za >= 0.0: return 0.5 * (math.erfc(za / _SQRT2) - math.erfc(zb / _SQRT2))
    return 0.5 * (math.erf(zb / _SQRT2) - math.erf(za / _SQRT2))


def project_gaussian(mean, sd, binning):
    """Project N(mean, sd²) onto the bin grid; returns the PMF (open tails exact, closed ends conditioned)."""
    if not (math.isfinite(sd) and sd > 0.0 and math.isfinite(mean)): raise ValueError(f"bad gaussian mean={mean} sd={sd}")
    edges = binning["edges"]; z = [(e - mean) / sd for e in edges]
    raw = []
    if binning.get("open_low"): raw.append(normal_cdf(z[0]))
    raw.extend(standard_bin_mass(z[k], z[k + 1]) for k in range(len(edges) - 1))
    if binning.get("open_high"): raw.append(normal_cdf(-z[-1]))
    total = math.fsum(raw)
    if total <= 0.0:  # every bin underflowed: boundary point mass nearest the mean
        mass = [0.0] * len(raw); mass[0 if mean < edges[0] else len(raw) - 1] = 1.0; return mass
    return [r / total for r in raw]


def space_signature(os_):
    """Canonical identity of an outcome space: what the PMF slots mean."""
    k = os_.get("kind")
    if k == "categorical": return ("categorical", tuple(os_.get("labels") or []), bool(os_.get("allow_other")))
    if k == "numeric":
        b = os_.get("binning") or {}; return ("numeric", tuple(b.get("edges") or []), bool(b.get("open_low")), bool(b.get("open_high")))
    return (k,)


def main():
    """Apply the four rules in place and print the rev-3 report."""
    meta = {}
    for l in gzip.open(f"{DATA}/questions.jsonl.gz", "rt"):
        r = json.loads(l); meta[r["_key"]] = r
    tables = {g: pq.read_table(f"{DATA}/values/forecasts_clean_{FILES[g]}.parquet") for g in FILES}
    rows = []
    for g, t in tables.items():
        cols = t.column_names
        for rec in t.to_pylist(): rows.append(rec)
    n0 = len(rows); print(f"input: {n0:,} rows / {len({r['question_key'] for r in rows}):,} questions")
    grp = lambda q: SPACES[q.split("#", 1)[0]]
    has_col = "submitted_form" in tables["Kalshi"].column_names

    # 1. no forecast
    kept = [r for r in rows if r["forecast_value"] is not None]
    drop1 = collections.Counter(grp(r["question_key"]) for r in rows if r["forecast_value"] is None)
    print(f"1. rows without a forecast dropped: {n0 - len(kept):,} {dict(drop1)}")

    # 2. unscoreable questions
    def is_multi(q): return bool(meta.get(q, {}).get("Outcome Kind"))
    def unscoreable(q):
        m = meta.get(q)
        if m is None: return "no_meta"
        if m.get("Status") == "voided": return "voided"
        if is_multi(q):
            return "void_multiway" if m.get("Outcome Status") == "void" else None
        return None if str(m.get("Resolution")) in BINARY_RESOLUTIONS else f"resolution={m.get('Resolution')!r}"
    reasons = {q: r for q in {r["question_key"] for r in kept} if (r := unscoreable(q))}
    os.makedirs(PROV, exist_ok=True)
    with open(f"{PROV}/unscoreable_questions.tsv", "w") as fh:
        fh.write("question_key\treason\tquestion\n")
        for q in sorted(reasons): fh.write(f"{q}\t{reasons[q]}\t{(meta.get(q, {}).get('Question') or '').replace(chr(9), ' ').replace(chr(10), ' ')}\n")
    before = len(kept); kept = [r for r in kept if r["question_key"] not in reasons]
    print(f"2. unscoreable questions dropped: {len(reasons):,} q / {before - len(kept):,} rows; by reason "
          f"{dict(collections.Counter(('scalar/none' if v.startswith('resolution') else v, grp(q)) for q, v in reasons.items()))}")

    # 3. gaussian → pmf
    n_proj = collections.Counter(); bad_g = []
    for r in kept:
        if not has_col: r["submitted_form"] = r["forecast_form"]
        if r["forecast_form"] != "gaussian": continue
        j = json.loads(r["forecast_value"]); rep = j["representation"]; os_ = j["outcome_space"]
        if os_.get("kind") != "numeric": bad_g.append(r["row_key"]); continue
        try: mass = project_gaussian(float(rep["mean"]), float(rep["sd"]), os_["binning"])
        except (ValueError, KeyError, TypeError): bad_g.append(r["row_key"]); continue
        j["submitted_representation"] = rep; j["representation"] = {"form": "pmf", "mass": mass}
        r["forecast_value"] = json.dumps(j); r["forecast_form"] = "pmf"; r["submitted_form"] = "gaussian"
        n_proj[(r["base_lane"], grp(r["question_key"]))] += 1
    kept = [r for r in kept if r["row_key"] not in set(bad_g)]
    print(f"3. gaussian rows projected to PMF: {sum(n_proj.values()):,} on {len({k for k in n_proj}):,} lane×space; unprojectable dropped: {len(bad_g)}")
    by_lane = collections.Counter()
    for (lane, _), n in n_proj.items(): by_lane[lane] += n
    print("   by lane:", dict(by_lane.most_common()))

    # 4. multiway consistency
    sig, lens = collections.defaultdict(set), collections.defaultdict(set)
    for r in kept:
        if r["prediction"] is not None or not is_multi(r["question_key"]): continue
        j = json.loads(r["forecast_value"]); sig[r["question_key"]].add(space_signature(j["outcome_space"])); lens[r["question_key"]].add(len(j["representation"]["mass"]))
    incons = {}
    for q in sig:
        if len(sig[q]) > 1 or len(lens[q]) > 1: incons[q] = f"outcome_space_varies({len(sig[q])} spaces, pmf lengths {sorted(lens[q])})"; continue
        oi = meta[q].get("Outcome Index"); n = next(iter(lens[q]))
        if oi is None or not (0 <= int(oi) < n): incons[q] = f"outcome_index={oi}_outside_pmf_len={n}"
    with open(f"{PROV}/inconsistent_multiway_questions.tsv", "w") as fh:
        fh.write("question_key\treason\tquestion\n")
        for q in sorted(incons): fh.write(f"{q}\t{incons[q]}\t{(meta[q].get('Question') or '').replace(chr(9), ' ').replace(chr(10), ' ')}\n")
    before = len(kept); kept = [r for r in kept if r["question_key"] not in incons]
    print(f"4. inconsistent multiway questions dropped: {len(incons):,} q / {before - len(kept):,} rows "
          f"{dict(collections.Counter(grp(q) for q in incons))}; reasons {dict(collections.Counter(v.split('(')[0].split('=')[0] for v in incons.values()))}")

    # ---- report ----
    qs = {r["question_key"] for r in kept}; fires = {(r["question_key"], r["fire_ts"]) for r in kept}
    print(f"\n== REV 3 CLEAN: {len(qs):,} q / {len(kept):,} rows / {len(fires):,} fires / {len({r['base_lane'] for r in kept})} base models ({len({r['lane'] for r in kept})} lane keys)")
    by = collections.defaultdict(lambda: {"q": set(), "rows": 0, "fires": set(), "multi": set()})
    for r in kept:
        g = grp(r["question_key"]); d = by[g]; d["q"].add(r["question_key"]); d["rows"] += 1; d["fires"].add((r["question_key"], r["fire_ts"]))
        if is_multi(r["question_key"]): d["multi"].add(r["question_key"])
    for g in FILES:
        d = by[g]; binq = d["q"] - d["multi"]; yes = sum(1 for q in binq if str(meta[q].get("Resolution")) in ("1", "1.0")); no = len(binq) - yes
        print(f"   {g:11s} {len(d['q']):>7,} q ({len(binq):,} binary / {len(d['multi']):,} multi-outcome) {d['rows']:>9,} rows {len(d['fires']):>7,} fires   YES/NO {yes:,}/{no:,}")
    fire_ts = sorted(r["fire_ts"] for r in kept); print(f"   fire range {fire_ts[0]} → {fire_ts[-1]}")
    print(f"   rows without forecast: {sum(1 for r in kept if r['forecast_value'] is None)}; non-pmf forms: {sum(1 for r in kept if r['forecast_form'] != 'pmf')}; submitted_form: {dict(collections.Counter(r['submitted_form'] for r in kept))}")

    # ---- write back (same schema as hydrate.py + submitted_form), preserving row order ----
    base_cols = [c for c in tables["Kalshi"].column_names if c != "submitted_form"]
    typ = {c: tables["Kalshi"].schema.field(c).type for c in base_cols}
    schema = pa.schema([(c, typ[c]) for c in base_cols] + [("submitted_form", pa.large_string())])
    by_file = collections.defaultdict(list)
    for r in kept: by_file[grp(r["question_key"])].append(r)
    for g, f in FILES.items():
        pq.write_table(pa.Table.from_pylist(by_file[g], schema=schema), f"{DATA}/values/forecasts_clean_{f}.parquet", compression="zstd")
    with gzip.open(f"{DATA}/forecast_rows_clean.tsv.gz", "wt") as fh:
        for r in kept: fh.write(f"{r['lane']}\t{r['fire_ts']}\t{r['question_key']}\n")
    print(f"\nwrote data/values/*.parquet ({len(kept):,} rows) and data/forecast_rows_clean.tsv.gz; provenance/unscoreable_questions.tsv ({len(reasons)}), provenance/inconsistent_multiway_questions.tsv ({len(incons)})")


if __name__ == "__main__":
    main()
