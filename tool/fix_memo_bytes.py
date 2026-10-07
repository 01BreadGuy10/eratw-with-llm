# -*- coding: utf-8 -*-
"""
字节级定点修正（用 raw string，避免转义地狱）。

① `@"\\n\\n\\n` → `@"\\n\\n`   （段首最多空一行；3 个是 Plan B 副作用）
② `###MEMO### [5]` → `###MEMO### [3]`（会变的条目不该标 5）

用法：python tool/fix_memo_bytes.py [--apply]
"""
import sys

PATH = r"ERB\魔改内容\LLM_CONVERSATION.ERB"

A_OLD = r'@"\n\n\n'
A_NEW = r'@"\n\n'
B_OLD = '###MEMO### [5]'
B_NEW = '###MEMO### [3]'


def main():
    apply = "--apply" in sys.argv
    with open(PATH, encoding="utf-8") as f:
        txt = f.read()

    na = txt.count(A_OLD)
    nb = txt.count(B_OLD)
    print("将替换：")
    print("  %-18r → %r   共 %d 处" % (A_OLD, A_NEW, na))
    print("  %-18r → %r   共 %d 处" % (B_OLD, B_NEW, nb))

    if not apply:
        print("\n（dry-run。加 --apply 才写入）")
        return 0

    txt = txt.replace(A_OLD, A_NEW).replace(B_OLD, B_NEW)
    with open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write(txt)
    print("\n✅ 已写入。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
