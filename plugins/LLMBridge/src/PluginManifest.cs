// ============================================================================
//  PluginManifest.cs —— 插件主入口与可调用方法
// ============================================================================
//  暴露给 ERB 的 4 个 CALLSHARP 方法：
//      LLM_HAS_FREE_TALK     (runtimeIndex, outResult)  → "1" / "0" / "-1"
//      LLM_HAS_FREE_INTIMATE (runtimeIndex, outResult)  → "1" / "0" / "-1"
//      LLM_DUMP              (runtimeIndex, outResult)  → 该角色完整状态串
//      LLM_DEBUG             (任意参数)                  → 在游戏内打印全部开关
//
//  安全约定：
//    · 绝不修改任何游戏变量 / 存档 / 游戏目录文件（唯一写盘是本插件自己的 debug.log）
//    · 每个 Execute 全程 try/catch，异常不穿透到引擎
//    · 出错时回填 "-1"，并在日志里留痕
// ============================================================================

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using MinorShift.Emuera.Runtime.Utils.PluginSystem;

namespace LLMBridge
{
    /// <summary>
    /// 引擎通过 `DLL.GetTypes().Where(v => v.Name == "PluginManifest")` 查找本类。
    /// ⚠️ 类名必须精确为 PluginManifest，且必须有无参构造。
    /// </summary>
    public sealed class PluginManifest : PluginManifestAbstract
    {
        public override string PluginName => "LLMBridge";
        public override string PluginDescription => "Per-character switches for free-talk / free-intimate features (switches only; no LLM call in this build).";
        public override string PluginVersion => "0.1.0";
        public override string PluginAuthor => "generated for eratw-sub-modding";

        /// <summary>插件自身目录：plugins/LLMBridge/（DLL 在 plugins/ 下，配置在子目录里）。</summary>
        internal static string BaseDir { get; private set; } = string.Empty;

        internal static BridgeConfig Config { get; private set; } = null!;

        /// <summary>LLM 接口注册表（apis.txt）。</summary>
        internal static ApiRegistry Apis { get; private set; } = null!;

        /// <summary>LLM 调用与对话历史。</summary>
        internal static LlmClient Llm { get; private set; } = null!;

        public PluginManifest()
        {
            // 构造函数内任何异常都不得外泄（引擎 LoadPlugins 无 try/catch）。
            // 正常路径只按 debug_log 配置写日志；仅出错时无条件记录。
            try
            {
                BaseDir = ResolveBaseDir();
                Config = new BridgeConfig(BaseDir);
                Apis = new ApiRegistry(BaseDir);
                Llm = new LlmClient();
                Log("plugin constructed; dir=" + BaseDir + "; " + Config.Describe());
                Log("api registry: " + Apis.DescribeAll());

                methods.Add(new HasFreeTalkMethod());
                methods.Add(new HasFreeIntimateMethod());
                methods.Add(new IsReadyMethod());
                methods.Add(new DumpMethod());
                methods.Add(new DebugMethod());
                methods.Add(new RawMethod());
                methods.Add(new ReloadMethod());
                // ── LLM 相关 ──
                methods.Add(new ApiCountMethod());
                methods.Add(new ApiTotalMethod());
                methods.Add(new ApiNameMethod());
                methods.Add(new ApiInfoMethod());
                methods.Add(new ApiListMethod());
                methods.Add(new ApiReloadMethod());
                methods.Add(new HistoryCountMethod());
                methods.Add(new HistoryClearMethod());
                methods.Add(new HistoryDumpMethod());
                methods.Add(new ChatSendMethod());
                methods.Add(new ChatPollMethod());
                methods.Add(new ChatCancelMethod());

                Log("registered methods: " + methods.Count
                    + " [" + string.Join(", ", System.Linq.Enumerable.Select(methods, m => m.Name)) + "]");
            }
            catch (Exception ex)
            {
                // 出错时无条件记录（此时 debug_log 配置可能还没读出来）
                LogAlways("CTOR-ERROR", ex.GetType().FullName + ": " + ex.Message
                    + Environment.NewLine + ex.StackTrace);
                try
                {
                    if (BaseDir == null || BaseDir.Length == 0)
                        BaseDir = Path.Combine(AppContext.BaseDirectory, "plugins", "LLMBridge");
                    if (Config == null)
                        Config = new BridgeConfig(BaseDir);
                }
                catch { }

                // 兜底注册：即使配置初始化失败，也要把方法挂上，
                // 否则 CALLSHARP 会报 "No native method"
                if (methods.Count == 0)
                {
                    try { methods.Add(new HasFreeTalkMethod()); } catch { }
                    try { methods.Add(new HasFreeIntimateMethod()); } catch { }
                    try { methods.Add(new IsReadyMethod()); } catch { }
                    try { methods.Add(new DumpMethod()); } catch { }
                    try { methods.Add(new DebugMethod()); } catch { }
                    try { methods.Add(new ChatSendMethod()); } catch { }
                    try { methods.Add(new ChatPollMethod()); } catch { }
                    LogAlways("CTOR-ERROR", "fallback registration -> " + methods.Count + " methods");
                }
            }
        }

