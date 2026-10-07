# -*- coding: utf-8 -*-
"""
LLM 对话系统 —— 完整自查（一次跑完，不许漏项）

用法：  python tool/llm_selfcheck.py

⚠️ 为什么要有这个脚本：
   2026-09-15 出过一次事故 —— 给 `@LLM_APPLY_DELTA` 加"身体接触"分支时，
   我把检查**手动精简**成了 5 项，**漏掉了"跨函数变量"那一项**，
   结果 `LLM_MSG` 被用在了没声明它的函数里，游戏加载时报：
       警告Lv2: 变量"LLM_MSG"未在此函数中定义
   代码没崩，但**那个分支完全不生效** —— 静默失效，最难查的一类。
   ⇒ 所以把所有检查**固化在一个脚本里**，跑一次就够，不依赖我记得勾哪几项。

检查项：
   1. 缩进 / 配对（调用 tool/erb_check.py）
   2. 引号配平
   3. `%` 配平
   4. `SIF` 只绑一行 & 后不跟同缩进的 ELSE/ELSEIF/ENDIF
   5. 数值变量被写进 `%…%`
   6. ★ **跨函数变量**（声明与使用不在同一函数）—— 就是漏跑害人的那一项
   7. `@"…"` 内的裸 ASCII 双引号
   8. 容量（`#LOCALSIZE` / `#LOCALSSIZE`）
   9. 行首合法性（markdown 残留 = 错；CJK 开头 = 警告）
"""
import os
import re
import subprocess
import sys

# ⚠️ `.ERH` 里的声明是**全局变量** —— 各 .ERB 里直接就能用，
#    所以检查"未声明左值"时必须把它们算进去，否则满屏误报。
GLOBAL_ERH = ["ERB/魔改内容/LLM_KOJO.ERH"]

GLOBALS = set()   # 由 main() 用 load_global_decls() 填

# ERB 引擎自己的内置标识符（不是我们声明的）
BUILTIN = {
    "TIME", "DAY", "MONEY", "RESULT", "RESULTS", "LOCAL", "LOCALS", "LOCALSS",
    "ARG", "ARGS", "TARGET", "MASTER", "PLAYER", "ASSI", "CHARANUM", "RAND",
    "SELECTCOM", "PREVCOM", "LINE", "LINECOUNT", "ISTIMEOVER", "FLAG", "SAVEDATA",
}


def load_global_decls():
    """从 .ERH 收集全局声明（含参数形式）"""
    g = set()
    for p in GLOBAL_ERH:
        if not os.path.exists(p):
            continue
        for l in open(p, encoding="utf-8"):
            m = re.match(r'#(DIM|DIMS)\s+(?:CONST\s+|REF\s+|DYNAMIC\s+|CHARADATA\s+|SAVEDATA\s+|GLOBAL\s+)*([A-Za-z_][A-Za-z_0-9]*)',
                         l.strip())
            if m:
                g.add(m.group(2))
            # 形如 `#DIM X, 8` 或带多个修饰
            for mm in re.finditer(r'#DIMS?\s+([^;]+)', l):
                for w in re.findall(r'\b[A-Za-z_][A-Za-z_0-9]*\b', mm.group(1)):
                    g.add(w)
    return g


TARGETS = [
    "ERB/魔改内容/LLM_CONVERSATION.ERB",
    "ERB/魔改内容/LLM_CHAT_BRIDGE.ERB",
    "ERB/魔改内容/LLM_KOJO.ERH",
    # ★ 2026-09-20 加：亲密互动的独立模块
    #   ⚠️ **必须一起扫** —— 它写入 `LLM_AWAKE` / `LLM_AWAKE_BOOST` /
    #      `LLM_HALFAWAKE` 这些在别的文件里声明的变量；
    #      不扫它就会误报「只有读、从没写过」⚠️
    "ERB/魔改内容/LLM_INTIMATE.ERB",
]

# 合法的"引用型"裸引号（`REPLACE(x, @"…", "")` 这种）—— 白名单
BARE_QUOTE_OK = re.compile(r"'\s*=\s*REPLACE\(")   # 用 search，不是 match


def read(p):
    return open(p, encoding="utf-8").read().splitlines()


def func_map(lines):
    """行号 → 所属函数名"""
    starts = [(i, l.split("(")[0][1:].strip()) for i, l in enumerate(lines) if l.startswith("@")]

    def fof(idx):
        cur = None
        for si, n in starts:
            if si <= idx:
                cur = n
            else:
                break
        return cur
    return fof


