import sys, os, json, threading, queue, time
sys.path.insert(0,'.')
import fetch2
# monkeypatch retry
orig=fetch2.fetch
def safe(cid):
    for attempt in range(4):
        try:
            r=orig(cid)
            if r: return r
        except Exception as e:
            err=str(e)
        time.sleep(3+attempt*3)
    return {'cid':cid,'err':'retryfail'}
ids=[int(x) for x in open('ids2.txt').read().split()]
q=queue.Queue()
for i in ids: q.put(i)
lock=threading.Lock()
def worker():
    while True:
        try: cid=q.get_nowait()
        except queue.Empty: return
        r=safe(cid)
        with lock: print(json.dumps(r,ensure_ascii=False),flush=True)
        time.sleep(0.8)
ts=[threading.Thread(target=worker) for _ in range(2)]
for t in ts: t.start()
for t in ts: t.join()
print("ALLDONE2")
