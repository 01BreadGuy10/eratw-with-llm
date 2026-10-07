# -*- coding: utf-8 -*-
"""
修复 @LLM_PARSE_NOTE：清引号后没有重新 TRIM / 判空。

⚠️ 铁律①：先构造完整新内容再一次性写出（new = lines[:] 然后改 new）
⚠️ 铁律②：锚点先用唯一性确认

用法：python tool/fix_parse_note.py [--apply] [--show]
"""
import sys

PATH = r"ERB\魔改内容\LLM_CONVERSATION.ERB"

MARK_TRIM = "TRIM_STRING(LLM_P:0)"
MARK_TAIL = "SIF STRLENS(REF_OUT) > 30"


def main():
    apply = "--apply" in sys.argv
    show = "--show" in sys.argv

    with open(PATH, encoding="utf-8") as f:
        lines = f.readlines()

    # ── 按"包含标记"定位，不靠精确字面量 ──
    idx_trim = [i for i, l in enumerate(lines) if MARK_TRIM in l]
    idx_tail = [i for i, l in enumerate(lines) if MARK_TAIL in l]
    print("含 %r 的行: %s" % (MARK_TRIM, [i + 1 for i in idx_trim]))
    print("含 %r 的行: %s" % (MARK_TAIL, [i + 1 for i in idx_tail]))

    if show:
        lo = max(0, idx_trim[-1] - 1)
        hi = min(len(lines), idx_tail[-1] + 3)
        print("\n── 该函数尾部真实内容（repr）──")
        for i in range(lo, hi):
            print("  L%-5d %s" % (i + 1, repr(lines[i])))
        return 0

    if len(idx_tail) != 1:
        print("❌ 尾部标记不唯一 —— 中止")
        return 1
    # ⚠️ `TRIM_STRING(LLM_P:0)` 在文件里有**两处**：
    #    · 6668 = `@LLM_PARSE_MEMO`（那是好的，不要动！）
    #    · 7139 = `@LLM_PARSE_NOTE`（★ 要修的）
    #    ⇒ 取**紧邻尾部标记之前**的那一处，而不是硬编码行号 ✓
    cand = [i for i in idx_trim if i < idx_tail[0]]
    if not cand:
        print("❌ 找不到目标处 —— 中止")
        return 1
    at = cand[-1]
    end = idx_tail[0]           # SIF 那一行
    block = lines[at:end + 2]   # 含 SIF 与下面一行

    print("\n将替换 第 %d ~ %d 行：" % (at + 1, end + 2))
    for l in block:
        print("   - " + repr(l))

    Q = '"'
    new_block = [
        lines[at],                                              # TRIM_STRING(LLM_P:0)
        "REF_OUT '= REPLACE(REF_OUT, " + Q + "\\\\" + Q + ", " + Q + Q + ")\n",
        "REF_OUT '= REPLACE(REF_OUT, " + Q + "「" + Q + ", " + Q + Q + ")\n",
        "REF_OUT '= REPLACE(REF_OUT, " + Q + "」" + Q + ", " + Q + Q + ")\n",
        "; ⚠️⚠️ **清掉引号之后必须再 TRIM 一次，然后判空**（2026-09-16 修）——\n",
        ";    实测：模型有时写成 `###CALLHER###" + Q + Q + "`（标记后直接跟两个引号）。\n",
        ";    原顺序是「先 TRIM、再清引号」⇒ 清完引号没有第二次 TRIM ⇒\n",
        ";    抠出来的是 " + Q + Q + " 这两个字符 ⇒ 它不等于空串 ⇒\n",
        ";      ① 被当成「解析成功」写进槽（槽里存下 " + Q + Q + "）\n",
        ";      ② 回执每轮都误触发（用户实测：每轮都会出现）\n",
        ";    ⇒ 正确顺序：清引号 → 再 TRIM → 再判空 ✓\n",
        "REF_OUT '= TRIM_STRING(REF_OUT)\n",
        "SIF REF_OUT == " + Q + Q + "\n",
        "\tRETURN\n",
        "SIF STRLENS(REF_OUT) > 30\n",
        "\tREF_OUT = " + Q + Q + "\n",
    ]
    print("   ---- 替换为 ----")
    for l in new_block:
        print("   + " + repr(l))

    if not apply:
        print("\n（dry-run，未写盘。加 --apply 才写入）")
        return 0

    new_lines = lines[:]                                  # ★ 铁律①
    new_lines[at:end + 2] = new_block
    with open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write("".join(new_lines))
    print("\n✅ 已写入。行数 %d -> %d" % (len(lines), len(new_lines)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
