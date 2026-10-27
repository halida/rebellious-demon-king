import time, sys, os
sys.path.insert(0,'.')
from fetch3 import fetch
ids=[1,341,809,779,829,818,849,838,851,852,856,859,876,896,897,1084,1085,1100,1102,1104,1160,1165,1180,1181,1199,1200,1201,1300,1400,1500,1524,1532,1533]
done=set()
for rnd in range(12):
    todo=[i for i in ids if i not in done]
    if not todo: break
    for cid in todo:
        if cid in done: continue
        try:
            r=fetch(cid)
            if r:
                done.add(cid); print("OK",r,flush=True)
            else:
                print("NULL",cid,flush=True)
        except Exception as e:
            print("ERR",cid,str(e)[:80],flush=True)
        time.sleep(8)
    if len(done)>=len(ids): break
    print("--- round %d done=%d, sleeping 120s"%(rnd,len(done)),flush=True)
    time.sleep(120)
print("PATIENT DONE",sorted(done),flush=True)
