import sys, re, os, json, subprocess, time, html as htmlmod, random

BASE="https://www.tingyuzw.com"
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'

def get(url, tries=3):
    last=None
    for t in range(tries):
        p=subprocess.run(['curl','-s','--max-time','45','--retry','2','--retry-delay','3',
                          '-A',UA,'-H','Referer: '+BASE+'/info/29668/','-H','Accept: text/html',
                          url], capture_output=True, text=True, timeout=90)
        if p.returncode==0 and len(p.stdout)>500:
            return p.stdout
        last=p.returncode
        time.sleep(5+5*t)
    raise RuntimeError('curl fail %s rc=%s'%(url,last))

def post(data, tries=3):
    last=None
    for t in range(tries):
        p=subprocess.run(['curl','-s','--max-time','60','--retry','2','--retry-delay','3',
                          '-A',UA,'-H','Referer: '+BASE+'/info/29668/',
                          '-H','Content-Type: application/x-www-form-urlencoded',
                          '-X','POST','--data',data, BASE+'/home/index/ajaxchapter'],
                         capture_output=True, text=True, timeout=120)
        if p.returncode==0 and p.stdout.strip().startswith('{'):
            return p.stdout
        time.sleep(5+5*t)
    raise RuntimeError('post fail')

def clean(s):
    s=s.replace('<br/>','\n').replace('<br />','\n').replace('<br>','\n')
    s=re.sub(r'</p>','\n',s); s=re.sub(r'<[^>]+>','',s); s=htmlmod.unescape(s)
    lines=[l.strip() for l in s.split('\n')]
    return '\n'.join([l for l in lines if l])

def fetch(cid, outdir='chap'):
    os.makedirs(outdir, exist_ok=True)
    page=get(BASE+"/info/29668/%d.html"%cid)
    ekey=re.search(r'var hash = "([^"]+)"', page).group(1)
    tm=re.search(r'var chaptername = "([^"]+)"', page)
    title=tm.group(1) if tm else str(cid)
    pages=[]; nextpage=None; pagehash=None
    while True:
        data='id=29668&eKey=%s&cid=%d&basecid=%d'%(ekey,cid,cid)
        if nextpage:
            data+='&nextpage=%s&pagehash=%s'%(nextpage,pagehash)
        j=json.loads(post(data))
        if j.get('status')!='success': return None
        info=j.get('info') or {}
        pages.append(clean(info.get('content','')))
        if j.get('nextpage'):
            nextpage=str(j['nextpage']); pagehash=j.get('hash'); time.sleep(0.4)
        else: break
    txt='\n\n===PAGEBREAK===\n\n'.join(pages)
    open(os.path.join(outdir,"%d.txt"%cid),'w').write(txt)
    return dict(cid=cid,title=title,pages=len(pages),chars=len(txt))

if __name__=='__main__':
    for a in sys.argv[1:]:
        try:
            print(fetch(int(a)), flush=True)
        except Exception as e:
            print({'cid':int(a),'err':str(e)}, flush=True)