        /// <summary>
        /// 定位配置目录。优先用 DLL 所在位置推导（最可靠），失败再回退到工作目录。
        /// 目标： &lt;game&gt;/plugins/LLMBridge
        /// </summary>
        private static string ResolveBaseDir()
        {
            try
            {
                var loc = typeof(PluginManifest).Assembly.Location;
                if (!string.IsNullOrEmpty(loc))
                {
                    var dllDir = Path.GetDirectoryName(loc);           // <game>/plugins
                    if (!string.IsNullOrEmpty(dllDir))
                    {
                        return Path.Combine(dllDir, "LLMBridge");      // <game>/plugins/LLMBridge
                    }
                }
            }
            catch
            {
                // 忽略，走回退
            }
            return Path.Combine(AppContext.BaseDirectory, "plugins", "LLMBridge");
        }

        // ────────────────────────────────────────────────────────────────
        //  可调用方法
        // ────────────────────────────────────────────────────────────────

        /// <summary>返回角色运行时索引 → 角色编号（NO）</summary>
        private static long ResolveCharNo(long runtimeIndex)
        {
            return EngineApi.GetCharacterNo(runtimeIndex);
        }

        private static string GetCharNameSafe(long runtimeIndex)
        {
            return EngineApi.GetCharacterName(runtimeIndex);
        }

        private abstract class BridgeMethodBase : IPluginMethod
        {
            public abstract string Name { get; }
            public abstract string Description { get; }

            public void Execute(PluginMethodParameter[] args)
            {
                try
                {
                    // 调用追踪：确认 ERB 侧到底调了哪些方法（排查用）
                    try
                    {
                        var sb = new StringBuilder();
                        sb.Append("CALLED ").Append(Name).Append(" args=")
                          .Append(args == null ? 0 : args.Length).Append(" [");
                        if (args != null)
                        {
                            for (int i = 0; i < args.Length; i++)
                            {
                                if (i > 0) sb.Append(", ");
                                sb.Append(args[i] == null ? "null"
                                    : (args[i].isString ? ("s:" + args[i].strValue) : ("i:" + args[i].intValue)));
                            }
                        }
                        sb.Append(']');
                        PluginManifest.LogAlways("TRACE", sb.ToString());
                    }
                    catch { }

                    var cfg = Config;
                    if (cfg != null) cfg.Tick();
                    // apis.txt 与 config.txt 一样支持热重载。所有插件入口都会经过这里，
                    // 因此按 ApiRegistry 自身的 1 秒节流检查一次即可，不增加明显开销。
                    var apis = Apis;
                    if (apis != null) apis.Tick();
                    Run(args);

                    // 记录回填结果
                    try
                    {
                        if (args != null && args.Length > 0)
                        {
                            var last = args[args.Length - 1];
                            PluginManifest.LogAlways("TRACE", "  -> " + Name + " returned '"
                                + (last == null ? "null" : last.strValue) + "'");
                        }
                    }
                    catch { }
                }
                catch (Exception ex)
                {
                    // 回填错误标记，绝不抛出
                    try
                    {
                        if (args != null && args.Length > 0)
                        {
                            var last = args[args.Length - 1];
                            if (last != null) { last.isString = true; last.strValue = "-1"; }
                        }
                    }
                    catch { }
                    TryWriteCrashLog(Name, ex);
                }
            }

