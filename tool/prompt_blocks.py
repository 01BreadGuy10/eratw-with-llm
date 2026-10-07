# -*- coding: utf-8 -*-
"""把 `@LLM_BUILD_SYSTEM_PROMPT` 的 prompt 字面量按"连续块"列出来，按字数排序。

用途：找 prompt 里的**肥肉**（哪些连续段落最占字数）。
`tool/prompt_audit.py` 按小节汇总；这个脚本按"连续块"细看，方便定位要删的行。
"""
import re

PATH = r"ERB\魔改内容\LLM_CONVERSATION.ERB"
LIT = re.compile(r'REF_PROMPT\s*\+?=\s*@"(.*)"\s*$')

lines = open(PATH, encoding='utf-8').read().splitlines()
start = next(i for i, l in enumerate(lines) if l.startswith('@LLM_BUILD_SYSTEM_PROMPT'))
end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith('@'))

blocks = []
cur = None
for i in range(start, end):
    m = LIT.search(lines[i])
    if m:
        s = m.group(1).replace('\\n', '\n').replace('\\"', '"')
        if cur is None:
            cur = [i + 1, i + 1, 0, 0, '']
        cur[1] = i + 1
        cur[2] += 1
        cur[3] += len(s)
        if not cur[4] and s.replace('\n', '').strip():
            cur[4] = s.replace('\n', ' ').strip()[:48]
    elif cur is not None and lines[i].strip().startswith(';'):
        blocks.append(cur)
        cur = None
if cur:
    blocks.append(cur)

blocks.sort(key=lambda b: -b[3])
print(f'{"行范围":<14}{"字":>6}{"条":>4}  首句')
print('-' * 100)
for b in blocks[:30]:
    print(f'{str(b[0]) + "-" + str(b[1]):<14}{b[3]:>6}{b[2]:>4}  {b[4]}')
print('-' * 100)
print(f'{"全部块合计":<14}{sum(b[3] for b in blocks):>6}   共 {len(blocks)} 块')
