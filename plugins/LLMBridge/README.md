# LLMBridge —— eraTW「自由对话 / 自由亲密」大模型桥接插件

插件让每个角色可以独立开启/关闭「自由对话」与「自由亲密」功能，
开关状态保存在 `plugins/LLMBridge/config.txt`，接口配置保存在
`plugins/LLMBridge/apis.txt`；两者都可热重载，不写入游戏存档。

LLM 请求由插件在后台线程发出，并由 ERB 轮询结果，因此等待模型回复时不会阻塞游戏界面。

---

## 1. 这个插件做了什么 / 没做什么

### 做了

- 从 `plugins/LLMBridge/config.txt` 读取开关配置（支持热重载，改完即生效，不必重开游戏）
- 暴露 4 个 `CALLSHARP` 方法给 ERB 查询/调试
- 全部 `Execute` 有异常保护，**任何错误都不会让游戏崩溃**
- 支持随时删除 DLL 或整个文件夹来彻底关闭

### 没做（刻意如此）

| 项目 | 原因 |
|---|---|
| **不调用 LLM** | 本版只验证插件链路；LLM 接入属下一阶段 |
| **不写游戏状态** | 只读查询，**绝不修改任何游戏变量** |
| **不写存档** | 开关只存在外部 txt，不进 `CFLAG` 等游戏变量 |
| **不写游戏目录任何文件** | 唯一写盘是 `plugins/LLMBridge/debug.log`（可用配置关掉） |
| **不修改任何 ERB / CSV / exe** | 完全不碰游戏本体 |

---

## 2. 目录结构

```
plugins/
├── LLMBridge.dll              ← 插件本体（唯一需要放进 plugins/ 的文件）
└── LLMBridge/
    ├── config.txt             ← ★ 调试用开关文件（你可以直接编辑）
    ├── README.md              ← 本文件
    ├── Directory.Build.props  ← 共享构建属性
    ├── debug.log              ← 插件日志（自动生成，可删）
    ├── api/
    │   └── Emuera/
    │       ├── Emuera.csproj      ← 引用桩工程（AssemblyName=Emuera）
    │       └── PluginContracts.cs ← 契约类型（逐字对照上游源码）
    └── src/                   ← 插件源码
        ├── LLMBridge.csproj
        ├── PluginManifest.cs
        ├── BridgeConfig.cs
        ├── EngineApi.cs
        └── build.ps1
```

> ⚠️ **`api/Emuera/` 只是编译期引用桩，绝不随插件分发。**
> 绝不要把 `api\Emuera\bin\...\Emuera.dll` 复制到 `plugins\` 里。

---

## 2b. ⚠️ 关键实现约束：必须引用名为 `Emuera` 的程序集

**这是本项目最容易踩、后果最严重的坑。首次实现就因此让游戏无法启动。**

引擎 `PluginManager.LoadPlugins()` 里有一句强转：

```csharp
PluginManifestAbstract manifest = (PluginManifestAbstract)Activator.CreateInstance(manifestType);
```

它要求插件的 `PluginManifest` **真正继承引擎自己的** `PluginManifestAbstract`。

### ❌ 错误做法：在插件里本地声明契约类型

若在插件工程内声明同名同命名空间的 `PluginManifestAbstract` / `IPluginMethod` /
`PluginMethodParameter`，运行时会存在**两个同名但不同程序集的类**，强转必然失败：

```
System.InvalidCastException: Unable to cast object of type 'LLMBridge.PluginManifest'
to type 'MinorShift.Emuera.Runtime.Utils.PluginSystem.PluginManifestAbstract'.
   at PluginManager.LoadPlugins()
   at Emuera.GameProc.Process.Initialize(StreamWriter logWriter)
```

而**引擎没有 try/catch**，异常直接冒到启动流程 → **读 ERH 阶段终止，游戏打不开**。

### ✅ 正确做法

插件的 `PluginManifest` 必须让编译器生成**指向程序集 `Emuera` 的 TypeRef**。
但本出厂 exe 是单文件，磁盘上没有 `Emuera.dll`，因此用 `api/Emuera/` 这个
**身份完全相同、内容仅含契约类型**的桩程序集充当编译期引用。

身份必须精确匹配（取自随附 `ClassLibrary1.dll` 的 AssemblyRef 行）：

| 项 | 值 |
|---|---|
| Name | `Emuera` |
| Version | `1.824.0.0` |
| PublicKeyToken | *（空 —— **未强命名**）* |

`src/LLMBridge.csproj` 的关键配置：

```xml
<ProjectReference Include="..\api\Emuera\Emuera.csproj">
  <Private>false</Private>            <!-- 绝不复制桩 DLL 到输出 -->
  <ReferenceOutputAssembly>true</ReferenceOutputAssembly>
