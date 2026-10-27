#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《反叛的大魔王》全书 TXT 生成器（个人离线阅读用）

工作方式：
  1) 抓取目录页 index_1..index_N，收集所有章节链接（按数字 id 升序 = 书中顺序）
  2) 逐章抓取正文（自动翻页 _2 / _3 …）
  3) 输出：合并 TXT + 单章 TXT 目录

用法：
    python3 抓取全文.py                     # 默认抓取全部章节
    python3 抓取全文.py --workers 4
    python3 抓取全文.py --only-range 1 50   # 只抓指定区间（调试用）

说明：
  * 本文件仅供个人离线阅读与学习使用；作品版权归作者赵青杉与阅文集团所有。
  * 若你已在起点/QQ阅读购买，请优先使用官方 APP 的「下载/离线缓存」功能，支持正版。
  * 请勿二次分发或用于商业用途。
"""

import argparse
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
BASE = "https://www.xiaoshuo01.com"
BOOK_INDEX = "/1/1041/"          # 《反叛的大魔王》目录页
LOCK = threading.Lock()
DONE = {"n": 0, "fail": 0, "chars": 0}


def get(url, retries=3, timeout=30):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept-Language": "zh-CN,zh;q=0.9",
                                                       "Referer": BASE + BOOK_INDEX})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
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
            time.sleep(1.5 + attempt * 1.5)
    return None


def clean(fragment):
    fragment = re.sub(r"<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"</p>", "\n\n", fragment)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    fragment = fragment.replace("&nbsp;", " ").replace("&amp;", "&")
    fragment = fragment.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    fragment = re.sub(r"[ \t　]+", " ", fragment)
    fragment = re.sub(r"\n{3,}", "\n\n", fragment)
    return fragment.strip()


def collect_index():
    """收集目录页所有章节 -> [(id, url, title)]，按 id 升序"""
    chapters = {}
    for page in range(1, 40):
        url = BASE + BOOK_INDEX + ("" if page == 1 else f"index_{page}.html")
        raw = get(url)
        if raw is None:
            break
        found = re.findall(r'href="(/1/1041/(\d+)\.html)"[^>]*>(.*?)</a>', raw)
        new = 0
        for href, cid, title in found:
            title = clean(title)
            if not title or "第(" in title:
                continue
            if cid not in chapters:
                chapters[cid] = (href, title)
                new += 1
        if new == 0:
            break
        print(f"目录页 {page:>2}: 累计 {len(chapters)} 章", flush=True)
        time.sleep(0.25)
    out = [(int(cid), chapters[cid][0], chapters[cid][1]) for cid in chapters]
    out.sort(key=lambda x: x[0])
    return out


def fetch_chapter(item, chapdir=None):
    cid, href, title = item
    parts = []
    page = 1
    while True:
        url = BASE + href if page == 1 else BASE + re.sub(r"\.html$", f"_{page}.html", href)
        raw = get(url)
        if raw is None:
            break
        m = re.search(r'<article[^>]*>(.*?)</article>', raw, re.S)
        if not m:
            break
        seg = clean(m.group(1))
        seg = re.sub(r"第\(\d+/\d+\)页", "", seg)
        parts.append(seg)
        nxt = re.search(r'id="next1"[^>]*href="([^"]+)"', raw)
        if not nxt:
            break
        nxt_href = nxt.group(1)
        if not re.match(r"^/1/1041/%d_\d+\.html$" % cid, nxt_href):
            break
        page += 1
        if page > 12:
            break
        time.sleep(0.15)
    body = "\n".join(p for p in parts if p)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if chapdir:                      # 边抓边落盘，中断也不丢进度
        try:
            with open(os.path.join(chapdir, f"{cid}.txt"), "w", encoding="utf-8") as fh:
                fh.write(title + "\n\n" + body + "\n")
        except OSError:
            pass
    with LOCK:
        DONE["n"] += 1
        DONE["chars"] += len(body)
        if not body:
            DONE["fail"] += 1
        if DONE["n"] % 25 == 0 or not body:
            print(f"  进度 {DONE['n']} 章 / 失败 {DONE['fail']} / 累计 {DONE['chars']:,} 字", flush=True)
    return cid, title, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--outdir", default="原文")
    ap.add_argument("--only-range", nargs=2, type=int, metavar=("START", "END"))
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    outdir = os.path.join(root, args.outdir)
    chapdir = os.path.join(outdir, "章节")
    os.makedirs(chapdir, exist_ok=True)

    print("→ 收集目录……", flush=True)
    index = collect_index()
    print(f"→ 共 {len(index)} 章", flush=True)
    if args.only_range:
        lo, hi = args.only_range
        index = [x for x in index if lo <= x[0] <= hi]
        print(f"→ 仅抓取 {len(index)} 章（{lo}-{hi}）", flush=True)

    merged_path = os.path.join(outdir, "反叛的大魔王-全书.txt")
    order_path = os.path.join(outdir, "反叛的大魔王-章节索引.txt")

    print("→ 抓取正文……", flush=True)
    results = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for cid, title, body in pool.map(lambda it: fetch_chapter(it, chapdir), index):
            results[cid] = (title, body)

    print("→ 写入文件……", flush=True)
    with open(merged_path, "w", encoding="utf-8") as f:
        f.write("《反叛的大魔王》\n")
        f.write("作者：赵青杉\n")
        f.write("首发：起点中文网 / QQ阅读（book.qq.com/book-detail/19996289）\n\n")
        f.write("—— 本文件由个人离线阅读脚本生成，仅供个人学习使用，请支持正版 ——\n")
        f.write("—— 版权归属作者赵青杉与阅文集团，请勿二次分发或商用 ——\n\n")
        for cid, (title, body) in sorted(results.items()):
            f.write(f"\n\n{'=' * 60}\n{title}\n{'=' * 60}\n\n")
            f.write(body)
            f.write("\n")

    with open(order_path, "w", encoding="utf-8") as f:
        for n, (cid, (title, body)) in enumerate(sorted(results.items()), 1):
            f.write(f"{n:04d}\t{cid}\t{title}\t{len(body)}字\n")

    print(f"\n完成：{len(results)} 章，共 {DONE['chars']:,} 字")
    print("合并文件：", merged_path)
    print("单章目录：", chapdir)
    print("章节索引：", order_path)


if __name__ == "__main__":
    main()