def strip_comment(l):
    """剥掉行尾注释（``;`` 之后的部分）。

    ⚠️ 为什么必须剥：`#DIM  LLM_TP  ; 单位（%）` 这种行会让 `%` 计数变成奇数，
       而它**完全合法** —— 注释里的 `%` 不参与求值。

    ⚠️⚠️ 但**不能见到 `;` 就切** —— 字符串里的分号不算注释！
       实测：`"&lt;该角色没有口上剧本&gt;"` 里的 HTML 实体自带 `;`，
       一刀切会把字符串腰斩 ⇒ 引号变成奇数 ⇒ 满屏误报。
       ⇒ 所以必须**跟踪引号状态**（`in_str`）。
    """
    out = []
    in_str = False
    for ch in l:
        if ch == '"':
            in_str = not in_str          # ⚠️ 要跟踪引号状态
        if ch == ";" and not in_str:
            break
        out.append(ch)
    return "".join(out)


def check_quotes_and_pct(lines, path):
    bad = []
    for i, l in enumerate(lines):
        s = strip_comment(l).strip()
        if not s or '\\"' in s:
            continue
        if s.count('"') % 2:
            bad.append(f"  ★ [{path}] 行{i+1} 引号不成对: {s[:90]}")
        # ★ 取模豁免（2026-09-20）——
        #   ⚠️ `LOCAL:3 = LOCAL:2 % 1000 / 100` 里的 % 是**取模运算符**，
        #      官方 `@PRINT_DATE_F`（COMMON.ERB:2657）就是这么写的 ⚠️
        #   ⇒ 判据：没有 @"（不是字符串）+ 有 = + 等号左边只有数值变量
        #      ⇒ 那这个 % 一定是取模，跳过检查 ✓
        _is_numeric_assign = (
            '@"' not in s
            and "=" in s
            and re.match(r'^(LOCAL(:\d+)?|LLM_[A-Z_0-9]+(:[^=]*)?)\s*=[^=]', s)
        )
        if s.count("%") % 2 and not _is_numeric_assign:
            bad.append(f"  ★ [{path}] 行{i+1} % 不成对: {s[:90]}")
    return bad


def check_sif(lines, path):
    """SIF 只绑紧随的一行；且后面不能跟**同缩进**的 ELSE/ELSEIF/ENDIF"""
    bad = []
    for i, ln in enumerate(lines):
        m = re.match(r'^(\s*)SIF\s', ln)
        if not m:
            continue
        ind = len(m.group(1))
        j = i + 1
        children = 0
        while j < len(lines):
            s = lines[j]
            if not s.strip():
                break
            if s.strip().startswith(";"):
                j += 1
                continue
            sind = len(s) - len(s.lstrip())
            if sind < ind:
                break
            if sind == ind:
                # ★ 同缩进出现 ELSE/ELSEIF/ENDIF —— SIF 不能配它们
                if re.match(r'^\s*(ELSE|ELSEIF|ENDIF)\b', s):
                    bad.append(f"  ★ [{path}] 行{j+1} SIF 后跟了同缩进的 {s.strip().split()[0]}（应改 IF）")
                break
            # ⚠️ 只数**直接子行**（缩进恰好 +1）——
            #    `SIF A` 下面跟一个 `SIF B`、`SIF B` 下面再跟一行，
            #    是**合法**的（`SIF A` 只绑 `SIF B` 那一行）。
            #    把孙行也算进来会误报。
            if sind == ind + 1:
                children += 1
            j += 1
        if children > 1:
            bad.append(f"  ★ [{path}] 行{i+1} SIF 绑了多行: {ln.strip()[:80]}")
    return bad


def check_bare_quote(lines, path):
    bad = []
    for i, l in enumerate(lines):
        s = l.strip()
        if s.startswith(";") or '@"' not in s:
            continue
        if BARE_QUOTE_OK.search(s):
            continue
        rest = re.sub(r'@"[^"]*"', "", s)
        if '"' in rest:
            bad.append(f"  ★ [{path}] 行{i+1} @\"…\" 里有裸引号: {s[:90]}")
    return bad


