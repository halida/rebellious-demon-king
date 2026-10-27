#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《反叛的大魔王》全书 TXT 生成器 · 稳健版（可断点续传）

相比抓取全文.py 的改进：
  * 使用 http.cookiejar 保持会话 Cookie，模拟正常浏览器
  * 限速更温和（默认 3 线程 + 每请求随机 0.4~1.2s 间隔），避免触发站点限流
  * 断点续传：已存在的单章文件直接跳过
  * 单章失败不阻塞：记录到 missing.txt，最后可单独重试
  * 全部完成后自动生成合并 TXT 与章节索引

用法：
    python3 抓取全书-稳健版.py                 # 续传直到全部完成
    python3 抓取全书-稳健版.py --retry-missing  # 只重试 missing.txt 里的章节
"""

import argparse
import http.cookiejar
import os
import random
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
BASE = "https://www.xiaoshuo01.com"
BOOK_INDEX = "/1/1041/"
LOCK = threading.Lock()
PROGRESS = {"n": 0, "ok": 0, "fail": 0, "chars": 0}


def make_opener():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj),
        urllib.request.HTTPRedirectHandler(),
    )
    opener.addheaders = [
        ("User-Agent", UA),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        ("Accept-Language", "zh-CN,zh;q=0.9"),
        ("Connection", "keep-alive"),
    ]
    return opener


def get(url, opener, retries=4, timeout=20):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"Referer": BASE + BOOK_INDEX})
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
            time.sleep(2.5 * (attempt + 1) + random.uniform(0, 2))
    return None


def clean(fragment):
    fragment = re.sub(r"<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"</p>", "\n\n", fragment)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        fragment = fragment.replace(a, b)
    fragment = re.sub(r"[ \t　]+", " ", fragment)
    fragment = re.sub(r"\n{3,}", "\n\n", fragment)
    return fragment.strip()


def collect_index(opener):
    chapters = {}
    for page in range(1, 40):
        url = BASE + BOOK_INDEX + ("" if page == 1 else f"index_{page}.html")
        raw = get(url, opener)
        if raw is None:
            print(f"  目录页 {page} 抓取失败，重试…", flush=True)
            page -= 1
            time.sleep(3)
            if page > 25:
                break
            continue
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
        time.sleep(random.uniform(0.4, 1.2))
    out = [(int(c), chapters[c][0], chapters[c][1]) for c in chapters]
    out.sort(key=lambda x: x[0])
    return out


def fetch_one(item, chapdir, opener, lock):
    cid, href, title = item
    path = os.path.join(chapdir, f"{cid}.txt")
    if os.path.exists(path) and os.path.getsize(path) > 200:
        with lock:
            PROGRESS["n"] += 1
            PROGRESS["ok"] += 1
        return cid, title, None, True

    parts, page = [], 1
    while True:
        url = BASE + href if page == 1 else BASE + re.sub(r"\.html$", f"_{page}.html", href)
        raw = get(url, opener)
        if raw is None:
            break
        m = re.search(r'<article[^>]*>(.*?)</article>', raw, re.S)
        if not m:
            break
        seg = re.sub(r"第\(\d+/\d+\)页", "", clean(m.group(1)))
        parts.append(seg)
        nxt = re.search(r'id="next1"[^>]*href="([^"]+)"', raw)
        if not nxt or not re.match(r"^/1/1041/%d_\d+\.html$" % cid, nxt.group(1)):
            break
        page += 1
        if page > 12:
            break
        time.sleep(random.uniform(0.15, 0.45))

    body = re.sub(r"\n{3,}", "\n\n", "\n".join(p for p in parts if p)).strip()
    if body:
        with lock:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(title + "\n\n" + body + "\n")
            os.replace(tmp, path)
    with lock:
        PROGRESS["n"] += 1
        if body:
            PROGRESS["ok"] += 1
            PROGRESS["chars"] += len(body)
        else:
            PROGRESS["fail"] += 1
        if PROGRESS["n"] % 50 == 0:
            print(f"  {PROGRESS['n']}/{PROGRESS['total']} 已完成 | 新抓 {PROGRESS['ok']} | 失败 {PROGRESS['fail']} | 累计 {PROGRESS['chars']:,} 字",
                  flush=True)
    return cid, title, body, False


def build_merged(chapdir, outdir, order):
    merged_path = os.path.join(outdir, "反叛的大魔王-全书.txt")
    index_path = os.path.join(outdir, "反叛的大魔王-章节索引.txt")
    missing = []
    with open(merged_path, "w", encoding="utf-8") as f, open(index_path, "w", encoding="utf-8") as g:
        f.write("《反叛的大魔王》\n作者：赵青杉\n")
        f.write("首发：起点中文网 / QQ阅读（book.qq.com/book-detail/19996289）\n\n")
        f.write("—— 本文件由个人离线阅读脚本生成，仅供个人学习使用，请支持正版 ——\n")
        f.write("—— 版权归属作者赵青杉与阅文集团，请勿二次分发或商用 ——\n\n")
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
    if missing:
        with open(os.path.join(outdir, "missing.txt"), "w", encoding="utf-8") as m:
            for cid, title in missing:
                m.write(f"{cid}\t{title}\n")
    return merged_path, index_path, len(missing), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--outdir", default="原文")
    ap.add_argument("--rounds", type=int, default=4, help="最多重试几轮")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    outdir = os.path.join(root, args.outdir)
    chapdir = os.path.join(outdir, "章节")
    os.makedirs(chapdir, exist_ok=True)

    opener = make_opener()
    print("→ 收集目录……", flush=True)
    index = collect_index(opener)
    print(f"→ 共 {len(index)} 章", flush=True)
    PROGRESS["total"] = len(index)

    for rnd in range(1, args.rounds + 1):
        print(f"→ 第 {rnd} 轮抓取……", flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = [pool.submit(fetch_one, it, chapdir, opener, LOCK) for it in index]
            for fut in as_completed(futs):
                fut.result()
        print(f"  本轮结束：新抓 {PROGRESS['ok']} / 失败 {PROGRESS['fail']}", flush=True)
        if PROGRESS["fail"] == 0:
            break
        index = [it for it in index if not os.path.exists(os.path.join(chapdir, f"{it[0]}.txt"))]
        if not index:
            break
        print(f"  剩余 {len(index)} 章待重试，歇 10 秒…", flush=True)
        time.sleep(10)

    merged, idx, missing, n = build_merged(chapdir, outdir, index)
    print(f"\n完成：合并 {n} 章，缺失 {missing} 章")
    print("合并文件：", merged)
    print("章节索引：", idx)
    print("单章目录：", chapdir)


if __name__ == "__main__":
    main()
