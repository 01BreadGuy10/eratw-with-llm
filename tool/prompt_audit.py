# -*- coding: utf-8 -*-
"""prompt 体量审计 —— 离线统计 `@LLM_BUILD_SYSTEM_PROMPT` 各段的字面量字数。

为什么需要它：
    `debug.log` 只记 `sysLen`（一个总数），**不记 prompt 正文** ⇒
    想压 prompt 就得知道"哪一段最肥"。这个脚本把 ERB 里
    `REF_PROMPT += @"..."` 的字面量抠出来，按**所属小节**归类统计。

它**只读** `LLM_CONVERSATION.ERB`，不改任何文件。

分节规则（v2）：
  ① 标题候选 = 注释行里**纯分隔标题**（`; ── xxx ──`）或**含【…】的短注释**；
  ② 一段字面量归属于**它前面最近的那个标题**（注释描述的是它下面的代码）；
  ③ 解释性长注释**不算标题** —— 否则会把"上一个标题"截断成一句废话。

口径说明（看数时注意）：
  · 统计的是**代码里的字面量**（`\\n` 还原成 1 个字符），
    **不含** `%变量%` 展开后的实际内容（persona / 记忆 / 素质…）。
  · 所以「合计」+「变量展开」才等于真实 `sysLen`。
  · `%…%` 的**名字**会计入（那点长度可忽略，但它标出了"这里插了变量"）。
"""
import re
import sys

PATH = r"ERB\魔改内容\LLM_CONVERSATION.ERB"
LIT_RE = re.compile(r'REF_PROMPT\s*\+?=\s*@"(.*)"\s*$')
SEP_RE = re.compile(r'^\s*;\s*[─=]{2,}\s*(.+?)\s*[─=]{2,}\s*$')
INJ_RE = re.compile(r'^\s*;\s*.*(【[^】]{2,30}】)')
VAR_RE = re.compile(r'%[^%]{1,40}%')


def unescape(s: str) -> str:
    return s.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')


def title_of(raw: str):
    """注释行 → 标题（不是标题就返回 None）。"""
    if not raw.strip().startswith(';'):
        return None
    m = SEP_RE.match(raw)
    if m:
        return m.group(1)[:44]
    m = INJ_RE.match(raw)
    if m:
        return m.group(0).split('】')[0].lstrip('; ').strip() + '】'
    return None


def main() -> int:
    lines = open(PATH, encoding='utf-8').read().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith('@LLM_BUILD_SYSTEM_PROMPT'))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith('@'))

    segs = []          # [标题, 字数, 条数, 行范围, 变量数]
    cur_title = '（开头：基础设定，无小节）'
    cur_from = start + 1
    cur = [cur_title, 0, 0, None, 0]

    def flush():
        if cur[2]:
            cur[3] = f'{cur_from}-{last[0]}'
            segs.append(tuple(cur[:4]) + (cur[4],))

    last = [start + 1]
    for i in range(start, end):
        raw = lines[i]
        t = title_of(raw)
        if t:
            flush()
            cur_title = t
            cur[1] = cur[2] = cur[4] = 0
            cur_from = i + 1
            cur[0] = t
            continue
        m = LIT_RE.search(raw)
        if m:
            s = unescape(m.group(1))
            cur[1] += len(s)
            cur[2] += 1
            cur[4] += len(VAR_RE.findall(s))
            last[0] = i + 1
    flush()

    total = sum(s[1] for s in segs)
    print(f'文件：{PATH}')
    print(f'函数：@LLM_BUILD_SYSTEM_PROMPT  （行 {start + 1} ~ {end}）')
    print(f'字面量合计：**{total}** 字符（不含 %变量% 的展开内容）')
    print()
    print(f'{"小节":<40}{"字数":>7}{"占比":>7}{"条":>5}{"变量":>5}  行范围')
    print('-' * 88)
    for title, chars, lits, rng, nv in sorted(segs, key=lambda x: -x[1]):
        pct = chars * 100.0 / total if total else 0
        print(f'{title:<40}{chars:>7}{pct:>6.1f}%{lits:>5}{nv:>5}  {rng}')
    print('-' * 88)
    print(f'{"合计":<40}{total:>7}')
    print()
    print('※ 「变量」列 = 该段里插了几个 %…%（那些位置的真实内容没算进字数）。')
    print('※ 想要真实 sysLen ⇒ 看 plugins\\LLMBridge\\debug.log 的 CHAT-SEND。')

    # ── 第二张表：按「注入条件」分类 ─────────────────────────────────
    #  为什么需要：`@LLM_BUILD_SYSTEM_PROMPT` 里有大量**只在特定条件下**才拼上去的段
    #  （开场白 / 互动模式 / 有记忆时 / 睡姦层…）⇒ 光看"合计"会**高估真实 prompt** ✓
    groups = {'总是注入': [0, 0], '开场白那轮': [0, 0], '互动模式': [0, 0],
              '有记忆时': [0, 0], '其它条件': [0, 0]}
    depth = 0
    live = []          # [(depth, 条件文本)] —— 只在 IF 入栈、ENDIF 出栈
    for i in range(start, end):
        s = lines[i].strip()
        # ⚠️ 两条容易写错的规则（第一版两条都写错了，导致分类完全失真）：
        #   ① **`SIF` 不算条件**（它只绑紧随的一行，没有 ENDIF）⇒ 正则要排除它 ⚠️
        #   ② **`ELSE` / `ELSEIF` 不新增嵌套层**（它们是同一层的分支）⇒
        #      只替换当前层的条件文本，**不能 depth += 1** ⚠️
        if re.match(r'^IF(?![A-Za-z_])', s):
            depth += 1
            live.append((depth, s))
        elif re.match(r'^(ELSEIF|ELSE)(?![A-Za-z_])', s):
            # 同层分支：把当前层那条替换掉
            for k in range(len(live) - 1, -1, -1):
                if live[k][0] == depth:
                    live[k] = (depth, s)
                    break
        elif re.match(r'^ENDIF(?![A-Za-z_])', s):
            for k in range(len(live) - 1, -1, -1):
                if live[k][0] == depth:
                    del live[k]
                    break
            depth -= 1
        m = LIT_RE.search(lines[i])
        if not m:
            continue
        n = len(unescape(m.group(1)))
        ctx = ' '.join(x[1] for x in live)
        if 'LLM_OPENING' in ctx:
            k = '开场白那轮'
        elif 'LLM_MODE == 1' in ctx:
            k = '互动模式'
        elif 'LLM_MEMO' in ctx:
            k = '有记忆时'
        elif live:
            k = '其它条件'
        else:
            k = '总是注入'
        groups[k][0] += n
        groups[k][1] += 1

    print()
    print('【按注入条件分类】—— 判断"真实一轮大概多长"用这张')
    print(f'{"条件":<12}{"字数":>7}{"占比":>7}{"条":>5}')
    print('-' * 34)
    tot2 = sum(v[0] for v in groups.values())
    for k, (n, c) in sorted(groups.items(), key=lambda x: -x[1][0]):
        print(f'{k:<12}{n:>7}{n * 100.0 / tot2:>6.1f}%{c:>5}')
    print('-' * 34)
    always = groups['总是注入'][0]
    print(f'★ 真实一轮 ≈ **{always}** 字（总是注入）+ 命中条件的那几段 + %变量% 展开')
    return 0


if __name__ == '__main__':
    sys.exit(main())
