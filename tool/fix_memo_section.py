# -*- coding: utf-8 -*-
"""
修正「必须记住的事」这一段的两个问题（2026-09-16）：

  ① **多了一层换行**：每行都是 `@"\\n\\n…"`（应为 `@"\\n…"`），
     段首还多出一个 ⇒ prompt 里会出现**成片空行**（浪费 token、观感差）
  ② **重要度从 5 降到 3**（用户反馈）：
     「身份条目这些东西的重要度为 5 太高了」
     ⇒ 称呼 / 身份是**会变**的东西，标 5 等于"永不丢 + 不可被顶掉"，
       换一次就两条并存 ⇒ **冗余记忆** ⚠️
     ⇒ 改标 3；**重复由代码的「同类替换」清**（见 `@LLM_MEMO_ADD`），
       不靠"重要度 5 焊死" ✓

  ③ 顺手把这一段的缩进去掉（Plan B 生成时带了 tab，和其他注入行不一致）

⚠️ 铁律：① 先构造完整新内容再一次性写出 ② 锚点先唯一性确认
用法：python tool/fix_memo_section.py [--apply] [--show]
"""
import re
import sys

PATH = r"ERB\魔改内容\LLM_CONVERSATION.ERB"
Q = '"'
START = "【必须记住的事（写成记忆"
END = "⚠️ **只写你确实知道的内容**"


def main():
    apply = "--apply" in sys.argv
    show = "--show" in sys.argv

    with open(PATH, encoding="utf-8") as f:
        lines = f.readlines()

    i_s = [i for i, l in enumerate(lines) if START in l]
    i_e = [i for i, l in enumerate(lines) if END in l]
    print("段首命中: %s" % [i + 1 for i in i_s])
    print("段尾命中: %s" % [i + 1 for i in i_e])
    if len(i_s) != 1 or len(i_e) != 1:
        print("❌ 锚点不唯一 —— 中止")
        return 1
    s, e = i_s[0], i_e[0]
    if e < s:
        print("❌ 端点顺序异常 —— 中止")
        return 1

    new = []
    for k in range(s, e + 1):
        l = lines[k]
        # ① 去掉行首缩进（这个块的注入行应顶格）
        l2 = l.lstrip("\t ")
        if not l2.startswith("REF_PROMPT"):
            new.append(l)          # 注释行原样保留
            continue
        # ② 把 @"\n\n...  收成 @"\n...
        l2 = l2.replace('@"\\n\\n\\n', '@"\\n')
        l2 = re.sub(r'@"\\n\\n', '@"\\\\n', l2)
        # ③ 重要度 5 -> 3（只改这一段的措辞）
        l2 = l2.replace("[5]", "[3]")
        l2 = l2.replace(
            "而且**重要度填 3**（填 5 系统会永久保留、不会被淡忘）：",
            "而且**重要度填 3** —— ⚠️ **别填 5**："
            "这几条都是**会变**的（称呼会改、身份会补充），"
            "填 5 就改不掉了。填 3 即可，系统会**自动用新的顶掉旧的那条**：")
        l2 = l2.replace("（写成记忆 · 重要度 5）", "（写成记忆 · 重要度 3）")
        new.append(l2)

    print("\n将重写 第 %d ~ %d 行（%d 行）" % (s + 1, e + 1, e - s + 1))
    if show:
        for a, b in zip(lines[s:e + 1], new):
            mark = "  " if a == b else "✎ "
            print("%s- %s" % (mark, a.rstrip()))
            if a != b:
                print("%s+ %s" % (mark, b.rstrip()))

    if not apply:
        print("\n（dry-run。加 --apply 才写入）")
        return 0

    out = lines[:]
    out[s:e + 1] = new
    with open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write("".join(out))
    print("\n✅ 已写入。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
