# -*- coding: utf-8 -*-
"""扫全部函数：声明区中间有没有夹代码（会报 Lv1「行只能在函数声明后立刻使用」）。

⚠️ 规则：`#DIM` / `#DIMS` 等声明必须**紧跟函数声明**，
   中间**只能有** `#` 声明 / `;` 注释 / 空行 —— 一旦出现真代码，
   后面的 `#DIM` 全部失效并报 Lv1 ⚠️
"""
import os, re

FILES = [
    "ERB/魔改内容/LLM_CONVERSATION.ERB",
    "ERB/魔改内容/LLM_CHAT_BRIDGE.ERB",
    "ERB/魔改内容/LLM_INTIMATE.ERB",
]

bad = 0
for path in FILES:
    lines = open(path, encoding="utf-8").read().splitlines()
    # 找所有函数起点
    starts = [k for k, l in enumerate(lines) if l.startswith("@")]
    starts.append(len(lines))
    for a, b in zip(starts, starts[1:]):
        # 从函数声明往下走
        k = a + 1
        seen_code = False
        code_line = None
        last_decl = None
        while k < b:
            st = lines[k].strip()
            if st == "" or st.startswith(";"):
                k += 1
                continue
            if st.startswith("#"):
                if seen_code:
                    print(f"  ⚠️ {os.path.basename(path)} 行{k+1}: 声明夹在代码之后"
                          f"（函数 {lines[a].strip()[:34]}，第一行代码在行{code_line}）")
                    bad += 1
                    break
                last_decl = k
                k += 1
                continue
            # 真代码
            if not seen_code:
                seen_code = True
                code_line = k + 1
            k += 1

print()
if bad:
    print(f"  ❌ 共 {bad} 处问题")
else:
    print("  ✅ 所有函数的声明区都干净（没有代码夹在中间）")
