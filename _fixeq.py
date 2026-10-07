# -*- coding: utf-8 -*-
"""修 `'=` 用在数值变量上的错误（2026-09-20 用户报错）。

⚠️ 报错：
   警告Lv2: LLM_INTIMATE.ERB:第287行:整型数值的赋值运算符不能使用"'="
   LLM_V '= LLM_INT_GETVAL(LLM_BP, "B")     （290/293/296/299 同理）

⚠️ 原因：
   `'=` 是**字符串**赋值运算符（把右边当表达式求值后转字符串）⚠️
   `LLM_V` 是**数值**变量 ⇒ 只能用 `=` 或 `%…%` ✓
   ⚠️ 而 `@LLM_INT_GETVAL` **没有 `#FUNCTION`** ⇒ 只能用 `CALL` + `RESULT` ✓
"""
import re

D = "ERB/魔改内容/LLM_INTIMATE.ERB"
lines = open(D, encoding="utf-8").read().splitlines()

print("=== 修改前：所有 '= 用法 ===")
for i, l in enumerate(lines, 1):
    if "'=" in l:
        print(f"  {i:>4}: {l.strip()[:80]}")

n = 0
out = []
for l in lines:
    s = l.strip()
    m = re.match(r'^LLM_V\s*\'=\s*LLM_INT_GETVAL\((.+)\)$', s)
    if m:
        ind = l[:len(l) - len(l.lstrip())]
        out.append(ind + f"CALL LLM_INT_GETVAL({m.group(1)})")
        out.append(ind + "LLM_V = RESULT")
        n += 1
        print(f"  ✓ 改写: {s[:60]} → CALL + RESULT")
    else:
        out.append(l)

open(D, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
print(f"\n  共修 {n} 处")
