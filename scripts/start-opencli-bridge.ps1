param(
    [Parameter(Mandatory = $true)]
    [string]$Token,
    [int]$Port = 19826,
    [string]$OpenCliPackage = "@jackwener/opencli@1.8.7"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $repoRoot "backend"
$python = Join-Path $backendRoot ".venv-test\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python).Source
}
$node = (Get-Command node).Source
$nodeRoot = Split-Path -Parent $node
$npxCli = Join-Path $nodeRoot "node_modules\npm\bin\npx-cli.js"
if (-not (Test-Path -LiteralPath $npxCli)) {
    $npmPrefix = (& npm prefix -g).Trim()
    $npxCli = Join-Path $npmPrefix "node_modules\npm\bin\npx-cli.js"
}
if (-not (Test-Path -LiteralPath $npxCli)) {
    throw "Cannot locate npm's npx-cli.js beside Node or under npm's global prefix"
}

$env:OPENCLI_BRIDGE_TOKEN = $Token
$env:OPENCLI_NODE_PATH = $node
$env:OPENCLI_NPX_CLI_PATH = $npxCli
$env:OPENCLI_PACKAGE = $OpenCliPackage

& $python -m uvicorn tools.opencli_bridge:app `
    --app-dir $backendRoot `
    --host 0.0.0.0 `
    --port $Port
