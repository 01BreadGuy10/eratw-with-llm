// ============================================================================
//  Emuera 契约类型 —— 引用桩（REFERENCE STUB）
// ============================================================================
//  ⚠️ 本文件**只用于编译期**，不是引擎的实现，也绝不随插件分发。
//
//  内容逐字对照上游 emuera.em 源码，不可臆改：
//    Emuera/Runtime/Utils/PluginSystem/BasePluginManifest.cs
//    Emuera/Runtime/Utils/PluginSystem/IPluginMethod.cs
//    Emuera/Runtime/Utils/PluginSystem/PluginMethodParameter.cs
//  （https://gitlab.com/EvilMask/emuera.em ）
//
//  编译出的 Emuera.dll 只是给插件"指路"，运行时会被真实的引擎程序集取代。
// ============================================================================

using System.Collections.Generic;

namespace MinorShift.Emuera.Runtime.Utils.PluginSystem
{
    /// <summary>
    /// 插件方法参数。引擎在 CALLSHARP 执行后会遍历参数，
    /// 凡是"变量"（非字面量）的都会按 isString 回写 strValue / intValue。
    /// </summary>
    public class PluginMethodParameter
    {
        public PluginMethodParameter(string initialValue)
        {
            isString = true;
            strValue = initialValue;
        }

        public PluginMethodParameter(long initialValue)
        {
            isString = false;
            intValue = initialValue;
        }

        public bool isString;
        public string strValue;
        public long intValue;
    }

    /// <summary>可由 ERB 通过 CALLSHARP &lt;Name&gt;(...) 调用的方法。</summary>
    public interface IPluginMethod
    {
        public abstract string Name { get; }
        public abstract string Description { get; }
        public abstract void Execute(PluginMethodParameter[] args);
    }

    /// <summary>
    /// 插件清单基类。引擎查找名为精确等于 "PluginManifest" 的派生类。
    /// </summary>
    public abstract class PluginManifestAbstract
    {
        //For future cases
        public abstract string PluginName { get; }
        public abstract string PluginDescription { get; }
        public abstract string PluginVersion { get; }
        public abstract string PluginAuthor { get; }

        public PluginManifestAbstract() { }

        public List<IPluginMethod> GetPluginMethods()
        {
            return methods;
        }

        protected List<IPluginMethod> methods = new List<IPluginMethod>();
    }
}
