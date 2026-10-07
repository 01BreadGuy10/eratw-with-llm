# ERB 语法避坑清单（本项目实际踩过的错）

> 本文件是**开发备忘**，记录写这个 mod 时反复踩的 ERB 语法坑。
> 每次改 ERB 前先扫一遍，改完用 `tool/erb_check.py` 过一遍。
> 所有条目均为**实际触发过的报错**，不是理论推测。

---

## 0. 改完必做

> ★★ **2026-09-27 更新：现在有现成的脚本，别再手抄下面的自查** ——
> **标准流程 = `llm_selfcheck.py`（15 项）+ `decl_check.py` + `isolation_check.py` + `erb_check.py`** ✓
> （完整命令见 `llmmd\LLM交接文档_v2.md` §16.4）
> **下面是"脚本为什么会这么写"的原始推导，留着是为了看懂每一项在防什么。**

### 0.1 结构检查

```powershell
$env:PYTHONIOENCODING="utf-8"
python tool/erb_check.py "ERB/魔改内容/你的文件.ERB"
python tool/llm_selfcheck.py        # ★ 15 项，主力
python tool/decl_check.py           # 声明区
python tool/isolation_check.py      # 自由互动隔离
```

> `erb_check.py` 只能查**缩进/配对**这类结构问题，**查不出下面这些语义错误**，
> 所以仍需人工逐条自查。
> ⚠️ 它对**含多个函数块的文件会误报**（报出来的行号常常是下一个函数），
> **不能当唯一判据**。

### 0.2 四项语义自查（每一项都对应一条实际踩过的坑）

```powershell
$files = @("ERB\魔改内容\LLM_CONVERSATION.ERB","ERB\魔改内容\LLM_CHAT_BRIDGE.ERB")
foreach ($file in $files) {
  $lines = Get-Content $file -Encoding UTF8

  # ① 跨物理行的 @"…" —— 会让整个游戏停止运行（见 5c）
  # ② SIF 后跟多行   —— 后面几行会无条件执行（见 5j）
  for ($i=0; $i -lt $lines.Count; $i++) {
    $t = $lines[$i]
    if ($t -match '^\s*SIF\s') {
      $ind = ($t -replace '[^\t].*$','').Length
      $j = $i + 1; $cnt = 0
      while ($j -lt $lines.Count) {
        $n = $lines[$j]
        if ($n.Trim() -eq '') { break }
        $nind = ($n -replace '[^\t].*$','').Length
        if ($nind -gt $ind) { $cnt++; $j++ } else { break }
      }
      if ($cnt -gt 1) { "⚠ SIF 多行 {0}:{1}  {2}" -f $file,($i+1),$t.Trim() }
      # 紧邻的 ELSE/ELSEIF/ENDIF 若缩进 >= SIF，说明误把 SIF 当成 IF 用（见 5k）
      if ($j -lt $lines.Count -and $lines[$j] -match '^\s*(ELSE|ELSEIF|ENDIF)') {
        $oind = ($lines[$j] -replace '[^\t].*$','').Length
        if ($oind -ge $ind) {
          "⚠ SIF 后跟同缩进/更深的 {0}（{1}:{2}）—— 这里该用 IF" -f $lines[$j].Trim(),$file,($i+1)
        }
      }
    }
  }

  # 引号奇偶（忽略 \" 转义；判不准时以"能否加载"为准）
  $n=0
  foreach ($l in $lines) {
    $n++; $t=$l.Trim()
    if ($t.StartsWith(';')) { continue }
    if (([regex]::Matches($t,'"')).Count % 2 -ne 0) { "⚠ 引号可能不配对 {0}:{1}" -f $file,$n }
  }

  # ③ 变量当独立 + 项（见 5f）—— **必须两条正则，一条会漏！**
  #    这条抓 `X += %VAR%`
  Select-String -Path $file -Pattern '\+=\s*%[A-Za-z_(]' |
    Where-Object { $_.Line.Trim() -notmatch '^;' } |
    ForEach-Object { "⚠ 累加变量 {0}:{1}" -f $file,$_.LineNumber }
  #    这条抓 `X = "文" + %VAR%`
  Select-String -Path $file -Pattern '[^=<>!]\+\s+%[A-Za-z_(]' |
    Where-Object { $_.Line.Trim() -notmatch '^;' } |
    ForEach-Object { "⚠ 拼接变量 {0}:{1}" -f $file,$_.LineNumber }

  # ④ 字符串函数裸写在 = 右侧（见 5e）
  Select-String -Path $file -Pattern "^\s*[A-Z_][A-Z_0-9]*\s*=\s*(REPLACE|SUBSTRING|TRIM_STRING|STRLENS)\(" |
    ForEach-Object { "⚠ 危险赋值 {0}:{1}" -f $file,$_.LineNumber }
}
```

> ### ⚠️ 关于 ③：这条自查本身漏过一次
>
> 原来只写 `'\+\s*%[A-Za-z_]'` —— 它**只匹配 `+ %VAR%`**（加号后直接跟 `%`）。
> 而 `X += %VAR%` 里加号后面是 **`=`**，不是空白，所以**永远匹配不到**。
>
> 结果：`LLM_OTHERS += %CALLNAME:LOCAL%` 逃过了自查，
> 直到游戏加载时报 `Lv2 表达式异常` 才被发现。
>
> **教训：写完自查脚本，要用"已知的错误样本"验一遍它真能报出来。**
> 测试样例至少要有这三条：
> ```
> X += %A%          → 应报（累加变量）
> X = "t" + %A%     → 应报（拼接变量）
> X = %A%           → 不该报（这是合法的 FORM 赋值）
> ```

