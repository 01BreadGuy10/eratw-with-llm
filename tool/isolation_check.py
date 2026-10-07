# -*- coding: utf-8 -*-
"""隔离自检（可复用工具）—— 每加一个互动功能就跑一次。

⚠️ 用户问：「我后面想加自由互动特有的一些东西也能保持隔离对吧
            比如摸屁股摸胸涨高潮进度条」

⇒ 这个脚本是**规则的机器检查** ✓
   以后每加互动功能跑它一次，就知道有没有破隔离 ✓

规则：
  ① 互动独有逻辑 ⇒ 全写在 `LLM_INTIMATE.ERB`（删文件即消失）
  ② 原文件里只留**调用点**
  ③ 互动独有变量 ⇒ 尽量在模块里声明（删文件即消失）
     ⚠️ 只有原文件也要读的才放 `.ERH`，且**必须追加在末尾**（存档按声明顺序存偏移）
  ④ 存盘数值 ⇒ 优先用**游戏现成的**（BASE:絶頂余韻 / CFLAG:えへへ / TCVAR:爛酔）
  ⑤ `LLM_MODE` 是唯一的模式开关

⚠️ 已知无害的例外（白名单）：
   · `LLM_INT_PARSE_BODY` —— 自由对话时她不会输出 `###BODY###` ⇒ 结果为空
   · `LLM_INT_APPLY_BODY` —— 上一行有 `SIF LLM_BODY_TAG != ""` 挡着
   · `LLM_CHARA_FORM`     —— **有意**：身体特征对日常对话也有用（用户要求「加强」）
   · `LLM_INT_HALFAWAKE_TEXT` —— 被外层 `IF LLM_MODE == 1` 包着
"""
import os, re

F = "ERB/魔改内容/LLM_CONVERSATION.ERB"
B = "ERB/魔改内容/LLM_CHAT_BRIDGE.ERB"
D = "ERB/魔改内容/LLM_INTIMATE.ERB"
E = "ERB/魔改内容/LLM_KOJO.ERH"

# 已知无害、不需要 LLM_MODE 守卫的（附理由）
NO_GUARD_OK = {
    "LLM_INT_PARSE_BODY": "自由对话时不会输出 ###BODY### ⇒ 结果为空",
    "LLM_INT_APPLY_BODY": "上一行有 SIF LLM_BODY_TAG != \"\" 挡着",
    "LLM_CHARA_FORM": "有意：身体特征对日常对话也有用",
    "LLM_INT_HALFAWAKE_TEXT": "被外层 IF LLM_MODE == 1 包着",
    "LLM_INT_RESET": "无条件复位，删模块后自动变成空操作",
}

cls = []
def ok(m): cls.append(("OK", m))
def warn(m): cls.append(("WARN", m))
def bad(m): cls.append(("BAD", m))

conv = open(F, encoding="utf-8").read().splitlines()
brg = open(B, encoding="utf-8").read().splitlines()
mod = open(D, encoding="utf-8").read().splitlines()
erh = open(E, encoding="utf-8").read().splitlines()

# ① 互动函数是否只在模块里定义
mod_funcs = set(re.findall(r'^@(\w+)', "\n".join(mod), re.M))
conv_funcs = set(re.findall(r'^@(\w+)', "\n".join(conv), re.M))
inter_names = {n for n in (mod_funcs | conv_funcs) if n.startswith("LLM_INT_") or
               n in ("LLM_SCENE_WRITE", "LLM_PRINT_SCENE", "LLM_CHARA_FORM")}
in_conv = inter_names & conv_funcs
print("=== ① 互动函数在哪定义 ===")
if in_conv:
    bad(f"原文件里还定义着：{sorted(in_conv)} ⇒ 删模块删不掉")
else:
    ok(f"全部 {len(inter_names)} 个互动函数都只在模块里定义")

# ② 原文件里的互动 CALL + 守卫
calls = []
for i, l in enumerate(conv, 1):
    m = re.match(r'\s*CALL\s+(LLM_INT_\w+|LLM_SCENE_WRITE|LLM_PRINT_SCENE|LLM_CHARA_FORM)', l)
    if m:
        calls.append((i, m.group(1), l.strip()))

print()
print("=== ② 原文件里的 CALL 与守卫 ===")
for ln, fn, src in sorted(calls):
    guard = None
    for k in range(max(0, ln - 13), ln - 1):
        s = conv[k].strip()
        if s.startswith(";"):
            continue
        if "LLM_MODE" in s:
            guard = (k + 1, s)
    if guard:
        print(f"  {ln:>5} {fn:<26} ✓ 行{guard[0]}: {guard[1][:30]}")
    elif fn in NO_GUARD_OK:
        print(f"  {ln:>5} {fn:<26} ~ 白名单：{NO_GUARD_OK[fn]}")
    else:
        print(f"  {ln:>5} {fn:<26} ⚠️ 无守卫")
        warn(f"行{ln} 的 {fn} 没有 LLM_MODE 守卫")

# ③ 互动独有变量
mod_vars = set(re.findall(r'#DIMS?\s+(LLM_[A-Z_0-9]+)', "\n".join(mod)))
erh_vars = set(re.findall(r'#DIMS?\s+(?:CHARADATA\s+)?(?:SAVEDATA\s+)?(LLM_[A-Z_0-9]+)', "\n".join(erh)))
shared = mod_vars & erh_vars
print()
print("=== ③ 互动变量 ===")
print(f"  模块内声明 {len(mod_vars)} 个（删文件即消失）")
for v in sorted(shared):
    if any(re.search(rf'\b{v}\b', l) for l in conv if not l.strip().startswith(";")):
        print(f"  {v}: 原文件确实要读 ⇒ 放 .ERH 是对的 ✓")
    else:
        print(f"  {v}: ⚠️ 原文件并不读它 ⇒ 其实可以搬进模块，删得更干净")
        warn(f"{v} 可以搬进模块")

# ④ SAVEDATA / 末尾声明检查
print()
print("=== ④ .ERH 末尾结构（存档兼容）===")
sav = [i for i, l in enumerate(erh) if "SAVEDATA" in l and l.strip().startswith("#")]
tail = [i for i, l in enumerate(erh) if i > (sav[-1] if sav else 0)]
nondecl = [(i + 1, erh[i].strip()) for i in tail
           if erh[i].strip() and not erh[i].strip().startswith(("#", ";"))]
print(f"  SAVEDATA 共 {len(sav)} 个，最后一个在行 {sav[-1]+1}（文件 {len(erh)} 行）")
if nondecl:
    bad(f"最后一个 SAVEDATA 之后还有非声明内容：{nondecl[:3]}")
else:
    ok("最后一个 SAVEDATA 之后全是声明 ⇒ 追加新变量安全")

print()
print("=" * 74)
nbad = sum(1 for t, _ in cls if t == "BAD")
nwarn = sum(1 for t, _ in cls if t == "WARN")
for t, m in cls:
    icon = {"OK": "✅", "WARN": "⚠️ ", "BAD": "❌"}[t]
    print(f"  {icon} {m}")
print("=" * 74)
print(f"  {'❌ 有真问题' if nbad else '✅ 隔离完好'}"
      + (f"（另有 {nwarn} 条提示）" if nwarn else ""))
