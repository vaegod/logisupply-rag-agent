param([switch]$Install)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv .venv
    $Install = $true
}
if ($Install) {
    & $pythonPath -m pip install -r requirements-local.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
}
& $pythonPath deploy/dify/prepare.py
if ($LASTEXITCODE -ne 0) { throw 'Local configuration preparation failed.' }
$driveLetter = $projectRoot.Substring(0,1).ToLower()
$linuxRoot = '/mnt/' + $driveLetter + $projectRoot.Substring(2).Replace('\','/')
$composeArgs = @('compose','--env-file', "$linuxRoot/dify/local/selfhost/local-dify.env", '-p','logisupply-dify','-f', "$linuxRoot/deploy/dify/compose.yml")
function Invoke-LocalDocker {
    param([string[]]$DockerArgs)
    & wsl.exe -d Ubuntu-24.04 -- docker @DockerArgs
    if ($LASTEXITCODE -ne 0) { throw 'Local Docker command failed.' }
}
Invoke-LocalDocker -DockerArgs @('compose','-p','logisupply-milvus','-f',"$linuxRoot/compose.rag.yml",'up','-d')
Invoke-LocalDocker -DockerArgs @('volume','create','logisupply-dify_business_data')
Invoke-LocalDocker -DockerArgs ($composeArgs + @('up','-d','--build'))
$networkState = & wsl.exe -d Ubuntu-24.04 -- docker inspect logisupply-milvus-milvus-1 --format '{{json .NetworkSettings.Networks}}'
if ($networkState -notmatch 'logisupply-local') {
    Invoke-LocalDocker -DockerArgs @('network','connect','--alias','milvus-rag','logisupply-local','logisupply-milvus-milvus-1')
}
function Wait-LocalUrl {
    param([string]$Url)
    for ($attempt=0; $attempt -lt 120; $attempt++) {
        try { $response = Invoke-WebRequest -Uri $Url -TimeoutSec 5; if ($response.StatusCode -eq 200) { return } } catch { }
        Start-Sleep -Seconds 2
    }
    throw "Local service did not become ready: $Url"
}
Wait-LocalUrl -Url 'http://127.0.0.1:8088/console/api/setup'
Wait-LocalUrl -Url 'http://127.0.0.1:8020/health'
& $pythonPath deploy/dify/bootstrap.py
if ($LASTEXITCODE -ne 0) { throw 'Local Dify initialization failed; inspect private diagnostics.' }
Invoke-LocalDocker -DockerArgs ($composeArgs + @('up','-d','--no-deps','logisupply-api'))
Invoke-LocalDocker -DockerArgs ($composeArgs + @('exec','-T','logisupply-api','python','-m','order_api.rag_index'))
Wait-LocalUrl -Url 'http://127.0.0.1:8020/health'
Write-Host 'Local workspace: http://127.0.0.1:8020'
Write-Host 'Local operator:  http://127.0.0.1:8020/operator'
Write-Host 'Local Dify:      http://127.0.0.1:8088'
Write-Host 'Private credentials: dify/local/selfhost/local-admin.json'
