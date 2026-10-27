import sys, re, os, json, urllib.request, urllib.parse, time, html as htmlmod

BASE="https://www.tingyuzw.com"
UA={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
    'Referer': BASE+'/info/29668/'}

def get(url):
    req=urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=45).read().decode('utf-8','replace')

def post(url, data):
    d=urllib.parse.urlencode(data).encode()
    req=urllib.request.Request(url, data=d, headers=UA)
    return urllib.request.urlopen(req, timeout=60).read().decode('utf-8','replace')

def clean(s):
    s=s.replace('<br/>','\n').replace('<br />','\n').replace('<br>','\n')
    s=re.sub(r'</p>','\n',s)
    s=re.sub(r'<[^>]+>','',s)
    s=htmlmod.unescape(s)
    lines=[l.strip() for l in s.split('\n')]
    return '\n'.join([l for l in lines if l])

def fetch(cid, outdir='chap'):
    os.makedirs(outdir, exist_ok=True)
    page=get(BASE+"/info/29668/%d.html"%cid)
    m=re.search(r'var hash = "([^"]+)"', page)
    ekey=m.group(1)
    title=re.search(r'var chaptername = "([^"]+)"', page)
    title=title.group(1) if title else str(cid)
    pages=[]; nextpage=None; pagehash=None
    while True:
        data={'id':'29668','eKey':ekey,'cid':str(cid),'basecid':str(cid)}
        if nextpage:
            data['nextpage']=nextpage; data['pagehash']=pagehash
        raw=post(BASE+"/home/index/ajaxchapter", data)
        try:
            j=json.loads(raw)
        except Exception as e:
            open(os.path.join(outdir,"%d.err"%cid),'w').write(raw[:3000]); return None
        if j.get('status')!='success':
            return None
        info=j.get('info') or {}
        pages.append(clean(info.get('content','')))
        if j.get('nextpage'):
            nextpage=str(j['nextpage']); pagehash=j.get('hash')
            time.sleep(0.15)
        else:
            break
    txt='\n\n===PAGEBREAK===\n\n'.join(pages)
    open(os.path.join(outdir,"%d.txt"%cid),'w').write(txt)
    return dict(cid=cid,title=title,pages=len(pages),chars=len(txt))

if __name__=='__main__':
    out=[]
    for a in sys.argv[1:]:
        r=fetch(int(a))
        print(r if r else 'FAIL %s'%a)
        out.append(r)