> ### ⚠️ 三个"静态查不出来、只有跑起来才发现"的坑
>
> **① `#DIMS REF` 的引用参数：不要直接拿它做字符串比较**
>
> ```erb
> @FUNC(REF_KIND)
> #DIMS REF REF_KIND
> IF REF_KIND == "工作"      ; ❌ 实测判为假，走进了别的分支
> IF REF_KIND == ""          ; ❌ 同样不可靠
> ```
>
> 表现：界面明明打印出 `（"工作"停下来了）`，说明值确实是"工作"，
> 但 `== "工作"` 就是**不成立**，于是模式被错误地判成另一种、当场打断。
>
> **解法：进函数就复制一份局部副本，去引号，再比较/显示**：
> ```erb
> #DIMS LLM_TGKIND
> LLM_TGKIND = %REF_KIND%
> LLM_TGKIND '= REPLACE(LLM_TGKIND, "\"", "")
> IF LLM_TGKIND == "工作"
> ```
> （本项目里还发现它的值会**带引号**，所以顺带去一下更稳。）
>
> **② 拼接提示串时，后面别用 `=` 覆盖**
>
> ```erb
> LLM_MSG += @"（你帮她干活…）"     ; 先拼了陪伴提示
> ...
> LLM_MSG = "好感度"               ; ❌ 把它整段覆盖掉！
> ```
>
> 表现极隐蔽：**只有那一轮好感度恰好有变化时**提示才会消失，
> 其余时候看起来完全正常 —— 很容易被当成"偶发"。
> 统一用 `+=`（按需在前面补个全角空格）就不会有这个问题。
>
> **③ 局部变量不跨函数：声明和使用的函数必须一致**>
> ```erb
> @FUNC_A(...)
> #DIMS LLM_NOW          ; ← 声明在 A
> ...
> @FUNC_B(...)
> LLM_NOW = %時刻表示(TIME)%    ; ❌ 报 Lv2「变量"LLM_NOW"未在此函数中定义」
> ```
>
> 实测一次报了 **6 条 Lv2**（每次使用一条），但游戏照样能启动 ——
> 很容易被当成"能跑就行"而忽略，结果那个变量**永远是空**。
>
> **自查脚本**（放在 §0 那套里一起跑）：按 `@函数名` 切分函数边界，
> 收集每个函数的 `#DIM/#DIMS` 声明，再检查每个 `LLM_*` 的使用是否
> 落在声明它的那个函数里；若该变量在**别的**函数里被声明过，就报出来：
> ```powershell
> # 见 §0 的 Python 版自查脚本（build 时会顺带跑）
> ```
> 本项目加这项检查后为 0 问题。
>
> **④ `#FUNCTIONS` 的函数只能返回字符串 —— 返回数值会报 Lv2**
>
> ```erb
> @MY_CHECK
> #FUNCTIONS
> SIF BASE:MASTER:体力 <= 0
> 	RETURNF 1          ; ❌ Lv2「#FUNCTIONS属性的函数返回了数值类型」
> ```
>
> 而且**调用侧会连带报错**：每次 `CALL MY_CHECK` 都会多一条
> 「对标记为 `#FUNCTION(S)` 的函数进行 CALL 调用」（实测一次报 4 条）。
>
> **两种改法**：
> ```erb
> ; A. 要返回数值 → 用普通函数（返回值落在 RESULT）
> @MY_CHECK
> SIF BASE:MASTER:体力 <= 0
> 	RETURN 1
> RETURN 0
> ; 调用：CALL MY_CHECK / IF RESULT ...
>
> ; B. 确实要返回字符串 → 保留 #FUNCTIONS + RETURNF "文本"
> ```
>
> 本项目里 `@LLM_WORK_SKILL`（返回技能值）和 `@LLM_TOO_TIRED`（返回状态码）
> 都是 A 这种写法 —— **只有 `@時刻表示` 之类返回字符串的才用 `#FUNCTIONS`**。
>
> **⑤ `#FUNCTION` 的函数要用"表达式调用"，不能用 `CALL`**
>
> ```erb
> ; ❌ 报 Lv2「对标记为 #FUNCTION(S) 的函数进行 CALL 调用」
> CALL CHARA_HOLIDAY(LLM_CID, 1)
> IF RESULT
> ; ✅ 直接用表达式
> IF CHARA_HOLIDAY(LLM_CID, 1)
> ```
>
> **三种调用方式要分清**（很容易混）：
>
> | 函数类型 | 怎么调 | 怎么取返回值 |
> |---|---|---|
> | `#FUNCTION`（返回数值） | **表达式**：`IF F(x)` / `Y = F(x)` | 表达式本身就是值 |
> | `#FUNCTIONS`（返回字符串） | **`%F(x)%` 插值** | 插值出来就是文本 |
> | **无标记**（普通函数） | **`CALL F(x)`** | 读 `RESULT` |
>
> ⚠️ 游戏里大量函数都是 `#FUNCTION`（扫到 2100+ 个），
> 所以"照抄游戏里某函数的用法"时，**先看它有没有 `#FUNCTION` 标记**。
> 反例：`@CHARA_HOLIDAY` 有标记（要用表达式），
> 而项目自己的 `@LLM_WORK_SKILL` 没标记（用 `CALL` + `RESULT`）。

>
> **⑥ `#DIMS 变量, N` 是「字符串数组」，占 **N 个** 字符串局部槽**
>
> ```erb
> #LOCALSSIZE 8
> #DIMS LLM_PART, 4      ; 占 4 槽
> #DIMS LLM_NUM,  8      ; 占 8 槽  ⇒ 合计 12 > 8，**溢出**
> ```
>
> ⚠️ 这是本项目**潜伏最久**的一个问题：`@LLM_PARSE_DELTA` 从写下那天起
> 就是 `12 槽 / 容量 8`，而 **`tool/erb_check.py` 不查容量**、
> 加载时也**不一定报 Lv2**（可能只是让局部变量静默错乱），所以一直没暴露。
> **2026-09 自查时才揪出来。**
>
> **自查方法**：数每个函数里 `#DIMS` / `#DIM` 的声明数，
> **数组要按它的长度算**，别当成 1 个。
> （形参不算 —— 它不占局部槽。）
>
> **⑦ 不要写"带表达式的下标"，尤其别写进 `@"…"` 插值里**
>
> ```erb
> ; ❌ 双重表达式下标 —— 本项目在 MARK:(CID):反発刻印 上踩过
> LLM_MEMO:(LLM_CID):(LLM_MEMO_CNT:(LLM_CID)) = %LLM_TEXT%
> ; ❌ 插值里带下标 —— 解析失败会**静默变空**，不报错，极难查
> REF_OUT += @"%LLM_MEMO:(LLM_CID):LOCAL%"
> ; ✅ 先算进变量，再用简单下标
> LLM_MEMO_IDX = LLM_MEMO_CNT:(LLM_CID)
> LLM_MEMO:(LLM_CID):LLM_MEMO_IDX = %LLM_TEXT%
> LLM_MEMO_TMP = %LLM_MEMO:(LLM_CID):LOCAL%
> REF_OUT += @"%LLM_MEMO_TMP%"
> ```
>
> **⑧ 抄官方判定时，注意变量**作用域**（带不带角色下标）**
>
> 同一个概念，官方在**玩家侧**和**角色侧**是**两个不同的变量**：
>
> | 变量 | 编号 | 属于谁 |
> |---|---|---|
> | `CFLAG:诶嘿嘿`（不带角色）| 317 | **玩家**（= `CFLAG:MASTER:诶嘿嘿`）|
> | `CFLAG:角色:诶嘿嘿` | 317 | **角色** |
> | `CFLAG:角色:延迟` | 333 | **角色** |
> | `CFLAG:角色:信赖度` | 4 | **角色** |
>
> ⚠️ `@被逆推` 里的判定 `!CFLAG:诶嘿嘿 && TFLAG:102 != 3` 用的是**玩家侧**的，
> 照抄时若写成 `CFLAG:角色:诶嘿嘿` 就会判错（该拦的没拦住）。
>
> **⑨ 调官方流程函数前，先把它内部的 `RETURN` 前置条件抄过来**
>
> 例：`@被逆推` 开头是 `IF FLAG:推倒 == 2 / RETURN`（**静默返回，什么都不做**）。
> 如果不检查就 `CALL` 然后按"已触发"处理（比如 `BREAK` 掉对话循环），
> 玩家看到的就是**「对话突然结束，却什么都没发生」**。

>
> **⑩ `%…%` 只能装**字符串**；输出**数值**要用 `{…}`**
>
> ```erb
> ; ❌ Lv2「% %中的表达式结果不是字符串」
> PRINTFORML 　正在思考（已等待 %LLM_WAIT / 1000% 秒）
> PRINTFORML 　重试 %LLM_TRY%／2
> ; ✅ 数值用 {…}
> PRINTFORML 　正在思考（已等待 {LLM_WAIT / 1000} 秒）
> PRINTFORML 　重试 {LLM_TRY}／2
> ```
>
> ⚠️ **`%…%` 和 `{…}` 分工不同**：
>
> | 写法 | 装什么 | 例子 |
> |---|---|---|
> | **`%…%`** | **字符串**（函数/字符串变量）| `%CALLNAME:TARGET%`、`%TOSTR(X)%` |
> | **`{…}`** | **数值**（数值表达式）| `{积攒度 / 10}`、`{LOCAL}` |
>
> 官方也是这么用的：`BODY_INFO.ERB:25` → `接吻过{EXP:選択中キャラID:接吻経験}次`；
> `PRINT_STATE.ERB:73` → `欲求：{CFLAG:選択中キャラID:积攒度 / 10}％`。
>
> **记忆法**：**花括号 `{}` 装数字，百分号 `%%` 装文字。**
>
> **⚠️ 另一个易混点**：`%` 在 ERB 里**既是插值分隔符、又是取模运算符**。
> 写 `IF X % 5000 < 80` 是合法的取模，但自查脚本会误报"百分号不配平" ——
> 遇到这种判断（比如"每 5 秒更新一次"），**改用"下次触发时间"变量更清晰**：
> ```erb
> IF LLM_WAIT >= LLM_NEXT_TIP
> 	LLM_NEXT_TIP += 5000
> 	...
> ENDIF
> ```

