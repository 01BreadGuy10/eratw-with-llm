# -*- coding: utf-8 -*-
"""
扫描：**被当表达式调用、但定义处没有 `#FUNCTION(S)` 标记**的函数。

背景（2026-09-16 真事故）：
  我在 prompt 侧写了 `IF LLM_CALLME_SHOW(LLM_CID) == ""`（表达式形式），
  但那个函数定义处**没有 `#FUNCTION`** ⇒ 游戏报
  `Lv2: 对未被标记为 #FUNCTION 的函数进行了行内函数形式的调用` ⚠️
  这类错**三个静态检查器都查不出**（`check_func_markers` 只管定义行是否完整）——
  只有引擎报。所以补这个专项扫描。

规则（本项目已有结论，见 `LLM_ERB语法避坑.md`）：
  · `#FUNCTION` / `#FUNCTIONS` ⇒ **只能用表达式调用**，不能 `CALL`
  · 无标记                     ⇒ 必须 `CALL` + 读 `RESULT`
  ⚠️ 例外：`RESULT = 函数(...)` 这种**也是表达式调用** ✓
  ⚠️ 例外：`EXISTFUNCTION(@"名")` / `TRYCALLFORM` 等**引擎内建**不算调用

用法：python tool/check_call_style.py
"""
import os
import re
import sys

PATH = r"ERB\魔改内容\LLM_CONVERSATION.ERB"

# 引擎内建 / 官方的函数名（不在本文件定义，别误报）
BUILTIN_HINT = (
    "EXISTFUNCTION", "EXISTMETH", "GETMAPID", "GETMAPNAME", "GETPLACENAME",
    "HASSTANDING", "MONEYNAME", "DAYNAME", "CHARA_HOLIDAY", "GET_JOBNAME",
    "YOUBI_MATCH", "GROUP_MATCH", "TOSTR", "TOINT", "STRLENS", "STRFIND",
    "SUBSTRING", "TRIM_STRING", "REPLACE", "GETBIT", "SETBIT", "CLEARBIT",
    "GETPALAMLV", "GROUPMATCH", "MAX", "MIN", "LIMIT", "ABS", "SQRT",
    "RAND", "RECOVER_PERMIL", "IN_HOME", "AT_HOME", "BATHROOM", "BEDROOM",
    "IN_TOILET", "OUTROOF", "IS_GAP_GUEST", "IS_DATING_WITH_PLAYER",
    "TIME_PROGRESS", "CHK_DATENOW", "GET_WEATHER", "PERSONALITY_TYPE",
    "MUSIC_ABLE", "SOURE_DOWNBASE", "SOURCE_DOWNBASE", "PRINT_FIGURE",
    "PRINT_FACE", "SET_KOJO_COLOR", "BUILD_COM_BUTTON_HTML",
    "Qol_XpProgressToNextLevel", "CALC_RANK", "GET_RANK",
)


def main():
    with open(PATH, encoding="utf-8") as f:
        lines = f.readlines()

    # ① 收集定义 + 是否带 #FUNCTION(S)
    funcs = {}          # name -> True(有#FUNCTION) / False(无)
    cand = []           # (行号, 函数名)
    for i, l in enumerate(lines):
        s = l.strip()
        m = re.match(r'^@([A-Za-z_][A-Za-z_0-9]*)\s*(\(|$)', s)
        if m:
            name = m.group(1)
            has = False
            for k in range(i + 1, min(i + 8, len(lines))):
                t = lines[k].strip()
                if t.startswith("#FUNCTION"):
                    has = True
                    break
                if t.startswith("@") or (t and not t.startswith("#")):
                    break
            funcs[name] = has
        # ② 找"表达式形式"的调用：不是 CALL / 不是定义行 / 不是注释
        if s.startswith(";") or s.startswith("@"):
            continue
        for m2 in re.finditer(r'(?<![A-Za-z_0-9@])([A-Za-z_][A-Za-z_0-9]*)\s*\(', l):
            nm = m2.group(1)
            # 排除 CALL 形式
            before = l[:m2.start()]
            if re.search(r'\bCALL\s*$', before):
                continue
            cand.append((i + 1, nm, l.rstrip()))

    print("本文件定义的函数: %d 个（带 #FUNCTION 的 %d 个）"
          % (len(funcs), sum(1 for v in funcs.values() if v)))

    bad = []
    for no, nm, txt in cand:
        if nm not in funcs:
            continue                       # 引擎内建 / 官方函数
        if not funcs[nm]:
            bad.append((no, nm, txt))

    print("\n★ **被当表达式用、但没标 #FUNCTION** 的: %d 处" % len(bad))
    for no, nm, txt in bad:
        print("  L%-6d %s() … %s" % (no, nm, txt.strip()[:90]))

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
