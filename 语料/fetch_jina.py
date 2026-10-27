import sys, os, re, subprocess, time

OUT='chap'
os.makedirs(OUT,exist_ok=True)

def jina(url, tries=3):
    for t in range(tries):
        p=subprocess.run(['curl','-s','--max-time','120','-H','Accept: text/plain',
                          'https://r.jina.ai/'+url], capture_output=True, text=True, timeout=180)
        if p.returncode==0 and len(p.stdout)>400:
            return p.stdout
        time.sleep(8+8*t)
    return None

def strip_hdr(t):
    i=t.find('Markdown Content:')
    body = t[i+len('Markdown Content:'):] if i>=0 else t
    title=''
    m=re.search(r'^Title:\s*(.+)$', t, re.M)
    if m: title=m.group(1).strip()
    return title, body

def grab(cid):
    pages=[]; titles=[]
    base="https://www.tingyuzw.com/info/29668/%d.html"%cid
    t=jina(base)
    if not t: return None
    ti,b=strip_hdr(t); titles.append(ti); pages.append(b)
    total=None
    m=re.search(r'\((\d+)/(\d+)\)', (ti+'\n'+b[:400]))
    if m: total=int(m.group(2))
    n=1
    while True:
        if total is not None and n>total: break
        t2=jina("https://www.tingyuzw.com/info/29668/%d_%d.html"%(cid,n))
        if not t2: break
        ti2,b2=strip_hdr(t2)
        if not b2.strip() or len(b2)<200: break
        if '猜您还喜欢看' in b2[:1500] or '小说书库' in b2[:800]: break
        m2=re.search(r'\((\d+)/(\d+)\)', (ti2+'\n'+b2[:400]))
        if m2:
            idx=int(m2.group(1)); tot=int(m2.group(2))
            if total is None: total=tot
            if idx>tot: break
        pages.append(b2); titles.append(ti2)
        n+=1
        if n>8: break
        time.sleep(4)
    txt='\n\n===PAGEBREAK===\n\n'.join(pages)
    open(os.path.join(OUT,"%d.txt"%cid),'w').write(txt)
    return dict(cid=cid,pages=len(pages),chars=len(txt),titles=titles)

if __name__=='__main__':
    for a in sys.argv[1:]:
        try:
            print(grab(int(a)), flush=True)
        except Exception as e:
            print({'cid':int(a),'err':str(e)[:120]}, flush=True)
        time.sleep(5)