            protected abstract void Run(PluginMethodParameter[] args);

            /// <summary>把结果写回最后一个参数（通常由 ERB 传入一个字符串变量）。</summary>
            protected static void SetResult(PluginMethodParameter[] args, string value)
            {
                if (args == null || args.Length == 0) return;
                var p = args[args.Length - 1];
                if (p == null) return;
                p.isString = true;
                p.strValue = value;
            }

            protected static long GetIndexArg(PluginMethodParameter[] args)
            {
                if (args == null || args.Length == 1)
                {
                    // LLM_DEBUG(0) 这类只有一个参数时，第一个参数就是索引
                }
                if (args == null || args.Length == 0) return -1;
                var p = args[0];
                if (p == null) return -1;
                return p.isString ? -1 : p.intValue;
            }

            /// <summary>取第 n 个参数当整数（非整数或缺失时返回 def）。</summary>
            /// ⚠️ 名字**不能**叫 `ArgInt` —— 基类里已经有一个 `ArgInt(args, i)`
            ///    （第 672 行，默认值当 0 处理），同名会把已有调用全打乱：
            ///    编译报 CS7036「未提供与…所需参数 def 对应的参数」。
            protected static int ArgIntDef(PluginMethodParameter[] args, int n, int def)
            {
                if (args == null || n < 0 || n >= args.Length) return def;
                var p = args[n];
                if (p == null || p.isString) return def;
                return (int)p.intValue;
            }
        }

        private sealed class HasFreeTalkMethod : BridgeMethodBase
        {
            public override string Name => "LLM_HAS_FREE_TALK";
            public override string Description => "Returns 1 if the given character has the free-talk feature enabled.";

            protected override void Run(PluginMethodParameter[] args)
            {
                long idx = GetIndexArg(args);
                long no = ResolveCharNo(idx);
                var cfg = Config;
                bool on = cfg != null && cfg.IsFreeTalkEnabled(idx, no);
                SetResult(args, on ? "1" : "0");
            }
        }

        private sealed class HasFreeIntimateMethod : BridgeMethodBase
        {
            public override string Name => "LLM_HAS_FREE_INTIMATE";
            public override string Description => "Returns 1 if the given character has the free-intimate feature enabled.";

            protected override void Run(PluginMethodParameter[] args)
            {
                long idx = GetIndexArg(args);
                long no = ResolveCharNo(idx);
                var cfg = Config;
                bool on = cfg != null && cfg.IsFreeIntimateEnabled(idx, no);
                SetResult(args, on ? "1" : "0");
            }
        }

        /// <summary>
        /// 插件是否"可用"：全局开关至少有一个打开。
        /// 供 ERB 侧判断要不要显示入口，避免功能被全局关闭后仍留一个点了没反应的按钮。
        /// 参数：(结果变量)
        /// </summary>
        private sealed class IsReadyMethod : BridgeMethodBase
        {
            public override string Name => "LLM_IS_READY";
            public override string Description => "Returns 1 if the plugin has at least one global feature switch enabled.";

            protected override void Run(PluginMethodParameter[] args)
            {
                var cfg = Config;
                bool ready = cfg != null && (cfg.EnableFreeTalk || cfg.EnableFreeIntimate);
                SetResult(args, ready ? "1" : "0");
            }
        }

        private sealed class DumpMethod : BridgeMethodBase
        {
            public override string Name => "LLM_DUMP";
            public override string Description => "Returns a one-line state dump for the given character index.";

            protected override void Run(PluginMethodParameter[] args)
            {
                long idx = GetIndexArg(args);
                long no = ResolveCharNo(idx);
                var name = GetCharNameSafe(idx);
                var cfg = Config;
                bool talk = cfg != null && cfg.IsFreeTalkEnabled(idx, no);
                bool inti = cfg != null && cfg.IsFreeIntimateEnabled(idx, no);
                SetResult(args,
                    string.Format("idx={0} no={1} name={2} talk={3} intimate={4}",
                        idx, no, name, talk ? 1 : 0, inti ? 1 : 0));
            }
        }

