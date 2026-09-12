"""Fetch question meta for every question key with >=1 external-lane forecast row."""
import json,sys,time
from google.cloud import bigtable
from google.cloud.bigtable.row_filters import RowFilterChain, FamilyNameRegexFilter, CellsColumnLimitFilter
from google.cloud.bigtable.row_set import RowSet
SC="."
sys.path.insert(0,SC); from lanes import keep
keys=set()
for line in open(f"{SC}/all_rows.tsv"):
    lane,ts,q=line.rstrip("\n").split("\t",2)
    if keep(lane): keys.add(q)
keys=sorted(keys); print("keys",len(keys),flush=True)
COLS=["Platform","Category","Sooth_Category","End Date","Start Date","First Observed At","Resolve Date","Resolution Date","Resolution Date Est",
      "Sooth_Resolved_At","Sooth_Resolution_Date","Sooth_Resolution_Status","Last Resolver Attempt At","Last_Sooth_Resolver_Attempt_At",
      "Resolution","Status","Question","Num Markets in Event","Event ID","Volume_USD","Outcome Kind","Outcome Status","Outcome Index"]
t=bigtable.Client(project="data-ingestion-v1",admin=False).instance("sooth-events-database").table("forecast_questions_v2")
flt=RowFilterChain(filters=[FamilyNameRegexFilter("meta"),CellsColumnLimitFilter(1)])
n=0;t0=time.time()
with open(f"{SC}/question_meta_all.jsonl","w") as out:
    for i in range(0,len(keys),2000):
        rs=RowSet()
        for k in keys[i:i+2000]: rs.add_row_key(k.encode())
        for row in t.read_rows(row_set=rs,filter_=flt):
            d={"_key":row.row_key.decode()}
            for col,cells in row.cells.get("meta",{}).items():
                c=col.decode()
                if c in COLS: d[c]=cells[0].value.decode("utf-8","replace")
            out.write(json.dumps(d)+"\n"); n+=1
        print(f"{min(i+2000,len(keys))}/{len(keys)} -> {n} {time.time()-t0:.0f}s",flush=True)
print("done",n)
