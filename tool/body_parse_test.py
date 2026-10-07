# -*- coding: utf-8 -*-
"""`###BODY###` 解析链路验证 —— 纯代码、零内容风险。

为什么做这个（对应 `tool\\TODO_自由互动.md` 第 ③ 项）：
    用户实测症状是「计量表 6 条全显示，但**全是 0**」。
    两种可能：① 模型没输出这个标记；② 输出了但**解析器吃不下**。
    只靠玩游戏分不出来 ⇒ 这里把解析链路**逐条喂样例**，直接判定。

复刻的两段代码（`ERB\\魔改内容\\LLM_INTIMATE.ERB`）：
    `@LLM_INT_PARSE_BODY`  —— 从回复里抠出 `###BODY###` 那一行
    `@LLM_INT_GETVAL`      —— 从 `B+8,V+3` 里取某个字母的增量（**含去前导 `+` 的兼容**）
    `@LLM_INT_APPLY_BODY`  —— 分号切分：前 = 部位增量，后 = 觉醒增量

⚠️ 这是**复刻**，不是调用游戏引擎 ⇒ 结论是"按代码逻辑应当如此"。
   与游戏实际不一致时，以游戏为准（但那时就是代码有别的坑了）✓
"""
import re
import sys

# ── 复刻 @LLM_INT_PARSE_BODY ──────────────────────────────────────────
TAG = "###BODY###"


def erb_strlens(s: str) -> int:
    """Emuera 的 STRLENS 数的是**字节**（中文 1 字 = 2）✓"""
    return len(s.encode('utf-8'))


def parse_body(text: str) -> str:
    """等价于 @LLM_INT_PARSE_BODY：抠出标记后到行尾的内容。"""
    pos = text.find(TAG)
    if pos < 0:
        return ""
    rest = text[pos + len(TAG):]
    nl = rest.find("\n")
    if nl >= 0:
        rest = rest[:nl]
    return rest.strip()


# ── 复刻 @LLM_INT_GETVAL ─────────────────────────────────────────────
LETTERS = ['B', 'V', 'C', 'A', 'M']


def getval(s: str, ch: str):
    """等价于 @LLM_INT_GETVAL。返回 (值, 说明)。"""
    i = s.find(ch)
    if i < 0:
        return None, '该部位没出现'
    start = i + 1
    comma = s.find(",", start)
    seg = s[start:] if comma < 0 else s[start:comma]
    raw = seg
    # ★ 去前导 '+'（这就是"标记收到了、值却全是 0"的修复点）
    stripped = seg[1:] if seg.startswith('+') else seg
    try:
        # Emuera 的 TOINT：不认前导 '+'，不认非数字前缀
        if stripped.startswith('-'):
            v = -int(stripped[1:]) if stripped[1:].isdigit() else 0
        elif stripped.isdigit():
            v = int(stripped)
        else:
            v = 0
    except Exception:
        v = 0
    note = f'子串="{raw}"'
    if raw.startswith('+') and v != 0:
        note += ' → 靠"去前导+"救回来了 ✓'
    elif raw.startswith('+'):
        note += ' → ⚠️ 去"+"后仍解析失败'
    if v == 0 and stripped not in ('', '0'):
        note += ' → ⚠️ 非零子串却得 0'
    return v, note


# ── 复刻 @LLM_INT_APPLY_BODY 的切分 ───────────────────────────────────
def split_body(tag_text: str):
    i = tag_text.find(";")
    if i < 0:
        return tag_text, "0", "无分号 ⇒ 觉醒增量按 0（代码里写 LLM_AK = \"0\"）"
    return tag_text[:i], tag_text[i + 1:], ""


# ── 样例（前 3 条是**格式说明里的原例**，其余是边界）──────────────────
CASES = [
    ("标准（提示词原例）", "台词在这\n###BODY###B+8,V+3,C+2;A+5"),
    ("单部位 + 觉醒", "…\n###BODY###B+12;6"),
    ("全 0（轻碰）", "…\n###BODY###V+0;0"),
    ("标记后为空", "…\n###BODY###"),
    ("标记后只有空格", "…\n###BODY###   "),
    ("完全没有标记", "她只是皱了皱眉，什么都没写。"),
    ("小写字母（不合格式）", "…\n###BODY###b+8;3"),
    ("负数（应该是 0~15）", "…\n###BODY###C-3;2"),
    ("两位数字", "…\n###BODY###B+15;12"),
    ("超范围 3 位数", "…\n###BODY###B+150;99"),
    ("多行混排（标记不在最后一行）", "…\n###BODY###B+8;4\n###DELTA### 0,0,0,0,0,0"),
    ("部位顺序颠倒", "…\n###BODY###A+5,B+8;C+2"),
    ("缺分号", "…\n###BODY###B+8,V+3"),
    ("分号后有空格", "…\n###BODY###B+8; 4"),
    ("中文全角分号", "…\n###BODY###B+8；4"),
    # ── ★ 下面是 2026-09-27「评审互演」里**故意埋的 4 行**，用来复核评分表 ──
    ("【埋点T1】缺分号（真违规）", "…\n###BODY###B+6;C+1"),
    ("【埋点T2】正常（评审判违规=误判）", "…\n###BODY###B+11,V+2;3"),
    ("【埋点T3】觉醒值带前导+（合法，且是刚修的 bug 场景）", "…\n###BODY###A+7;+6"),
    ("【埋点T4】标记为空（真违规）", "…\n###BODY###"),
]


