# ============================================================================
#  build.ps1 —— 编译 LLMBridge 并部署到 plugins/ 根目录
# ============================================================================
#  用法：
#      powershell -ExecutionPolicy Bypass -File build.ps1
#
#  产物：
#      ..\..\LLMBridge.dll          ← 引擎从这里加载（Plugins 目录不扫描子目录）
#
#  ⚠️ 关于 api\Emuera 桩程序集：
#      它只是编译期引用，用于让插件生成指向程序集 `Emuera` 的 TypeRef。
#      运行时由真实引擎程序集满足该引用。
#      **绝不要把 api\Emuera\bin\...\Emuera.dll 复制到 plugins\ 里**，
#      那会干扰引擎自身的程序集标识。
# ============================================================================

$ErrorActionPreference = 'Stop'

$srcDir      = Split-Path -Parent $MyInvocation.MyCommand.Path
$pluginDir   = Split-Path -Parent $srcDir                  # plugins\LLMBridge
$pluginsRoot = Split-Path -Parent $pluginDir               # plugins\
$stubProj    = Join-Path $pluginDir 'api\Emuera\Emuera.csproj'
$pluginProj  = Join-Path $srcDir    'LLMBridge.csproj'

Write-Host "src         : $srcDir"
Write-Host "plugins root: $pluginsRoot"

$dotnet = Get-Command dotnet -ErrorAction SilentlyContinue
if (-not $dotnet) {
    Write-Error "dotnet SDK 未找到。请安装 .NET SDK 8.0 或更高版本。"
    exit 1
}
Write-Host ("dotnet      : " + (& dotnet --version))

# --- 1) 先构建引用桩（插件依赖它） ---
Write-Host ""
Write-Host "[1/2] 构建引用桩 Emuera.dll ..."
& dotnet build $stubProj -c Release --nologo
if ($LASTEXITCODE -ne 0) { Write-Error "桩程序集构建失败"; exit $LASTEXITCODE }

# --- 2) 构建插件 ---
Write-Host ""
Write-Host "[2/2] 构建插件 LLMBridge.dll ..."
& dotnet build $pluginProj -c Release --nologo
if ($LASTEXITCODE -ne 0) { Write-Error "插件构建失败"; exit $LASTEXITCODE }

# --- 3) 部署 ---
$outDll = Join-Path $srcDir 'bin\Release\net8.0-windows\LLMBridge.dll'
if (-not (Test-Path -LiteralPath $outDll)) {
    Write-Error "未找到构建产物: $outDll"
    exit 1
}

$destDll = Join-Path $pluginsRoot 'LLMBridge.dll'
if (Test-Path -LiteralPath $destDll) { Remove-Item -LiteralPath $destDll -Force }
Copy-Item -LiteralPath $outDll -Destination $destDll -Force

Write-Host ""
Write-Host "OK  已部署 -> $destDll" -ForegroundColor Green
Write-Host ("    大小: " + (Get-Item -LiteralPath $destDll).Length + " 字节")

# --- 4) 自检：确认生成的是 TypeRef 到 Emuera，而非本地类型 ---
Write-Host ""
Write-Host "自检：插件引用的程序集"
try {
    $asm = [System.Reflection.Assembly]::ReflectionOnlyLoadFrom($destDll)
    foreach ($r in $asm.GetReferencedAssemblies()) {
        $pkt = (($r.GetPublicKeyToken() | ForEach-Object { $_.ToString('x2') }) -join '')
        $mark = ''
        if ($r.Name -eq 'Emuera') { $mark = ' <== 契约程序集（必须存在）' }
        Write-Host ("    {0,-24} {1,-12} PKT={2}{3}" -f $r.Name, $r.Version, $pkt, $mark)
    }
} catch {
    Write-Host "    (自检跳过: $($_.Exception.Message))"
}

$stray = Join-Path $srcDir 'bin\Release\net8.0-windows\Emuera.dll'
if (Test-Path -LiteralPath $stray) {
    Write-Warning "输出目录出现了 Emuera.dll —— Private 未生效，请检查 csproj 的 <Private>false</Private>"
}

Write-Host ""
Write-Host "提醒："
Write-Host "  · 卸载：删除 plugins\LLMBridge.dll 即可（需重启游戏）"
Write-Host "  · 若游戏启动报 InvalidCastException，说明契约程序集标识不匹配，"
Write-Host "    请核对 api\Emuera\Emuera.csproj 中的 AssemblyName/Version"
