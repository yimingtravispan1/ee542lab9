param(
    [string]$EnvFile,
    [string]$ProjectName
)
$ErrorActionPreference = 'Stop'
$taskAppRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\groupchat_app_src'))
if (-not $EnvFile) { $EnvFile = Join-Path $taskAppRoot '.env' }
$taskEnvPath = [System.IO.Path]::GetFullPath($EnvFile)

function New-LocalSecret {
    $taskBytes = New-Object byte[] 32
    $taskGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $taskGenerator.GetBytes($taskBytes) } finally { $taskGenerator.Dispose() }
    return ([System.BitConverter]::ToString($taskBytes)).Replace('-', '').ToLowerInvariant()
}

function Set-LocalSetting([string]$Name, [string]$Value) {
    $taskPattern = '(?m)^' + [regex]::Escape($Name) + '=.*$'
    if ([regex]::IsMatch($script:taskConfig, $taskPattern)) {
        $script:taskConfig = [regex]::Replace($script:taskConfig, $taskPattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($taskMatch) $Name + '=' + $Value })
    } else {
        $script:taskConfig = $script:taskConfig.TrimEnd() + "`n" + $Name + '=' + $Value + "`n"
    }
}

docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop and wait for its engine, then retry.' }
if (-not (Test-Path -LiteralPath $taskEnvPath)) {
    Copy-Item -LiteralPath (Join-Path $taskAppRoot '.env.example') -Destination $taskEnvPath
    Write-Host 'Created local configuration from .env.example.'
}
$script:taskConfig = [System.IO.File]::ReadAllText($taskEnvPath)
$taskGeneratedPassword = $null
foreach ($taskName in @('MYSQL_ROOT_PASSWORD', 'MYSQL_PASSWORD', 'JWT_SECRET')) {
    $taskMatch = [regex]::Match($script:taskConfig, ('(?m)^' + $taskName + '=(.*)$'))
    $taskValue = $taskMatch.Groups[1].Value.Trim().Trim('"').Trim("'")
    if (-not $taskValue -or $taskValue -eq 'please_change_me_to_a_long_random_value') {
        $taskNewValue = New-LocalSecret
        Set-LocalSetting $taskName $taskNewValue
        if ($taskName -eq 'MYSQL_PASSWORD') { $taskGeneratedPassword = $taskNewValue }
    }
}
if ($taskGeneratedPassword) {
    $taskMysqlPortMatch = [regex]::Match($script:taskConfig, '(?m)^MYSQL_PORT=(\d+)')
    $taskMysqlPort = if ($taskMysqlPortMatch.Success) { $taskMysqlPortMatch.Groups[1].Value } else { '3306' }
    Set-LocalSetting 'DATABASE_URL' ('mysql+asyncmy://chatuser:' + $taskGeneratedPassword + '@127.0.0.1:' + $taskMysqlPort + '/groupchat')
}
[System.IO.File]::WriteAllText($taskEnvPath, $script:taskConfig, (New-Object System.Text.UTF8Encoding($false)))
$taskKeyMatch = [regex]::Match($script:taskConfig, '(?m)^OPENAI_API_KEY=(.*)$')
$taskHasKey = -not [string]::IsNullOrWhiteSpace($taskKeyMatch.Groups[1].Value.Trim().Trim('"').Trim("'"))
if (-not $taskHasKey) {
    Write-Warning 'OPENAI_API_KEY is empty. The DMV data will restore without it; fill your own key in the local env file and rerun this command to enable answers.'
}
$taskComposeArgs = @('compose', '--env-file', $taskEnvPath, '-f', (Join-Path $taskAppRoot 'compose.yaml'))
if ($ProjectName) { $taskComposeArgs += @('--project-name', $ProjectName) }
Push-Location $taskAppRoot
try {
    & docker @taskComposeArgs config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Invalid Compose configuration. Review your local env file.' }
    & docker @taskComposeArgs up -d --build --wait --wait-timeout 240 mysql qdrant backend
    if ($LASTEXITCODE -ne 0) { throw 'Startup failed. Check Docker logs and whether another process occupies the configured ports. Existing data was preserved.' }
} finally {
    Pop-Location
}
$taskPortMatch = [regex]::Match($script:taskConfig, '(?m)^APP_PORT=(\d+)')
$taskWebPort = if ($taskPortMatch.Success) { $taskPortMatch.Groups[1].Value } else { '8000' }
Write-Host ('Ready: http://localhost:' + $taskWebPort)
Write-Host 'Register your own account. The curated DMV library is available immediately.'
Write-Host 'Edit backend source files locally; the development server reloads automatically.'