def main() -> int:
    print('=' * 84)
    print('`###BODY###` 解析链路验证（复刻 LLM_INTIMATE.ERB 的三段逻辑）')
    print('=' * 84)
    for title, text in CASES:
        tag = parse_body(text)
        parts, ak, aknote = split_body(tag)
        print(f'\n■ {title}')
        print(f'  回复原文: {text.replace(chr(10), "⏎")}')
        print(f'  ① 抠出的标记内容: 「{tag}」  （STRLENS = {erb_strlens(tag)}）')
        if tag == "":
            print('  ⇒ 结果：**部位全 0 / 觉醒 0** —— 等于"这一轮什么都没发生"')
            print('     ⚠️ 与"标记缺失"表现相同 ⇒ 光看计量表**分不出**这两种情况')
            continue
        hits = []
        for ch in LETTERS:
            v, note = getval(parts, ch)
            if v is not None:
                hits.append(f'{ch}={v}（{note}）')
        print(f'  ② 分号前「{parts}」 / 分号后「{ak}」  {aknote}')
        print(f'  ③ 部位取值：' + ('；'.join(hits) if hits else '⚠️ **一个部位都没解析出来**'))
        try:
            akv = int(ak.strip().lstrip('+'))
        except Exception:
            akv = 0
        print(f'  ④ 觉醒增量 = {akv}')
    print()
    print('=' * 84)
    print('结论要点')
    print('=' * 84)
    print('· 前导 `+` 确实需要去掉 —— 否则 `B+8` 会解析成 **0**（这正是待验的那个假设）')
    print('· 但 **`+` 的修复只对"分号前"生效**：分号后的觉醒增量在 `@LLM_INT_APPLY_BODY` 里')
    print('  走的是 `TOINT(LLM_AK)`，**没有去 `+`** ⇒ 模型若写 `;+5` 会得 0 ⚠️')
    print('  （★ 2026-09-27 **已修**：`LLM_INTIMATE.ERB:178-179` 加了去前导 `+`）')
    print('· "标记缺失" 与 "标记为空" 表现完全一样（都是全 0）⇒ 计量表分不出来，')
    print('  必须看 `[6]` 界面的「最近一次 ###BODY### 解析」才能区分 ✓')
    print()
    print('── 关于「埋点 T1~T4」的裁定（2026-09-27 用本脚本核对过）──')
    print('  T1 `B+6;C+1`      ⇒ **真违规**：分号后是 `C+1`，TOINT 解析失败 ⇒ 觉醒值 = 0')
    print('                       （部位只读到 B=6；C 的增量被当成无效的觉醒字段丢掉了）')
    print('  T2 `B+11,V+2;3`   ⇒ **合法**（B=11, V=2, 觉醒=3）⇒ 评审判"违规"是**误判** ⚠️')
    print('                       原因：它以为分号后必须带部位代号 —— 那是错的')
    print('  T3 `A+7;+6`       ⇒ **合法**（A=7, 觉醒=6；去前导 `+` 生效）⇒ 评审判"违规"是**误判** ⚠️')
    print('                       它以为 `+6` 缺部位代号 ⇒ 把"觉醒值"和"部位值"的语法搞混了')
    print('  T4 标记为空        ⇒ **真违规**（规则写"每轮必须输出这一行"）')
    print('  ⇒ 评审命中 2 / 4（T1、T4），误判 2 / 4（T2、T3）⚠️')
    print('  ⇒ 教训：**别用"LLM 评审"当唯一判据** —— 连 12 条明写规则都能读错一半；')
    print('     涉及格式/数值的判定，**一律用本脚本这种确定性检查** ✓')
    return 0


if __name__ == '__main__':
    sys.exit(main())