</ProjectReference>
```

### 如何自检

编译后检查插件的引用列表，必须出现 `Emuera`：

```powershell
[System.Reflection.Assembly]::ReflectionOnlyLoadFrom("plugins\LLMBridge.dll").GetReferencedAssemblies()
# 期望其中包含：
#   Name=Emuera   Version=1.824.0.0   PKT=
```

`build.ps1` 已内置该项自检，并会警告输出目录里误出现的 `Emuera.dll`。

### 运行时为何能解析

引擎自身程序集标识就是 `Emuera`（随附的 `ClassLibrary1.dll` 正是依赖这一点），
且运行在默认 AssemblyLoadContext 中，因此插件按名字发起的绑定会命中它。

---

## 3. config.txt 格式

`;` 或 `#` 开头为注释。键值用空格 / `=` / `:` 分隔。

```ini
; ── 全局总开关 ──
enable_free_talk     1     ; 1 = 允许自由对话功能
enable_free_intimate 1     ; 1 = 允许自由亲密功能
debug_log            0     ; 1 = 写 plugins/LLMBridge/debug.log
scan_interval_ms     200   ; 配置热重载检查间隔

; ── 每角色开关 ──
; 键可以是 "idx:<运行时索引>" 或 "no:<角色编号>"，也可以只写数字
; 值格式: <talk>,<intimate>   1=开 0=关
idx:1  = 1,0
idx:2  = 1,1
no:50  = 0,1
```

### 关于 `idx` 与 `no`

| 标识 | 含义 | 稳定性 |
|---|---|---|
| `idx:<N>` | **运行时索引** = ERB 的 `NO:角色` / `TARGET` / 循环变量 | 存档中会变（角色增删后偏移） |
| `no:<N>` | **角色编号** = `CSV\Chara\Chara<N> ...csv` 的文件号 | 稳定，与存档无关 |

若只写数字（如 `1,1,1`），插件会**同时尝试** `idx` 与 `no` 两种解释。

`no` 编号对照 `CSV\Chara\` 下的文件名，例如：

| no | 角色 |
|---|---|
| 1 | 博丽 灵梦 |
| 11 | 雾雨 魔理沙 |
| 16 | 蕾米莉亚 |
| 50 | 芙兰 |

### 未列出的角色

由 `default_talk` / `default_intimate` 决定（默认都为 0 = 关闭）。
即：**默认全关，只有显式列出的角色才开启。**

---

## 4. ERB 侧调用

```erb
; 声明接收返回值的变量
#DIMS LLM_RET

; 查询：角色是否有「自由对话」
CALLSHARP LLM_HAS_FREE_TALK(TARGET, LLM_RET)
PRINTFORML 自由对话 = %LLM_RET%