### 0.3 加载后必看

- **加载画面有没有 `Lv1` / `Lv2` 警告**（这些**不会写进任何日志文件**，只能在屏幕上看）
- 游戏内点 **`[5] 自检`**，确认函数都被注册
- 看 `plugins/LLMBridge/debug.log`

> **教训**：本项目排查最久的一个 bug（点 `[4]` 没反应）最终就是 **5j 的 `SIF` 多行**，
> 而它**不报错、不写日志、自检还全 OK** —— 因为 `@COM381` 用 `TRYCALLFORM`，
> 会把被调函数的异常**静默吞掉**。

---

## 1. `%...%` 求值：结果必须是字符串

### 报错
```
%中的表达式结果不是字符串
```

### 错误
```erb
#DIM LLM_COL
PRINTFORML [%LLM_COL%] 选项名          ; ← LLM_COL 是整数，#DIM
```

### 原因
`%...%` 是**字符串求值**语法，要求内容求值为字符串。
`#DIM` 声明的是**整数**变量（`#DIMS` 才是字符串）。

### 正确
```erb
; 方案 A：写成字面量，不插值（最稳，推荐）
PRINTBUTTON "[0] 切换开关", 0

; 方案 B：数值先转字符串再插值
PRINTFORML [%TOSTR(LLM_COL)%] 选项名
```

### 附：能安全放进 `%...%` 的
| 可放 | 例 |
|---|---|
| 字符串变量 | `%CALLNAME:TARGET%`、`%RESULTS%` |
| 字符串函数 | `%GETCOMNAME(300)%` |
| 转成字符串后的数值 | `%TOSTR(TARGET)%` |

**别放**：`#DIM` 声明的整数变量、`TARGET`/`RESULT` 等整数内置变量（直接放会报错）。

---

## 2. `@"..."` 里不要再嵌 `%...%`

### 报错
```
%中的表达式结果不是字符串
```

### 错误
```erb
CALL LOG(@"目标=%TARGET% 名字=%CALLNAME:TARGET%")
```

### 原因
`@` 前缀是**抑制转义/延迟求值**语义，与 `%...%` 内联求值冲突，嵌套时解析失败。

### 正确
```erb
; 改用普通字符串
CALL LOG("目标已确定")
; 或在 PRINTFORM 系里用 {} 花括号求值
PRINTFORML 目标={TARGET} 名字={CALLNAME:TARGET}
```

---

## 3. `#FUNCTION` / `#FUNCTIONS` 不能用 `CALL`

### 报错
```
对标记为#FUNCTION(S)的函数"@XXX"进行CALL调用
```

### 错误
```erb
CALL BUILD_COM_BUTTON_HTML(9000, "文字")
```

### 正确
```erb
; #FUNCTION 返回整数，#FUNCTIONS 返回字符串，都要用变量接收
#DIMS L_HTML
L_HTML '= BUILD_COM_BUTTON_HTML(9000, "文字")    ; 接函数返回值 → 用 '=
#DIM L_NUM
L_NUM = SOME_INT_FUNC(1)                          ; 整数赋值用 =
```

判断方法：看目标函数定义处是否有 `#FUNCTION` 或 `#FUNCTIONS`。

---

## 3b. 字符串变量赋值：拷贝内容必须用 `%...%`（FORM 语法）

> **本条曾写错，现依据官方文档更正。**
> 出处：Emuera 帮助文档 → Emuera 概要 → 面向开发者 → Emuera中新增的语法 →
> 「使用FORM语法对字符串变量赋值」/「使用字符串表达式对字符串变量赋值」

### 报错 / 现象
```
表达式异常
整型数值的赋值运算符不能使用"'="
%%中的表达式结果不是字符串
```
或**不报错但内容错误**：显示出来的是**变量名本身**（如 `LLM_KOJO_LBL`），而不是它的值。

### 原因
Emuera 里给字符串变量赋值有**两套语义**，文档里有明确的正确/错误示例：

```erb
;官方「正确示例」
SAVESTR:0 = %RESULTS%      ; 把 RESULTS 的**内容**赋过去

;官方「错误示例」
STR:0 = RESULTS            ; 得到字面字符串 "RESULTS"（变量名本身！）
RESULTS += %STR:0%         ; 出错
```

**裸写变量名 = 字面字符串**；要取变量的**内容**必须套 FORM 语法 `%...%`。

### 正确写法
```erb
;拷贝另一个字符串变量的内容 —— 用 %...%
LLM_A = %RESULTS%
LLM_A = %RESULTS:1%
LLM_A = %LLM_B%

;赋字面量 —— 直接写
LLM_A = 初始
LLM_A = 自由对话
```

### 那 `'=` 什么时候能用？
`'=` 是「字符串**表达式**赋值」，需要 config 开关配合：
```
emuera.config: STRING VARIABLE ASSIGNMENT ON VALID WITH STRING EXPRESSION:NO
```
**本作为 NO，所以 `'=` 不可用**（用了会报「整型数值的赋值运算符不能使用'=」）。

只有函数返回值那类场合才必须用到 `'=`，本仓库既有写法：
```erb
LOCALS:1 '= BUILD_COM_BUTTON_HTML(9999, LOCALS)   ; #FUNCTIONS 返回值
```
> 注意：这行在本作里能工作，说明 `#FUNCTIONS` 返回值走的是另一条路径；
> 但**不要**把 `'=` 用在普通字符串变量拷贝上。

### 口诀
| 右边是 | 写法 |
|---|---|
| 另一个**字符串变量的内容** | `X = %变量%` |
| **字面量**文本 | `X = 文本` |
| `#FUNCTION(S)` **函数返回值** | `X = 函数(...)` 或 `X '= 函数(...)` |

---

## 4. 具名 CFLAG 必须先登记

### 报错
```
无法解析的标识符"XXX"
```

### 错误
```erb
CFLAG:TARGET:LLM对话临时开关 = 1     ; 该名字没在 CSV\CFLAG.csv 里
```

### 原因
`CFLAG` 的**具名**下标来自 `CSV\CFLAG.csv`（中文别名见 `CFLAG.als`）。
没登记的名字，ERB 解析期就找不到。

### 正确
```erb
; 不改 CSV 时，用数字下标（CFLAG 数组上限 10000，无需声明）
CFLAG:TARGET:1100 = 1                ; 1100 属本 mod 空闲区
```

**本 mod 可安全使用的 CFLAG 空闲区**：
- `1100~1149`（实测未被 `CFLAG.csv` 占用）
- `6000~6399`（本汉化 mod 预留；`6300`/`6320`/`6326`/`6327` 已被占用）
- `9100~9173`（本 mod 新增区）

**已占用不可用**：`998 口上セレクタ`、`999 口上用引継ぎ枠`、`1000~1999 口上预留`

---

## 5. `ARGS` 是保留变量名