def check_undeclared_lvalue(lines, path):
    """★ 左值变量必须在本函数里声明过。

    ⚠️ 为什么单独查这个：
       `check_cross_function` 只查 `LLM_*` 前缀 —— 所以 `REF_HINT += ...`
       这种**别的名字**的未声明变量它看不见（实测漏过一次）。
       而"给一个不存在的变量赋值"是**运行时静默出错**，最难查。

    ⚠️ 只查**纯标识符**左值（`XXX = ` / `XXX += ` / `XXX ++`）——
       带 `:` 的（`CFLAG:X` / `TFLAG:Y` / `BASE:Z`…）都是引擎变量，跳过。
    """
    fof = func_map(lines)
    decl = {}
    for i, l in enumerate(lines):
        m = re.match(r'#(DIM|DIMS)\s+(?:CONST\s+|REF\s+|DYNAMIC\s+)?([A-Za-z_][A-Za-z_0-9]*)', l.strip())
        if m:
            decl.setdefault(fof(i), set()).add(m.group(2))
        # 参数也算声明
        if l.startswith("@"):
            inner = l.split("(", 1)[1].rsplit(")", 1)[0] if "(" in l else ""
            for a in inner.split(","):
                a = a.strip().split("=")[0].strip()
                if re.match(r'^[A-Za-z_][A-Za-z_0-9]*$', a):
                    decl.setdefault(fof(i), set()).add(a)
    bad = []
    for i, l in enumerate(lines):
        s = strip_comment(l).strip()
        if not s or s.startswith("#"):
            continue
        # ── ① 赋值左值（原有）──
        m = re.match(r'^([A-Za-z_][A-Za-z_0-9]*)\s*(\+=|-=|\*=|/=|=|\+\+|--)(?!=)', s)
        if m:
            var = m.group(1)
            if var not in BUILTIN and var not in GLOBALS:
                fn = fof(i)
                if fn is not None and var not in decl.get(fn, set()):
                    owners = [f for f, vs in decl.items() if var in vs]
                    bad.append(f"  ★ [{path}] 行{i+1} 『{var}』在 {fn} 里**没有声明**"
                               + (f"（声明在 {owners[0]}）" if owners else "（全文件都没有）"))
            continue
        # ── ② ★ `CALL f(a, XXX)` 的**实参**（2026-09-18 扩展）──
        #   ⚠️ 实测漏过一次：`CALL LLM_CHARA_BODY(LLM_CID, LLM_BODYTXT)` 少了声明 ⇒
        #      游戏报 `Lv2: 无法解析的标识符"LLM_BODYTXT"` ⚠️
        #   ⚠️ 只认 `LLM_` 开头的标识符 —— 别的名字（如 `TARGET`）多是引擎变量或形参，
        #      一律查会满屏误报 ✓
        m2 = re.match(r'^CALL\s+[A-Za-z_][A-Za-z_0-9]*\((.*)\)\s*$', s)
        if m2:
            fn = fof(i)
            if fn is None:
                continue
            for a in m2.group(1).split(","):
                a = a.strip()
                if not re.fullmatch(r'LLM_[A-Za-z_0-9]*', a):
                    continue
                if a in GLOBALS or a in decl.get(fn, set()):
                    continue
                owners = [f for f, vs in decl.items() if a in vs]
                bad.append(f"  ★ [{path}] 行{i+1} 『{a}』作为**实参**传给 CALL，"
                           f"但在 {fn} 里**没有声明**"
                           + (f"（声明在 {owners[0]}）" if owners else "（全文件都没有）⚠️"))
    return bad


def check_savedata_scalar(paths):
    """★★ **标量的 `SAVEDATA` 存不住** —— 必须写成 `, 1` 数组（2026-09-18 实测）。

    ⚠️⚠️ 用户实测（这是本作一个**反直觉**的行为）：
       · `#DIM CHARADATA SAVEDATA X, 16`（数组）⇒ 存档 → 读档 **保留** ✓
       · `#DIM CHARADATA SAVEDATA X, 1` （数组）⇒ **保留** ✓
       · `#DIM CHARADATA SAVEDATA X`   （**标量**）⇒ **读档后丢失** ⚠️
    症状：态度 / 最爱 / 持久记忆计数**存档后全部消失**，
          而"牵手实绩"（`LLM_AGREE, 16`）却留着 ⇒ **极易误判成"记忆系统的 bug"** ✓
    症状特征：**只有带尺寸的才活下来** ✓
    """
    bad = []
    for p in paths:
        for i, l in enumerate(open(p, encoding="utf-8"), 1):
            m = re.match(r'\s*#(DIMS|DIM)\s+(?:CHARADATA\s+|GLOBAL\s+)?SAVEDATA\s+(\w+)\s*(?:;.*)?$', l)
            if m:
                bad.append(f"  ★ [{p}] 行{i} 『{m.group(2)}』是**标量** SAVEDATA "
                           f"⇒ **读档后会丢失** ⚠️ 改成 `, 1` 数组，并把引用写成 `X:(角色):0` ✓")
    return bad


def check_charadata_two_dim(path, erh_path):
    """★ 两维 `CHARADATA`（`#DIM CHARADATA SAVEDATA X, N`）的**第一维必须是角色**。

    ⚠️ 2026-09-18 实测踩坑：`LLM_AGREE:(LLM_D6)` ——
       `LLM_AGREE` 是两维（角色, 槽），而这里把 `LLM_D6`（行为号 1~7）当成了**角色号** ⚠️
       ⇒ "她接受过牵手"被写到**角色 1~7** 上，换个角色就读不到
       ⇒ 用户看到的现象是「**换位置记忆就丢了**」✓
    ⇒ 判据：两维变量的引用必须形如 `X:(角色):(槽)` —— **至少两个下标** ✓
    """
    import re as _re
    two = []
    for l in open(erh_path, encoding="utf-8"):
        m = _re.match(r'#DIMS?\s+CHARADATA\s+(?:SAVEDATA\s+)?(\w+)\s*,\s*(\d+)', l.strip())
        if m:
            two.append(m.group(1))
    if not two:
        return []
    bad = []
    for i, l in enumerate(open(path, encoding="utf-8"), 1):
        s = l.strip()
        if s.startswith(";"):
            continue
        for v in two:
            # ⚠️ 下标可以是 `(...)` 也可以是**裸标识符/数字**（如 `:0`）——
            #    所以这里把两种都收进来，再数冒号 ✓
            #    （2026-09-18：第一版只认 `(...)`，导致 `X:(cid):0` 被误报成"一个下标"）
            for m in _re.finditer(rf'\b{v}:((?:\([^)]*\)|[A-Za-z_0-9]+)(?::(?:\([^)]*\)|[A-Za-z_0-9]+))*)', s):
                idx = m.group(1)
                if ":" not in idx:      # 只有一个下标 ⇒ 只带了第一维
                    bad.append(f"  ★ [{path}] 行{i} 『{v}』是**两维** CHARADATA，"
                               f"但只写了一个下标 ⇒ **第一个下标被当成角色号** ⚠️")
    return bad


