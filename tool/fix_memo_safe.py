# -*- coding: utf-8 -*-
"""
保守版：只做**无歧义**的定点修正（2026-09-16）。

⚠️ 上一版（normalize_memo_block.py）**没执行** —— 它会把所有注入行的缩进拉平、
   还把段内 `\\n` 改成 `\\n\\n`（每行之间都空一行），**会破坏排版**。
   ⇒ 教训：**格式归一不能靠一条正则通吃**，`\\n` 与 `\\n\\n` 是按语义分配的。

本脚本只做这三件**确定性**的事：
  ① `@"\\n\\n\\n` → `@"\\n\\n`（段首最多空一行；3 个是 Plan B 的副作用）
  ② `###MEMO### [5]` → `###MEMO### [3]`（会变的条目不该标 5）
  ③ 定位并打印 `[5]` 的其它出现，人工确认

用法：python tool/fix_memo_safe.py [--apply] [--show]
"""
import sys

PATH = r"ERB\魔改内容\LLM_CONVERSATION.ERB"
START = "【必须记住的事（写成记忆"
END = "你还没熟到主动给人起外号的地步"


def main():
    apply = "--apply" in sys.argv
    show = "--show" in sys.argv

    with open(PATH, encoding="utf-8") as f:
        lines = f.readlines()

    i_s = [i for i, l in enumerate(lines) if START in l]
    i_e = [i for i, l in enumerate(lines) if END in l]
    if len(i_s) != 1 or len(i_e) != 1:
        print("❌ 锚点不唯一 —— 中止")
        return 1
    s, e = i_s[0], i_e[0]
    print("处理范围: 第 %d ~ %d 行" % (s + 1, e + 1))

    new = []
    n1 = n2 = 0
    for k in range(s, e + 1):
        l = lines[k]
        o = l
        if l.lstrip("\t ").startswith("REF_PROMPT"):
            if '@"\\n\\n\\n' in l:
                l = l.replace('@"\\n\\n\\n', '@"\\n\\n')
                n1 += 1
            if "###MEMO### [5]" in l:
                l = l.replace("###MEMO### [5]", "###MEMO### [3]")
                n2 += 1
        new.append(l)

    print("  `\\n\\n\\n` → `\\n\\n` : %d 处" % n1)
    print("  `[5]` → `[3]`      : %d 处" % n2)
    if show:
        for a, b in zip(lines[s:e + 1], new):
            if a != b:
                print("  - %s" % a.rstrip())
                print("  + %s" % b.rstrip())

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
