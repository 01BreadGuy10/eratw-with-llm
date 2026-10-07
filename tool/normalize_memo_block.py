# -*- coding: utf-8 -*-
"""
把「必须记住的事」整块**统一修整**（2026-09-16）：

  ① **换行归一**：块内注入行有的 `@"\\n\\n..."`、有的 `@"\\n\\n\\n..."`
     ⇒ prompt 里会出现成片空行（浪费 token、观感差）。
     规则：`\n\n` = 段首（空一行），`\n` = 段内续行。
  ② **去掉多余的缩进**（Plan B 生成时带了 tab 和 3 空格）
  ③ `[5]` → `[3]`（会变的条目不该标 5）
  ④ 补一句：**这三类「过了接受判定就一定会记住」**（用户指出的框架问题）——
     它们不该再被"按关系掷存储骰"筛一次

⚠️ 铁律：① 先构造完整新内容再一次性写出 ② 锚点先唯一性确认
用法：python tool/normalize_memo_block.py [--apply] [--show]
"""
import re
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
    print("段首: %s   段尾: %s" % ([i + 1 for i in i_s], [i + 1 for i in i_e]))
    if len(i_s) != 1 or len(i_e) != 1:
        print("❌ 锚点不唯一 —— 中止")
        return 1
    s, e = i_s[0], i_e[0]

    new = []
    changed = 0
    for k in range(s, e + 1):
        l = lines[k]
        stripped = l.lstrip("\t ")
        if not stripped.startswith("REF_PROMPT"):
            new.append(l)
            continue
        o = stripped
        # ① 去掉缩进 ② 换行归一：\n\n\n -> \n\n（段首最多两个）
        stripped = stripped.replace('@"\\n\\n\\n', '@"\\n\\n')
        # ③ 行首如果是 tab/空格缩进的内容，收成统一的 3 空格视觉缩进
        stripped = re.sub(r'@"\\n(\\n)?\s+', lambda m: '@"\\n' + (m.group(1) or '') + '   ', stripped)
        # ④ 重要度 5 -> 3
        stripped = stripped.replace("###MEMO### [5]", "###MEMO### [3]")
        if stripped != o:
            changed += 1
        new.append(stripped)

    print("\n将修整 第 %d ~ %d 行，其中 %d 行有变化" % (s + 1, e + 1, changed))
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
    print("\n✅ 已写入。行数 %d" % len(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