### 报错
```
变量名"ARGS"为Emuera所使用的变量名
```

### 原因
`ARG` / `ARGS` / `RESULT` / `RESULTS` / `LOCAL` / `LOCALS` / `TARGET` / `MASTER` / `TIME` / `DAY`
等都是 **Emuera 内置变量名**，不能作为自定义函数的参数名或局部变量名。

### 正确
```erb
; 换个名字
@MY_LOG(LLM_MSG)
#DIMS LLM_MSG
...
```

**自定义变量建议统一加前缀**（如 `LLM_`），既避开保留名，也避开与其它 mod 撞名。

---

## 5b. 形参名写 `REF_` **不等于**引用传递 —— 必须 `#DIM REF 名`

### 现象（两个都实际发生过，且极难定位）
- 函数里拼好的字符串传不回调用方 → 表现为**空串**（日志 `sysLen=0`，persona 送不出去）
- 输出的状态码永远是最初值 → 表现为**"秒超时"**，明明模型 2 秒就回了

### 原因
Emuera 里**只有**声明成 `#DIM REF 名` / `#DIMS REF 名` 的形参才是引用传递（参照渡し）。
形参**叫什么名字完全不影响语义** —— `REF_XXX` 只是人类约定，引擎不认。

### 错误
```erb
@MY_FUNC(REF_TEXT)
#DIMS REF_TEXT          ; ← 值传递！里面的修改外部看不见
REF_TEXT = "结果"
RETURN
```

### 正确
```erb
@MY_FUNC(REF_TEXT)
#DIMS REF REF_TEXT      ; ← 引用传递
REF_TEXT = "结果"
RETURN
```

本作既有范例：`DOKU_ABOUT_ULTRA_ASK_M.ERB:7-9`（`#DIMS REF REF_STR`）、
`SHOW_PANTIES.ERB:61`（`#DIM REF グラフィックID`）、`CASINO_SLOT_TYUSEN.ERB`。

> 数值形参（如 `#DIM LLM_CID`）读值是没问题的，只有**需要"写回调用方"**的
> 形参才必须加 `REF`。

### 本项目实际漏过 **三处**，症状各不相同（值得逐个记住）

| 函数 | 漏 REF 的形参 | 症状 |
|---|---|---|
| `@LLM_BUILD_SYSTEM_PROMPT` | `REF_PROMPT` | 拼好的 prompt 传不回来 → 日志 `sysLen=0`，persona 从未送给模型 |
| `@LLM_POLL` | `REF_STATE` / `REF_TEXT` | 状态码永远是初值 → 判"超时"，表现为**秒超时** |
| `@LLM_SANITIZE_REPLY` | `REF_TEXT` | 清洗**从未生效** → 模型带的引号、换行、`名字：`前缀原样显示 |

> 前两处的共同点：**函数看起来完全正确，日志也不报错**，只是"结果没传出来"。
> 第三处更隐蔽 —— 程序照常工作，只是少做了一步清洗，很容易被当成"模型输出就这样"。
>
> ⇒ **规矩**：每新增一个"要写回调用方"的形参，都专门确认一次有没有 `REF`。
> 检查办法：把所有 `#DIM/#DIMS` 里出现过 `REF ` 的函数列出来，逐个对照它的形参表。

### ⚠️⚠️ 补上 `REF` 之后，**必须把那几行的右侧写法也重看一遍**

这是本项目最贵的一次教训（`@LLM_SANITIZE_REPLY`）：

那一串清洗语句原本全是**错的写法**：
```erb
REF_TEXT = REPLACE(REF_TEXT, "  ", " ")     ; ← 字符串函数裸写在 = 右侧
```
但因为同一函数**还漏了 `REF`**（结果根本传不回来），这段坏代码**从未生效**，
所以一直没人发现。等我给形参补上 `REF` 之后，它们**立刻开始生效**，
于是把台词整个替换成了字面文本：

```
「REPLACE(REF_TEXT, "  ", " ")」      ← 玩家实际看到的"台词"
```

**机制**：`REF` 只负责"传得回来"，不负责"算得对"。原来是"算错了但传不回来"，
补了 `REF` 就变成"算错了而且真的写进去了" —— 从"静默无害"升级成"静默有害"。

### ⇒ 规矩

**修好引用传递（`REF`）之后，重新检查那几行有没有"本作没有的函数"或"字符串函数裸写"**，
因为这些错误原先被"传不回来"掩盖着。

正确写法是 `'=`（字符串**表达式**赋值）：
```erb
REF_TEXT '= REPLACE(REF_TEXT, "  ", " ")    ; ✅
REF_TEXT '= TRIM_STRING(REF_TEXT)           ; ✅
```
参考本作 `@TRIM_STRING` 自身的实现（`PRINT_STATE_BODYGRAPH.ERB:222-223`），
它内部就是 `LOCALS '= REPLACE(...)`。

> 一句话：**两个错误叠在一起会互相掩护；修掉其中一个，另一个就会现形。**
> 本例中"漏 REF"掩护了"裸写字符串函数"，两者都修完才是真的对。

---

## 5c. 绝不写跨物理行的 `@"…"` 字符串 —— 会**整个游戏停止运行**

### 现象
加载时刷一屏 Lv2 警告，最后一句是：
```
由于ERB脚本出现无法解释的行，Emuera停止运行
GameBaseにエラーが発生しました
```
具体警告形如：`无法解析的行`（第二行起每一行都报）、`没有闭合的 "`。

### 错误
```erb
LLM_P = @"第一行
第二行
"
```

### 原因
Emuera 的解析器**不支持多行字符串字面量**。它按物理行切语句，
第二行起被当成新的语句，于是"无法解析的行"，而那个 `"` 永远等不到闭合。

### 正确
把 `\n` **转义写在同一行里**（本作既有写法）：
```erb
LLM_P = "第一行\n第二行\n"
LLM_P = %LLM_P% + "\n第三行"
```
参考：`DLC\小游戏\抛硬币.ERB`、`DLC\OPTIONPRINT.ERB`。

> ⚠️ 这一条 `tool/erb_check.py` **查不出来**，必须人工扫。
> 自查办法：非注释行里 `"` 的个数必须是**偶数**，奇数即为跨行字符串。

---

## 5d. `CALLSHARP` 只回填**最后一个参数**

### 现象
插件把状态码写在倒数第二个参数、文本写在最后一个参数，
结果状态码那一路**永远是初值**（本例：轮询状态恒为 0 → 无限轮询到超时）。

### 原因
引擎在 `CALLSHARP` 之后只把**最后一个参数**回写给 ERB 变量。
中间参数即使插件改了，也会被丢掉。

### 正确
**状态码和文本拼进同一个（最后一个）参数**，约定一个前缀格式，例如：

| 插件回填 | 含义 |
|---|---|
| `"0"` | 仍在等待 |
| `"1"` + 文本 | 成功 |
| `"-1"` + 原因 | 失败 |

ERB 侧用 `SUBSTRING(串, 0, 1)` 取状态码，再按需截取正文。

### 另外：回填的**类型**也要对
`PluginMethodParameter` 有 `isString` / `strValue` / `intValue`：
- 回填给 `#DIM`（数值）变量的，用 `intValue`（`isString = false`）
- 回填给 `#DIMS`（字符串）变量的，用 `strValue`

类型不对时改动同样会被丢弃。

---

## 5e. 字符串函数（`SUBSTRING` 等）**只能写在 `%…%` 里**，裸写会变成字面文本