        /// <summary>在游戏内打印全部角色开关；返回摘要串。</summary>
        private sealed class DebugMethod : BridgeMethodBase
        {
            public override string Name => "LLM_DEBUG";
            public override string Description => "Prints all LLMBridge switch states into the game console.";

            protected override void Run(PluginMethodParameter[] args)
            {
                var sb = new StringBuilder();
                var cfg = Config;

                string header = "===== LLMBridge " + (typeof(PluginManifest).Assembly.GetName().Version?.ToString() ?? "?") + " =====";
                Print(header);
                Print("config : " + (cfg?.ConfigPath ?? "(none)"));
                Print("state  : " + (cfg?.Describe() ?? "(no config)"));

                long count = 0;
                try
                {
                    var ids = EngineApi.GetCharacterIDs();
                    if (ids != null)
                    {
                        Print("--- characters ---");
                        for (int i = 0; i < ids.Length; i++)
                        {
                            long no = ids[i];
                            var nm = GetCharNameSafe(i);
                            bool talk = cfg != null && cfg.IsFreeTalkEnabled(i, no);
                            bool inti = cfg != null && cfg.IsFreeIntimateEnabled(i, no);
                            string line = string.Format("  [{0,3}] no={1,-4} {2,-14} talk={3} intimate={4}",
                                i, no, Truncate(nm, 14), talk ? 1 : 0, inti ? 1 : 0);
                            Print(line);
                            sb.Append(i).Append('=').Append(talk ? 1 : 0).Append(talk && inti ? "+" : "-")
                              .Append(inti ? 1 : 0).Append(';');
                            count++;
                        }
                    }
                    else
                    {
                        Print("  (GetCharacterIDs unavailable)");
                    }
                }
                catch (Exception ex)
                {
                    Print("  (character enumeration failed: " + ex.GetType().Name + ")");
                }

                Print("total characters: " + count);
                Print("===== end LLMBridge =====");

                SetResult(args, "ok:" + count);
            }

            private static string Truncate(string s, int n)
            {
                if (string.IsNullOrEmpty(s)) return string.Empty;
                return s.Length <= n ? s : s.Substring(0, n);
            }
        }

        /// <summary>返回解析后的原始开关值，用于诊断配置是否被正确读取。</summary>
        private sealed class RawMethod : BridgeMethodBase
        {
            public override string Name => "LLM_RAW";
            public override string Description => "Diagnostic: returns the parsed raw toggle for an index, plus config summary.";

            protected override void Run(PluginMethodParameter[] args)
            {
                long idx = GetIndexArg(args);
                long no = ResolveCharNo(idx);
                var cfg = Config;
                if (cfg == null) { SetResult(args, "no-config"); return; }
                var sb = new StringBuilder();
                sb.Append("idx=").Append(idx);
                sb.Append(" no=").Append(no);
                sb.Append(" talk=").Append(cfg.IsFreeTalkEnabled(idx, no) ? 1 : 0);
                sb.Append(" inti=").Append(cfg.IsFreeIntimateEnabled(idx, no) ? 1 : 0);
                sb.Append(" | ").Append(cfg.Describe());
                sb.Append(" | entries:");
                foreach (var kv in cfg.EnumerateEntries())
                {
                    sb.Append(' ').Append(kv.Key).Append("=(")
                      .Append(kv.Value.Talk ? 1 : 0).Append(',')
                      .Append(kv.Value.Intimate ? 1 : 0).Append(')');
                }
                SetResult(args, sb.ToString());
            }
        }

        /// <summary>强制立即重载配置（跳过时间戳节流），供调试使用。</summary>
        private sealed class ReloadMethod : BridgeMethodBase
        {
            public override string Name => "LLM_RELOAD";
            public override string Description => "Forces an immediate config reload and returns the resulting state.";

            protected override void Run(PluginMethodParameter[] args)
            {
                var cfg = Config;
                if (cfg == null) { SetResult(args, "no-config"); return; }
                cfg.Reload(true);
                SetResult(args, "reloaded: " + cfg.Describe());
            }
        }