; 查询：角色是否有「自由亲密」
CALLSHARP LLM_HAS_FREE_INTIMATE(TARGET, LLM_RET)
PRINTFORML 自由亲密 = %LLM_RET%
```

可用方法：

| 方法 | 参数 | 返回值 |
|---|---|---|
| `LLM_HAS_FREE_TALK` | `(角色索引, 结果变量)` | `"1"` / `"0"` / `"-1"`(出错) |
| `LLM_HAS_FREE_INTIMATE` | `(角色索引, 结果变量)` | 同上 |
| `LLM_DUMP` | `(角色索引, 结果变量)` | 该角色一行状态：`idx= no= name= talk= intimate=` |
| `LLM_DEBUG` | `(任意)` | 在游戏内打印全部角色开关表 |
| `LLM_RAW` | `(角色索引, 结果变量)` | **诊断**：解析后的原始开关值 + 全部条目 + 配置摘要 |
| `LLM_RELOAD` | `(任意, 结果变量)` | **诊断**：强制立即重载配置（跳过时间戳节流） |

一行版（用 `GETMETH` 风格不可用，须用参数回填）：

```erb
#DIMS R
CALLSHARP LLM_HAS_FREE_TALK(TARGET, R)
```

### 排查配置没生效时的用法

```erb
#DIMS R
CALLSHARP LLM_RAW(1, R)
PRINTFORML %R%
; 输出示例：
;   idx=1 no=-1 talk=1 inti=0 | enable_free_talk=1 enable_free_intimate=0
;   default=0,0 entries=5 loads=2 | entries: idx:1=(1,0) idx:2=(1,1) ...
```

看 `entries:` 段即可确认：
- 你的配置行**有没有被解析到**（不在列表里 = 键写错了）
- **值对不对**（`(talk,inti)`）
- **全局开关是否把它压掉了**（`enable_free_intimate=0` 时所有 inti 都会返回 0）

> `no=-1` / `name=` 为空是**正常现象**（在游戏外测试或引擎 API 尚未就绪时的安全回退）。

---

## 5. 编译

需要 **.NET SDK 8.0 或更高**（本仓库实测环境为 SDK 10.0 + 8.0 运行时）。

```powershell
cd plugins\LLMBridge\src
powershell -ExecutionPolicy Bypass -File build.ps1
```

或手动：

```powershell
dotnet build -c Release -f net8.0-windows
```

产物 `bin\Release\net8.0-windows\LLMBridge.dll` 会被脚本自动复制到 `plugins\LLMBridge.dll`。

> ⚠️ **必须 target `net8.0-windows`**。
> 本出厂 exe 实测为 .NET 8（`.NETCoreApp,Version=v8.0` 命中 7 次，v9/v10 为 0），
> 而上游 master 的示例工程是 `net10.0-windows`。照抄上游会导致加载失败。

---

## 6. 验证是否生效

1. 编译并放置 `LLMBridge.dll`
2. 启动游戏，ERB 里执行：
   ```erb
   LLM_DEBUG
   ```
   或在任意可执行 ERB 处加：
   ```erb
   CALLSHARP LLM_DEBUG(0)
   ```
3. 若游戏内打印出角色开关注解表 → **插件加载成功、`CALLSHARP` 可用**
4. 若无任何输出 → 插件未被加载（见下方排查）

### 排查

| 现象 | 可能原因 |
|---|---|
| 无任何输出 | DLL 未放在 `plugins\` 根目录（**不扫描子目录**） |
| 无任何输出 | 类名不是精确的 `PluginManifest` |
| 无任何输出 | 目标框架不是 `net8.0-windows` |
| 无任何输出 | 缺少 `pluginsAware.txt`（旧版引擎要求；建议在游戏根目录放一个空文件） |
| 游戏启动报错 | 删除 `LLMBridge.dll` 即可恢复，插件不会破坏本体 |

---

## 7. 如何彻底关闭 / 卸载

按侵入性从低到高：

| 方式 | 操作 | 生效时机 |
|---|---|---|
| 关功能 | `config.txt` 里 `enable_free_talk 0` | **立即**（热重载，无需重启） |
| 关单角色 | `idx:1,0,0` | **立即**（热重载） |
| 停插件 | 删除 `plugins\LLMBridge.dll` | 需**重启游戏** |
| 完全清除 | 删除 `plugins\LLMBridge\` 整个文件夹 | 需**重启游戏** |
| 恢复原状 | 把 `plugins\` 恢复为只剩原有的 2 个 DLL | 需**重启游戏** |

### ⚠️ 关于"随时关闭"的一个重要区分

- **开关状态**：**随时可改，改完立即生效**，不用退出游戏。这是本插件的主要设计目标。
- **插件本体（DLL）**：一旦游戏启动时被加载，**.NET 无法在运行中卸载程序集**。
  因此"删除 DLL"要**重启游戏**才真正停止加载。

  若要"立刻让插件完全不起作用"，正确做法是把 `config.txt` 里两个全局开关都设为 `0`
  —— 此时所有查询一律返回 `0`，且插件不再做任何有效工作（仅剩极轻量的时间戳检查）。

**本插件不写入任何游戏文件、不修改存档、不改变任何游戏变量**，因此上述操作**不需要回滚存档**。

---

## 8. 安全设计要点

1. **零游戏状态写入** —— 插件只读取 `config.txt`，回填一个字符串给 ERB。不改 `CFLAG`/`FLAG`/`TALENT`/存档。
2. **异常全捕获** —— 每个 `Execute` 外层 `try/catch`，出错返回 `"-1"` 并写日志，**不让异常穿到引擎**。
3. **配置解析容错** —— 非法行、越界值、编码异常都被忽略，不会抛。
4. **热重载降频** —— 默认 200ms 检查一次文件时间戳，避免每帧 IO。
5. **可空转** —— 若没有任何 ERB 调用，插件加载后完全静默，不产生任何行为。

---

### ⚠️ 一个很容易误判的陷阱：多实例锁住 DLL

Emuera 支持多开（`emuera.conf` 里 `ALLOW MULTIPLE INSTANCES:YES`）。
**DLL 被运行中的实例独占锁定**，如果此时重新编译部署，新文件会写不进去
（`Copy-Item` 报 `being used by another process`）。

后果很有迷惑性：**正在运行的旧实例用着旧 DLL，你新启动的实例读不到插件方法**，
于是 `CALLSHARP` 报 `No native method XXX found` —— 看起来像"插件坏了"，
实际是**部署没成功 + 有残留进程**。

排查步骤：

```powershell
# 1) 看有没有残留实例
Get-Process -Name "Emuera_skiaV10_x64" | Select-Object Id, StartTime, MainWindowTitle