def check_charadata_rank(path):
    """★ `CHARADATA` 变量**自己占一层下标** —— 写多了会报
    「角色一维数组变量"X"的参数过多」（Lv2，游戏屏幕上才看得见）。

    ⚠️ 为什么必须查：
       `#DIMS CHARADATA SAVEDATA LLM_MEMO, 32` ⇒ 合法写法是
       `LLM_MEMO:(角色):(下标)`（**两层**）。
       写成 `LLM_MEMO:(角色):LOCAL:1`（三层）会静默降级 ——
       游戏能开，但那几行是无效的 ⚠️
       （实测踩过，是用户截图报错才发现的。）
    """
    # ① 从 .ERH 收集 CHARADATA 变量及其数组维度
    decl = {}
    for gp in GLOBAL_ERH:
        if not os.path.exists(gp):
            continue
        for l in open(gp, encoding="utf-8"):
            m = re.match(r'#(DIM|DIMS)\s+(.*)', l.strip())
            if not m or "CHARADATA" not in m.group(2):
                continue
            body = m.group(2)
            # 取变量名（CHARADATA/SAVEDATA/GLOBAL 这些修饰词之后那个）
            mm = re.search(r'([A-Za-z_][A-Za-z_0-9]*)\s*(?:,\s*(\d+))?\s*$', body.split(";")[0].strip())
            if not mm:
                continue
            name = mm.group(1)
            if name in ("CHARADATA", "SAVEDATA", "GLOBAL", "DIM", "DIMS"):
                continue
            decl[name] = 1 if mm.group(2) else 0    # 数组维度数（不含角色那一层）
    bad = []
    for p in TARGETS:
        if not os.path.exists(p):
            continue
        for i, l in enumerate(read(p)):
            s = strip_comment(l).strip()
            if not s or s.startswith("#"):
                continue
            # 数 `VAR:(..):X:Y` 里的下标层数
            for m in re.finditer(r'\b([A-Za-z_][A-Za-z_0-9]*)((?::\([^)]*\)|:[A-Za-z_0-9]+)+)', s):
                name = m.group(1)
                if name not in decl:
                    continue
                layers = len(re.findall(r':(?:\([^)]*\)|[A-Za-z_0-9]+)', m.group(2)))
                if layers > decl[name] + 1:      # +1 = 角色那一层
                    bad.append(f"  ★ [{p}] 行{i+1} 『{name}』下标 {layers} 层，"
                               f"但 CHARADATA 声明只允许 {decl[name]+1} 层：{s[:70]}")
    return bad


def check_cross_function(lines, path):
    """★ 声明与使用不在同一函数 —— 游戏会报『变量未在此函数中定义』并**静默失效**"""
    fof = func_map(lines)
    decl = {}
    for i, l in enumerate(lines):
        m = re.match(r'#(DIM|DIMS)\s+(?:CONST\s+|REF\s+|DYNAMIC\s+)?([A-Za-z_][A-Za-z_0-9]*)', l.strip())
        if m:
            decl.setdefault(fof(i), set()).add(m.group(2))
    bad = []
    for i, l in enumerate(lines):
        s = l.strip()
        if s.startswith(";") or s.startswith("#"):
            continue
        fn = fof(i)
        if fn is None:
            continue
        for var in set(re.findall(r'\b(LLM_[A-Z_0-9]+)\b', s)):
            if var in decl.get(fn, set()):
                continue
            owners = [f for f, vs in decl.items() if var in vs]
            if owners:
                bad.append(f"  ★ [{path}] 行{i+1} 『{var}』声明在 {owners[0]}，却用在 {fn}")
    return bad


def split_args(s):
    """按**顶层逗号**拆参数 —— 括号里的逗号不算。

    ⚠️ 为什么需要：`MAX(A * B, 50)` 这种参数里带逗号，
       用 `s.split(",")` 会拆成 2 个 ⇒ **误报"参数过多"** ⚠️
       （实测踩过：`CALL LLM_GAIN_COST(X, "体力", MAX(A, B))`）
    """
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