### 现象（极隐蔽：不报错、不崩溃，逻辑静默走错）
```erb
LLM_ST = SUBSTRING(LLM_RAW, 0, 1)
SIF LLM_ST != "0"
    BREAK
```
结果 `LLM_ST` 得到的**不是**首字符，而是字符串
`SUBSTRING(LLM_RAW, 0, 1)` 本身 —— 于是它永远 `!= "0"`，
循环第一轮就被当成"已有结果"退出。表现是**轮询一次就"超时"**。

实测证据（把值打印出来的诊断行）：
```
[LLM 诊断] 轮询次数=1 累计等待=0ms 状态=SUBSTRING(LLM_RAW, 0, 1) 原始=[0]
                                 ↑ 字面文本，不是返回值
```

### 原因
`SUBSTRING` 是"可在 FORM 语法中使用的函数"，**在普通赋值右侧裸写不会调用它**。
这和第 1 条（`%...%` 只接受字符串结果）是同一族的坑，但方向相反：
第 1 条是"放进去会报错"，这条是"不放进去就静默变成文本"。

### 正确
```erb
LLM_ST = %SUBSTRING(LLM_RAW, 0, 1)%      ; 套上 %...%
```
或者干脆直接用在条件里 / 直接用在 `PRINTFORML` 里：
```erb
SIF %SUBSTRING(LLM_RAW, 0, 1)% != "0"
```

### 同类需要留意的函数
`STRLENS` / `SUBSTRING` / `TOSTR` 这类**返回值的字符串函数**，
在赋值右侧都要用 `%…%` 包住；只有 `#FUNCTION` 用户函数才能裸写调用。

> 排查技巧：怀疑某个表达式没被求值时，**先把它打印出来**。
> 如果打印出来是"表达式原文"，那就是本条。

---

## 5f. 字符串拼接：变量**必须写在引号内**（`@"…%变量%…"` + `+=`）（最坑的一条）

### 现象
拼出来的 system prompt 里，本该是"角色名 / persona"的位置，
变成了**变量名的原文**。模型拿不到角色是谁，于是自己瞎编 ——
实测表现为：**所有角色都 OOC，自称博丽灵梦 / 八云紫 / 上白泽慧音**，
而且每个角色说的都不一样（因为模型在随机猜）。

### 错误
```erb
REF_PROMPT = "…【角色】" + LLM_CHAR_NAME + "【本作…】"
```
拼出来的是：
```
…【角色】" + LLM_CHAR_NAME + "【本作…】
          ^^^^^^^^^^^^^ 变量名原文
```

### 日志证据（把 prompt 原文落盘就一眼看到）
```
CHAT-SYS head="你正在扮演…" + " 【角色】" + LLM_CHAR_NAME + " 【本作…" + LLM_PERS…
```

### ⚠️ 只套上 `%…%` **仍然不够**（下面这版才是最终结论）
```erb
REF_PROMPT = %REF_PROMPT% + "\n【角色】" + %LLM_CHAR_NAME%    ; ❌ 依然坏
```
拼出来的是：
```
\n【角色】" + 灵梦 + "
          ^^^^^^^^^^^ 引号和加号被一起拼进串里
```
**把变量当成独立的 `+` 项时**（哪怕套了 `%…%`），求值结果会**连引号和加号一起**进串。

### 正确（唯一安全写法）
变量必须写在**字符串内部**，并用 `+=` 累积：
```erb
REF_PROMPT = @"你正在扮演…"
REF_PROMPT += @"\n【角色】%LLM_CHAR_NAME%"
REF_PROMPT += @"\n【与玩家的关系】%LLM_REL%"
```
即 **`@"…%变量%…"` 配 `+=`**。

### 规则总结

| 拼接里的东西 | 写法 |
|---|---|
| 纯文本 | `X += "…"` |
| **字符串变量** | `X += @"…%变量%…"` ← 变量写在**引号内** |
| 数值变量 | `X += @"…{变量}…"`（也在引号内） |
| `#FUNCTION(S)` 用户函数 | 直接写 `函数(…)` |

> 这和 5e 条（`SUBSTRING` 裸写变文本）是同一个根因：
> **Emuera 的求值只发生在字符串内部**，写在字符串外面（哪怕是 `%…%`）
> 都可能把定界符一起拼进去。
> 排查办法永远一样：**把拼出来的串打印/落盘**，看到变量名或引号加号就是它。

---

## 5g. 本作**没有**的函数名 —— 用了只报 Lv2，逻辑静默失效

### 现象
加载时一行 Lv2：`无法解析的标识符"TRIM"`。
**不阻止运行**，但那个表达式/判断等于没生效 —— 比崩溃更难发现。

### 实例（本 mod 实际踩的）
| 想用的（错） | 本作实际的名字 | 出处 |
|---|---|---|
| `TRIM(x)` | **`TRIM_STRING(x)`**（`#FUNCTIONS`，用 `'=` 接） | `PRINT_STATE_BODYGRAPH.ERB:216` |
| `STRLEN(x)` | **`STRLENS(x)`** | 引擎内建 |
| `SUBSTRING(…)` 裸写 | 必须包在 `%…%` 里（见 5e） | — |

### 教训
`@LLM_SANITIZE_REPLY` 里那句 `REF_TEXT = TRIM(REF_TEXT)` **一直就是坏的**，
但因为同一函数当时还漏了 `REF`（结果传不回来，见 5b），
"清洗没生效"被误当成"模型输出就这样"，直到这次在别处复用同样写法才暴露。

> **两个错误叠在一起，会互相掩护。** 修好一个之后要重新看另一个是不是也一直没工作。

### 自查办法：全项目函数名存在性扫描（推荐每次改完跑一次）

思路：我用到的每个函数名，如果**全项目其它 4000 多个 ERB/ERH 里从没出现过**，
那它多半不存在（`TRIM` 就是这么抓出来的）。

```powershell
$target = (Resolve-Path "ERB\魔改内容\LLM_CONVERSATION.ERB").Path
$mine  = [System.IO.File]::ReadAllText($target)
$defined = [regex]::Matches($mine,'(?m)^@([A-Za-z_0-9]+)') | % { $_.Groups[1].Value }
$myCalls = [regex]::Matches($mine,'(?<![A-Za-z_0-9])([A-Za-z_][A-Za-z_0-9]*)\s*\(') |
           % { $_.Groups[1].Value } | Sort-Object -Unique
$others  = Get-ChildItem "ERB" -Recurse -File -Include *.ERB,*.ERH |
           Where-Object { $_.FullName -ne $target }
$seen = New-Object 'System.Collections.Generic.HashSet[string]'
foreach ($f in $others) {
  foreach ($m in [regex]::Matches([System.IO.File]::ReadAllText($f.FullName),
      '(?<![A-Za-z_0-9])([A-Za-z_][A-Za-z_0-9]*)\s*\(')) { [void]$seen.Add($m.Groups[1].Value) }
}
foreach ($c in $myCalls) {
  if ($defined -contains $c) { continue }
  if ($seen.Contains($c))    { continue }
  "⚠ $c"
}
```

> 只有 `LLM_CHAT_SEND` / `LLM_CHAT_POLL` / `LLM_CHAT_CANCEL` 会被报出来 ——
> 那是插件方法（走 `CALLSHARP`），本来就不在 ERB 里定义，属正常。

---

## 5h. `#LOCALSIZE` 只是分配槽位，**变量仍要 `#DIM` 声明**

### 现象
```
Lv2: 无法解析的标识符"LLM_ANGER_LIMIT"
```

### 错误
```erb
@FUNC(A)
#DIM A
#LOCALSIZE 1              ; ← 以为这样就能用局部变量了
LLM_ANGER_LIMIT = 6       ; ← 报错：没有声明过这个名字
```

