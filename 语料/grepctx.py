import sys, os, re, glob
pat=sys.argv[1]
ctx=int(sys.argv[2]) if len(sys.argv)>2 else 160
files=sorted(glob.glob('chap/*.txt'), key=lambda p:int(re.search(r'(\d+)',p).group(1)))
for f in files:
    cid=int(re.search(r'(\d+)',f).group(1))
    s=open(f,encoding='utf-8').read()
    for m in re.finditer(pat, s):
        a=max(0,m.start()-ctx); b=min(len(s), m.end()+ctx)
        seg=s[a:b].replace('\n',' ')
        print("[%d] %s"%(cid,seg))