# 2) 全部结束
Get-Process -Name "Emuera_skiaV10_x64" | Stop-Process -Force

# 3) 重新部署（build.ps1 会先结束进程）
powershell -ExecutionPolicy Bypass -File build.ps1
```

`build.ps1` 已内置"部署前结束残留实例"的防呆。

### 如何确认插件真的注册了方法

把 `config.txt` 的 `debug_log` 设为 `1`，重启游戏，然后看：

```
plugins\LLMBridge\debug.log
```

正常应出现：

```
[INFO] plugin constructed; dir=...\plugins\LLMBridge; enable_free_talk=1 ...
[INFO] registered methods: 7 [LLM_HAS_FREE_TALK, LLM_HAS_FREE_INTIMATE, LLM_IS_READY, ...]
```

若 `debug.log` 完全不生成 → 插件 DLL 根本没被加载（检查是否放在 `plugins\` 根目录）。
若生成但 `registered methods` 为空 → 构造函数抛异常，日志里会有 `[ERROR] CTOR-ERROR`。

### 与插件无关的两个既有报错

排查时会看到下面两条，**都不是本插件引起的**，可忽略：

| 报错 | 原因 |
|---|---|
| `PLAYSOUND "bad-apple-audio.MP3" ... 指定的音频文件格式不受支持`（`TITLE.ERB:131 @BADAPPLE`） | 发行版标题画面的 BAD APPLE 音效，MP3 解码在当前环境不支持 |
| `SQL_IMPORT_MAP_XML ... 找不到文件 'plugins/tw_csv_chs.xml'`（`魔改内容\qol\qol_db.ERB:46 @QOL_DB_INIT`） | 该 mod 依赖 `plugins\` 下的数据文件；若被误删就会报这个。**请勿删除 `plugins\` 里的 `tw_csv_chs.xml` / `tw_taste_chs.xml` / `bbas_dataset.xml` / `schema.xml` / `qol_data.db`** |

---

## 9. 接入 CommandCode（保留原有三字段方案）

CommandCode 的 OpenAI / 开源模型可直接使用现有 `apis.txt` 格式，玩家**不需要安装 DSH**，
也不需要修改 DLL：

```ini
[* CommandCode]
key   = 在此粘贴玩家自己的 CommandCode Provider API key
model = deepseek/deepseek-v4-flash
url   = https://api.commandcode.ai/provider/v1
```

插件会把上述 URL 自动归一化为：

```text
https://api.commandcode.ai/provider/v1/chat/completions
```

当前已按插件真实请求体（OpenAI Chat Completions、Bearer 鉴权、`thinking` 关闭、
非流式）验证可工作的常用模型包括：

- `deepseek/deepseek-v4-flash`（推荐用于角色对话）
- `gpt-5.6-sol`
- `gpt-5.6-luna`
- `moonshotai/Kimi-K3`
- `Qwen/Qwen3.8-Max`
- `z-ai/glm-5.3-flash`
- `MiniMaxAI/MiniMax-M3`
- `google/gemini-3.8-flash`

> `claude-*` 是例外：CommandCode 强制它们使用 Anthropic
> `/provider/v1/messages` 协议，不能放进现有 OpenAI 三字段条目；而且具体模型还受
> CommandCode 套餐限制。为保持普通玩家接入简单，LLMBridge 当前默认不提供 Claude
> 专用协议入口。

修改 `apis.txt` 后最多约 1 秒自动重载；也可以在游戏的“接口列表”页面手动重载。
切换模型仍然只需修改 `model` 一行，或增加多个 `[名字]` 段并给选中的段加 `*`。

---

## 10. 已知限制（初版）

- 当前聊天传输支持 OpenAI Chat Completions 与 Ollama 原生 `/api/chat`；不直接支持 Anthropic Messages
- `Plugins` 目录**不扫描子目录**，DLL 必须直接在 `plugins\` 下
- 运行时索引与角色编号的对应关系**会随存档变化**，调试时建议用 `LLM_DEBUG` 打印对照表确认
- 未做多角色（助手）场景的独立开关

---

## 11. ERB 侧集成（`ERB\魔改内容\LLM_CHAT_BRIDGE.ERB`）

插件本身**不会**在游戏里添加任何菜单；必须有一个 ERB 文件去调 `CALLSHARP`，
按钮才会出现。这个桥接文件已随本插件提供：

```
ERB\魔改内容\LLM_CHAT_BRIDGE.ERB
```

- 新增文件，**不修改任何现有 ERB / CSV**
- 删除即完全恢复原状
- 入口：**和角色互动时的指令界面**，需先打开 `[自定义]` 指令块（见 §11.1）
- 使用自定义指令编号 **30**（0~19 / 100~102 / 228 / 500 已被占用）

### 11.1 ⚠️ 入口在哪（作者曾把这里写错，特此更正）

**主菜单（`[102] 居住环境设定` 那一屏）里看不到它。** 自定义指令属于**游戏内指令系统**，
只在**与角色互动时**的指令界面里出现。

操作步骤：

1. 先**正常开始游戏**（`[1] 继续游戏`），能自由行动
2. 走到某个角色身边，**触发与该角色的互动**，进入她的指令菜单
   （界面顶部会显示 `====== Act_COM ==`，即过滤按钮行）
3. 在那一行里找到 **`[自定义]`** 按钮（对应内部编号 841），点它**打开自定义指令块**
   - 该按钮控制 `ADD_CUSTOM_COM_SWITCH`
   - 默认是**关**的，不打开的话任何自定义指令都不会显示
4. 打开后，自定义指令列表里就会出现 **「自由对话」**

> 说明：作者此前把它称为"MOD 菜单"，这是**不准确**的说法。
> 它其实是 MOD 系统自带的**全局自定义指令块**，挂在角色指令界面上。
>
> ⚠️ 另外该指令块的渲染有条件：`TFLAG:100` 必须为真（即处于常规指令时机）。
> 在少数特殊状态下它不会显示。

### 为什么用 `ADD_CUSTOM_COM` 而不是口上侧的 `KOJO_*_COM_*`

口上侧自定义指令名里带**剧本标识符**（196 套各不相同），要加指令必须逐个改剧本文件，
与"不改动现有文件"的约束冲突。`ADD_CUSTOM_COM` 是全局的，新增一个文件即可，对所有角色生效。

代价：它出现在 MOD 菜单的 [自定义] 指令块里，而不是角色的指令列表。

### ⚠️ 写 ERB 时的四个坑（本项目全部踩过）

| # | 错误写法 | 报错 | 正确写法 |
|---|---|---|---|
| 1 | 在插件里**本地声明**契约类型 | `InvalidCastException` → **游戏无法启动** | 引用身份为 `Emuera` 的桩程序集（见 §2b） |
| 2 | `CALL BUILD_COM_BUTTON_HTML(...)` | `对标记为 #FUNCTION(S) 的函数进行 CALL 调用` | `LOCALS:1 '= BUILD_COM_BUTTON_HTML(...)` —— 用字符串赋值接返回值 |
| 3 | `CFLAG:TARGET:LLM对话临时开关` | `无法解析的标识符` | 具名 CFLAG 必须先在 `CSV\CFLAG.csv` 登记；**不改 CSV 就用数字下标**：`CFLAG:TARGET:1100` |
| 4 | `HTML_PRINTC %LOCALS:1%` | `表达式异常` | `%...%` 只能用在**字符串字面量内部**；变量单独作参数时不加百分号：`HTML_PRINTC LOCALS:1` |

> 第 3 条用的下标 `CFLAG:1100` 属于本 mod 的空闲区间（`1100~1149` 实测未被 `CFLAG.csv` 占用）。

### 桥接文件用到的接口

| 函数 | 用途 |
|---|---|
| `@ADD_CUSTOM_COM_ABLE30` | 决定指令是否显示（插件缺失 / 全局开关关闭时隐藏） |
| `@ADD_CUSTOM_COM30` | 指令本体，调用 `@LLM_CHAT_MENU` |
| `@ADD_CUSTOM_COM_PRINT30` | MOD 菜单里的按钮文字（`自由对话` / `自由对话 ★`） |
| `@LLM_CHAT_MENU` | 菜单界面：显示状态 + 切换临时开关 + 打印调试信息 |
| `@LLM_TALK_ON(ARG)` / `@LLM_INTIMATE_ON(ARG)` | 供其它 ERB 复用的查询包装（`#FUNCTION`） |

---