### 正确
```erb
@FUNC(A)
#DIM A
#DIM LLM_ANGER_LIMIT      ; ← 变量必须显式声明
#LOCALSIZE 1
LLM_ANGER_LIMIT = 6
```

### 附：`LOCAL` / `LOCALS` 是**引擎内建**的局部变量
它们不需要声明、量也足够，游戏里到处直接用（`LOCAL = GETPALAMLV(...)`）。
自己起名（`LLM_xxx`）时就必须老老实实 `#DIM`。

> 自查：把所有赋值左侧出现的 `LLM_` 变量收集起来，
> 与 `#DIM/#DIMS`（含 `.ERH`）里声明的名字对照，差集就是漏声明的。

---

## 5i. 裸文本在不同位置规则不同 —— **函数参数位置必须加引号**

### 现象
```
Lv2: 无法解析的标识符"通常"
CALL GET_BASE_RESOURCE(LLM_CID, LLM_STYLE, "", 通常)
                                              ^^^^ 少了引号
```

### 原因
Emuera 对"裸文本"（不加引号的文本）的处理**按位置各不相同**：

| 位置 | 裸文本的含义 | 例子 |
|---|---|---|
| 赋值右侧 | **字符串字面量** ✅ | `LLM_EXPR = 通常` 合法 |
| **函数参数** | **变量名 / 标识符** ❌ | `FUNC(通常)` → 报"无法解析的标识符" |
| `PRINTFORM` 系命令后 | 要打印的文本 ✅ | `PRINTFORML 你好` 合法 |

所以**同一个词，写在赋值里没问题，写进函数参数就报错** —— 这个不一致最容易踩。

### 正确
```erb
CALL GET_BASE_RESOURCE(LLM_CID, LLM_STYLE, "", "通常")
CALL PRINT_FIGURE(LLM_CID, "通常", "", "", "", "顔絵")
```

### 附带：本作里"字符串"相关的三条规则合起来看

1. **函数参数**里的文本要加引号（本条 5i）
2. **字符串变量**在 `+` 拼接里要写在引号内或用 `%…%`（第 5f 条）
3. **字符串函数**只能写在 `%…%` 里，或用 `'=` 接（第 5e 条）

> 一句话：**除了"赋值右侧"和"PRINT 系命令后"，其它位置看见裸文本就要警惕。**
> 排查办法：在含 `CALL/IF/SIF` 的行里，找参数位上"不带引号、不带 `%`、也不是纯 ASCII 标识符"的东西。

---

## 5j. `SIF` **只作用于紧随的一行** —— 后跟多行会静默改变语义

### 现象（本项目踩过两次，症状完全不同）
```
① 点 [4] 后菜单直接退出、什么都不显示（像是"点了没反应"）
② 明明有可用接口，菜单却总显示「接口：0 条可用 / 请点 [1] 查看具体缺什么」
```

### 错误
```erb
SIF LLM_API_CNT <= 0
	PRINTFORML 请先填写接口      ; ← 只有这一行受 SIF 约束
	WAIT                        ; ← 这两行**无条件执行**！
	BREAK                       ;    于是点 [4] 必然直接 BREAK 掉菜单
ENDIF                           ;    （而且 ENDIF 变成了多余的 → 语义更乱）
```

### 原因
`SIF`（Single IF）**只管紧随其后的那一行**，缩进对它没有任何约束力。
所以"`SIF` + 多行缩进块"这种写法里，**第二行起会无条件执行** ——
不报错、不警告，只是逻辑悄悄变了。

### 正确
需要管多行就用完整的 `IF ... ENDIF`：
```erb
IF LLM_API_CNT <= 0
	PRINTFORML ...
	WAIT
	BREAK
ENDIF
```
只有**确实只有一行**时才用 `SIF`：
```erb
SIF !LLM_READY
	BREAK                       ; ✅ 单行，安全
```

### 自查脚本（每次改完跑一遍）
思路：`SIF` 之后如果跟着**多于一行**的更深缩进块，就可疑。

```powershell
foreach ($file in @("ERB\魔改内容\LLM_CONVERSATION.ERB","ERB\魔改内容\LLM_CHAT_BRIDGE.ERB")) {
  $lines = Get-Content $file -Encoding UTF8
  for ($i=0; $i -lt $lines.Count; $i++) {
    $t = $lines[$i]
    if ($t -notmatch '^\s*SIF\s') { continue }
    $ind = ($t -replace '[^\t].*$','').Length
    $j = $i + 1; $cnt = 0
    while ($j -lt $lines.Count) {
      $n = $lines[$j]
      if ($n.Trim() -eq '') { break }
      $nind = ($n -replace '[^\t].*$','').Length
      if ($nind -gt $ind) { $cnt++; $j++ } else { break }
    }
    if ($cnt -gt 1) { "⚠ {0}:{1} SIF 后跟 {2} 行: {3}" -f $file,($i+1),$cnt,$t.Trim() }
  }
}
```

> 这个坑的可怕之处：**改动极小（`IF…ENDIF` → `SIF`），逻辑却完全变了，
> 而且没有任何报错**。我当时正是为了"顺手简化"才改成 SIF 的。

---

## 6. `EXISTMETH` / `EXISTFUNCTION` 不认插件方法

### 现象
不是报错，而是**静默失效**：判定恒为假，导致入口永远不显示。

### 错误
```erb
SIF !EXISTMETH("LLM_HAS_FREE_TALK")    ; CALLSHARP 插件方法 → 恒为假
    RETURN 0
```

### 原因
`EXISTMETH` 只查 **ERB 侧**方法，不查 `CALLSHARP` 注册的插件方法。

### 正确
```erb
; 直接调插件，用返回值判断
#DIMS LLM_TMP
CALLSHARP LLM_IS_READY(LLM_TMP)
SIF LLM_TMP != "1"
    RETURN 0
```
插件缺失时 `CALLSHARP` 只会由引擎报一条 `No native method` 警告并**回填空串**，
不会中止游戏，所以直接调是安全的。

---

## 7. `PRINTBUTTON` 是"按钮带"语义 —— 多个按钮会横向拼接

### 现象
菜单里多个选项挤在同一行：`[1] 甲[2] 乙[99] 返回`

### 原因
`PRINTBUTTON` **不是**普通文本打印，而是往当前行插入一个**按钮**。
用 `STR:1` 可验证它的实际输出：

```
STR:1 = "[0] 切换本角色的临时开关[0] "    ← 注意自带尾随空格，且是按钮结构
```

按钮属于 Emuera 的按钮栏机制。即使写成 `PRINTBUTTON` + `PRINTL` 交替
（这确实是本 mod 的惯用竖排写法，仓库里有 6 处范例），
在复杂上下文里换行仍可能不受控，实测出现过粘连。

### 推荐
需要**可控排版**时，选项改用 `PRINTPLAIN`（纯文本，不产生按钮标记）：

```erb
PRINTPLAIN [0] 选项甲
PRINTL
PRINTPLAIN [1] 选项乙
PRINTL
...
INPUT
```

`INPUT` 同时接受**点击按钮**和**输入编号回车**，
所以用 `PRINTPLAIN` 只是放弃"可点"，不会失去"可选择"。

> 若确实需要可点按钮，优先用 mod 的封装：
> `CALL PRINTBUTTON_EX(文本, 值)`（`HTML_PRINT_Components.ERB:13`），
> 它统一处理颜色/禁用态，`IS_DISABLED=0` 时内部走普通 `PRINTBUTTON`。

---

## 8b. 跨函数共享的变量必须**文件级声明**

