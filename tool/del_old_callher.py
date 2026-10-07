# -*- coding: utf-8 -*-
"""
方案 B 收尾：删掉「重复的旧 ③ 段」（`###CALLHER###` 那段）。

背景：Plan B 已经把 ③ 的内容并进新的合并块（【「他对你的称呼」的成立条件】），
      但旧的 ③ 段还在文件里 ⇒ **内容重复**，而且其中的示例还是**已废弃的
      `###CALLHER###`** ⇒ 模型会被引导去输出一个没人解析的标记 ⚠️

⚠️ 铁律：① 先构造完整新内容再一次性写出 ② 锚点先唯一性确认
用法：python tool/del_old_callher.py [--apply]
"""
import sys

PATH = r"ERB\魔改内容\LLM_CONVERSATION.ERB"
START_MARK = 'REF_PROMPT += @"\\n③ ★ **他对你的称呼**'
END_MARK = 'REF_PROMPT += @"\\n④ ★ **玩家要脱你身上某件衣服**'


def main():
    apply = "--apply" in sys.argv
    with open(PATH, encoding="utf-8") as f:
        lines = f.readlines()

    i_s = [i for i, l in enumerate(lines) if START_MARK in l]
    i_e = [i for i, l in enumerate(lines) if END_MARK in l]
    print("起点命中: %s" % [i + 1 for i in i_s])
    print("终点命中: %s" % [i + 1 for i in i_e])
    if len(i_s) != 1 or len(i_e) != 1:
        print("❌ 锚点不唯一 —— 中止")
        return 1
    s, e = i_s[0], i_e[0]
    if e <= s:
        print("❌ 终点在起点之前 —— 中止")
        return 1

    print("\n将删除 第 %d ~ %d 行（共 %d 行）" % (s + 1, e, e - s))
    print("  首行: %s" % lines[s].rstrip())
    print("  末行(前一行): %s" % lines[e - 1].rstrip())
    print("  保留行: %s" % lines[e].rstrip())

    if not apply:
        print("\n（dry-run。加 --apply 才写入）")
        return 0

    new_lines = lines[:]
    del new_lines[s:e]
    with open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write("".join(new_lines))
    print("\n✅ 已删除。行数 %d -> %d" % (len(lines), len(new_lines)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
