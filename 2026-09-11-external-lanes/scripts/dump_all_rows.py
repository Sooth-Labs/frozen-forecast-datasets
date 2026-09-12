"""Row-key-only scan of forecast_reports_v2 panel_ rows -> TSV (lane, fire_ts, qkey) for all non-User spaces."""
import time, collections, json
from google.cloud import bigtable
from google.cloud.bigtable.row_filters import CellsColumnLimitFilter, RowFilterChain, StripValueTransformerFilter
from google.cloud.bigtable.row_set import RowRange, RowSet
SC="."
table = bigtable.Client(project="data-ingestion-v1", admin=False).instance("sooth-events-database").table("forecast_reports_v2")
rs = RowSet(); rs.add_row_range(RowRange(start_key=b"panel_", end_key=b"panel`"))
flt = RowFilterChain(filters=[CellsColumnLimitFilter(1), StripValueTransformerFilter(True)])
t0=time.time(); n=0; kept=0; by_space=collections.Counter(); lane_space=collections.Counter()
with open(f"{SC}/all_rows.tsv","w") as out:
    for row in table.read_rows(row_set=rs, filter_=flt):
        n+=1
        if n%500000==0: print(f"... {n} {time.time()-t0:.0f}s", flush=True)
        parts=row.row_key.decode().split("#")
        if len(parts)<4: continue
        qkey="#".join(parts[2:]); space=parts[2]
        by_space[space]+=1
        if space=="User": continue
        lane_space[(parts[0],space)]+=1
        out.write(f"{parts[0]}\t{parts[1]}\t{qkey}\n"); kept+=1
json.dump({"total":n,"kept":kept,"by_space":dict(by_space),"lane_space":{f"{l}|{s}":c for (l,s),c in lane_space.most_common()},"elapsed":round(time.time()-t0)}, open(f"{SC}/dump_all_out.json","w"), indent=1)
print("done", n, kept, round(time.time()-t0))