### 报错
```
无法解析的标识符"LLM_PERSONA"
```
一次刷出几十条，指向同一组变量。

### 错误
```erb
@FUNC_A
#LOCALSIZE 1
LLM_PERSONA = "x"        ; 只在 A 里出现 → 隐式变量
RETURN

@FUNC_B
#LOCALSIZE 1
SIF LLM_PERSONA == ""    ; ← 报「无法解析的标识符」
```

### 原因
Emuera 里**函数内首次出现的变量不会自动升级为全局**。
一个变量要在多个函数间共享，必须声明在**头文件 `.ERH`** 里。

### ⚠️ 关键：声明**不能**直接写在 `.ERB` 文件级

```erb
; ❌ 错误 —— 放在 .ERB 顶部会报 Lv1
;    「#行只能在函数声明后立刻使用」
#DIMS LLM_PERSONA

@FUNC_A
```

```
; ✅ 正确 —— 单独建一个 .ERH，声明放里面
; 文件：LLM_KOJO.ERH
#DIMS LLM_PERSONA
#DIM  LLM_PERSONA_OK

; 文件：LLM_CONVERSATION.ERB
@FUNC_A
LLM_PERSONA = "x"
RETURN
```

参考本 mod 的既有写法：`ERB\口上・メッセージ関連\KOJO_MESSAGE.ERH`
就是文件级 `#DIMS KOJO_ACTIVE_NAME, 人物数量上限`。

`.ERH` 会被自动读取（`emuera.config: SEARCH SUBFOLDERS:YES`），
**不需要**在任何地方 `#INCLUDE` 或手动加载。

### 另外两点

1. **数值用 `#DIM`，字符串用 `#DIMS`**。用错会在比较时报
   `无法对字符串型和数值型使用二相运算符`。
   （实例：`#DIMS LLM_STATE` 却写 `WHILE LLM_STATE == 0`）
2. **不要重复声明内置变量**（`TARGET` / `RESULT` / `ARG` / `TIME` …），
   直接赋值即可。

---

若某个选项会按条件隐藏，硬编码 `CASE` 编号会点错。两种做法：

```erb
; 方案 A：字面量编号，但每个分支都显式对应
IF 条件
    PRINTBUTTON "[0] 甲", 0
    PRINTL
    PRINTBUTTON "[1] 乙", 1
    PRINTL
ELSE
    PRINTBUTTON "[0] 乙", 0        ; ← 注意这里乙变成 0
    PRINTL
ENDIF
SELECTCASE RESULT
    CASE 0
        IF 条件
            ...甲...
        ELSE
            ...乙...
        ENDIF
ENDSELECT
```

---

## 9. 选项编号别硬编码（隐藏项会导致错位）

若某个选项会按条件隐藏，硬编码 `CASE` 编号会点错。两种做法：

```erb
; 方案 A：字面量编号，但每个分支都显式对应
IF 条件
    PRINTBUTTON "[0] 甲", 0
    PRINTL
    PRINTBUTTON "[1] 乙", 1
    PRINTL
ELSE
    PRINTBUTTON "[0] 乙", 0        ; ← 注意这里乙变成 0
    PRINTL
ENDIF
SELECTCASE RESULT
    CASE 0
        IF 条件
            ...甲...
        ELSE
            ...乙...
        ENDIF
ENDSELECT
```

> 注：本项目最终改用**显式 HTML + `<br>`**（见第 7 条）后，
> 不再使用 `PRINTBUTTON`，本条的适用场景也相应减少。

---

## 10. 相关文件位置

| 用途 | 路径 |
|---|---|
| ERB 结构检查器 | `tool\erb_check.py` |
| CFLAG 名表 | `CSV\CFLAG.csv`（中文别名 `CSV\CFLAG.als`） |
| CFLAG 常量头 | `ERB\Headers\AutoConst_CFLAG.ERH` |
| 口上调度 | `ERB\口上・メッセージ関連\KOJO_MESSAGE.ERB` |
| 全局自定义指令 | `ERB\fromEN\Custom_Commands\Add_Custom_Commands.ERB` |
| 自定义指令名表 | `ERB\fromEN\Custom_Commands\ADD_CUSTOM_SCOM_NAMES.ERB` |

---

## 11. Prompt 工程经验（不是语法坑，但同样花了两轮才解决）

### 想追加额外输出格式时：**位置靠前 + 完整示例 + 明确禁止省略**

**踩坑过程**：让模型在台词后附带一个结算块
（`###DELTA###` + `a,b,c`，用于数值联动）。
最初把要求写在 **system prompt 末尾**，只说了句"必须输出"，**也没给例子**。
结果模型**完全无视**它 —— 日志里回复干干净净，连 `###DELTA###` 都没有：

```
CHAT-OK id=1 replyLen=16 reply=有事吗？没事的话别站在这里挡路。
```

排查时容易误判成"ERB 解析失败"，**其实模型压根没输出**。
（判断办法：直接看插件日志的 `reply=` 原文，别猜。）

**改成下面三条一起上，立刻就服了**：

1. **把格式要求提到【硬性要求】之前**（末尾的长指令容易被忽略）
2. **给两个完整的输入→输出示例**（含分隔符和真实数字）
3. **明确写"漏掉数值块视为格式错误"**（堵住"省略也无所谓"的解读）

之后日志变成：

```
CHAT-OK id=2 reply=嗯，你好……有事吗？没事的话就别在这站着了。  ###DELTA### 0,0,0
```

### 附带的两个次要观察

- 模型会把结算块接在**台词同一行**（用空格分隔）而不是另起一行 ——
  解析要**同时兼容**两种情况，不能假定有换行。
- 它倾向给 `0,0,0`（对平淡寒暄这是**正确**的）。
  所以"看不到数字"未必是坏了 —— **不要设计成"全 0 就静默"**，
  否则玩家无法区分「给了 0」/「没给块」/「功能没跑」。

> 详细实现见 `LLM对话系统实现说明.md` §5.3 与 §10。

---

## 5k. ⚠️⚠️ **行的开头必须是合法字符** —— 否则游戏**直接拒绝启动**

### 现象

游戏启动时：

```
警告Lv2:魔改内容\LLM_CONVERSATION.ERB:第1785行:使用不正确的文字作为行的开始
半句话去撩他。
文件读取完成。耗时：3.62 秒
按 Enter 键或点击鼠标左键继续
由于ERB脚本出现无法解释的行，Emuera停止运行
```

**⇒ 这不是"少个功能"，是**整个游戏起不来**。**

### 错误

```erb
;     · **关系深**（= 2，恋慕 / 恋人 / 爱欲）⇒ 才会用眼神、小动作、
>       半句话去撩他。          ← ★ 行的开头是 ">"，不是 ";"
```

**⇒ 写注释时**手带着 markdown 习惯**，把 `;` 敲成了 `>`。
在 ERB 里这不是引用块，是一个"以 `>` 开头的语句" ⇒ 解释器无法解释 ⇒ 停。**

### 正确

```erb
;     · **关系深**（= 2，恋慕 / 恋人 / 爱欲）⇒ 才会用眼神、小动作、
;       半句话去撩他。
```

### ⚠️⚠️ 真正该记的：`erb_check.py` 当时报的是 **"All checks passed"**

因为它当时是**缩进/配对**检查器 —— **根本不看"行的开头合不合法"**。
**⇒ 一个能让游戏完全起不来的错误，从它眼皮底下过去了。**

### 规矩

