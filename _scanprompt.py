# -*- coding: utf-8 -*-
"""扫描 plugins/LLMBridge/debug.log 里的 CHAT-SYS，统计 prompt 的字面量外泄。

⚠️ 背景：`ERB/魔改内容/LLM_ERB语法避坑.md:108-115` 记着
   「`#DIMS REF` 传出来的值**会带引号**」——
   这个脚本用来量一下它到底影响多少条 prompt、分别在哪个段上。
"""
import collections
import re

LOG = r"plugins/LLMBridge/debug.log"

lines = open(LOG, encoding="utf-8", errors="replace").read().splitlines()
heads = [l.split("CHAT-SYS head=", 1)[1] for l in lines if "CHAT-SYS head=" in l]
sends = [l for l in lines if " CHAT-SEND " in l]

print(f"CHAT-SEND 总数: {len(sends)}    CHAT-SYS 总数: {len(heads)}")

starts_literal = sum(1 for h in heads if h.startswith('@"'))
starts_plain = sum(1 for h in heads if h.startswith('"') and not h.startswith('@"'))
print(f"  以 `@\"` 开头（`=` 赋值的字面量连引号一起进串）: {starts_literal}")
print(f"  以 `\"`  开头（同上，无 @）: {starts_plain}")

# 找「段名】"值"」这种：值被引号包住
pat = re.compile(r'【([^】]{2,20})】(?:"|@")')
seg = collections.Counter()
for h in heads:
    for m in pat.finditer(h):
        seg[m.group(1)] += 1

print()
print("被引号/字面量污染过的段落（段名 -> 出现次数）:")
for k, v in seg.most_common():
    print(f"  【{k}】 x{v}")

print()
print("每条 prompt 里 `@\"` 的出现次数与位置（判断是「= 赋值」还是「REF 传值」的外泄）:")
for i, h in enumerate(heads, 1):
    pos = [m.start() for m in re.finditer(r'@\\?"', h)]
    print(f"  #{i}: n={len(pos)} pos={pos[:8]}")
    for p in pos[:8]:
        print(f"        @{p}: …{h[max(0,p - 12):p + 26]}…")

print()
print("最近 1 条完整 prompt:")
print(heads[-1] if heads else "(none)")
