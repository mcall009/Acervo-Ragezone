# Kali Archive - Script de Instalação e Execução para Windows (PowerShell)
# Versão PowerShell para configuração e uso do Kali Archive

# Cores no PowerShell
$Green = [System.ConsoleColor]::Green
$Blue = [System.ConsoleColor]::Cyan
$Red = [System.ConsoleColor]::Red
$Yellow = [System.ConsoleColor]::Yellow
$White = [System.ConsoleColor]::White

Clear-Host

# Função para escrever mensagens coloridas
function Write-ColoredMessage {
    param(
        [string]$Message,
        [System.ConsoleColor]$ForegroundColor = [System.ConsoleColor]::White
    )
    
    Write-Host $Message -ForegroundColor $ForegroundColor
}

# Função para verificar requisitos
function Test-Requirements {
    # Verificar Python 3.7+
    try {
        $PythonVersion = python -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
        $VersionCheck = python -c "import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)" 2>$null
        
        if ($LASTEXITCODE -eq 0) {
            Write-ColoredMessage "✓ Python $PythonVersion" $Green
        } else {
            Write-ColoredMessage "✗ Necessário Python 3.7 ou superior (atual: $PythonVersion)" $Red
            exit 1
        }
    } catch {
        Write-ColoredMessage "✗ Python não encontrado. Por favor, instale Python 3.7 ou superior." $Red
        Write-ColoredMessage "   Download: https://www.python.org/downloads/windows/" $Yellow
        exit 1
    }
    
    # Verificar arquivo principal
    if (-not (Test-Path "kali_archive.py")) {
        Write-ColoredMessage "✗ Arquivo kali_archive.py não encontrado" $Red
        exit 1
    }
    Write-ColoredMessage "✓ Arquivo principal verificado" $Green

    # Verificar Microsoft Visual C++ Build Tools
    $vcRedistCheck = Get-WmiObject -Query "SELECT * FROM Win32_Product WHERE Name LIKE '%Microsoft Visual C++ %Runtime%'"
    if ($null -eq $vcRedistCheck) {
        Write-ColoredMessage "! Microsoft Visual C++ Redistributable pode não estar instalado." $Yellow
        Write-ColoredMessage "  Alguns módulos como lxml podem falhar durante a instalação." $Yellow
        Write-ColoredMessage "  Download: https://visualstudio.microsoft.com/visual-cpp-build-tools/" $Yellow
    }
}

# Função para extrair template HTML
function Extract-Template {
    if (-not (Test-Path "index_template.html")) {
        Write-ColoredMessage "• Extraindo template HTML..." $Blue
        
        $scriptContent = Get-Content -Path "kali_archive.py" -Raw -Encoding UTF8
        
        if ($scriptContent -match '(?s)def\s+_get_fallback_template.*?return\s+"""(.*?)"""') {
            $templateContent = $matches[1]
            Set-Content -Path "index_template.html" -Value $templateContent -Encoding UTF8
            Write-ColoredMessage "✓ Template HTML extraído" $Green
        } else {
            Write-ColoredMessage "! Não foi possível extrair o template HTML" $Yellow
        }
    }
}