        // ────────────────────────────────────────────────────────────────
        //  LLM：接口注册表
        // ────────────────────────────────────────────────────────────────

        /// <summary>**可用**接口条目数（用于门控"开始对话"）。参数：(结果变量)</summary>
        private sealed class ApiCountMethod : BridgeMethodBase
        {
            public override string Name => "LLM_API_COUNT";
            public override string Description => "Number of USABLE API entries in apis.txt.";

            protected override void Run(PluginMethodParameter[] args)
            {
                var r = Apis;
                SetResult(args, r == null ? "0" : r.UsableCount.ToString());
            }
        }

        /// <summary>接口条目总数（含不完整的）。参数：(结果变量)</summary>
        private sealed class ApiTotalMethod : BridgeMethodBase
        {
            public override string Name => "LLM_API_TOTAL";
            public override string Description => "Total number of API entries (including unusable ones).";

            protected override void Run(PluginMethodParameter[] args)
            {
                var r = Apis;
                SetResult(args, r == null ? "0" : r.Count.ToString());
            }
        }

        /// <summary>当前生效条目的名字。参数：(结果变量)</summary>
        private sealed class ApiNameMethod : BridgeMethodBase
        {
            public override string Name => "LLM_API_ACTIVE_NAME";
            public override string Description => "Name of the active API entry.";

            protected override void Run(PluginMethodParameter[] args)
            {
                var r = Apis;
                var a = r == null ? null : r.Active;
                SetResult(args, a == null ? "" : a.Name);
            }
        }

        /// <summary>某个条目的详情。参数：(序号, 结果变量)</summary>
        private sealed class ApiInfoMethod : BridgeMethodBase
        {
            public override string Name => "LLM_API_INFO";
            public override string Description => "Describe one API entry by index.";

            protected override void Run(PluginMethodParameter[] args)
            {
                long idx = GetIndexArg(args);
                var r = Apis;
                if (r == null) { SetResult(args, "(no registry)"); return; }
                if (idx < 0 || idx >= r.Count) { SetResult(args, "(index out of range)"); return; }
                SetResult(args, r.All[(int)idx].Describe());
            }
        }

        /// <summary>列出全部条目（每个一行，用 \n 分隔）。参数：(结果变量)</summary>
        private sealed class ApiListMethod : BridgeMethodBase
        {
            public override string Name => "LLM_API_LIST";
            public override string Description => "List all API entries, one per line.";

            protected override void Run(PluginMethodParameter[] args)
            {
                var r = Apis;
                if (r == null) { SetResult(args, "(no registry)"); return; }
                var sb = new StringBuilder();
                for (int i = 0; i < r.Count; i++)
                {
                    bool act = (r.Active != null && ReferenceEquals(r.Active, r.All[i]));
                    sb.Append(act ? "▶ " : "  ");
                    sb.Append('[').Append(i).Append("] ");
                    sb.Append(r.All[i].Describe());
                    sb.Append('\n');
                }
                if (r.Count == 0) sb.Append("(apis.txt 里没有可用条目)\n");
                sb.Append(r.DescribeAll());
                SetResult(args, sb.ToString());
            }
        }

        /// <summary>强制重载 apis.txt。参数：(结果变量)</summary>
        private sealed class ApiReloadMethod : BridgeMethodBase
        {
            public override string Name => "LLM_API_RELOAD";
            public override string Description => "Force reload of apis.txt.";

            protected override void Run(PluginMethodParameter[] args)
            {
                var r = Apis;
                if (r == null) { SetResult(args, "no-registry"); return; }
                r.Reload();
                SetResult(args, "reloaded: " + r.DescribeAll());
            }
        }

        // ────────────────────────────────────────────────────────────────
        //  LLM：对话历史
        // ────────────────────────────────────────────────────────────────

        /// <summary>某角色的历史条数。参数：(角色索引, 结果变量)</summary>
        private sealed class HistoryCountMethod : BridgeMethodBase
        {
            public override string Name => "LLM_HISTORY_COUNT";
            public override string Description => "Number of stored history messages for a character.";

