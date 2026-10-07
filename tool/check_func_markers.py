# -*- coding: utf-8 -*-
"""
检查 LLM ERB：函数定义是否被"粘"进了别的行（例如注释行末尾）。

背景（2026-09-16 真事故）：
  一次编辑误删了换行，导致
      ; ── ...（[6] 按钮）──@LLM_SHOW_MEMORY(LLM_CID)
  注释和 `@函数名` 被挤进同一行 ⇒ 引擎**认不出这个函数** ⇒
  函数体里的 `#DIM` 全变成"文件级" ⇒ 刷屏 Lv1/Lv2 警告、**游戏拒绝启动**。

用法：python tool/check_func_markers.py
"""
import re
import sys

PATH = r"ERB\魔改内容\LLM_CONVERSATION.ERB"

# 合法的函数定义行：行首（可有空白）后紧跟 @名称
# ⚠️ 无参函数**不带括号**也是合法的（本文件就有 3 个：
#    `@LLM_TOO_TIRED` / `@LLM_SHOW_API_HINT` / `@LLM_SELFTEST`）
#    ⇒ 所以这里**必须允许没有括号**，否则会误报 ✓
RE_DEF = re.compile(r"^\s*@[A-Za-z_][A-Za-z_0-9]*\s*(\(|$)")
# 行内出现的 @名称( —— 如果不在行首，就是被粘进别的行了
RE_INLINE = re.compile(r"@[A-Za-z_][A-Za-z_0-9]*\s*\(")


def main():
    with open(PATH, encoding="utf-8") as f:
        lines = f.readlines()

    bad = []
    defs = []
    for i, l in enumerate(lines):
        stripped = l.lstrip()
        is_comment = stripped.startswith(";")
        if RE_DEF.match(l):
            defs.append((i + 1, l.strip()))
            continue
        if is_comment:
            continue      # ★ 注释行里引用 `@官方函数(...)` 是正常的，跳过
        # 非注释行里出现 @xxx( —— 可疑（说明可能被粘进了代码行）
        for m in RE_INLINE.finditer(l):
            s = m.start()
            if l[:s].rstrip().endswith("`"):
                continue          # 反引号包裹 = 文档性提及
            bad.append((i + 1, l.rstrip("\n")))
            break

    print("函数定义数: %d" % len(defs))
    print("可疑行（@函数名 出现在非注释行的非行首）: %d" % len(bad))
    for no, txt in bad:
        print("  ⚠️ L%-5d %s" % (no, txt))

    # 顺带查：函数定义行**多参数**形式后面不该再跟东西
    # ⚠️ 无参函数（`@名` 后面什么都没有）是合法的，不能算"多余内容"
    extra = []
    for no, txt in defs:
        sig = txt                         # 例如 @LLM_SHOW_MEMORY(LLM_CID)
        if "(" not in sig:
            continue                      # 无参函数 ⇒ 跳过
        rest = re.sub(r"^@[A-Za-z_][A-Za-z_0-9]*\s*\([^)]*\)\s*", "", sig)
        if rest.strip():
            extra.append((no, txt))
    print("定义行尾部有多余内容: %d" % len(extra))
    for no, txt in extra:
        print("  ⚠️ L%-5d %s" % (no, txt))

    return 1 if (bad or extra) else 0


if __name__ == "__main__":
    sys.exit(main())
