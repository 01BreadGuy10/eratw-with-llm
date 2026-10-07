# -*- coding: utf-8 -*-
"""存档兼容性硬核对：比较改前 / 改后 `.ERH` 里 **所有 `SAVEDATA` 声明**的
「名字 + 尺寸 + 出现顺序」是否完全一致。

为什么必须查这个：
    Emuera 的二进制存档是**按声明顺序连续排布**的 ⇒ 只要顺序或尺寸变了，
    旧档读进来就会**整体错位**（不只是新变量为空）⚠️
    ⇒ 本轮虽然自认为"只动了 prompt 文本"，也要**用工具证明**没碰存档结构 ✓
"""
import re

OLD = r"ERB\魔改内容\LLM_KOJO.ERH.20260927_011339_promptopt_final"
NEW = r"ERB\魔改内容\LLM_KOJO.ERH"

# #DIM / #DIMS [CHARADATA] SAVEDATA 名字[, 尺寸] [; 注释]
DECL = re.compile(r'^#DIM(?:S)?\s+(?:CHARADATA\s+)?SAVEDATA\s+([A-Za-z_0-9]+)\s*(?:,\s*(\d+))?')


def decls(path, only_savedata=True):
    out = []
    for i, l in enumerate(open(path, encoding='utf-8').read().splitlines(), 1):
        s = l.strip()
        if s.startswith(';'):
            continue
        m = DECL.match(s)
        if m:
            out.append((m.group(1), int(m.group(2)) if m.group(2) else 1, i))
        elif only_savedata and (s.startswith('#DIM') or s.startswith('#DIMS')):
            # 非 SAVEDATA 的声明也记下来，方便看新增项落在哪
            mm = re.match(r'^#DIM(?:S)?\s+(?:CHARADATA\s+)?([A-Za-z_0-9]+)', s)
            if mm:
                out.append(('(非存档) ' + mm.group(1), 0, i))
    return out


o, n = decls(OLD), decls(NEW)
osav = [x for x in o if not x[0].startswith('(非存档)')]
nsav = [x for x in n if not x[0].startswith('(非存档)')]

print(f'改前 SAVEDATA {len(osav)} 个 / 改后 {len(nsav)} 个')
print()
if [x[0] for x in osav] == [x[0] for x in nsav] and [x[1] for x in osav] == [x[1] for x in nsav]:
    print('✅ 存档结构完全一致（名字、尺寸、顺序三者全同）⇒ 旧档可继续用 ✓')
else:
    print('❌ 存档结构有变化！逐项对照：')
    for a, b in zip(osav, nsav):
        flag = '  ' if a[:2] == b[:2] else '⚠️'
        print(f'  {flag} 改前 {a[0]}({a[1]}) @{a[2]}   改后 {b[0]}({b[1]}) @{b[2]}')
    if len(osav) != len(nsav):
        print(f'  ⚠️ 数量不同：{len(osav)} vs {len(nsav)}')

print()
print('改后新增的非存档声明：')
oldnames = {x[0] for x in o}
for name, sz, ln in n:
    if name not in oldnames:
        print(f'  + 行{ln}: {name}')
