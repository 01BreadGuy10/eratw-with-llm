# -*- coding: utf-8 -*-
"""
给「清引号后没重新 TRIM / 判空」这个缺陷收尾 —— 把 `@LLM_PARSE_MEMO` 也补上。

⚠️ 铁律①：先构造完整新内容再一次性写出（new = lines[:] 然后改 new）
⚠️ 铁律②：锚点先做唯一性确认

背景（2026-09-16 实测定案）：
  两个解析函数的顺序都是「先 TRIM、再清引号」⇒ 清完引号**没有第二次 TRIM** ⇒
  模型写成 `###TAG###""` 时抠出来的是 `""` 这两个字符 ⇒ 不等于空串 ⇒
  ① 被当成解析成功写进槽  ② 回执每轮误触发。
  `@LLM_PARSE_NOTE`(L7139) 已修；本脚本补 `@LLM_PARSE_MEMO`(L6668)。

用法：python tool/fix_parse_memo.py [--apply] [--show]
"""
import sys

PATH = r"ERB\魔改内容\LLM_CONVERSATION.ERB"
Q = '"'

MARK_TRIM = "TRIM_STRING(LLM_P:0)"
MARK_TAIL = "SIF STRLENS(REF_MEMO) > 40"


def main():
    apply = "--apply" in sys.argv
    show = "--show" in sys.argv

    with open(PATH, encoding="utf-8") as f:
        lines = f.readlines()

    idx_trim = [i for i, l in enumerate(lines) if MARK_TRIM in l]
    idx_tail = [i for i, l in enumerate(lines) if MARK_TAIL in l]
    print("含 %r: %s" % (MARK_TRIM, [i + 1 for i in idx_trim]))
    print("含 %r: %s" % (MARK_TAIL, [i + 1 for i in idx_tail]))

    if show:
        lo = max(0, idx_trim[0] - 1)
        hi = min(len(lines), idx_tail[0] + 3)
        print("\n── @LLM_PARSE_MEMO 尾部真实内容 ──")
        for i in range(lo, hi):
            print("  L%-5d %s" % (i + 1, repr(lines[i])))
        return 0

    if len(idx_tail) != 1:
        print("❌ 尾部标记不唯一 —— 中止")
        return 1
    cand = [i for i in idx_trim if i < idx_tail[0]]
    if not cand:
        print("❌ 找不到目标处 —— 中止")
        return 1
    at = cand[0]                      # ★ MEMO 用**第一**处（NOTE 用最后一处）
    end = idx_tail[0]

    block = lines[at:end + 2]
    print("\n将替换 第 %d ~ %d 行" % (at + 1, end + 2))
    for l in block:
        print("   - " + repr(l))

    new_block = [
        lines[at],
        "REF_MEMO '= REPLACE(REF_MEMO, " + Q + "\\\\" + Q + ", " + Q + Q + ")\n",
        "REF_MEMO '= REPLACE(REF_MEMO, " + Q + "「" + Q + ", " + Q + Q + ")\n",
        "REF_MEMO '= REPLACE(REF_MEMO, " + Q + "」" + Q + ", " + Q + Q + ")\n",
        "; ⚠️ **清掉引号之后必须再 TRIM 一次、再判空**（2026-09-16 修）——\n",
        ";    与 `@LLM_PARSE_NOTE` 同一个缺陷（先 TRIM 后清引号 ⇒ 清完没再判空）⇒\n",
        ";    模型写 `###MEMO###" + Q + Q + "` 时会存下一条内容为 " + Q + Q + " 的垃圾记忆 ⚠️\n",
        "REF_MEMO '= TRIM_STRING(REF_MEMO)\n",
        "SIF REF_MEMO == " + Q + Q + "\n",
        "\tRETURN\n",
        "SIF STRLENS(REF_MEMO) > 40\n",
        "\tREF_MEMO = " + Q + Q + "\n",
    ]
    print("   ---- 替换为 ----")
    for l in new_block:
        print("   + " + repr(l))

    if not apply:
        print("\n（dry-run，未写盘。加 --apply 才写入）")
        return 0

    new_lines = lines[:]                                   # ★ 铁律①
    new_lines[at:end + 2] = new_block
    with open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write("".join(new_lines))
    print("\n✅ 已写入。行数 %d -> %d" % (len(lines), len(new_lines)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
