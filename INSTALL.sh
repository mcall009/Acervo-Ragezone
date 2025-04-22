#!/bin/bash
set -e

# Cores minimalistas
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

clear

echo -e "${BLUE}${BOLD}Kali Archive - Instalação${NC}"
echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Verificar Python 3.7+
if command -v python3 >/dev/null 2>&1; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)"; then
        echo -e "✓ Python ${PYTHON_VERSION}"
    else
        echo -e "${RED}✗ Necessário Python 3.7 ou superior (atual: ${PYTHON_VERSION})${NC}"
        exit 1
    fi
else
    echo -e "${RED}✗ Python 3 não encontrado${NC}"
    exit 1
fi

# Verificar arquivo principal
if [ ! -f "kali_archive.py" ]; then
    echo -e "${RED}✗ Arquivo kali_archive.py não encontrado${NC}"
    exit 1
fi
echo -e "✓ Arquivo principal verificado"

# Verificar template
if [ ! -f "index_template.html" ]; then
    echo -e "• Extraindo template de HTML"
    python3 -c "
import re
with open('kali_archive.py', 'r', encoding='utf-8') as f:
    content = f.read()
template_match = re.search(r'def _get_fallback_template.*?return \"\"\"(.*?)\"\"\"\s*$', content, re.DOTALL | re.MULTILINE)
if template_match:
    with open('index_template.html', 'w', encoding='utf-8') as tf:
        tf.write(template_match.group(1))
"
fi

# Configurar ambiente virtual
echo -e "• Configurando ambiente virtual"
python3 -m venv venv > /dev/null 2>&1
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1

# Instalar dependências
echo -e "• Instalando dependências"
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt > /dev/null 2>&1
else
    pip install aiohttp aiofiles beautifulsoup4 requests urllib3 tqdm psutil diskcache lxml bs4 asyncio typing-extensions > /dev/null 2>&1
fi

# Preparar diretório de cache
mkdir -p .kali_cache

# Tornar script executável
chmod +x kali_archive.py

# Criar link simbólico
if [ ! -d "$HOME/.local/bin" ]; then
    mkdir -p "$HOME/.local/bin"
fi
ln -sf "$(pwd)/kali_archive.py" "$HOME/.local/bin/kali-archive"
chmod +x "$HOME/.local/bin/kali-archive"

# Atualizar PATH se necessário
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    if [ -f "$HOME/.bashrc" ]; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
    fi
    if [ -f "$HOME/.zshrc" ]; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"
    fi
fi

echo -e "✓ Instalação concluída"
echo

echo -e "${BLUE}${BOLD}Uso${NC}"
echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "1. ${BOLD}Ativar ambiente:${NC}"
echo -e "   source venv/bin/activate"
echo
echo -e "2. ${BOLD}Executar:${NC}"
echo -e "   kali-archive --domain DOMÍNIO [opções]"
echo -e "   python kali_archive.py --domain DOMÍNIO [opções]"
echo

echo -e "${BLUE}${BOLD}Opções Principais${NC}"
echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  --domain            Domínio a extrair"
echo -e "  --output            Diretório de saída"
echo -e "  --start-date        Data inicial (YYYYMMDD)"
echo -e "  --end-date          Data final (YYYYMMDD)"
echo -e "  --threads           Threads paralelas (padrão: 12)"
echo -e "  --no-auto-detect    Desativa detecção automática de data"
echo -e "  --single-version    Apenas versão mais recente de cada URL"
echo -e "  --help              Exibe todas as opções"
echo

echo -e "${BLUE}${BOLD}Exemplo${NC}"
echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "kali-archive --domain exemplo.com.br --start-date 20150101"