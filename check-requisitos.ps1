# Verifica si el PC tiene lo necesario para correr este proyecto
# Uso: abrir PowerShell en cualquier carpeta y ejecutar: .\check-requisitos.ps1

Write-Output "=== Verificando requisitos ==="

# Git
try {
    $gitVersion = git --version
    Write-Output "[OK] Git instalado: $gitVersion"
} catch {
    Write-Output "[FALTA] Git no esta instalado -> https://git-scm.com"
}

# Git Credential Manager (viene con Git for Windows, pero puede no estar configurado)
$gcmHelper = git config --global --get credential.helper
if ($gcmHelper) {
    Write-Output "[OK] Credential helper configurado: $gcmHelper"
} else {
    Write-Output "[FALTA] No hay credential.helper configurado (necesario para login sin token en texto plano)"
}

# Python
try {
    $pyVersion = python --version
    Write-Output "[OK] Python instalado: $pyVersion (se recomienda 3.14.x)"
} catch {
    Write-Output "[FALTA] Python no esta instalado o no esta en PATH -> https://python.org"
}

# pip
try {
    $pipVersion = pip --version
    Write-Output "[OK] pip disponible: $pipVersion"
} catch {
    Write-Output "[FALTA] pip no disponible"
}

# VS Code
try {
    $codeVersion = code --version
    Write-Output "[OK] VS Code (comando 'code') disponible"
} catch {
    Write-Output "[FALTA] VS Code no esta instalado o el comando 'code' no esta en PATH -> https://code.visualstudio.com"
}

Write-Output "=== Fin de verificacion ==="