def check_call_signature(path):
    """★ 调用点的参数个数必须和定义一致。

    ⚠️ 为什么必须查：2026-09-16 事故重建后，`@LLM_CHAT_LOOP` 是旧版（9/14），
       它按**旧签名**调用 `@LLM_PARSE_DELTA`（4 个出参），而新定义要 6 个 ⇒
       游戏报「第 6 个参数是引用形式因此无法省略」并**停止运行** ⚠️
       这类错**自查和 erb_check 都抓不到**（语法是对的），只有游戏才报 ✓
    """
    lines = read(path)
    # ① 收集定义：@NAME(参数...)（换行续行要考虑）
    defs = {}
    i = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("@"):
            head = l
            j = i
            while head.count("(") > head.count(")") and j + 1 < len(lines):
                j += 1
                head += lines[j]
            m = re.match(r'@([A-Za-z_][A-Za-z_0-9]*)\((.*)\)', head)
            if m:
                inner = m.group(2).strip()
                n = 0 if inner == "" else len(split_args(inner))
                defs[m.group(1)] = n
        i += 1
    # ② 检查调用
    bad = []
    for i, l in enumerate(lines):
        st = strip_comment(l)
        for m in re.finditer(r'(?:CALL|TRYCALL)\s+([A-Za-z_][A-Za-z_0-9]*)\s*\(([^)]*)\)', st):
            name, args = m.group(1), m.group(2)
            if name not in defs:
                continue
            n = 0 if args.strip() == "" else len(split_args(args))
            if n > defs[name]:
                bad.append(f"  ★ [{path}] 行{i+1} CALL {name} 传了 {n} 个参数，"
                           f"但定义只要 {defs[name]} 个：{st.strip()[:64]}")
    # ③ 也检查表达式调用（%NAME(...)% 或 = NAME(...)）
    for i, l in enumerate(lines):
        st = strip_comment(l)
        for m in re.finditer(r'\b([A-Za-z_][A-Za-z_0-9]*)\s*\(([^()]*)\)', st):
            name, args = m.group(1), m.group(2)
            if name not in defs or name == "LLM_CID":
                continue
            if re.search(rf'(CALL|TRYCALL)\s+{name}\s*\(', st):
                continue
            n = 0 if args.strip() == "" else len(split_args(args))
            if n > defs[name]:
                bad.append(f"  ★ [{path}] 行{i+1} {name}(…) 传了 {n} 个参数，"
                           f"定义只要 {defs[name]} 个：{st.strip()[:64]}")
    return bad


def check_sif_sif(path):
    """★ `SIF` 的下一行**不能再是 `SIF`**。

    ⚠️ 游戏报 `Lv2: SIF的下一行"SIF"不能作为作用域` 并**停止运行** ⚠️
       （实测踩过：`IF ... / SIF A / SIF B / X` 这种嵌套。）
    ⇒ 外层**必须**写 `IF`/`ENDIF` ✓
    """
    lines = read(path)
    bad = []
    for i, l in enumerate(lines):
        st = strip_comment(l).strip()
        if not st.startswith("SIF "):
            continue
        ind = len(l) - len(l.lstrip())
        for j in range(i + 1, len(lines)):
            t = lines[j]
            if not t.strip() or t.strip().startswith(";"):
                continue
            ind2 = len(t) - len(t.lstrip())
            if ind2 > ind and t.strip().startswith("SIF "):
                bad.append(f"  ★ [{path}] 行{j+1} SIF 的下一行又是 SIF（外层在行{i+1}）"
                           f"⇒ 外层改 IF/ENDIF：{t.strip()[:56]}")
            break
    return bad


