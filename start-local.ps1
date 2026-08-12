# Inicia el servicio local de este proyecto (SGI_PT_Uvicorn, uvicorn en :9000)
$service = "SGI_PT_Uvicorn"
$nssm = Join-Path $PSScriptRoot "tools\nssm.exe"

Write-Output "Iniciando servicio $service ..."
& $nssm start $service

Start-Sleep -Seconds 1
& $nssm status $service
Write-Output "Disponible en http://127.0.0.1:9000"