            protected override void Run(PluginMethodParameter[] args)
            {
                long idx = GetIndexArg(args);
                var c = Llm;
                SetResult(args, c == null ? "0" : c.HistoryCount(idx).ToString());
            }
        }

        /// <summary>清空历史。参数：(角色索引, 结果变量)；角色索引 &lt;0 表示全部清空</summary>
        private sealed class HistoryClearMethod : BridgeMethodBase
        {
            public override string Name => "LLM_HISTORY_CLEAR";
            public override string Description => "Clear chat history for a character (or all if index<0).";

            protected override void Run(PluginMethodParameter[] args)
            {
                long idx = GetIndexArg(args);
                var c = Llm;
                if (c == null) { SetResult(args, "no-client"); return; }
                if (idx < 0) { c.ClearAllHistory(); SetResult(args, "cleared-all"); return; }
                c.ClearHistory(idx);
                SetResult(args, "cleared:" + idx);
            }
        }

        /// <summary>
        /// 导出历史为纯文本。参数：(角色索引, 最多轮数, 结果变量)
        /// ⚠️ ERB 侧拿不到历史内容就没法把它"降级"成补充记忆 ——
        ///    这是"以开场白为分界线"那个设计的前提。
        /// </summary>
        private sealed class HistoryDumpMethod : BridgeMethodBase
        {
            public override string Name => "LLM_HISTORY_DUMP";
            public override string Description => "Dump stored history as text. Args: (charIndex, maxTurns, out).";

            protected override void Run(PluginMethodParameter[] args)
            {
                long idx = GetIndexArg(args);
                int maxTurns = ArgIntDef(args, 1, 6);
                if (maxTurns <= 0) maxTurns = 6;
                if (maxTurns > 15) maxTurns = 15;

                var c = Llm;
                if (c == null) { SetResult(args, ""); return; }
                SetResult(args, c.DumpHistory(idx, maxTurns));
            }
        }

        // ────────────────────────────────────────────────────────────────
        //  LLM：对话
        // ────────────────────────────────────────────────────────────────

        /// <summary>
        /// 发起对话（非阻塞）。
        /// 参数：(角色索引, system提示, 玩家输入, [记录历史], 结果变量)
        ///   第 4 个参数若为 0，则这一轮不进历史（用于开场白，避免污染上下文）
        /// 结果变量回填：正数 = 请求 id（用 LLM_CHAT_POLL 取结果）；负数 = 发起失败
        /// </summary>
        private sealed class ChatSendMethod : BridgeMethodBase
        {
            public override string Name => "LLM_CHAT_SEND";
            public override string Description => "(charIndex, systemPrompt, userText, recordHistory, outRequestId) -> starts async chat";

            protected override void Run(PluginMethodParameter[] args)
            {
                var c = Llm;
                var r = Apis;
                if (c == null || r == null) { SetResult(args, "-998"); return; }

                long idx = ArgInt(args, 0);
                string sys = ArgStr(args, 1);
                string user = ArgStr(args, 2);
                // 第4个参数可省略；省略时默认记录历史
                bool record = args != null && args.Length >= 5 ? (ArgInt(args, 3) != 0) : true;

                string err;
                long id = c.Send(idx, r.Active, sys, user, out err, record);
                if (id <= 0)
                {
                    r.LastCallError = err;
                    LogAlways("CHAT-SEND-FAIL", err);
                    SetResult(args, "-1");
                    return;
                }
                SetResult(args, id.ToString());
            }
        }

        /// <summary>
        /// 轮询结果。
        /// 参数：(请求 id, 结果变量)
        /// 结果变量回填一个**首字符为状态码**的字符串：
        ///   "0"                  = 仍在等待（后面没有内容）
        ///   "1" + <文本>         = 成功，从第 2 个字符起是回复文本
        ///   "-1" + <原因>        = 失败，从第 3 个字符起是原因
        /// 说明：Emuera 的 CALLSHARP **只回填最后一个参数**，
        ///       所以状态码不能单独占一个参数（中间的参数写了也会被引擎丢掉），
        ///       必须和文本拼进同一个参数里。
        /// </summary>
        private sealed class ChatPollMethod : BridgeMethodBase
        {
            public override string Name => "LLM_CHAT_POLL";
            public override string Description => "(requestId, outStateAndText) -> \"0\" waiting / \"1Reply\" done / \"-1Reason\" error";