def check_var_three_col(paths, extra_erbs=()):
    """★ 变量三列：**声明 / 写入 / 读取**。

    ⚠️ **2026-09-20 加 `extra_erbs`**：
       亲密互动的独立模块 `LLM_INTIMATE.ERB` 会写 `LLM_AWAKE` /
       `LLM_AWAKE_BOOST` / `LLM_HALFAWAKE`（声明在别处）——
       不把它算进来的话，那几个变量会被误报成「只有读、从没写过」⚠️

    ⚠️ 为什么必须查（2026-09-16 审计的真实收获）：
       `LLM_BYE_KEPT` 和 `LLM_WANT_SLEEP` 都**只有读、从没写** ⇒
       那两个分支**永远不成立** ⇒「挽留只一次」「她会主动去睡」**静默失效** ⚠️
       这类缺口**语法完全正确**，`erb_check` 和游戏都不会报 ✓
       ⇒ 和 `###STRIP###`（有解析没 prompt 说明）是**同一类**：
         **两个本该配对的地方，只做了一半。**

    ⚠️ 只报「**从没写过**」，且**排除**下面三种（否则误报会淹掉真问题）：
       · **形参** —— 由调用方传入，本来就不该在函数里赋值
       · **`#DIM CONST` 常量数组** —— 声明时就赋值了
       · **在桥接文件里写的** —— 那两个文件是一套
    """
    ERH, ERBS, BRIDGE = paths
    allsrc = ""
    for f in (ERBS, BRIDGE) + tuple(extra_erbs):
        if os.path.exists(f):
            allsrc += open(f, encoding="utf-8").read() + chr(10)
    if os.path.exists(ERH):
        allsrc += open(ERH, encoding="utf-8").read() + chr(10)

    # ① 收集形参：把每个 @func(...) 的**完整签名**（含续行）拼起来
    sigs = ""
    for f in (ERBS, BRIDGE):
        if not os.path.exists(f):
            continue
        ls = read(f)
        i = 0
        while i < len(ls):
            if ls[i].startswith("@"):
                head = ls[i]
                j = i
                while head.count("(") > head.count(")") and j + 1 < len(ls):
                    j += 1
                    head += " " + ls[j]
                sigs += head + chr(10)
                i = j
            i += 1
    params = set(re.findall(r'\b(LLM_[A-Za-z_0-9]+)\b', sigs))

    # ② 收集 CONST 常量
    consts = set()
    for f in (ERBS, ERH):
        if not os.path.exists(f):
            continue
        for l in read(f):
            if "CONST" in l:
                consts |= set(re.findall(r'\b(LLM_[A-Za-z_0-9]+)\b', l))

    # ③ 收集真变量
    real = {}
    for f in (ERH, ERBS):
        if not os.path.exists(f):
            continue
        for l in read(f):
            m = re.match(r'#(DIMS?)\s+(.*?)(LLM_[A-Za-z_0-9]+)\s*(?:,.*)?$', l.strip())
            if m:
                real[m.group(3)] = "str" if m.group(1) == "DIMS" else "num"

    # ⚠️⚠️ **已知的白名单** —— 这些确实"没有显式赋值"，但**不是缺口**：
    #   · 引用传递回填：`CALL f(..., VAR)` 在 ERB 里靠 `#DIM REF VAR` 回填，
    #     我的正则遇到嵌套括号（`CALL f(A, MAX(B,C))`）会漏 ⇒ 宁可放过
    #   · 调试 / 循环用的局部：`LLM_DB0~3`、`LLM_IS_SILENT3` 等
    #   ⇒ **审计的目的是抓"功能性分支永远不成立"，不是抓所有未赋值变量** ✓
    WHITELIST = {
        "LLM_CK", "LLM_CT",              # @LLM_WORK_COST 引用回填
        "LLM_DB0", "LLM_DB1", "LLM_DB2", "LLM_DB3",   # 调试
        "LLM_IDX", "LLM_NUM", "LLM_PART", "LLM_REL_TIRED",  # 形参（多行签名漏判）
        "LLM_IS_SILENT3",                # 遗留局部
        # ⚠️⚠️ **2026-09-16「方案 B」刻意废弃的三个槽** ——
        #   `###ADDR###` / `###CALL###` / `###CALLHER###` 三个专用标记取消，
        #   称呼 / 身份 / 约定**统一写成 `###MEMO### [5]`**（用户决定）。
        #   ⚠️ 但这三个 `CHARADATA SAVEDATA` 变量**故意保留不删** ——
        #      删 `.ERH` 里的声明会移动 `.sav` 里后面所有变量的偏移，
        #      可能让旧存档读到垃圾值 ⚠️
        #   ⇒ 它们从此**只被读（都是注释/文档性的）、不再被写**，
        #      这是**预期的**，不是缺口 ✓
        #   ⚠️ 别再往这里加东西 —— 白名单只放"确实是预期的"，
        #      否则就把第 12 项检查的意义吃掉了 ⚠️
        "LLM_ADDRESS", "LLM_CALLME", "LLM_CALLHER",
    }
    bad = []
    for v in sorted(real):
        if v in params or v in consts or v in WHITELIST:
            continue
        # ⚠️ 只报**读了 >= 2 次**的 —— 读一次的多半是写法怪的正常代码；
        #    真缺口（如 `LLM_BYE_KEPT` / `LLM_WANT_SLEEP` / `LLM_SESSION_T0`）
        #    都是被当条件用的，必然读不止一次 ✓
        nread = len(re.findall(rf'\b{v}\b', allsrc))
        if nread < 2:
            continue
        # ⚠️ 三种写法都算"写"：
        #    `V = ...` / `V:(下标) = ...` / `V '= ...`（`'=` 是表达式赋值）
        nw = len(re.findall(rf"\b{v}\b\s*(?::[^\s=]+)*\s*'?=", allsrc))
        nw += len(re.findall(rf'SETBIT\s+{v}\b', allsrc))
        nw += len(re.findall(rf'CALL\s+\w+\([^)]*\b{v}\b[^)]*\)', allsrc))
        nw += len(re.findall(rf'\b{v}\b\s*\+', allsrc))
        if nw == 0:
            bad.append(f"  ★ 【{os.path.basename(ERBS)}】变量『{v}』"
                       f"**只有读、从没写过** ⇒ 相关分支永远不成立 ⚠️")
    return bad


