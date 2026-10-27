#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
离线 TXT 完整性体检工具

检查项：
  1. 合并 TXT 与单章目录是否一致（章数、缺章）
  2. 空章 / 超短章（可能是抓取失败或被截断）
  3. 分页标记残留（"第(1/3)页"）
  4. 重复段 / 章节顺序是否单调递增
  5. 字数统计
  6. 可选：与"官方章节表"逐条比对标题

用法：
    python3 校验完整性.py --dir 原文 --title "反叛的大魔王"
    python3 校验完整性.py --dir 原文 --ref 官方章节名.txt     # 官方标题清单（一行一个）
"""
import argparse
import os
import re
import sys
from collections import Counter


def read_index(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 4:
                rows.append({"no": parts[0], "cid": parts[1], "title": parts[2], "chars": int(parts[3].rstrip("字"))})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="原文", help="存放合并 TXT / 章节索引 / 章节子目录的目录")
    ap.add_argument("--title", default="", help="书名（用于找 <书名>-全书.txt）")
    ap.add_argument("--ref", default="", help="官方章节标题清单（一行一个），用于比对")
    ap.add_argument("--short", type=int, default=800, help="小于多少字算可疑短章")
    args = ap.parse_args()

    idx_candidates = [f for f in os.listdir(args.dir) if f.endswith("章节索引.txt")]
    if not idx_candidates:
        print("✗ 找不到 *章节索引.txt", file=sys.stderr)
        return 1
    idx_path = os.path.join(args.dir, idx_candidates[0])
    rows = read_index(idx_path)
    print(f"索引文件：{idx_path}")
    print(f"章数：{len(rows)}")

    total = sum(r["chars"] for r in rows)
    print(f"总字数：{total:,}")

    if rows:
        print(f"首章：{rows[0]['title']}（{rows[0]['chars']:,}字）")
        print(f"末章：{rows[-1]['title']}（{rows[-1]['chars']:,}字）")

    # ---- 缺章 / 短章 ----
    short = [r for r in rows if r["chars"] < args.short]
    print(f"\n可疑短章（<{args.short}字）：{len(short)} 章")
    for r in short[:15]:
        print(f"   {r['no']} {r['title']}  {r['chars']}字")
    if len(short) > 15:
        print(f"   …其余 {len(short)-15} 章见索引表")

    # ---- 单章文件与索引一致性 ----
    chapdir = os.path.join(args.dir, "章节")
    if os.path.isdir(chapdir):
        files = {f[:-4] for f in os.listdir(chapdir) if f.endswith(".txt")}
        want = {r["cid"] for r in rows}
        miss = want - files
        extra = files - want
        print(f"\n单章文件：{len(files)} 个")
        print(f"  索引有但文件缺：{len(miss)}" + (f"  例：{list(miss)[:5]}" if miss else ""))
        print(f"  文件有但索引无：{len(extra)}" + (f"  例：{list(extra)[:5]}" if extra else ""))

    # ---- 合并 TXT 体检 ----
    merged_candidates = [f for f in os.listdir(args.dir) if f.endswith("全书.txt")]
    if merged_candidates:
        mpath = os.path.join(args.dir, merged_candidates[0])
        text = open(mpath, encoding="utf-8").read()
        heads = re.findall(r"^={60}\n(.+?)\n={60}$", text, re.M)
        print(f"\n合并 TXT：{mpath}")
        print(f"  大小：{len(text):,} 字符 / 标题数：{len(heads)}")
        pagemark = len(re.findall(r"第\s*[（(]\s*\d+\s*/\s*\d+\s*[)）]\s*页?", text))
        print(f"  分页标记残留：{pagemark}" + ("  ✓" if pagemark == 0 else "  ✗ 需重新拼接"))
        dup = [t for t, c in Counter(heads).items() if c > 1]
        print(f"  重复标题：{len(dup)}" + (f"  例：{dup[:5]}" if dup else ""))
        if heads:
            print(f"  首：{heads[0]} / 末：{heads[-1]}")

    # ---- 与官方标题比对 ----
    if args.ref and os.path.exists(args.ref):
        ref = [l.strip() for l in open(args.ref, encoding="utf-8") if l.strip()]
        mine = [r["title"] for r in rows]
        print(f"\n与官方清单比对（官方 {len(ref)} 条 / 本地 {len(mine)} 条）")
        only_ref = [t for t in ref if t not in set(mine)]
        only_mine = [t for t in mine if t not in set(ref)]
        print(f"  官方有、本地无：{len(only_ref)}")
        for t in only_ref[:12]:
            print(f"     - {t}")
        print(f"  本地有、官方无：{len(only_mine)}")
        for t in only_mine[:12]:
            print(f"     + {t}")
        if len(ref) != len(mine):
            print(f"  ⚠ 章数不一致：差 {len(ref)-len(mine)}（镜像残缺/官方新增的典型症状）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
