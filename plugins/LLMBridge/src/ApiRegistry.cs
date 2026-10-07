// ============================================================================
//  ApiRegistry.cs —— LLM 接口注册表（apis.txt）的读取与遍历
// ============================================================================
//  设计目标：**便利添加**。
//    · 从服务商后台复制的 URL 直接粘进来即可（自动补 /v1/chat/completions）
//    · 不带 https:// 也能识别（按主机名判断）
//    · 本地服务可不写 key
//    · 条目不完整（缺 url / 缺 model）时跳过并记日志，不影响其它条目
//    · 改文件即生效（与 config.txt 一样的热重载思路）
// ============================================================================

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace LLMBridge
{
    /// <summary>一条 LLM 接口配置。</summary>
    internal sealed class ApiEndpoint
    {
        public string Name = "";
        public string Url = "";        // 已归一化，保证可直接 POST
        public string RawUrl = "";     // 用户原始写法（用于显示）
        public string Key = "";
        public string Model = "";
        public string Type = "openai"; // openai | ollama_native
        public double Temperature = 0.8;
        public int MaxTokens = 400;
        public bool Starred;           // 头部写了 [* 名字]

        /// <summary>true = 来自显式的 [名字] 段头；false = 段外散装行自动生成的条目。</summary>
        public bool FromHeader;

        /// <summary>是否可用（必须能发请求）。</summary>
        public bool IsUsable
        {
            get
            {
                if (string.IsNullOrWhiteSpace(Url)) return false;
                if (string.IsNullOrWhiteSpace(Model)) return false;
                // openai 风格通常需要 key，但本地服务可空；这里只要求"不是明显占位符"
                if (LooksLikePlaceholder(Key)) return false;
                return true;
            }
        }

        private static bool LooksLikePlaceholder(string k)
        {
            if (string.IsNullOrWhiteSpace(k)) return false; // 空 = 允许（本地服务）
            var s = k.Trim();
            if (s.IndexOf("粘贴", StringComparison.Ordinal) >= 0) return true;
            if (s.IndexOf("在此", StringComparison.Ordinal) >= 0) return true;
            if (s.Equals("none", StringComparison.OrdinalIgnoreCase)) return false;
            if (s.IndexOf("your", StringComparison.OrdinalIgnoreCase) >= 0 &&
                s.IndexOf("key", StringComparison.OrdinalIgnoreCase) >= 0) return true;
            return false;
        }

        public string Describe()
        {
            var sb = new StringBuilder();
            sb.Append(Name);
            sb.Append("  [").Append(Model).Append(']');
            sb.Append("  ").Append(RawUrl);
            if (!string.IsNullOrWhiteSpace(Key))
                sb.Append("  key:").Append(MaskKey(Key));
            else
                sb.Append("  key:(无)");
            return sb.ToString();
        }

        internal static string MaskKey(string k)
        {
            if (string.IsNullOrEmpty(k)) return "";
            if (k.Length <= 8) return "****";
            return k.Substring(0, 4) + "****" + k.Substring(k.Length - 4);
        }
    }

    internal sealed class ApiRegistry
    {
        private const string FileName = "apis.txt";

        private readonly List<ApiEndpoint> _all = new List<ApiEndpoint>();
        private int _activeIndex = -1;
        private string _activeOverride = "";

        private DateTime _lastWriteUtc = DateTime.MinValue;
        private long _lastLength = -1;
        private DateTime _lastCheckUtc = DateTime.MinValue;

        public string Path { get; }
        public string LastError { get; private set; } = "";
        public int LoadCount { get; private set; }

        /// <summary>逐条诊断（哪些条目被跳过、缺什么），供菜单显示。</summary>
        private readonly List<string> _diagnostics = new List<string>();
        public IReadOnlyList<string> Diagnostics => _diagnostics;

        /// <summary>最近一次请求失败的原因（供菜单显示）。</summary>
        public string LastCallError { get; set; } = "";

        public ApiRegistry(string baseDir)
        {
            Path = System.IO.Path.Combine(baseDir ?? "", FileName);
            Reload();
        }

        public int Count => _all.Count;

        /// <summary>可用条目数（url/model 齐全、key 非占位符）。用于门控"开始对话"。</summary>
        public int UsableCount
        {
            get
            {
                int n = 0;
                for (int i = 0; i < _all.Count; i++)
                    if (_all[i].IsUsable) n++;
                return n;
            }
        }

        public IReadOnlyList<ApiEndpoint> All => _all;

        public ApiEndpoint Active
        {
            get
            {
                if (_activeIndex >= 0 && _activeIndex < _all.Count) return _all[_activeIndex];
                return null;
            }
        }

        /// <summary>节流式热重载检查。可安全高频调用。</summary>
        public void Tick()
        {
            var now = DateTime.UtcNow;
            if ((now - _lastCheckUtc).TotalMilliseconds < 1000) return;
            _lastCheckUtc = now;
            try
            {
                var fi = new FileInfo(Path);
                if (!fi.Exists)
                {
                    if (_lastLength != -2) { _lastLength = -2; Reload(); }
                    return;
                }
                if (fi.LastWriteTimeUtc != _lastWriteUtc || fi.Length != _lastLength)
                    Reload();
            }
            catch { }
        }

        public void Reload()
        {
            try
            {
                LastError = "";
                _all.Clear();
                _diagnostics.Clear();
                _activeIndex = -1;

                if (!File.Exists(Path))
                {
                    _lastWriteUtc = DateTime.MinValue;
                    _lastLength = -2;
                    LastError = FileName + " not found";
                    LoadCount++;
                    return;
                }

                var fi = new FileInfo(Path);
                _lastWriteUtc = fi.LastWriteTimeUtc;
                _lastLength = fi.Length;

                string[] lines = File.ReadAllLines(Path, new UTF8Encoding(false, false));

                ApiEndpoint cur = null;
                int starred = -1;

                foreach (var raw in lines)
                {
                    if (raw == null) continue;
                    var line = raw.Trim();
                    if (line.Length == 0) continue;
                    if (line[0] == ';' || line[0] == '#' || line[0] == '/') continue;

                    // ── 段头：[名字] / [* 名字] ──
                    if (line[0] == '[')
                    {
                        int close = line.IndexOf(']');
                        if (close < 0) continue;
                        var inner = line.Substring(1, close - 1).Trim();
                        bool star = false;
                        if (inner.StartsWith("*"))
                        {
                            star = true;
                            inner = inner.Substring(1).Trim();
                        }
                        if (inner.Length == 0) inner = "API" + (_all.Count + 1);

                        cur = new ApiEndpoint { Name = inner, Starred = star, FromHeader = true };
                        _all.Add(cur);
                        if (star) starred = _all.Count - 1;
                        continue;
                    }

                    // ── 键值 / 裸 URL ──
                    string k, v;
                    int eq = line.IndexOf('=');
                    if (eq > 0)
                    {
                        k = line.Substring(0, eq).Trim().ToLowerInvariant();
                        v = line.Substring(eq + 1).Trim();
                    }
                    else
                    {
                        // 裸行：若是 URL 且当前有段，就当作 url
                        if (cur != null && LooksLikeUrl(line))
                        {
                            k = "url"; v = line;
                        }
                        else
                        {
                            k = line.ToLowerInvariant();
                            v = "";
                        }
                    }

                    // 全局键
                    if (k == "active")
                    {
                        _activeOverride = v;
                        continue;
                    }

                    if (cur == null)
                    {
                        // 段外（还没出现过 [名字] 段头）的散装行 —— 起一条新条目。
                        // 用于容错"忘了写段头"：只要出现了 url/model/key 就开一条。
                        if (LooksLikeKeyField(k) || LooksLikeUrlField(k))
                        {
                            cur = new ApiEndpoint { Name = "API" + (_all.Count + 1) };
                            _all.Add(cur);
                        }
                        else continue;
                    }
                    else if (!cur.FromHeader && IsKeyField(k) && !string.IsNullOrEmpty(cur.Key))
                    {
                        // 散装模式下又遇到一个 key= —— 说明这是**下一条**配置了，另起一条。
                        // （同一个 [段头] 下的第二个 key= 按"覆盖本段"处理，不另起。）
                        cur = new ApiEndpoint { Name = "API" + (_all.Count + 1) };
                        _all.Add(cur);
                    }

                    switch (k)
                    {
                        case "key":
                        case "apikey":
                        case "api_key":
                            cur.Key = v; break;
                        case "model":
                        case "模型":
                            cur.Model = v; break;
                        case "url":
                        case "endpoint":
                        case "base":
                        case "host":
                        case "地址":
                            cur.RawUrl = v;
                            cur.Url = NormalizeUrl(v);
                            break;
                        case "type":
                        case "类型":
                            cur.Type = (v ?? "openai").Trim().ToLowerInvariant();
                            break;
                        case "temperature":
                        case "temp":
                            { double d; if (double.TryParse(v, NumberStyles.Float, CultureInfo.InvariantCulture, out d)) cur.Temperature = Clamp(d, 0.0, 2.0); }
                            break;
                        case "max_tokens":
                        case "maxtokens":
                            { int n; if (int.TryParse(v, NumberStyles.Integer, CultureInfo.InvariantCulture, out n) && n > 0) cur.MaxTokens = Math.Min(n, 8192); }
                            break;
                        default:
                            // 未知键忽略；但若值像 URL 就补上，容错
                            if (string.IsNullOrEmpty(cur.Url) && LooksLikeUrl(v))
                            {
                                cur.RawUrl = v;
                                cur.Url = NormalizeUrl(v);
                            }
                            break;
                    }
                }

                // ── 逐条诊断：把"为什么这条不能用"说清楚 ──
                //   这是本轮踩到的实际坑：用户只取消了 key 行的注释，
                //   model/url 还是注释状态 → 条目被静默跳过，界面上什么都不说。
                for (int i = 0; i < _all.Count; i++)
                {
                    var e = _all[i];
                    var miss = new List<string>();
                    if (string.IsNullOrWhiteSpace(e.Url)) miss.Add("url");
                    if (string.IsNullOrWhiteSpace(e.Model)) miss.Add("model");
                    if (e.IsUsable) continue;

                    string why;
                    if (miss.Count > 0)
                        why = "缺少 " + string.Join(" / ", miss) + "（检查该行是否被 ; 注释掉了）";
                    else
                        why = "key 看起来还是模板占位符，请换成真实密钥";

                    _diagnostics.Add("[" + (i + 1) + "] " + e.Name + " → 已跳过：" + why);
                }
                if (_all.Count == 0)
                    _diagnostics.Add("apis.txt 里没有任何以 [名字] 开头的配置段（段头不能少）");

                // ── 选出生效条目 ──
                // 优先级：active= 指定 > [*] 标记 > 第一条可用的
                if (!string.IsNullOrEmpty(_activeOverride))
                {
                    for (int i = 0; i < _all.Count; i++)
                    {
                        if (string.Equals(_all[i].Name, _activeOverride, StringComparison.OrdinalIgnoreCase))
                        { _activeIndex = i; break; }
                    }
                }
                if (_activeIndex < 0 && starred >= 0 && starred < _all.Count)
                    _activeIndex = starred;
                if (_activeIndex < 0)
                {
                    for (int i = 0; i < _all.Count; i++)
                    {
                        if (_all[i].IsUsable) { _activeIndex = i; break; }
                    }
                }

                if (_all.Count == 0)
                    LastError = "no API entry found in " + FileName;

                LoadCount++;
            }
            catch (Exception ex)
            {
                LastError = ex.GetType().Name + ": " + ex.Message;
                _all.Clear();
                _activeIndex = -1;
            }
        }

        /// <summary>
        /// 把用户写的地址归一化成可直接 POST 的 URL。
        /// 宽松接受：裸主机名 / 带协议 / 带 /v1 / 完整 chat/completions / 本地端口
        /// </summary>
        internal static string NormalizeUrl(string raw)
        {
            if (string.IsNullOrWhiteSpace(raw)) return "";
            var s = raw.Trim().Trim('"', '\'');

            bool hasScheme = s.StartsWith("http://", StringComparison.OrdinalIgnoreCase)
                          || s.StartsWith("https://", StringComparison.OrdinalIgnoreCase);
            if (!hasScheme)
            {
                // 本地/内网地址用 http，其余用 https
                bool localish = s.StartsWith("127.") || s.StartsWith("localhost", StringComparison.OrdinalIgnoreCase)
                             || s.StartsWith("0.0.0.0") || s.StartsWith("192.168.") || s.StartsWith("10.")
                             || s.StartsWith("[::1]");
                s = (localish ? "http://" : "https://") + s;
            }

            // 去掉末尾斜杠
            s = s.TrimEnd('/');

            // 已经指向具体端点就不再动
            if (s.EndsWith("/chat/completions", StringComparison.OrdinalIgnoreCase)) return s;
            if (s.EndsWith("/api/chat", StringComparison.OrdinalIgnoreCase)) return s;
            if (s.EndsWith("/completions", StringComparison.OrdinalIgnoreCase)) return s;

            // 以 /v1 结尾 / 含 /v1/ → 补 chat/completions
            if (s.EndsWith("/v1", StringComparison.OrdinalIgnoreCase)) return s + "/chat/completions";
            if (s.IndexOf("/v1/", StringComparison.OrdinalIgnoreCase) >= 0) return s.TrimEnd('/') + "/chat/completions";

            // 其它情况：补 /v1/chat/completions
            return s + "/v1/chat/completions";
        }

        // ── 字段名判定（用于散装行的容错）──

        private static bool IsKeyField(string k)
        {
            return k == "key" || k == "apikey" || k == "api_key";
        }

        private static bool LooksLikeKeyField(string k)
        {
            return IsKeyField(k);
        }

        private static bool LooksLikeUrlField(string k)
        {
            return k == "url" || k == "endpoint" || k == "base" || k == "host" || k == "地址"
                || k == "model" || k == "模型" || k == "type" || k == "类型"
                || k == "temperature" || k == "temp" || k == "max_tokens" || k == "maxtokens";
        }

        private static bool LooksLikeUrl(string s)
        {
            if (string.IsNullOrWhiteSpace(s)) return false;
            if (s.StartsWith("http://", StringComparison.OrdinalIgnoreCase)) return true;
            if (s.StartsWith("https://", StringComparison.OrdinalIgnoreCase)) return true;
            // 主机名特征：含点且无空格，或 localhost
            if (s.StartsWith("localhost", StringComparison.OrdinalIgnoreCase)) return true;
            if (s.IndexOf(' ') >= 0) return false;
            return s.IndexOf('.') > 0 || s.IndexOf(':') > 0;
        }

        private static double Clamp(double v, double lo, double hi)
        {
            if (v < lo) return lo;
            if (v > hi) return hi;
            return v;
        }

        /// <summary>构建所有条目的显示文本（供菜单/调试）。</summary>
        public string DescribeAll()
        {
            var sb = new StringBuilder();
            sb.Append("registry: ").Append(_all.Count).Append(" entries, active=");
            var a = Active;
            sb.Append(a == null ? "(none)" : a.Name);
            sb.Append(" loads=").Append(LoadCount);
            if (!string.IsNullOrEmpty(LastError)) sb.Append(" err=").Append(LastError);
            foreach (var d in _diagnostics)
                sb.Append('\n').Append("  ").Append(d);
            return sb.ToString();
        }
    }
}