def check_capacity(lines, path):
    """#LOCALSIZE / #LOCALSSIZE 够不够（数组按长度占槽）"""
    starts = [(i, lines[i]) for i, l in enumerate(lines) if l.startswith("@")]
    bad = []
    for k, (i, head) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        body = lines[i + 1:end]
        args = []
        if "(" in head:
            inner = head.split("(", 1)[1].rsplit(")", 1)[0]
            args = [a.strip().split("=")[0].strip() for a in inner.split(",") if a.strip()]
        ls = lss = nn = ns = 0
        for b in body:
            s = b.strip()
            m = re.match(r'#LOCALSIZE\s+(\d+)', s)
            if m:
                ls = int(m.group(1)); continue
            m = re.match(r'#LOCALSSIZE\s+(\d+)', s)
            if m:
                lss = int(m.group(1)); continue
            if re.match(r'#DIMS?\s+REF', s):
                continue
            m = re.match(r'#DIMS\s+(\S+?)(?:,\s*(\d+))?$', s)
            if m:
                if m.group(1) in args:
                    continue
                ns += int(m.group(2)) if m.group(2) else 1
                continue
            m = re.match(r'#DIM\s+(\S+?)(?:,\s*(\d+))?$', s)
            if m:
                if m.group(1) in args:
                    continue
                nn += int(m.group(2)) if m.group(2) else 1
                continue
        # ⚠️ 只报**真溢出**：LOCALSIZE/LOCALSSIZE 没写时默认是 0，
        #    但 `#DIMS` 声明**参数或 REF** 是合法的（不占槽）——
        #    所以只在"写了 SIZE 却不够"时报，没写的不报（避免误报）。
        if (ls and nn > ls) or (lss and ns > lss):
            bad.append(f"  ★ [{path}] {head[:44]} 数值 {nn}/{ls}  字符串 {ns}/{lss}")
    return bad


# ★ 游戏**内置**的数值变量 —— `%…%` 里出现它们同样会报
#   `Lv2: %中的表达式结果不是字符串`（2026-09-19 实测：`%DAY%` 踩过一次）
BUILTIN_NUM = {
    "DAY", "TIME", "MONEY", "RESULT", "CHARANUM", "RAND",
    "SELECTCOM", "PREVCOM", "LINE", "LINECOUNT", "MASTER", "TARGET",
    "ASSI", "LOCAL", "FLAG", "TFLAG", "CFLAG", "BASE", "MAXBASE",
    "ABL", "TALENT", "EXP", "MARK", "PALAM", "TCVAR", "CDFLAG",
    "JUEL", "GOTJUEL", "NO", "ISASSI", "SAVEDATA",
}


def check_values_in_pct(lines, path):
    """数值变量写进 %…% 会报 Lv2"""
    num, st = set(), set()
    for l in lines:
        s = l.strip()
        m = re.match(r'#DIM\s+(?:CONST\s+|REF\s+|DYNAMIC\s+)?(LLM_[A-Za-z_0-9]+)', s)
        if m:
            num.add(m.group(1)); continue
        m = re.match(r'#DIMS\s+(?:REF\s+)?(LLM_[A-Za-z_0-9]+)', s)
        if m:
            st.add(m.group(1))
    bad = []
    for i, l in enumerate(lines):
        s = l.strip()
        if s.startswith(";") or '@"' not in s:
            continue
        for m in re.finditer(r'%([^%]+)%', s):
            e = m.group(1)
            if "(" in e:
                continue
            # ── ① 我们自己的数值变量 ──
            for vid in re.findall(r'\b(LLM_[A-Za-z_0-9]+)\b', e):
                if vid in num and vid not in st:
                    bad.append(f"  ★ [{path}] 行{i+1} %{e}%（{vid} 是数值，应用 {{…}}）")
                    break
            else:
                # ── ② ★ 游戏**内置**的数值变量（2026-09-19 加）──
                #   实测：`%DAY%` 会报 `Lv2: %中的表达式结果不是字符串` ⚠️
                #   ⚠️ 但**含 `:` 的不能报** —— `%CALLNAME:TARGET%`、
                #      `%CFLAG:MASTER:体力%` 里的 `TARGET`/`MASTER` 只是**索引**，
                #      整体是合法的字符串 ✓（第一版没排除，误报 4 处）
                if ":" not in e:
                    for vid in re.findall(r'\b([A-Z][A-Z_0-9]*)\b', e):
                        if vid in BUILTIN_NUM:
                            bad.append(f"  ★ [{path}] 行{i+1} %{e}%"
                                       f"（{vid} 是**引擎内置数值**，应用 {{…}}）")
                            break
    return bad


