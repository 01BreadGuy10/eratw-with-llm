# -*- coding: utf-8 -*-
"""列出「本轮 prompt 瘦身」删掉/新增的**全部 prompt 字面量行**，并标出可能涉及
"记忆写入要求 / 标记输出要求"的行 —— 用来人工复核压缩有没有碰坏记忆链路。

对比对象：
    改前 = LLM_CONVERSATION.ERB.20260927_011339_promptopt_final（用户上一轮压完的版本）
    改后 = LLM_CONVERSATION.ERB（当前）
"""
import re
import difflib

OLD = r"ERB\魔改内容\LLM_CONVERSATION.ERB.20260927_011339_promptopt_final"
NEW = r"ERB\魔改内容\LLM_CONVERSATION.ERB"
LIT = re.compile(r'REF_PROMPT\s*\+?=\s*@"(.*)"\s*$')

# 这些词命中 ⇒ 该行可能在教模型"什么时候写记忆 / 怎么输出标记"
RISK = ['MEMO', 'ATTITUDE', 'PROMISE', 'STRIP', 'DELTA', '记', '称呼', '身份', '约定', '写']


def lits(path):
    out = []
    for i, l in enumerate(open(path, encoding='utf-8').read().splitlines(), 1):
        m = LIT.search(l)
        if m:
            out.append((i, m.group(1)))
    return out


old, new = lits(OLD), lits(NEW)
old_set = {t for _, t in old}
new_set = {t for _, t in new}

removed = [(i, t) for i, t in old if t not in new_set]
added = [(i, t) for i, t in new if t not in old_set]

print(f'改前字面量 {len(old)} 条 / 改后 {len(new)} 条')
print(f'删除 {len(removed)} 条 · 新增 {len(added)} 条')
print()
print('=' * 78)
print('★ 被删掉、且**可能涉及记忆/标记**的行（要逐条人工确认）')
print('=' * 78)
n = 0
for i, t in removed:
    plain = t.replace('\\n', '').strip()
    if any(k in plain for k in RISK):
        n += 1
        print(f'  改前行{i:>5}: {plain[:96]}')
print(f'  —— 命中 {n} 条')
print()
print('=' * 78)
print('★ 新增的行（哪些是新写的措辞）')
print('=' * 78)
for i, t in added[:40]:
    print(f'  改后行{i:>5}: {t.replace(chr(92) + "n", "").strip()[:96]}')
if len(added) > 40:
    print(f'  … 另有 {len(added) - 40} 条')