# Função para configurar ambiente virtual
function Setup-VirtualEnvironment {
    Write-ColoredMessage "• Configurando ambiente virtual Python..." $Blue
    
    if (-not (Test-Path "venv")) {
        python -m venv venv
        
        if (-not $?) {
            Write-ColoredMessage "✗ Falha ao criar ambiente virtual" $Red
            exit 1
        }
    }
    
    # Ativar ambiente virtual (necessário ajuste para PowerShell)
    try {
        & .\venv\Scripts\Activate.ps1
    } catch {
        Write-ColoredMessage "! Erro ao ativar ambiente virtual. Tente executar manualmente:" $Yellow
        Write-ColoredMessage "  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process" $Yellow
        Write-ColoredMessage "  .\venv\Scripts\Activate.ps1" $Yellow
        
        # Tentar configurar política de execução para esse processo
        try {
            Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force
            & .\venv\Scripts\Activate.ps1
        } catch {
            Write-ColoredMessage "✗ Não foi possível ativar o ambiente virtual automaticamente" $Red
            exit 1
        }
    }
    
    # Atualizar pip
    Write-ColoredMessage "• Atualizando pip..." $Blue
    python -m pip install --upgrade pip | Out-Null
    
    # Instalar dependências
    Write-ColoredMessage "• Instalando dependências..." $Blue
    
    if (Test-Path "requirements.txt") {
        pip install -r requirements.txt | Out-Null
    } else {
        # Instalar pacotes essenciais
        try {
            pip install aiohttp aiofiles beautifulsoup4 requests urllib3 tqdm psutil diskcache | Out-Null
            
            # Tentar instalar pacotes com componentes nativos (que podem falhar)
            try {
                pip install lxml | Out-Null
            } catch {
                Write-ColoredMessage "! Falha ao instalar lxml. Tentando versão pré-compilada..." $Yellow
                pip install --only-binary :all: lxml | Out-Null
            }
            
            # Restante dos pacotes
            pip install bs4 asyncio typing-extensions | Out-Null
        } catch {
            Write-ColoredMessage "✗ Erro ao instalar dependências. Veja o erro completo:" $Red
            Write-ColoredMessage $_.Exception.Message $Red
            exit 1
        }
    }
    
    # Preparar diretório de cache
    if (-not (Test-Path ".kali_cache")) {
        New-Item -Path ".kali_cache" -ItemType Directory | Out-Null
    }
    
    Write-ColoredMessage "✓ Ambiente configurado com sucesso" $Green
}

# Função para criar atalho no desktop
function Create-Shortcut {
    Write-ColoredMessage "• Criando atalho para fácil acesso..." $Blue
    
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Kali Archive.lnk")
    $Shortcut.TargetPath = "powershell.exe"
    $Shortcut.Arguments = "-ExecutionPolicy Bypass -File `"$PWD\kali_archive.ps1`" -ExecuteKali"
    $Shortcut.WorkingDirectory = $PWD
    $Shortcut.Description = "Executa o Kali Archive"
    $Shortcut.IconLocation = "powershell.exe,0"
    $Shortcut.Save()
    
    Write-ColoredMessage "✓ Atalho criado no Desktop" $Green
}

# Função para mostrar instruções de uso
function Show-Instructions {
    Write-ColoredMessage "`nKali Archive - Instruções de Uso" $Blue
    Write-ColoredMessage "========================================"
    
    Write-ColoredMessage "`n1. Executar com este script:" -ForegroundColor $White
    Write-ColoredMessage "   .\kali_archive.ps1 -ExecuteKali [-Domain exemplo.com.br] [-Output pasta_saida] [-StartDate 20150101]"
    
    Write-ColoredMessage "`n2. Executar manualmente:" -ForegroundColor $White
    Write-ColoredMessage "   .\venv\Scripts\Activate.ps1"
    Write-ColoredMessage "   python kali_archive.py --domain DOMINIO [opcoes]"
    
    Write-ColoredMessage "`nOpções Principais:" $Blue
    Write-ColoredMessage "========================================" 
    Write-ColoredMessage "  --domain            Domínio a extrair"
    Write-ColoredMessage "  --output            Diretório de saída"
    Write-ColoredMessage "  --start-date        Data inicial (YYYYMMDD)"
    Write-ColoredMessage "  --end-date          Data final (YYYYMMDD)"
    Write-ColoredMessage "  --threads           Threads paralelas (padrão: 12)"
    Write-ColoredMessage "  --no-auto-detect    Desativa detecção automática de data"
    Write-ColoredMessage "  --single-version    Apenas versão mais recente de cada URL"
    Write-ColoredMessage "  --help              Exibe todas as opções"
    
    Write-ColoredMessage "`nExemplo:" $Blue
    Write-ColoredMessage "========================================" 
    Write-ColoredMessage "python kali_archive.py --domain exemplo.com.br --start-date 20150101"
}

