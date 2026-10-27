#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《反叛的大魔王》正文抓取器（个人离线阅读用）

用途：把章节页面抓下来，合并成一个纯文本 .txt。

用法：
    python3 抓取正文.py                     # 默认：官方免费章节 1-135
    python3 抓取正文.py --start 1 --end 135
    python3 抓取正文.py --site mirror       # 镜像站（全文，需镜像站可访问）
    python3 抓取正文.py --site mirror --start 1 --end 1458

说明：
  * 官方站 book.qq.com 的 VIP 章节网页端只返回开头一小段（脚本会检测并跳过/截断标记），
    付费章节请用「起点读书/QQ阅读」APP 的离线缓存功能下载到本地阅读。
  * 请优先支持正版；本脚本仅供个人学习与离线阅读。

依赖：仅标准库（urllib）。请在有网络的环境下运行。
"""

import argparse
import html
import os
import re
import sys
import time
import urllib.request
import urllib.error

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

# ---------------- 站点适配 ----------------

def fetch_official(chap_no):
    """起点/QQ阅读官方章节页 -> (标题, 正文文本 or None)"""
    url = f"https://book.qq.com/book-read/19996289/{chap_no}"
    raw = _get(url)
    if raw is None:
        return None, None
    m = re.search(r"<title>(.*?)</title>", raw, re.S)
    title = html.unescape(m.group(1)).split("_")[1].strip() if m and "_" in m.group(1) else f"第{chap_no}章"
    title = re.sub(r"[-—]?\s*(在线无广告版)?阅读[-—]?\s*Q?Q?阅?读?(\s*男生网)?\s*$", "", title).strip()
    title = re.sub(r"在线阅读.*$", "", title).strip()
    body = _extract_official(raw)
    return title, body


def fetch_mirror(chap_no):
    """听雨中文网（转码镜像）章节页 -> (标题, 正文文本 or None)"""
    url = f"https://www.tingyuzw.com/info/29668/{chap_no}.html"
    raw = _get(url)
    if raw is None:
        return None, None
    m = re.search(r"<title>(.*?)</title>", raw, re.S)
    title = html.unescape(m.group(1)).strip() if m else f"第{chap_no}章"
    title = title.split("_", 1)[1].replace("在线无广告版阅读-听雨中文网", "").strip() if "_" in title else title
    body = _extract_mirror(raw)
    return title, body


VIP_MARK = ("登录订阅本章", "上QQ阅读APP看后续精彩内容", "下载QQ阅读APP")


def _extract_official(raw):
    """官方页：正文在 <div id="article" class="chapter-content isTxt"> ... </div>"""
    m = re.search(r'<div id="article"[^>]*>(.*?)</div>\s*<', raw, re.S)
    if not m:
        return None
    text = _clean(m.group(1))
    if any(k in text for k in VIP_MARK):
        return text  # VIP 章节只有开头，会在合并时打上截断标记
    return text


def _extract_mirror(raw):
    """镜像页：正文在 <div class="content"> 或 <div id="content">"""
    for pat in (r'<div class="content"[^>]*>(.*?)</div>\s*<div',
                r'<div id="content"[^>]*>(.*?)</div>\s*<div',
                r'<div class="content"[^>]*>(.*?)</div>'):
        m = re.search(pat, raw, re.S)
        if m:
            return _clean(m.group(1))
    return None


def _clean(fragment):
    fragment = re.sub(r"<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"</p>", "\n\n", fragment)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    fragment = html.unescape(fragment)
    fragment = re.sub(r"[ \t　]+", " ", fragment)
    fragment = re.sub(r"\n{3,}", "\n\n", fragment)
    return fragment.strip()


def _get(url, retries=3, timeout=25):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept-Language": "zh-CN,zh;q=0.9"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            for enc in ("utf-8", "gbk", "gb18030"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "ignore")
        except Exception as exc:                      # noqa: BLE001
            if attempt == retries - 1:
                print(f"    ! 抓取失败 {url} -> {exc}", file=sys.stderr)
                return None
            time.sleep(2 + attempt * 2)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", choices=["official", "mirror"], default="official")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=135)
    ap.add_argument("--delay", type=float, default=1.2, help="每章间隔秒数，别调太小")
    ap.add_argument("--outdir", default="原文")
    args = ap.parse_args()

    fetcher = fetch_official if args.site == "official" else fetch_mirror
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    outdir = os.path.join(root, args.outdir)
    chapdir = os.path.join(outdir, "章节")
    os.makedirs(chapdir, exist_ok=True)

    merged_path = os.path.join(outdir, f"反叛的大魔王-第{args.start:03d}-{args.end:03d}章.txt")
    ok = trunc = fail = 0
    with open(merged_path, "w", encoding="utf-8") as merged:
        merged.write("《反叛的大魔王》\n作者：赵青杉\n\n")
        merged.write("—— 本文件由个人离线阅读脚本生成，仅供个人学习使用，请支持正版 ——\n")
        merged.write("来源：起点中文网 / QQ阅读（官方首发）\n\n")
        for n in range(args.start, args.end + 1):
            title, body = fetcher(n)
            if title is None or not body:
                fail += 1
                print(f"[{n}] 失败")
                time.sleep(args.delay)
                continue
            is_vip = any(k in body for k in VIP_MARK)
            if is_vip:
                trunc += 1
            header = f"\n\n{'=' * 60}\n{title}\n{'=' * 60}\n\n"
            merged.write(header)
            merged.write(body)
            merged.write("\n")
            with open(os.path.join(chapdir, f"{n:04d}.txt"), "w", encoding="utf-8") as fh:
                fh.write(title + "\n\n" + body + "\n")
            ok += 1
            print(f"[{n}] {title}  ({len(body)} 字{'  [VIP截断]' if is_vip else ''})")
            time.sleep(args.delay)

    print(f"\n完成：成功 {ok} 章 / VIP 截断 {trunc} 章 / 失败 {fail} 章")
    print("合并文件：", merged_path)
    print("单章文件：", chapdir)


if __name__ == "__main__":
    main()
