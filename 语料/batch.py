import sys, os, json, threading, queue, time
sys.path.insert(0,'.')
from fetch2 import fetch

ids=[int(x) for x in open('ids.txt').read().split()]
q=queue.Queue()
for i in ids: q.put(i)
lock=threading.Lock()
done=[]
def worker():
    while True:
        try: cid=q.get_nowait()
        except queue.Empty: return
        try:
            r=fetch(cid)
        except Exception as e:
            r={'cid':cid,'err':str(e)}
        with lock:
            print(json.dumps(r,ensure_ascii=False),flush=True)
        time.sleep(0.3)
ts=[threading.Thread(target=worker) for _ in range(4)]
for t in ts: t.start()
for t in ts: t.join()
print("ALLDONE")