            protected override void Run(PluginMethodParameter[] args)
            {
                var c = Llm;
                if (c == null) { SetResult(args, "-1no-client"); return; }

                long id = ArgInt(args, 0);
                string text, err;
                int st = c.Poll(id, out text, out err);

                if (st == 0) { SetResult(args, "0"); return; }
                if (st == 1) { SetResult(args, "1" + (text ?? "")); return; }
                SetResult(args, "-1" + (err ?? "未知错误"));
            }
        }

        /// <summary>放弃跟踪某个请求。参数：(请求 id, 结果变量)</summary>
        private sealed class ChatCancelMethod : BridgeMethodBase
        {
            public override string Name => "LLM_CHAT_CANCEL";
            public override string Description => "Stop tracking a pending chat request.";

            protected override void Run(PluginMethodParameter[] args)
            {
                long id = ArgInt(args, 0);
                var c = Llm;
                if (c != null) c.Forget(id);
                SetResult(args, "ok");
            }
        }

        // ── 参数读取小工具（供上面这些方法用）──

        /// <summary>取第 i 个参数的整数值；非数值参数返回 -1。</summary>
        private static long ArgInt(PluginMethodParameter[] args, int i)
        {
            if (args == null || i < 0 || i >= args.Length) return -1;
            var p = args[i];
            if (p == null) return -1;
            if (p.isString)
            {
                long v;
                if (long.TryParse((p.strValue ?? "").Trim(), out v)) return v;
                return -1;
            }
            return p.intValue;
        }

        /// <summary>取第 i 个参数的字符串值。</summary>
        private static string ArgStr(PluginMethodParameter[] args, int i)
        {
            if (args == null || i < 0 || i >= args.Length) return "";
            var p = args[i];
            if (p == null) return "";
            if (p.isString) return p.strValue ?? "";
            return p.intValue.ToString();
        }

        // ────────────────────────────────────────────────────────────────
        //  输出与日志
        // ────────────────────────────────────────────────────────────────

        /// <summary>安全地向游戏控制台打印一行。失败则忽略。</summary>
        internal static void Print(string text)
        {
            EngineApi.Print((text ?? string.Empty) + Environment.NewLine);
        }

        /// <summary>写插件自身日志（仅当 config 打开 debug_log）。绝不写游戏目录其它位置。</summary>
        internal static void Log(string text)
        {
            try
            {
                if (Config == null || !Config.DebugLog) return;
                WriteLogLine("INFO", text);
            }
            catch { }
        }

        /// <summary>
        /// 无条件写日志。用于构造期/异常期这类"必须留下痕迹"的场合
        /// —— 此时 debug_log 配置可能还没读出来，或读取本身就失败了。
        /// </summary>
        internal static void LogAlways(string level, string text)
        {
            try { WriteLogLine(level, text); } catch { }
        }

        internal static void TryWriteCrashLog(string where, Exception ex)
        {
            LogAlways("ERROR", where + " -> " + ex.GetType().FullName + ": " + ex.Message
                + Environment.NewLine + ex.StackTrace);
        }

        private static readonly object LogLock = new object();

        private static void WriteLogLine(string level, string text)
        {
            lock (LogLock)
            {
                var dir = BaseDir;
                if (string.IsNullOrEmpty(dir)) return;
                try
                {
                    if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
                    var path = Path.Combine(dir, "debug.log");
                    // 简单的尺寸封顶，避免无限增长
                    try
                    {
                        var fi = new FileInfo(path);
                        if (fi.Exists && fi.Length > 1024 * 512)
                        {
                            File.Delete(path);
                        }
                    }
                    catch { }

                    File.AppendAllText(path,
                        DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " [" + level + "] " + text + Environment.NewLine,
                        new UTF8Encoding(false));
                }
                catch { }
            }
        }
    }
}
