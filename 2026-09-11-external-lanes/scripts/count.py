import json,sys,collections,datetime as dt,gzip
from datetime import timezone
SC="."
sys.path.insert(0,SC); from lanes import keep,base
SPACES={"Kalshi":"Kalshi","Polymarket":"Polymarket","Sooth_QGen":"QGen","Sooth_QGen_v2":"QGen","qgen":"QGen","Sooth_QGen_Calendar":"Calendar","Sooth_QGen_Calendar_v2":"Calendar"}
def pts(s):
    if not s: return None
    s=s.strip().replace(" ","T")
    if s.endswith("Z"): s=s[:-1]+"+00:00"
    try: d=dt.datetime.fromisoformat(s)
    except Exception: return None
    if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
    return d
def pfire(s): return dt.datetime.strptime(s,"%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
meta={}
for l in open(f"{SC}/question_meta_all.jsonl"):
    r=json.loads(l); meta[r["_key"]]=r
pool_res={}
for l in open(f"{SC}/pool_v2_resolved.jsonl"):
    if l.strip():
        e=json.loads(l); pool_res[e["_key"]]=e
rows=[]; int_rows=collections.Counter(); ext_lanes=collections.Counter(); int_lanes=collections.Counter()
for line in open(f"{SC}/all_rows.tsv"):
    lane,ts,q=line.rstrip("\n").split("\t",2)
    sp=q.split("#",1)[0]
    if sp not in SPACES: continue
    if keep(lane): rows.append((lane,pfire(ts),q)); ext_lanes[lane]+=1
    else: int_rows[SPACES[sp]]+=1; int_lanes[lane]+=1
grp=lambda q:SPACES[q.split("#",1)[0]]
def resolve_ts(q):
    m=meta.get(q,{})
    for c in ("Resolve Date","Sooth_Resolved_At","Sooth_Resolution_Date"):
        if (d:=pts(m.get(c))): return d
    p=pool_res.get(q)
    return pts(p.get("resolved_at")) if p else None
def is_multi(q):
    m=meta.get(q,{}); return bool(m.get("Outcome Kind")) or q.split("#",1)[1].startswith("f_") or m.get("Sooth_Resolution_Status")=="resolved_multi"
def is_resolved(q):
    m=meta.get(q,{})
    return m.get("Status")=="resolved" or q in pool_res or m.get("Resolution") not in (None,"","None")
def summarize(rs,label):
    qs={q for _,_,q in rs}; fires={(q,f) for _,f,q in rs}
    by=collections.defaultdict(lambda:[set(),0,set()])
    for lane,f,q in rs:
        g=grp(q); by[g][0].add(q); by[g][1]+=1; by[g][2].add((q,f))
    print(f"\n== {label}: {len(qs):,} q / {len(rs):,} rows / {len(fires):,} fires / {len({base(l) for l,_,_ in rs})} base models ({len({l for l,_,_ in rs})} lane keys)")
    for g in ("Kalshi","Polymarket","QGen","Calendar"):
        s=by[g]; multi=sum(1 for q in s[0] if is_multi(q))
        print(f"   {g:11s} {len(s[0]):>7,} q ({multi:,} multi-outcome) {s[1]:>9,} rows {len(s[2]):>7,} fires")
    return qs
allq=summarize(rows,"ALL questions with >=1 external forecast (resolved + open)")
missing=[q for q in allq if q not in meta]; print("   questions with no meta row:",len(missing), collections.Counter(grp(q) for q in missing))
res_rows=[r for r in rows if is_resolved(r[2])]
resq=summarize(res_rows,"RESOLVED questions, raw")
# cleaning
first={}
for lane,f,q in res_rows:
    if q not in first or f<first[q]: first[q]=f
leak={q for q in first if (r:=resolve_ts(q)) and r<first[q]}
print("   leak-suspect q (resolve < first fire):",len(leak),collections.Counter(grp(q) for q in leak),"rows",sum(1 for r in res_rows if r[2] in leak))
def late(f,q):
    e=pts(meta.get(q,{}).get("End Date")); r=resolve_ts(q)
    return (e is not None and f>=e) or (r is not None and f>=r)
r2=[r for r in res_rows if r[2] not in leak]
late_n=sum(1 for lane,f,q in r2 if late(f,q))
clean=[r for r in r2 if not late(r[1],r[2])]
print("   late rows dropped:",late_n,"; q emptied:",len({q for _,_,q in r2})-len({q for _,_,q in clean}))
cleanq=summarize(clean,"RESOLVED + CLEANED (drop leak-suspect q, drop rows at/after close or resolve)")
# outcome breakdown for cleaned binary
oc=collections.Counter()
for q in cleanq:
    if is_multi(q): oc[(grp(q),"multi")]+=1; continue
    r=meta.get(q,{}).get("Resolution"); s=meta.get(q,{}).get("Status")
    k="voided" if s=="voided" else "YES" if r in("1","1.0") else "NO" if r in("0","0.0") else "none" if r in(None,"","None") else "other"
    oc[(grp(q),k)]+=1
print("\n   cleaned outcomes:"); 
for g in ("Kalshi","Polymarket","QGen","Calendar"): print("   ",g,{k:v for (gg,k),v in sorted(oc.items()) if gg==g})
print("\n   internal-lane rows excluded (same 4 spaces):",sum(int_rows.values()),dict(int_rows))
print("   external lanes:",len(ext_lanes)); print("   ",sorted(ext_lanes))
print("   internal lanes:",len(int_lanes)); print("   ",sorted(int_lanes))
fire_dates=sorted(f for _,f,_ in clean); print("   cleaned fire range",fire_dates[0],fire_dates[-1])
with gzip.open(f"{SC}/frozen_clean_rows.tsv.gz","wt") as g:
    for lane,f,q in clean: g.write(f"{lane}\t{f:%Y%m%d_%H%M%S}\t{q}\n")
with gzip.open(f"{SC}/frozen_all_rows.tsv.gz","wt") as g:
    for lane,f,q in rows: g.write(f"{lane}\t{f:%Y%m%d_%H%M%S}\t{q}\n")
