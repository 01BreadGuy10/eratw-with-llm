# -*- coding: utf-8 -*-
"""加「自由互动诊断」（2026-09-20 用户报告「她不知道自己在睡觉」）。

⚠️ 用户原话：
   「现在负责角色对话那边的llm又有问题了
    感觉像是没有把角色正在睡觉的事实注入进去
    还是说 其实我们调用的有问题」

⚠️ 代码结构看着是对的（三层在 `@LLM_BUILD_SYSTEM_PROMPT` 的 `:3388`），
   所以要**看运行时的值**才能定位 ⇒ 在 [3] 调试信息里加一段 ✓
"""
F = "ERB/魔改内容/LLM_CONVERSATION.ERB"
lines = open(F, encoding="utf-8").read().splitlines()

if any("自由互动诊断" in l for l in lines):
    print("  - 已加过，跳过")
    raise SystemExit

# 插在位置诊断之后
i = next(k for k, l in enumerate(lines) if "季节地图名(GET_MAPNAME,1)" in l)
j = next(k for k in range(i, i + 12) if "上一场对话（LLM_PREV）" in lines[k])
print(f"  插在 行{j+1} 之前")

lines[j:j] = [
    "PRINTFORML 　【自由互动诊断】",
    "PRINTFORML 　　LLM_MODE = {LLM_MODE}   ← 1 = 自由互动",
    "PRINTFORML 　　TARGET = {TARGET}  名字 = %CALLNAME:(TARGET)%",
    "PRINTFORML 　　CFLAG:睡眠 = {CFLAG:(TARGET):睡眠}   ← 1 = 睡着",
    "PRINTFORML 　　TCVAR:烂醉 = {TCVAR:(TARGET):烂醉}",
    "PRINTFORML 　　CFLAG:诶嘿嘿 = {CFLAG:(TARGET):诶嘿嘿}",
    "PRINTFORML 　　LLM_HALFAWAKE = {LLM_HALFAWAKE}",
    "PRINTFORML 　　LLM_AWAKE = {LLM_AWAKE:(TARGET):0}   AWAKE_BOOST = {LLM_AWAKE_BOOST}",
    "PRINTFORML 　　REL_LEVEL = {LLM_REL_LEVEL(TARGET)}   好感 = {CFLAG:(TARGET):好感度}  信赖 = {CFLAG:(TARGET):信赖度}",
    "PRINTFORML 　　三个部位的絶頂余韻：B={BASE:(TARGET):Ｂ絶頂余韻} V={BASE:(TARGET):Ｖ絶頂余韻} C={BASE:(TARGET):Ｃ絶頂余韻}",
    "",
]

open(F, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
print("  ✓ 完成")