**① 注释永远 `;` 开头，别让 markdown 习惯跑出来。**
   `>` `|` `` ` `` `~` `^` `*` `?` 开头的行**任何情况下都非法**。

**② 每次遇到工具没抓到的错，就当场把规则补进 `tool\erb_check.py`。**
   现在已经补了第 8 项检查（`check_line_starts`），并且**分了级**：

| 级别 | 规则 | 依据 |
|---|---|---|
| **error** | 行首是 markdown 残留 `> \| \` ~ ^ * ?` | **任何情况下都不可能是合法语句** ⇒ 0 误报 |
| **warn** | 行首是中日韩文字 | ⚠️ **有两个合法来源**，只能提示 |

**⚠️ 那两个合法来源是**扫全库 613 个文件**才发现的**（否则天天误报）：
1. **日文变量名赋值** —— era 系脚本大量这么写
   （`基礎攻撃力 = ABL:MASTER:戦闘能力 + 1`）
2. **`[SKIPSTART] … [SKIPEND]` 块内** —— 整段被解释器跳过
   （`NOUMIN.ERB` 开头整段中文说明）

**⇒ lint 里同时跳过 `[SKIPSTART]` 块。**

---

## 5l. `SIF` 后面**不能跟同缩进的** `ELSE` / `ELSEIF` / `ENDIF`

上一节（5j）说的是"SIF 只绑紧随的一行"，但那个自查脚本有个**盲区**：

**⚠️ 它只看"子行"（缩进更深的），同缩进的行不算子行** ⇒ 漏判了这种写法：

```erb
SIF CFLAG:角色:积攒度 >= 800
	LLM_NEED = MAX(LLM_NEED - 2, 1)
ELSEIF CFLAG:角色:积攒度 >= 500      ← ★ SIF 不能配 ELSEIF！
	LLM_NEED = MAX(LLM_NEED - 1, 1)
ENDIF                                 ← ★ 编译器：Extra closing tag 'ENDIF'
```

### 报错

```
[ERROR] Line 781: Extra closing tag 'ENDIF'.
```

### 正确

```erb
; ⚠️ 有多档就用 IF … ELSEIF … ENDIF，别用 SIF
IF CFLAG:角色:积攒度 >= 800
	LLM_NEED = MAX(LLM_NEED - 2, 1)
ELSEIF CFLAG:角色:积攒度 >= 500
	LLM_NEED = MAX(LLM_NEED - 1, 1)
ENDIF
```

### 自查脚本已补强

现在会同时检查**同缩进**的 `ELSE`/`ELSEIF`/`ENDIF`（第 4 项检查）✓

**⇒ 口诀：`SIF` 后面要么是普通语句、要么什么都没有 —— 出现 `ELSE` 一律改 `IF`。**


---

## ★★ `STRLENS` 数的是**字节**，中文 1 字 = **2**（2026-09-16 实测）

**实测数据**：字符串 `算是说得上话的熟人，别太自来熟就行。`（**18 个字符**）
⇒ `STRLENS` 返回 **36** = 18 × 2 ✅

**⚠️ 所以所有"长度上限"都要按**中文字数 × 2**来定** ——
**否则阈值会严一倍，把正常的中文误杀** ⚠️

**踩过的实例**：
| 位置 | 原阈值 | 相当于 | 后果 |
|---|---|---|---|
| `@LLM_PARSE_NOTE` | `> 30` | **15 个汉字** | 「对玩家的态度」（21 字）**永远存不进** ⚠️ |
| `@LLM_PARSE_MEMO` | `> 40` | **20 个汉字** | 稍长的身份/约定会被丢 ⚠️ |
| 脏数据判据 | `<= 6` | **3 个汉字** | 条件**永远不成立** ⇒ 脏数据漏过 ⚠️ |

**⇒ 现在的值**：`> 90`（45 汉字）· `> 120`（60 汉字）· `<= 12`（6 汉字）✓

**⚠️ 写新代码时**：**要限长就用"汉字数 × 2"**，并在注释里写明"这是字节数" ✓


---

## ★★ `IF/ENDIF` 总数相等 ≠ 嵌套正确（2026-09-18 踩）

**症状**：插入代码后 `IF/ENDIF` 计数仍然相等（248/248），但**新插入的两段被塞进了上一个 `IF` 里面** ⚠️
**⇒ 后果**：那个条件为空时，新内容**完全不注入**（如 `IF LLM_RELATION` 为空 ⇒ 体型/经验都不注入）⚠️

**⇒ 教训**：
> **插入代码后，必须把那一段的实际结构打印出来核对一遍** ——
> 尤其是**锚点选在某个 `IF` 块内部**的时候 ⚠️

---

## ★★ Python 脚本里的中文引号会静默失败（2026-09-18，犯了 4 次）

**症状**：脚本报 `SyntaxError: invalid syntax` ⇒ **文件根本没被写**，
但脚本前面几行已经打印了"✓ 完成"字样 ⇒ **很容易以为改了，其实没改** ⚠️

**⇒ 规则**：
- **在 Python 字符串里写中文时，一律用「」括起来**，不要用 `"` ✓
- **脚本报错后，必须确认"到底写没写"** 再跑自查 ——
  否则你会以为"自查通过 = 代码没问题"，其实只是**文件没变** ⚠️


---

## ★★★ 标量的 `SAVEDATA` **存不住** —— 必须写成 `, 1` 数组（2026-09-18 实测）

**⇒ 这条最反直觉、也最难查**（症状看起来像"记忆系统坏了"）⚠️

### 实测结果

| 写法 | 存档 → 读档 |
|---|---|
| `#DIM CHARADATA SAVEDATA X, 16`（数组）| ✅ **保留** |
| `#DIM CHARADATA SAVEDATA X, 1`（数组）| ✅ **保留** |
| `#DIM CHARADATA SAVEDATA X`（**标量**）| ❌ **丢失** ⚠️ |

### 当时的症状（**记住这个模式**）

> 态度、最爱、持久记忆**存档后全部消失**，
> 而**"牵手实绩"（`LLM_AGREE, 16`）却留着** ⇒
> **极易误判成"记忆系统的 bug"**，然后去查记忆代码 —— **完全查错方向** ⚠️

**⇒ 判据**：**只有"带尺寸的"活下来了** ⇒ 那就是这个坑 ✓

### 修法

```erb
; ❌ 错：
#DIMS CHARADATA SAVEDATA LLM_ATTITUDE

; ✅ 对（尺寸 1 的数组）：
#DIMS CHARADATA SAVEDATA LLM_ATTITUDE, 1
; 引用也要跟着改：
;   LLM_ATTITUDE:(cid)  ⇒  LLM_ATTITUDE:(cid):0
```

### ⚠️ 代价

**改 `.ERH` 的尺寸 ⇒ 旧存档的读取会错乱** ⇒ **必须开新档** ✓
（所以**一开始就写对**最省事）

**⇒ 自查第 15 项会拦住它** ✓


---

## ★★ 加 `SAVEDATA` 变量时：**只能追加在最后**（2026-09-18）

**⇒ 否则玩家的**旧存档会错位**** ⚠️

| 做法 | 旧档 |
|---|---|
| **★ 追加在所有 SAVEDATA 的最后** | ✅ 能用（新变量读到默认值）|
| **❌ 插在中间** | ⚠️ 后面全错位 |
| **❌ 改已有变量的尺寸** | ⚠️ 错位（等于报废旧档）|
| **✅ 新增非 SAVEDATA 变量** | ✅ 不影响 |

**⇒ 配套要求**：**新变量要能容忍 0 / 空**（旧档读进来就是默认值）✓
**⇒ 而"标量一律写 `, 1`"**（标量存不住，见上一条）✓
