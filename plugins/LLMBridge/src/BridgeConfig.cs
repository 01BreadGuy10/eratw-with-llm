// ============================================================================
//  BridgeConfig.cs —— 配置读取与热重载
// ============================================================================
//  设计要点：
//    · 配置来自 plugins/LLMBridge/config.txt（纯文本，可随时手改）
//    · 按文件时间戳+长度做节流重载，默认 200ms 检查一次，避免每帧 IO
//    · 解析全程容错：非法行/非法值一律忽略，绝不抛异常
//    · 不写任何游戏状态、不写任何游戏文件
// ============================================================================

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace LLMBridge
{
    /// <summary>单个角色的开关状态。</summary>
    internal struct CharToggle
    {
        public bool Talk;
        public bool Intimate;

        public CharToggle(bool talk, bool intimate)
        {
            Talk = talk;
            Intimate = intimate;
        }
    }

    internal sealed class BridgeConfig
    {
        // ── 配置文件名（相对插件目录）──
        private const string ConfigFileName = "config.txt";

        // ── 默认值 ──
        private const bool DefaultEnableFreeTalk = true;
        private const bool DefaultEnableFreeIntimate = true;
        private const bool DefaultDebugLog = false;
        private const int DefaultScanIntervalMs = 200;
        private const bool DefaultPerCharValue = false;

        // ── 全局开关 ──
        public bool EnableFreeTalk { get; private set; } = DefaultEnableFreeTalk;
        public bool EnableFreeIntimate { get; private set; } = DefaultEnableFreeIntimate;
        public bool DebugLog { get; private set; } = DefaultDebugLog;
        public int ScanIntervalMs { get; private set; } = DefaultScanIntervalMs;

        // ── 每角色开关 ──
        // key = 运行时索引（idx 或裸数字）
        private readonly Dictionary<long, CharToggle> _byIndex = new Dictionary<long, CharToggle>();
        // key = 角色编号（no）
        private readonly Dictionary<long, CharToggle> _byNo = new Dictionary<long, CharToggle>();
        // 裸数字键同时写入上面两张表，查询时按优先级取用
        private readonly HashSet<long> _bareKeys = new HashSet<long>();

        public bool DefaultTalk { get; private set; } = DefaultPerCharValue;
        public bool DefaultIntimate { get; private set; } = DefaultPerCharValue;

        // ── 热重载状态 ──
        private DateTime _lastWriteUtc = DateTime.MinValue;
        private long _lastLength = -1;
        private DateTime _lastCheckUtc = DateTime.MinValue;

        public string ConfigPath { get; private set; } = string.Empty;
        public string LastError { get; private set; } = string.Empty;
        public int LoadCount { get; private set; }
        public int CharEntryCount => _byIndex.Count + _byNo.Count;

        /// <summary>插件目录（plugins/LLMBridge）。</summary>
        public string BaseDir { get; }

        public BridgeConfig(string baseDir)
        {
            BaseDir = baseDir ?? string.Empty;
            ConfigPath = Path.Combine(BaseDir, ConfigFileName);
            // 首次立即加载
            Reload(force: true);
        }

        /// <summary>节流式检查是否需要重载。可安全高频调用。</summary>
        public void Tick()
        {
            int interval = ScanIntervalMs;
            if (interval < 50) interval = 50;          // 下限保护
            if (interval > 10000) interval = 10000;    // 上限保护

            var now = DateTime.UtcNow;
            if ((now - _lastCheckUtc).TotalMilliseconds < interval) return;
            _lastCheckUtc = now;

            try
            {
                var fi = new FileInfo(ConfigPath);
                if (!fi.Exists)
                {
                    // 配置文件被删除 → 回落到默认（全关）
                    if (_lastLength != -2)
                    {
                        _lastLength = -2;
                        ApplyDefaults();
                    }
                    return;
                }
                if (fi.LastWriteTimeUtc != _lastWriteUtc || fi.Length != _lastLength)
                {
                    Reload(force: false);
                }
            }
            catch
            {
                // 忽略：IO 异常不影响游戏
            }
        }

        // ────────────────────────────────────────────────────────────────
        //  加载
        // ────────────────────────────────────────────────────────────────

        private void ApplyDefaults()
        {
            EnableFreeTalk = DefaultEnableFreeTalk;
            EnableFreeIntimate = DefaultEnableFreeIntimate;
            DebugLog = DefaultDebugLog;
            ScanIntervalMs = DefaultScanIntervalMs;
            DefaultTalk = DefaultPerCharValue;
            DefaultIntimate = DefaultPerCharValue;
            _byIndex.Clear();
            _byNo.Clear();
            _bareKeys.Clear();
        }

        public void Reload(bool force)
        {
            try
            {
                ApplyDefaults();
                LastError = string.Empty;

                if (!File.Exists(ConfigPath))
                {
                    _lastWriteUtc = DateTime.MinValue;
                    _lastLength = -2;
                    LastError = "config.txt not found, using defaults (all off)";
                    LoadCount++;
                    return;
                }

                var fi = new FileInfo(ConfigPath);
                _lastWriteUtc = fi.LastWriteTimeUtc;
                _lastLength = fi.Length;

                // 显式 UTF-8 读取；遇到非法字节用替换字符而非抛异常
                string[] lines = File.ReadAllLines(ConfigPath, new UTF8Encoding(false, false));

                foreach (var raw in lines)
                {
                    try
                    {
                        ParseLine(raw);
                    }
                    catch
                    {
                        // 单行解析失败不影响其它行
                    }
                }

                LoadCount++;
            }
            catch (Exception ex)
            {
                LastError = ex.GetType().Name + ": " + ex.Message;
                ApplyDefaults();
            }
        }

        private void ParseLine(string raw)
        {
            if (raw == null) return;
            var line = raw.Trim();
            if (line.Length == 0) return;
            // 注释
            if (line[0] == ';' || line[0] == '#' || line[0] == '/') return;

            // 去掉行尾注释
            int cut = line.IndexOfAny(new[] { ';', '#' });
            if (cut >= 0) line = line.Substring(0, cut).Trim();
            if (line.Length == 0) return;

            // 分隔符：'=' ':' 或空白
            int sep = line.IndexOf('=');
            if (sep < 0) sep = line.IndexOf(':');
            // 注意：'no:16' 这种冒号属于键的一部分，所以冒号分隔需满足"冒号不在键首段"
            string key;
            string val;
            if (sep > 0 && line.IndexOf('=') == sep)
            {
                key = line.Substring(0, sep).Trim();
                val = line.Substring(sep + 1).Trim();
            }
            else
            {
                // 以空白切分第一段为键，其余为值
                int ws = IndexOfWhitespace(line);
                if (ws < 0)
                {
                    key = line;
                    val = string.Empty;
                }
                else
                {
                    key = line.Substring(0, ws).Trim();
                    val = line.Substring(ws).Trim();
                }
            }
            if (key.Length == 0) return;

            var lkey = key.ToLowerInvariant();

            // ── 全局键 ──
            switch (lkey)
            {
                case "enable_free_talk":
                    EnableFreeTalk = ParseBool(val, EnableFreeTalk);
                    return;
                case "enable_free_intimate":
                    EnableFreeIntimate = ParseBool(val, EnableFreeIntimate);
                    return;
                case "debug_log":
                    DebugLog = ParseBool(val, DebugLog);
                    return;
                case "scan_interval_ms":
                    ScanIntervalMs = ParseInt(val, ScanIntervalMs);
                    return;
                case "default_talk":
                    DefaultTalk = ParseBool(val, DefaultTalk);
                    return;
                case "default_intimate":
                    DefaultIntimate = ParseBool(val, DefaultIntimate);
                    return;
                case "default_talk_intimate":
                case "default":
                    {
                        var pair = ParseTogglePair(val);
                        if (pair.HasValue)
                        {
                            DefaultTalk = pair.Value.Talk;
                            DefaultIntimate = pair.Value.Intimate;
                        }
                        return;
                    }
            }

            // ── 每角色键 ──
            // 形式： idx:<n>  /  no:<n>  /  <n>
            // 值：   "1,1"  或  <talk> <intimate>
            long id;
            var toggle = ParseTogglePair(val);
            if (!toggle.HasValue) return;

            if (lkey.StartsWith("idx:", StringComparison.Ordinal))
            {
                if (TryParseLong(key.Substring(4), out id))
                    _byIndex[id] = toggle.Value;
            }
            else if (lkey.StartsWith("no:", StringComparison.Ordinal))
            {
                if (TryParseLong(key.Substring(3), out id))
                    _byNo[id] = toggle.Value;
            }
            else if (TryParseLong(key, out id))
            {
                // 裸数字：两种解释都登记
                _byIndex[id] = toggle.Value;
                _byNo[id] = toggle.Value;
                _bareKeys.Add(id);
            }
        }

        // ────────────────────────────────────────────────────────────────
        //  查询
        // ────────────────────────────────────────────────────────────────

        /// <summary>
        /// 查询某角色的自由对话开关。
        /// runtimeIndex = ERB 的 NO:角色 / TARGET；charNo = 角色编号（用于 no: 键）。
        /// 解析优先级：idx: > no: > 裸数字 > default_*
        /// </summary>
        public bool IsFreeTalkEnabled(long runtimeIndex, long charNo)
        {
            if (!EnableFreeTalk) return false;
            return Lookup(runtimeIndex, charNo).Talk;
        }

        public bool IsFreeIntimateEnabled(long runtimeIndex, long charNo)
        {
            if (!EnableFreeIntimate) return false;
            return Lookup(runtimeIndex, charNo).Intimate;
        }

        private CharToggle Lookup(long runtimeIndex, long charNo)
        {
            if (_byIndex.TryGetValue(runtimeIndex, out var t)) return t;
            if (_byNo.TryGetValue(charNo, out var t2)) return t2;
            // 裸数字兜底：若该键存在但被 idx 覆盖过，上面已命中
            if (_bareKeys.Contains(runtimeIndex) && _byIndex.TryGetValue(runtimeIndex, out var t3)) return t3;
            return new CharToggle(DefaultTalk, DefaultIntimate);
        }

        /// <summary>导出全部显式登记的角色条目，供调试打印。</summary>
        public IEnumerable<KeyValuePair<string, CharToggle>> EnumerateEntries()
        {
            foreach (var kv in _byIndex) yield return new KeyValuePair<string, CharToggle>("idx:" + kv.Key, kv.Value);
            foreach (var kv in _byNo) yield return new KeyValuePair<string, CharToggle>("no:" + kv.Key, kv.Value);
        }

        public string Describe()
        {
            var sb = new StringBuilder();
            sb.Append("enable_free_talk=").Append(EnableFreeTalk ? 1 : 0);
            sb.Append(" enable_free_intimate=").Append(EnableFreeIntimate ? 1 : 0);
            sb.Append(" default=").Append(DefaultTalk ? 1 : 0).Append(',').Append(DefaultIntimate ? 1 : 0);
            sb.Append(" entries=").Append(CharEntryCount);
            sb.Append(" loads=").Append(LoadCount);
            if (!string.IsNullOrEmpty(LastError)) sb.Append(" err=").Append(LastError);
            return sb.ToString();
        }

        // ────────────────────────────────────────────────────────────────
        //  小工具（全部容错）
        // ────────────────────────────────────────────────────────────────

        private static int IndexOfWhitespace(string s)
        {
            for (int i = 0; i < s.Length; i++)
            {
                if (char.IsWhiteSpace(s[i])) return i;
            }
            return -1;
        }

        private static bool ParseBool(string val, bool fallback)
        {
            var v = (val ?? string.Empty).Trim().ToLowerInvariant();
            if (v.Length == 0) return fallback;
            switch (v)
            {
                case "1": case "true": case "yes": case "y": case "on": case "开": case "是":
                    return true;
                case "0": case "false": case "no": case "n": case "off": case "关": case "否":
                    return false;
            }
            return fallback;
        }

        private static int ParseInt(string val, int fallback)
        {
            if (int.TryParse((val ?? string.Empty).Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out var r))
                return r;
            return fallback;
        }

        private static bool TryParseLong(string s, out long v)
        {
            return long.TryParse((s ?? string.Empty).Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out v);
        }

        /// <summary>解析 "1,0" / "1 0" / "1" 形式的开关对。单值时两项相同。</summary>
        private static CharToggle? ParseTogglePair(string val)
        {
            var v = (val ?? string.Empty).Trim();
            if (v.Length == 0) return null;

            var parts = v.Split(new[] { ',', ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length == 0) return null;

            if (parts.Length == 1)
            {
                var b = ParseBool(parts[0], false);
                // 若无法解析为布尔（既不是 0/1 也不是 true/false），视为无效
                if (!IsRecognizableBool(parts[0])) return null;
                return new CharToggle(b, b);
            }

            if (!IsRecognizableBool(parts[0]) || !IsRecognizableBool(parts[1])) return null;
            return new CharToggle(ParseBool(parts[0], false), ParseBool(parts[1], false));
        }

        private static bool IsRecognizableBool(string s)
        {
            var v = (s ?? string.Empty).Trim().ToLowerInvariant();
            switch (v)
            {
                case "1": case "true": case "yes": case "y": case "on": case "开": case "是":
                case "0": case "false": case "no": case "n": case "off": case "关": case "否":
                    return true;
            }
            return false;
        }
    }
}
