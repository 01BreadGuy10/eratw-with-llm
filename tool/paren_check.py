# -*- coding: utf-8 -*-
"""检查 ERB 里 `@"..."` 字符串中的全角括号是否配平（2026-10-07 新增）。

⚠️ 背景：`:3213` 那行触发过 Emuera 报错
   `警告Lv2: 找不到与'('对应的')'`
   ⇒ 原因是该行有 `（` 但同行没有 `）`，而 Emuera 在某些写法下会严格检查。

⚠️ 注意：**跨行括号是允许的**（项目里大量存在，一直正常）。
   本工具只标出**可疑**的行（`（` 后紧跟内容、同行无 `）`、且以标点结尾），
   供人工判断，**不**当作硬错误。
"""
import sys
from pathlib import Path

files = sys.argv[1:] or [
    'ERB/魔改内容/LLM_CONVERSATION.ERB',
    'ERB/魔改内容/LLM_INTIMATE.ERB',
    'ERB/魔改内容/LLM_CHAT_BRIDGE.ERB',
]

total_suspect = 0
for path in files:
    p = Path(path)
    if not p.exists():
        continue
    lines = p.read_text(encoding='utf-8').splitlines()
    suspects = []
    for k, l in enumerate(lines, 1):
        s = l.strip()
        if not (s.startswith('REF_PROMPT') or s.startswith('PRINTFORM') or s.startswith('LLM_')):
            continue
        if '@"' not in s:
            continue
        body = s.split('@"', 1)[1].rsplit('"', 1)[0]
        n_open = body.count('（')
        n_close = body.count('）')
        if n_open > n_close:
            # 可疑：以「：」或「，」或「；」结尾，且这行开了括号
            tail = body.rstrip()
            if tail.endswith(('：', '，', '；', '。')):
                suspects.append((k, n_open, n_close, s[:74]))
    if suspects:
        print(f'── {path} ──')
        for k, a, b, txt in suspects:
            print(f'  ⚠️ 行{k}: （{a} ）{b}  {txt}')
        total_suspect += len(suspects)

print()
if total_suspect:
    print(f'  ⚠️ 共 {total_suspect} 行可疑（跨行括号允许，但建议改成 ⚠️ 开头避免踩坑）')
else:
    print('  ✅ 没有可疑行')
