# Detiene el servicio local de este proyecto (SGI_PT_Uvicorn, uvicorn en :9000)
$service = "SGI_PT_Uvicorn"
$nssm = Join-Path $PSScriptRoot "tools\nssm.exe"

Write-Output "Deteniendo servicio $service ..."
& $nssm stop $service

Start-Sleep -Seconds 1
& $nssm status $service
