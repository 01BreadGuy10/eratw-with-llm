// ============================================================================
//  EngineApi.cs —— 对引擎 PluginManager / PluginAPICharContext 的反射访问垫片
// ============================================================================
//  为什么不直接声明 PluginManager？
//
//  契约三件套（PluginManifestAbstract / IPluginMethod / PluginMethodParameter）
//  由引擎按"类型名 + 结构"使用，本地声明即可满足（见 Contract.cs 说明）。
//
//  但 PluginManager 是**引擎提供的服务**，插件要调用它的真实实现才能读游戏状态，
//  自己声明一个同名类只会得到一个空壳。因此这里改用反射，去已加载的程序集里
//  找引擎真实的 PluginManager 类型并调用。
//
//  全部方法：
//    · 只在首次使用时解析类型，之后缓存
//    · 任何一步失败都返回安全默认值，绝不抛出
//    · 不写任何游戏状态
// ============================================================================

using System;
using System.Linq;
using System.Reflection;

namespace LLMBridge
{
    internal static class EngineApi
    {
        private const string PluginManagerTypeName = "MinorShift.Emuera.Runtime.Utils.PluginSystem.PluginManager";
        private const string CharContextTypeName = "MinorShift.Emuera.Runtime.Utils.PluginSystem.PluginAPICharContext";

        private static bool _resolved;
        private static Type _managerType;
        private static MethodInfo _getInstance;
        private static MethodInfo _getCharacterIDs;
        private static MethodInfo _print;
        private static MethodInfo _createCharContext;
        private static Type _charContextType;
        private static PropertyInfo _propCallName;
        private static PropertyInfo _propName;

        /// <summary>是否成功解析到引擎 API。</summary>
        public static bool Available => Resolve();

        private static bool Resolve()
        {
            if (_resolved) return _managerType != null;
            _resolved = true;

            try
            {
                // 在已加载程序集中查找引擎程序集（其命名空间以 MinorShift.Emuera 开头）
                Assembly engineAsm = AppDomain.CurrentDomain.GetAssemblies()
                    .FirstOrDefault(a =>
                    {
                        try
                        {
                            return a.GetTypes().Any(t => t.FullName == PluginManagerTypeName);
                        }
                        catch
                        {
                            return false;
                        }
                    });

                if (engineAsm == null) return false;

                _managerType = engineAsm.GetType(PluginManagerTypeName, throwOnError: false);
                _charContextType = engineAsm.GetType(CharContextTypeName, throwOnError: false);

                if (_managerType == null) return false;

                _getInstance = _managerType.GetMethod("GetInstance",
                    BindingFlags.Public | BindingFlags.Static, null, Type.EmptyTypes, null);
                _getCharacterIDs = _managerType.GetMethod("GetCharacterIDs",
                    BindingFlags.Public | BindingFlags.Instance, null, Type.EmptyTypes, null);

                // Print 有多个重载，取 (string) 那个
                _print = _managerType.GetMethods(BindingFlags.Public | BindingFlags.Instance)
                    .FirstOrDefault(m =>
                    {
                        if (m.Name != "Print") return false;
                        var ps = m.GetParameters();
                        return ps.Length == 1 && ps[0].ParameterType == typeof(string);
                    });

                if (_charContextType != null)
                {
                    _createCharContext = _managerType.GetMethod("CreateCharContext",
                        BindingFlags.Public | BindingFlags.Static, null, new[] { typeof(long) }, null);

                    _propCallName = _charContextType.GetProperty("CALLNAME",
                        BindingFlags.Public | BindingFlags.Instance);
                    _propName = _charContextType.GetProperty("NAME",
                        BindingFlags.Public | BindingFlags.Instance);
                }

                return true;
            }
            catch
            {
                _managerType = null;
                return false;
            }
        }

        private static object GetManagerInstance()
        {
            if (!Resolve() || _getInstance == null) return null;
            try
            {
                return _getInstance.Invoke(null, null);
            }
            catch
            {
                return null;
            }
        }

        /// <summary>运行时索引 → 角色编号（NO）。失败返回 -1。</summary>
        public static long GetCharacterNo(long runtimeIndex)
        {
            try
            {
                if (!Resolve() || _getCharacterIDs == null) return -1;
                var inst = GetManagerInstance();
                if (inst == null) return -1;

                var ids = _getCharacterIDs.Invoke(inst, null) as long[];
                if (ids == null) return -1;
                if (runtimeIndex < 0 || runtimeIndex >= ids.Length) return -1;
                return ids[runtimeIndex];
            }
            catch
            {
                return -1;
            }
        }

        /// <summary>角色显示名（CALLNAME，空则回退 NAME）。失败返回空串。</summary>
        public static string GetCharacterName(long runtimeIndex)
        {
            try
            {
                if (!Resolve() || _createCharContext == null || _charContextType == null) return string.Empty;

                var ctx = _createCharContext.Invoke(null, new object[] { runtimeIndex });
                if (ctx == null) return string.Empty;

                var v = _propCallName?.GetValue(ctx) as string;
                if (!string.IsNullOrEmpty(v)) return v;

                v = _propName?.GetValue(ctx) as string;
                return v ?? string.Empty;
            }
            catch
            {
                return string.Empty;
            }
        }

        /// <summary>向游戏控制台打印一行。失败则忽略。</summary>
        public static void Print(string text)
        {
            try
            {
                if (!Resolve() || _print == null) return;
                var inst = GetManagerInstance();
                if (inst == null) return;
                _print.Invoke(inst, new object[] { text ?? string.Empty });
            }
            catch
            {
                // 忽略
            }
        }

        /// <summary>取全部角色的运行时索引列表。失败返回 null。</summary>
        public static long[] GetCharacterIDs()
        {
            try
            {
                if (!Resolve() || _getCharacterIDs == null) return null;
                var inst = GetManagerInstance();
                if (inst == null) return null;
                return _getCharacterIDs.Invoke(inst, null) as long[];
            }
            catch
            {
                return null;
            }
        }
    }
}
