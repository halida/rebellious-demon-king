#!/usr/bin/env python3
import sys, re, json, urllib.request, urllib.parse, html as htmlmod, time, os

# Bypass the environment HTTP proxy (proxy.llj.click throttles this host)
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

BASE = "https://www.tingyuzw.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

def get(url, data=None, retries=4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers={
                "User-Agent": UA,
                "Referer": BASE + "/info/29668/",
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
            })
            with _opener.open(req, timeout=40) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last

def strip_tags(s):
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = htmlmod.unescape(s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def fetch_chapter(cid, outdir):
    pageurl = f"{BASE}/info/29668/{cid}.html"
    h = get(pageurl)
    m = re.search(r'var hash = "([^"]+)"', h)
    if not m:
        return {"cid": cid, "status": "no-hash"}
    ekey = m.group(1)
    name = re.search(r'var chaptername = "([^"]*)"', h)
    name = name.group(1) if name else str(cid)
    # page 1
    post = urllib.parse.urlencode({"id": "29668", "eKey": ekey, "cid": str(cid), "basecid": str(cid)}).encode()
    try:
        raw = get(BASE + "/home/index/ajaxchapter", data=post)
    except Exception as e:
        return {"cid": cid, "status": "ajax-error", "err": str(e)}
    try:
        data = json.loads(raw)
    except Exception:
        return {"cid": cid, "status": "json-error", "raw": raw[:300]}
    if data.get("status") != "success":
        return {"cid": cid, "status": "fail", "raw": raw[:300]}
    parts = [strip_tags(data["info"]["content"])]
    nextpage = data.get("nextpage")
    pagehash = data.get("hash")
    n = 1
    while nextpage and n < 12:
        n += 1
        post = urllib.parse.urlencode({
            "id": "29668", "eKey": ekey, "cid": str(cid), "basecid": str(cid),
            "nextpage": nextpage, "pagehash": pagehash}).encode()
        try:
            raw = get(BASE + "/home/index/ajaxchapter", data=post)
            data = json.loads(raw)
        except Exception as e:
            parts.append(f"[[PAGE {n} ERROR: {e}]]")
            break
        if data.get("status") != "success":
            parts.append(f"[[PAGE {n} FAIL]]")
            break
        parts.append(strip_tags(data["info"]["content"]))
        nextpage = data.get("nextpage")
        pagehash = data.get("hash")
        time.sleep(0.25)
    text = "\n".join(parts)
    fn = os.path.join(outdir, f"{cid}.txt")
    with open(fn, "w", encoding="utf-8") as f:
        f.write(f"### {cid} {name}\n\n" + text + "\n")
    return {"cid": cid, "status": "ok", "name": name, "pages": n, "chars": len(text), "file": fn}

if __name__ == "__main__":
    outdir = sys.argv[1]
    ids = [int(x) for x in sys.argv[2:]]
    os.makedirs(outdir, exist_ok=True)
    for cid in ids:
        try:
            r = fetch_chapter(cid, outdir)
        except Exception as e:
            r = {"cid": cid, "status": "exception", "err": str(e)[:120]}
        print(json.dumps(r, ensure_ascii=False), flush=True)
        time.sleep(0.4)
