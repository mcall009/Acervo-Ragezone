@echo off
setlocal enabledelayedexpansion

:: Cores no CMD do Windows
set "GREEN=[92m"
set "BLUE=[94m"
set "RED=[91m"
set "BOLD=[1m"
set "NC=[0m"

cls
echo %BLUE%%BOLD%Kali Archive - Instalacao para Windows%NC%
echo ========================================

:: Verificar Python 3.7+
echo * Verificando Python...
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo %RED%x Python nao encontrado. Por favor, instale Python 3.7 ou superior.%NC%
    exit /b 1
)

:: Verificar versão do Python
python -c "import sys; exit(0 if sys.version_info >= (3,7) else 1)" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    for /f "tokens=*" %%i in ('python -c "import sys; print(sys.version.split()[0])"') do set "PY_VERSION=%%i"
    echo %RED%x Necessario Python 3.7 ou superior ^(atual: !PY_VERSION!^)%NC%
    exit /b 1
)

for /f "tokens=*" %%i in ('python -c "import sys; print(sys.version.split()[0])"') do set "PY_VERSION=%%i"
echo √ Python !PY_VERSION!

:: Verificar arquivo principal
if not exist "kali_archive.py" (
    echo %RED%x Arquivo kali_archive.py nao encontrado%NC%
    exit /b 1
)
echo √ Arquivo principal verificado

:: Verificar template
if not exist "index_template.html" (
    echo * Extraindo template de HTML
    python -c "import re; f = open('kali_archive.py', 'r', encoding='utf-8'); content = f.read(); f.close(); template_match = re.search(r'def _get_fallback_template.*?return \"\"\"(.*?)\"\"\"\s*$', content, re.DOTALL | re.MULTILINE); tf = open('index_template.html', 'w', encoding='utf-8') if template_match else None; tf.write(template_match.group(1)) if tf else None; tf.close() if tf else None"
)

:: Configurar ambiente virtual
echo * Configurando ambiente virtual
if not exist "venv" (
    python -m venv venv
)

:: Ativar ambiente virtual
call venv\Scripts\activate.bat

:: Atualizar pip
echo * Atualizando pip...
python -m pip install --upgrade pip >nul 2>&1

:: Instalar dependências
echo * Instalando dependencias
if exist "requirements.txt" (
    pip install -r requirements.txt >nul 2>&1
) else (
    pip install aiohttp aiofiles beautifulsoup4 requests urllib3 tqdm psutil diskcache lxml bs4 asyncio typing-extensions >nul 2>&1
)

:: Preparar diretório de cache
if not exist ".kali_cache" (
    mkdir .kali_cache
)

echo √ Instalacao concluida
echo.

echo %BLUE%%BOLD%Uso%NC%
echo ========================================
echo 1. %BOLD%Ativar ambiente:%NC%
echo    venv\Scripts\activate.bat
echo.
echo 2. %BOLD%Executar:%NC%
echo    python kali_archive.py --domain DOMINIO [opcoes]
echo.

echo %BLUE%%BOLD%Opcoes Principais%NC%
echo ========================================
echo   --domain            Dominio a extrair
echo   --output            Diretorio de saida
echo   --start-date        Data inicial (YYYYMMDD)
echo   --end-date          Data final (YYYYMMDD)
echo   --threads           Threads paralelas (padrao: 12)
echo   --no-auto-detect    Desativa deteccao automatica de data
echo   --single-version    Apenas versao mais recente de cada URL
echo   --help              Exibe todas as opcoes
echo.

echo %BLUE%%BOLD%Exemplo%NC%
echo ========================================
echo python kali_archive.py --domain exemplo.com.br --start-date 20150101
echo.

:: Pergunta para executar script
echo %BOLD%Deseja executar o Kali Archive agora? (S/N)%NC%
set /p EXECNOW="> "
if /i "%EXECNOW%"=="S" (
    set /p DOMAIN="Digite o dominio para extrair: "
    if "!DOMAIN!"=="" set "DOMAIN=exemplo.com.br"
    echo Executando: python kali_archive.py --domain !DOMAIN!
    python kali_archive.py --domain !DOMAIN!
)

endlocal 