# Função para executar o Kali Archive
function Execute-KaliArchive {
    param(
        [string]$Domain = "",
        [string]$Output = "",
        [string]$StartDate = "",
        [string]$EndDate = "",
        [int]$Threads = 0,
        [switch]$NoAutoDetect,
        [switch]$SingleVersion,
        [switch]$NoCache,
        [switch]$SafeMemory
    )
    
    # Ativar ambiente virtual
    try {
        & .\venv\Scripts\Activate.ps1
    } catch {
        Write-ColoredMessage "! Erro ao ativar ambiente. Tentando ajustar políticas de execução..." $Yellow
        Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force
        & .\venv\Scripts\Activate.ps1
    }
    
    # Solicitar domínio se não fornecido
    if ([string]::IsNullOrEmpty($Domain)) {
        $Domain = Read-Host "Digite o domínio para extrair (ex: exemplo.com.br)"
        if ([string]::IsNullOrEmpty($Domain)) {
            $Domain = "exemplo.com.br"
        }
    }
    
    # Montar comando
    $CommandArgs = @("kali_archive.py", "--domain", $Domain)
    
    if (-not [string]::IsNullOrEmpty($Output)) {
        $CommandArgs += "--output"
        $CommandArgs += $Output
    }
    
    if (-not [string]::IsNullOrEmpty($StartDate)) {
        $CommandArgs += "--start-date"
        $CommandArgs += $StartDate
    }
    
    if (-not [string]::IsNullOrEmpty($EndDate)) {
        $CommandArgs += "--end-date"
        $CommandArgs += $EndDate
    }
    
    if ($Threads -gt 0) {
        $CommandArgs += "--threads"
        $CommandArgs += "$Threads"
    }
    
    if ($NoAutoDetect) {
        $CommandArgs += "--no-auto-detect"
    }
    
    if ($SingleVersion) {
        $CommandArgs += "--single-version"
    }
    
    if ($NoCache) {
        $CommandArgs += "--no-cache"
    }
    
    if ($SafeMemory) {
        $CommandArgs += "--safe-memory"
    }
    
    # Exibir comando a ser executado
    $CommandString = "python " + ($CommandArgs -join " ")
    Write-ColoredMessage "`nExecutando:" $Blue
    Write-ColoredMessage $CommandString $Yellow
    Write-ColoredMessage "========================================"
    
    # Registrar tempos para estatísticas
    $StartTime = Get-Date
    Write-ColoredMessage "Início: $StartTime" $White
    
    # Executar comando
    & python $CommandArgs
    
    # Exibir estatísticas de tempo
    $EndTime = Get-Date
    $Duration = $EndTime - $StartTime
    Write-ColoredMessage "`nExtração concluída em $($Duration.ToString('hh\:mm\:ss'))" $Green
    Write-ColoredMessage "Início: $StartTime" $White
    Write-ColoredMessage "Fim:    $EndTime" $White
}

# Verificar parâmetros do script
param(
    [switch]$InstallOnly,
    [switch]$ExecuteKali,
    [string]$Domain,
    [string]$Output,
    [string]$StartDate,
    [string]$EndDate,
    [int]$Threads,
    [switch]$NoAutoDetect,
    [switch]$SingleVersion,
    [switch]$NoCache,
    [switch]$SafeMemory
)

# Cabeçalho
Write-ColoredMessage "Kali Archive - Instalação e Execução para Windows" $Blue
Write-ColoredMessage "========================================" 

# Execução principal
Test-Requirements
Extract-Template
Setup-VirtualEnvironment

# Criar atalho no Desktop se primeira execução
if (-not $InstallOnly -and -not $ExecuteKali -and -not (Test-Path "$env:USERPROFILE\Desktop\Kali Archive.lnk")) {
    $createShortcut = Read-Host "Deseja criar um atalho no Desktop? (S/N)"
    if ($createShortcut -eq "S" -or $createShortcut -eq "s") {
        Create-Shortcut
    }
}

# Mostrar instruções de uso
if (-not $ExecuteKali) {
    Show-Instructions
    
    # Oferecer execução imediata se não foi executado com -InstallOnly
    if (-not $InstallOnly) {
        $runNow = Read-Host "`nDeseja executar o Kali Archive agora? (S/N)"
        if ($runNow -eq "S" -or $runNow -eq "s") {
            Execute-KaliArchive
        }
    }
} else {
    # Executar diretamente se chamado com -ExecuteKali
    Execute-KaliArchive -Domain $Domain -Output $Output -StartDate $StartDate -EndDate $EndDate `
                        -Threads $Threads -NoAutoDetect:$NoAutoDetect -SingleVersion:$SingleVersion `
                        -NoCache:$NoCache -SafeMemory:$SafeMemory
}

# Nota: Não desativamos o ambiente virtual para permitir execução contínua
Write-ColoredMessage "`nKali Archive pronto para uso." $Green 
