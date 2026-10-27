#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用网络小说离线下载器（个人离线阅读用）

支持三类常见站点结构，自动探测：
  A. 静态 HTML 型（笔趣阁/小说01/品书 等模板）：目录 index_N.html + 正文 <article>/<div id=article>
  B. 分页型：章节分页 <chapter_id>_2.html，正文里带 "第(n/m)页" 标记
  C. AJAX 型（听雨中文网等）：正文不在 HTML，需 POST /home/index/ajaxchapter（见 站点适配.md）

用法：
    python3 下载小说.py --probe  "https://www.xiaoshuo01.com/0/98/"     # 只探测结构
    python3 下载小说.py --book   "https://www.xiaoshuo01.com/0/98/"     # 抓全本
    python3 下载小说.py --book   "..." --limit 20 --workers 2           # 先试抓 20 章
    python3 下载小说.py --book   "..." --outdir "我的书" --title "书名" --author "作者"

断点续传：重复执行同一条命令即可，已存在的章节自动跳过。
礼貌抓取：默认低并发 + 随机延迟；请勿把并发调高到压站的程度。
"""
import argparse
import html
import http.cookiejar
import json
import os
import random
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

# 正文容器候选（按优先级）
CONTENT_SELECTORS = [
    r'<article[^>]*>(.*?)</article>',
    r'<div id="article"[^>]*>(.*?)</div>\s*<',
    r'<div id="content"[^>]*>(.*?)</div>\s*<',
    r'<div class="content"[^>]*>(.*?)</div>\s*<',
    r'<div class="txt"[^>]*>(.*?)</div>\s*<',
    r'<div class="article"[^>]*>(.*?)</div>\s*<',
]
# 章节页里的"下一章"链接 id（用于判断是否还有下一页）
NEXT_IDS = ('next1', 'next', 'nexturl')


def make_opener(use_proxy=False):
    cj = http.cookiejar.CookieJar()
    handlers = [urllib.request.HTTPCookieProcessor(cj), urllib.request.HTTPRedirectHandler()]
    if not use_proxy:
        # 绕过环境代理：很多站点对共享代理池限流，直连更快更稳
        handlers.append(urllib.request.ProxyHandler({}))
    opener = urllib.request.build_opener(*handlers)
    opener.addheaders = [
        ("User-Agent", UA),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        ("Accept-Language", "zh-CN,zh;q=0.9"),
    ]
    return opener


def get(url, opener, retries=4, timeout=25, data=None, headers=None):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers or {}, data=data)
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
            for enc in ("utf-8", "gbk", "gb18030"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "ignore")
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(2.0 * (attempt + 1) + random.uniform(0, 2.5))
    return None


def clean(fragment):
    fragment = re.sub(r"<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"</p>", "\n\n", fragment)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&ldquo;", "“"), ("&rdquo;", "”")):
        fragment = fragment.replace(a, b)
    fragment = re.sub(r"[ \t　]+", " ", fragment)
    fragment = re.sub(r"\n{3,}", "\n\n", fragment)
    return fragment.strip()


def strip_pagemark(text):
    # 去掉 "第(1/3)页" "第 1/3 页" 之类的分页标记
    text = re.sub(r"第\s*[（(]\s*\d+\s*/\s*\d+\s*[)）]\s*页?", "", text)
    text = re.sub(r"^\s*第\s*\d+\s*/\s*\d+\s*页\s*$", "", text, flags=re.M)
    return text


class Site:
    """一个书籍站点的解析器。"""

    def __init__(self, book_url, opener, delay=(0.3, 1.0)):
        self.book_url = book_url.rstrip("/") + "/"
        p = urllib.parse.urlparse(self.book_url)
        self.base = f"{p.scheme}://{p.netloc}"
        self.prefix = p.path.strip("/")          # 例：0/98
        self.opener = opener
        self.delay = delay
        self.chapters = {}                        # cid -> (href, title)

    # ---------- 目录 ----------
    def collect_index(self, max_pages=80):
        link_re = re.compile(r'href="/' + re.escape(self.prefix) + r'/(\d+)\.html"[^>]*>(.*?)</a>', re.S)
        for page in range(1, max_pages + 1):
            url = self.book_url + ("" if page == 1 else f"index_{page}.html")
            raw = get(url, self.opener)
            if raw is None:
                # 目录页失败 → 可能是最后一页，也可能是限流，重试一次
                raw = get(url, self.opener, retries=2)
                if raw is None:
                    if page == 1:
                        raise RuntimeError(f"目录首页抓取失败：{url}")
                    break
            new = 0
            for cid, title in link_re.findall(raw):
                title = clean(title)
                if not title or re.search(r"第\s*[（(]\s*\d+\s*/", title):
                    continue
                if cid not in self.chapters:
                    self.chapters[cid] = (f"/{self.prefix}/{cid}.html", title)
                    new += 1
            if new == 0:
                break
            time.sleep(random.uniform(*self.delay))
        # 关键：镜像站按入库顺序分配 id，数字 id 升序 == 书中顺序
        out = [(int(c), self.chapters[c][0], self.chapters[c][1]) for c in self.chapters]
        out.sort(key=lambda x: x[0])
        return out

    # ---------- 正文 ----------
    def extract(self, raw):
        for pat in CONTENT_SELECTORS:
            m = re.search(pat, raw, re.S)
            if m:
                return strip_pagemark(clean(m.group(1)))
        return None

    def title_of(self, raw, fallback):
        m = re.search(r"<title>(.*?)</title>", raw, re.S)
        if m:
            t = html.unescape(m.group(1))
            t = re.split(r"[_-]", t)[0]
            t = re.sub(r"[-—|]?\s*(在线无广告版)?阅读.*$", "", t)
            t = re.sub(r"[-—|]?\s*(免费)?在线阅读.*$", "", t)
            t = re.sub(r"[-—|]?\s*(最新章节|全文阅读).*$", "", t)
            t = t.strip(" -—_|")
            if t and len(t) < 80:
                return t
        return fallback

    def fetch_chapter(self, item):
        cid, href, title = item
        parts, page = [], 1
        while True:
            url = self.base + href if page == 1 else \
                self.base + re.sub(r"\.html$", f"_{page}.html", href)
            raw = get(url, self.opener, headers={"Referer": self.book_url})
            if raw is None:
                break
            body = self.extract(raw)
            if body is None:
                break
            parts.append(body)
            nxt = None
            for nid in NEXT_IDS:
                m = re.search(r'id="%s"[^>]*href="([^"]+)"' % nid, raw)
                if m:
                    nxt = m.group(1)
                    break
            if not nxt:
                break
            if not re.match(r"^/" + re.escape(self.prefix) + r"/%s_\d+\.html$" % cid, nxt):
                break
            page += 1
            if page > 15:
                break
            time.sleep(random.uniform(0.15, 0.45))
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(p for p in parts if p)).strip()
        return cid, title, text


def write_outputs(outdir, chapdir, order, results, book_title, author, source):
    os.makedirs(chapdir, exist_ok=True)
    merged = os.path.join(outdir, f"{book_title}-全书.txt")
    index = os.path.join(outdir, f"{book_title}-章节索引.txt")
    missing = []
    with open(merged, "w", encoding="utf-8") as f, open(index, "w", encoding="utf-8") as g:
        f.write(f"《{book_title}》\n")
        if author:
            f.write(f"作者：{author}\n")
        f.write(f"来源：{source}\n\n")
        f.write("—— 本文件由个人离线阅读脚本生成，仅供个人学习使用，请支持正版 ——\n")
        f.write("—— 版权归属原作者与出版/连载平台，请勿二次分发或商用 ——\n\n")
        n = 0
        for cid, href, title in order:
            path = os.path.join(chapdir, f"{cid}.txt")
            if not os.path.exists(path):
                missing.append((cid, title))
                continue
            body = open(path, encoding="utf-8").read()
            n += 1
            f.write(f"\n\n{'=' * 60}\n{title}\n{'=' * 60}\n\n")
            f.write(body)
            f.write("\n")
            g.write(f"{n:04d}\t{cid}\t{title}\t{len(body)}字\n")
    with open(os.path.join(outdir, "missing.txt"), "w", encoding="utf-8") as m:
        for cid, title in missing:
            m.write(f"{cid}\t{title}\n")
    return merged, index, n, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", help="书籍目录页 URL")
    ap.add_argument("--probe", help="只探测该 URL 的站点结构")
    ap.add_argument("--outdir", default="原文")
    ap.add_argument("--title", default="")
    ap.add_argument("--author", default="")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--delay", type=float, default=0.6)
    ap.add_argument("--limit", type=int, default=0, help="只抓前 N 章（调试）")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--use-proxy", action="store_true", help="默认直连；加此参数才走环境代理")
    args = ap.parse_args()

    if args.probe:
        opener = make_opener(args.use_proxy)
        site = Site(args.probe, opener)
        raw = get(site.book_url, opener)
        if raw is None:
            print("目录页抓取失败", file=sys.stderr)
            return 1
        print(f"站点根：{site.base}")
        print(f"书籍前缀：/{site.prefix}")
        for pat in CONTENT_SELECTORS:
            print(f"  正文容器候选 {pat[:28]:32s} -> {bool(re.search(pat, raw, re.S))}")
        idx = site.collect_index()
        print(f"目录页共 {len(idx)} 章；首章 {idx[0][2] if idx else '-'} / 末章 {idx[-1][2] if idx else '-'}")
        return 0

    if not args.book:
        ap.print_help()
        return 1

    opener = make_opener(args.use_proxy)
    site = Site(args.book, opener)
    print("→ 收集目录……", flush=True)
    order = site.collect_index()
    all_order = list(order)          # 完整目录（重试循环会改写 order）
    print(f"→ 共 {len(order)} 章", flush=True)
    if args.limit:
        order = order[:args.limit]

    book_title = args.title or (order[0][2] if order else "未命名")
    root = os.path.abspath(os.getcwd())
    outdir = os.path.join(root, args.outdir)
    chapdir = os.path.join(outdir, "章节")
    os.makedirs(chapdir, exist_ok=True)

    lock = threading.Lock()
    stat = {"ok": 0, "fail": 0, "chars": 0}

    def one(item):
        cid, href, title = item
        path = os.path.join(chapdir, f"{cid}.txt")
        if os.path.exists(path) and os.path.getsize(path) > 150:
            with lock:
                stat["ok"] += 1
            return cid, title, None
        c, t, body = site.fetch_chapter(item)
        if body:
            with lock:
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.write(f"{title}\n\n{body}\n")
                os.replace(tmp, path)
                stat["ok"] += 1
                stat["chars"] += len(body)
        else:
            with lock:
                stat["fail"] += 1
        return cid, title, body

    for rnd in range(1, args.rounds + 1):
        print(f"→ 第 {rnd} 轮抓取（剩余 {len(order)}）……", flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = [pool.submit(one, it) for it in order]
            for i, fut in enumerate(as_completed(futs), 1):
                fut.result()
                if i % 100 == 0:
                    print(f"  {i}/{len(order)} | 成功 {stat['ok']} | 失败 {stat['fail']} | {stat['chars']:,} 字",
                          flush=True)
        print(f"  本轮：成功 {stat['ok']}，失败 {stat['fail']}", flush=True)
        pending = [it for it in order if not os.path.exists(os.path.join(chapdir, f"{it[0]}.txt"))]
        if not pending:
            break
        order = pending
        print(f"  待重试 {len(pending)} 章，歇 10 秒…", flush=True)
        time.sleep(10)

    merged, index, n, missing = write_outputs(outdir, chapdir, all_order, None,
                                              book_title, args.author, site.book_url)
    print(f"\n完成：合并 {n} 章")
    print("合并文件：", merged)
    print("章节索引：", index)
    if missing:
        print("缺失：", len(missing), "章（见 missing.txt）")


if __name__ == "__main__":
    sys.exit(main())
