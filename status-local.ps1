$projectRoot = $PSScriptRoot
$linuxRoot = '/mnt/' + $projectRoot.Substring(0,1).ToLower() + $projectRoot.Substring(2).Replace('\','/')
& wsl.exe -d Ubuntu-24.04 -- docker compose --env-file "$linuxRoot/dify/local/selfhost/local-dify.env" -p logisupply-dify -f "$linuxRoot/deploy/dify/compose.yml" ps
& wsl.exe -d Ubuntu-24.04 -- docker compose -p logisupply-milvus -f "$linuxRoot/compose.rag.yml" ps