def check_line_starts(path):
    """委托给 tool/erb_check.py 的 check_line_starts"""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("erbcheck", "tool/erb_check.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        lines = read(path)
        out = []
        for ln, txt, why, lvl in m.check_line_starts(lines):
            if lvl == "error":
                out.append(f"  ★ [{path}] 行{ln} {why}: {txt[:60]}")
        return out
    except Exception as e:
        return [f"  （行首检查跳过：{e}）"]


def check_const_numeric(lines, path):
    """★ 第 13 项：`#DIM CONST` 数组的值**必须是数值**。

    ⚠️ 为什么必须查（2026-09-16 **真事故**，游戏直接起不来）：
       我写了
           #DIM CONST LLM_ID_LIST, 30 = 佣人, 女仆, 仆人, …
       想当"字符串词表"用 —— 但 **`#DIM CONST` 装不了字符串**，
       那些中文词被当成**变量名** ⇒ 游戏报
           Lv2: 无法解析的标识符「佣人」
           Lv2: 变量「LLM_ID_LIST」未在此函数中定义
           Emuera停止运行 ⚠️

    ⚠️ 项目里正确的 `#DIM CONST` 数组**全是数值**，例如
       `#DIM CONST LLM_BODY, 11 = 13, 14, 9, 10, 17, …`
       `#DIM CONST SLOT_LEFT, 20 = 7,2,4,5,3, …`
       ⇒ 要"字符串词表"时改用**连写 `SIF STRFIND(...)` 判定**（见 `@LLM_IS_BYE`）✓

    ⚠️ 允许的形态：十进制 / 十六进制(`0x…`) / 负数 / 逗号 / 空白 / 行尾注释
       出现**其它字符** ⇒ 报警（几乎一定是写成了字符串）✓
    """
    bad = []
    for i, l in enumerate(lines):
        s = l.strip()
        if not s.startswith("#DIM CONST"):
            continue
        if "=" not in s:
            continue                      # 只声明不赋值 ⇒ 不管
        rhs = s.split("=", 1)[1]
        # 去掉行尾注释（本项目注释用 `;`）
        rhs = rhs.split(";", 1)[0]
        # 允许：数字、0x 十六进制、负号、逗号、空白
        residue = re.sub(r'0[xX][0-9a-fA-F]+', '', rhs)
        residue = re.sub(r'[-+0-9,\s]', '', residue)
        if residue:
            bad.append(
                "  ★ 【%s】L%d `#DIM CONST` 的值里有**非数值内容**『%s』"
                " ⇒ 引擎会把它当**变量名**、游戏**起不来** ⚠️"
                "（字符串词表请改用连写 `SIF STRFIND(...)`）"
                % (os.path.basename(path), i + 1, residue[:20])
            )
    return bad


def main():
    global GLOBALS
    GLOBALS = load_global_decls()
    total = 0
    for path in TARGETS:
        if not os.path.exists(path):
            print(f"  （缺文件：{path}）")
            continue
        lines = read(path)
        problems = []
        problems += check_quotes_and_pct(lines, path)
        problems += check_sif(lines, path)
        problems += check_bare_quote(lines, path)
        problems += check_cross_function(lines, path)
        problems += check_undeclared_lvalue(lines, path)
        problems += check_charadata_rank(path)
        problems += check_call_signature(path)
        problems += check_sif_sif(path)
        problems += check_capacity(lines, path)
        problems += check_values_in_pct(lines, path)
        problems += check_line_starts(path)
        problems += check_const_numeric(lines, path)
        # ★★ 2026-09-18 新增两项 ——
        #   ① 标量 SAVEDATA **存不住**（实测：读档后丢）⇒ 必须 `, 1`
        #   ② 两维 CHARADATA 的第一维必须是角色（`LLM_AGREE:(LLM_D6)` 那次踩的）
        problems += check_savedata_scalar([path, GLOBAL_ERH[0]])
        problems += check_charadata_two_dim(path, GLOBAL_ERH[0])
        if problems:
            print(f"\n── {path} ──")
            for p in problems:
                print(p)
            total += len(problems)

    problems = check_var_three_col(
        (GLOBAL_ERH[0], TARGETS[0], TARGETS[1]),
        extra_erbs=tuple(t for t in TARGETS[2:] if t.endswith(".ERB")),
    )
    if problems:
        print("\n── 变量三列（跨文件）──")
        for p in problems:
            print(p)
        total += len(problems)

    print()
    if total == 0:
        # ⚠️ 这个数字必须跟**实际调用的 check_ 函数个数**一致
        #    （2026-09-27 核对：定义了 15 个、且全部都会被调用；
        #      这里原来硬编码 13 —— 09-18 新增两项后忘了改，显示与实际不符）
        print("  ✅ 全部检查通过（15 项）")
    else:
        print(f"  ❌ 共 {total} 个问题")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
