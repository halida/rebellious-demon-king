import sys, re, os, urllib.request, time

BASE="https://www.tingyuzw.com/info/29668/"
UA={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'}

def get(url):
    req=urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=40).read().decode('utf-8','replace')

def content_div(h):
    # find main content
    m=re.search(r'<div[^>]*id="content"[^>]*>(.*?)</div>\s*(?:<div[^>]*class="bottem"|<div[^>]*id="page|</div>)', h, re.S)
    if not m:
        m=re.search(r'<div[^>]*id="content"[^>]*>(.*)', h, re.S)
    body = m.group(1) if m else h
    # cut at navigation
    for stop in ['<div class="bottem"','<div id="page','<div class="page']:
        i=body.find(stop)
        if i>0: body=body[:i]
    body=re.sub(r'<br\s*/?>','\n',body)
    body=re.sub(r'</p>','\n',body)
    body=re.sub(r'<[^>]+>','',body)
    body=body.replace('&nbsp;',' ').replace('&amp;','&').replace('&quot;','"').replace('&#39;',"'").replace('&lt;','<').replace('&gt;','>')
    lines=[l.strip() for l in body.split('\n')]
    lines=[l for l in lines if l]
    return '\n'.join(lines)

def nextpage(h, cid):
    m=re.findall(r'href="(/info/29668/%d(?:_(\d+))?\.html)"[^>]*>([^<]*下一页[^<]*)</a>'%cid, h)
    if m:
        return BASE+m[0][0][len('/info/29668/'):]
    return None

def fetch(cid, outdir='chap'):
    os.makedirs(outdir, exist_ok=True)
    url = BASE + ("%d.html"%cid)
    pages=[]
    seen=set()
    while url and url not in seen:
        seen.add(url)
        h=get(url)
        pages.append(content_div(h))
        url=nextpage(h,cid)
        time.sleep(0.2)
    txt='\n\n===PAGEBREAK===\n\n'.join(pages)
    open(os.path.join(outdir,"%d.txt"%cid),'w').write(txt)
    print("OK %d  pages=%d chars=%d"%(cid,len(pages),len(txt)))

if __name__=='__main__':
    for a in sys.argv[1:]:
        fetch(int(a))
