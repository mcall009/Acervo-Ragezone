# Kali Archive

[![Status do Projeto](https://img.shields.io/badge/Status-Ativo-brightgreen.svg)](https://github.com/mcall009/kali-archive)
[![Python Version](https://img.shields.io/badge/Python-3.7%2B-blue.svg)](https://www.python.org/downloads/)
[![Licença](https://img.shields.io/badge/Licen%C3%A7a-GPL%20v3-blue.svg)](LICENSE)

Ferramenta avançada para extração e reconstrução de conteúdo web histórico via Wayback Machine. O Kali Archive realiza a recuperação completa, processamento e indexação de versões históricas de sites, preservando todos os recursos associados (HTML, CSS, JavaScript, imagens) em uma estrutura navegável localmente.

> **AVISO**: Use esta ferramenta de forma responsável, respeitando os termos de serviço do Internet Archive (archive.org) e as políticas de robôs do site alvo.

## 📋 [Sumário](#-sumário).

- [Visão Geral](#-visão-geral)
- [Características Principais](#-características-principais)
- [Requisitos](#-requisitos)
- [Instalação](#-instalação)
  - [Instalação Automática](#-instalação-automática)
  - [Instalação Manual](#-instalação-manual)
- [Uso Básico](#-uso-básico)
- [Parâmetros e Opções](#-parâmetros-e-opções)
  - [Formatos de Data Aceitos](#-formatos-de-data-aceitos)
- [Arquitetura e Funcionamento](#-arquitetura-e-funcionamento)
  - [Componentes Principais](#-componentes-principais)
  - [Fluxo de Execução](#-fluxo-de-execução)
- [Sistema de Detecção de Datas](#-sistema-de-detecção-de-datas)
  - [Hierarquia de Decisão](#-hierarquia-de-decisão)
  - [Controle da Detecção Automática](#-controle-da-detecção-automática)
- [Estrutura de Diretórios](#-estrutura-de-diretórios)
- [Gerenciamento de Recursos](#-gerenciamento-de-recursos)
  - [Sistema de Cache](#-sistema-de-cache)
  - [Monitoramento de Memória](#-monitoramento-de-memória)
  - [Controle de Concorrência](#-controle-de-concorrência)
- [Interface de Usuário](#-interface-de-usuário)
- [Exemplos Avançados](#-exemplos-avançados)
- [Resolução de Problemas](#-resolução-de-problemas)
- [Perguntas Frequentes](#-perguntas-frequentes)
- [Contribuição e Customização](#-contribuição-e-customização)

## 🔍 Visão Geral

O Kali Archive é uma ferramenta de linha de comando robusta que utiliza a API do Wayback Machine para recuperar, processar e armazenar localmente versões históricas completas de sites. Projetado com arquitetura modular e assíncrona, o script é capaz de processar grandes volumes de dados históricos enquanto gerencia eficientemente recursos computacionais.

A ferramenta não apenas extrai o conteúdo HTML, mas também processa e reconstrói toda a estrutura de recursos associados (CSS, JavaScript, imagens, fontes), corrigindo referências para criar uma versão navegável localmente que preserva fielmente o conteúdo original.

## ✨ Características Principais

- **Arquitetura Assíncrona**: Utiliza `asyncio` e `aiohttp` para operações I/O paralelas eficientes
- **Extração Inteligente**: Detecta automaticamente a data inicial do domínio no Wayback Machine
- **Reconstrução Completa**: Processa todos os recursos associados (CSS, JS, imagens, etc.)
- **Controle Preciso de Datas**: Permite especificar períodos exatos de interesse histórico
- **Interface Web Moderna**: Gera um índice HTML interativo usando Tailwind CSS e JavaScript
- **Gerenciamento de Recursos**: Monitoramento ativo de memória e controle de uso de disco
- **Cache Eficiente**: Sistema baseado em disco para evitar downloads redundantes
- **Resiliência**: Implementa retry com backoff exponencial para superar falhas temporárias
- **Modularidade**: Design baseado em classes especializadas para facilitar manutenção e extensão

## 📦 Requisitos

- Python 3.7 ou superior
- Dependências principais:
  - `aiohttp`: Para requisições HTTP assíncronas
  - `aiofiles`: Para operações de arquivo assíncronas
  - `beautifulsoup4`: Para processamento HTML
  - `requests`: Para requisições HTTP síncronas
  - `tqdm`: Para exibição de progresso
  - `diskcache`: Para sistema de cache em disco
  - `psutil`: Para monitoramento de recursos do sistema
  - `lxml`: Para processamento XML/HTML avançado

## 💻 Instalação

### Instalação Automática

O método mais simples é usar o script de instalação fornecido, que configura o ambiente virtual, instala dependências e prepara o script para uso imediato:

```bash
# Clone ou baixe o repositório
git clone https://github.com/mcall009/kali-archive.git
cd kali-archive

# Torne o script de instalação executável
chmod +x INSTALL.sh

# Execute o instalador
./INSTALL.sh
```

O instalador verifica os requisitos, cria um ambiente virtual Python, instala todas as dependências e configura um link simbólico para facilitar a execução.

### Instalação Manual

Se preferir instalar manualmente:

```bash
# Clone ou baixe o repositório
git clone https://github.com/mcall009/kali-archive.git
cd kali-archive

# Crie um ambiente virtual Python
python3 -m venv venv

# Ative o ambiente virtual
source venv/bin/activate  # Linux/macOS
# ou
venv\Scripts\activate     # Windows

# Instale as dependências
pip install -r requirements.txt

# Torne o script executável
chmod +x kali_archive.py  # Linux/macOS
```

## 🚀 Uso Básico

### Exemplo Simples

```bash
# Ative o ambiente virtual (se não estiver usando o link simbólico)
source venv/bin/activate

# Execute o script com configurações básicas
python kali_archive.py --domain exemplo.com.br
```

Este comando extrai o conteúdo histórico do domínio `exemplo.com.br`, detectando automaticamente a data do primeiro snapshot disponível. Os arquivos serão salvos no diretório com o nome do domínio.

### Especificar Período

```bash
python kali_archive.py --domain exemplo.com.br --start-date 20150101 --end-date 20201231
```

Este comando extrai apenas o conteúdo capturado entre 1º de janeiro de 2015 e 31 de dezembro de 2020.

### Definir Diretório de Saída

```bash
python kali_archive.py --domain exemplo.com.br --output meu_arquivo
```

Os arquivos serão salvos no diretório `meu_arquivo` em vez do padrão (nome do domínio).

## 🎛️ Parâmetros e Opções
Nota: Atualmente o diretório de saída (output) está definido com o valor padrão de "kali_archive".
Em breve o script será atualizado para a pasta ser gerada com o nome exato do domínio, como mostra na tabela abaixo.

O Kali Archive oferece um conjunto abrangente de opções para personalizar o comportamento da ferramenta:

| Parâmetro | Descrição | Valor Padrão |
|-----------|-----------|--------|
| `--domain`, `-d` | Domínio a ser extraído | `ragezone.com.br` |
| `--output`, `-o` | Diretório de saída para os arquivos | Nome do domínio |
| `--start-date` | Data inicial para snapshots | Detecção automática |
| `--end-date` | Data final para snapshots | Data atual |
| `--max-pages` | Número máximo de páginas a extrair | Sem limite |
| `--threads`, `-t` | Número de threads para download concorrente | 12 |
| `--single-version` | Extrair apenas a versão mais recente de cada URL | `False` |
| `--no-cache` | Desativar cache para economizar espaço em disco | `False` |
| `--safe-memory` | Monitorar uso de memória e limitar extrações em caso de uso elevado | `False` |
| `--timeout` | Timeout para requisições em segundos | 30 |
| `--no-auto-detect` | Desativar detecção automática da data inicial | `False` |
| `--help` | Exibir ajuda e sair | - |

### Formatos de Data Aceitos

O script oferece alta flexibilidade no formato de datas, aceitando:

- **Formato YYYYMMDD**: `20150101` (1º de janeiro de 2015)
- **Formato YYYY-MM-DD**: `2015-01-01`
- **Formato DD/MM/YYYY**: `01/01/2015`
- **Formato DD-MM-YYYY**: `01-01-2015`
- **Formato YYYY/MM/DD**: `2015/01/01`
- **Termos relativos em português**:
  - `hoje`: Data atual
  - `ontem`: Data de ontem
  - `semana_passada`: 7 dias atrás
  - `mes_passado`: 30 dias atrás
  - `ano_passado`: 365 dias atrás
- **Termos relativos em inglês**:
  - `today`
  - `yesterday`
  - `last_week`
  - `last_month`
  - `last_year`

Exemplos:
```bash
python kali_archive.py --domain exemplo.com.br --start-date 01/01/2015
python kali_archive.py --domain exemplo.com.br --start-date "ano_passado"
```

## 🏗️ Arquitetura e Funcionamento

### Componentes Principais

O Kali Archive é estruturado em classes especializadas, cada uma com responsabilidade única:

1. **`DomainDateDetector`**: Responsável por detectar a data inicial do domínio no Wayback Machine.

2. **`ResourceManager`**: Gerencia o download e armazenamento de recursos (CSS, JS, imagens).

3. **`SnapshotFetcher`**: Consulta a API do Wayback Machine para obter a lista de snapshots disponíveis.

4. **`HtmlProcessor`**: Processa arquivos HTML, extraindo recursos e corrigindo referências.

5. **`IndexBuilder`**: Gera a interface web para navegação do conteúdo arquivado.

6. **`KaliArchive`**: Classe principal que orquestra todo o processo de extração.

### Fluxo de Execução

O processo de extração segue as seguintes etapas:

1. **Inicialização**:
   - Parsing dos argumentos de linha de comando
   - Configuração de diretórios e cache
   - Inicialização dos componentes

2. **Determinação de Datas**:
   - Aplicação da hierarquia de decisão para data inicial
   - Validação e formatação das datas

3. **Busca de Snapshots**:
   - Consulta à API CDX do Wayback Machine
   - Divisão da busca em períodos para evitar timeouts
   - Filtragem e deduplicação dos resultados

4. **Download e Processamento**:
   - Download assíncrono dos snapshots HTML
   - Processamento para identificação de recursos
   - Correção de referências relativas e absolutas

5. **Extração de Recursos**:
   - Download concorrente de recursos (CSS, JS, imagens)
   - Organização em diretórios específicos
   - Aplicação de cache para evitar redundância

6. **Geração de Índice**:
   - Organização dos snapshots por URL original
   - Coleta de estatísticas e metadados
   - Geração do HTML interativo com Tailwind CSS

## 📅 Sistema de Detecção de Datas

### Hierarquia de Decisão

O Kali Archive implementa um sistema sofisticado em cascata para determinar a data inicial da extração:

1. **Data especificada pelo usuário** (via `--start-date`):
   - Se fornecida, tem prioridade absoluta
   - Suporta múltiplos formatos de entrada

2. **Detecção automática** (se habilitada):
   - Consulta a API do Wayback Machine
   - Identifica o snapshot mais antigo disponível
   - Otimiza a extração focando apenas em períodos com dados

3. **Fallback dinâmico** (se detecção falhar):
   - Utiliza data de 5 anos atrás da data atual
   - Configurável via constante `DYNAMIC_FALLBACK_YEARS`

4. **Fallback fixo** (último recurso):
   - Utiliza data fixa `20000101` (1º de janeiro de 2000)
   - Garante que a extração sempre tenha um ponto de partida

### Controle da Detecção Automática

A detecção automática pode ser controlada de três formas:

1. **Via linha de comando**: 
   ```bash
   python kali_archive.py --domain exemplo.com.br --no-auto-detect
   ```

2. **Via código** - Modificando o parâmetro ao instanciar `KaliArchive`:
   ```python
   extrator = KaliArchive(
       domain="exemplo.com.br",
       auto_detect_date=False
   )
   ```

3. **Globalmente** - Editando o arquivo `kali_archive.py` e modificando o valor padrão:
   ```python
   # Procure por:
   def __init__(self, 
               # ...
               auto_detect_date: bool = True,
               # ...
   ```

## 📁 Estrutura de Diretórios

O Kali Archive gera a seguinte estrutura de diretórios para armazenar o conteúdo extraído:

```
output_dir/               # Nome do domínio ou especificado pelo usuário
├── html/                 # Arquivos HTML extraídos
│   ├── 20160505123045_index.html
│   ├── 20180610092132_about.html
│   └── ...
├── resources/            # Recursos extraídos
│   ├── css/              # Folhas de estilo
│   ├── js/               # Scripts JavaScript
│   ├── images/           # Imagens (jpg, png, gif, etc.)
│   ├── fonts/            # Arquivos de fonte
│   └── other/            # Outros recursos
├── metadata/             # Metadados de cada snapshot
│   ├── 20160505123045_index.json
│   ├── 20180610092132_about.json
│   └── ...
└── index.html            # Interface web para navegação
```

Cada arquivo preserva o timestamp original do Wayback Machine como prefixo, permitindo manter e navegar entre múltiplas versões do mesmo recurso ao longo do tempo.

## 🧰 Gerenciamento de Recursos

### Sistema de Cache

O Kali Archive implementa um sistema de cache eficiente para minimizar tráfego e acelerar execuções repetidas:

- Baseado na biblioteca `diskcache`
- Armazena até 10GB de conteúdo por padrão
- Mantém snapshots HTML e recursos associados
- Persiste entre execuções para permitir retomada de extrações interrompidas
- Desativável via `--no-cache` quando economia de espaço é prioritária

### Monitoramento de Memória

Para garantir estabilidade em extrações de grande escala:

- Implementa o decorador `@memory_safe()` para operações críticas
- Monitora uso de memória em tempo real via `psutil`
- Pausa automaticamente operações quando uso ultrapassa 85% (configurável)
- Força coleta de lixo para liberar recursos
- Retoma operações quando níveis normalizados

### Controle de Concorrência

Mecanismos para balancear performance e sobrecarga:

- Semáforos para limitar download concorrente (`MAX_WORKERS`, configurável via `--threads`)
- Limite de conexões simultâneas por host (10 por padrão)
- Delays estratégicos entre requisições (`DOWNLOAD_DELAY`: 0.5s)
- Retry com backoff exponencial para lidar com limitações de API

## 🖥️ Interface de Usuário

O Kali Archive gera uma interface web moderna para navegação do conteúdo extraído:

- Baseada em Tailwind CSS para design responsivo
- Suporte a tema claro/escuro (com detecção automática de preferência)
- Recursos de busca e filtragem:
  - Filtro por tipo de conteúdo (tópicos, fóruns, perfis, etc.)
  - Filtro por ano de captura
  - Busca por texto em URLs
- Visualização de múltiplas versões do mesmo conteúdo
- Links diretos para o conteúdo local e para o Wayback Machine original
- Estatísticas sobre o conteúdo extraído

## 💡 Exemplos Avançados

### Extração de Alta Performance

Para máxima velocidade em sistemas com bons recursos:

```bash
python kali_archive.py --domain exemplo.com.br --threads 20 --timeout 60
```

### Modo Econômico

Para sistemas com recursos limitados:

```bash
python kali_archive.py --domain exemplo.com.br --threads 4 --single-version --no-cache --safe-memory
```

### Extração Focada com Período Específico

```bash
python kali_archive.py --domain exemplo.com.br --start-date 2010-01-01 --end-date 2015-12-31 --output exemplo_2010a2015
```

### Extração Rápida Apenas da Versão Mais Recente

```bash
python kali_archive.py --domain exemplo.com.br --single-version --no-auto-detect
```

### Extração de Múltiplos Domínios Sequencialmente

```bash
for dominio in site1.com site2.org site3.net; do
    python kali_archive.py --domain $dominio
done
```

## 🔧 Resolução de Problemas

### Mensagens de Erro Comuns

| Erro | Possível Causa | Solução |
|------|----------------|---------|
| `Cannot connect to host web.archive.org` | Problemas de conexão | Verifique sua conexão com a internet e tente novamente |
| `Alto uso de memória detectado` | Processamento de muitos snapshots simultaneamente | Use `--safe-memory` e reduza `--threads` |
| `Erro ao detectar data inicial` | API do Wayback Machine indisponível | Use `--no-auto-detect` ou especifique `--start-date` manualmente |
| `Falha após X tentativas` | Rate limiting ou problemas temporários | Aumente o timeout ou execute novamente mais tarde |
| `Espaço em disco insuficiente` | Menos de 5GB disponíveis | Libere espaço ou especifique período menor |
| `DeprecationWarning: loop` | Avisos de asyncio em Python 3.10+ | Ignorável, não afeta a funcionalidade |

### Limites e Considerações

- A API do Wayback Machine pode impor rate limits durante uso intensivo
- Extração de sites grandes pode levar horas ou dias, dependendo do volume
- Nem todos os recursos podem ser recuperáveis (alguns podem estar ausentes do Internet Archive)
- Alguns sites complexos podem exigir processamento manual adicional

## ❓ Perguntas Frequentes

**P: Quanto espaço em disco é necessário para uma extração completa?**  
R: Depende enormemente do tamanho e complexidade do site, mas reserve pelo menos 10GB para sites médios. Fóruns e sites ricos em mídia podem exigir 50GB ou mais.

**P: O script respeita os robots.txt do site original?**  
R: O Kali Archive acessa apenas o Wayback Machine, não o site original, portanto respeita as políticas do Internet Archive.

**P: É possível continuar uma extração que foi interrompida?**  
R: Sim. Se o cache estiver habilitado (padrão), o script não baixará novamente o conteúdo já processado. Simplesmente execute o mesmo comando e a extração continuará de onde parou.

**P: Como extrair apenas um subdiretório específico de um site?**  
R: Especifique o domínio completo com o caminho: `--domain exemplo.com.br/secao/especifica`.

**P: Por que a detecção automática de data é útil?**  
R: Economiza tempo e recursos, evitando consultas em períodos sem snapshots disponíveis. Particularmente útil para sites com histórico limitado no Internet Archive.

**P: É possível executar extrações simultâneas para diferentes domínios?**  
R: Sim, a ferramenta com o ajuste para usar o nome do domínio como diretório de saída permite executar múltiplas instâncias sem conflitos.

**P: Posso customizar a aparência do índice gerado?**  
R: Sim, crie ou modifique o arquivo `Templates/index_template.html`. O script usa este template se existir ou recorre ao template interno caso contrário.

## 🛠️ Contribuição e Customização

### Constantes Configuráveis

As principais constantes configuráveis estão no início do arquivo `kali_archive.py`:

```python
DEFAULT_DOMAIN = "ragezone.com.br"  # Domínio padrão
WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"  # Endpoint CDX API
MAX_WORKERS = 12  # Número máximo de threads
DOWNLOAD_DELAY = 0.5  # Pausa entre downloads (segundos)
CACHE_DIR = ".kali_cache"  # Diretório de cache
MAX_SNAPSHOTS_PER_PAGE = 500  # Limite de snapshots por consulta
MEMORY_LIMIT_PERCENT = 85  # Limite de uso de memória (%)
CONN_LIMIT = 50  # Limite de conexões HTTP simultâneas
REQUEST_TIMEOUT = 30  # Timeout de requisições (segundos)
FIXED_FALLBACK_DATE = "20000101"  # Data de fallback fixa
DYNAMIC_FALLBACK_YEARS = 5  # Anos atrás para fallback dinâmico
```

### Personalização do Template
Nota: Atualmente o index_template.html ainda está definido no diretório raiz por padrão, então, apenas edite-o sem criar a pasta "templates".

Para personalizar a interface web gerada:

1. Crie uma pasta `Templates` no diretório do script
2. Adicione um arquivo `index_template.html` com seu HTML personalizado
3. Mantenha os placeholders utilizados pelo script:
   - `{{STATS_INFO}}`: Estatísticas gerais
   - `{{TYPE_OPTIONS}}`: Opções de filtro por tipo
   - `{{YEAR_OPTIONS}}`: Opções de filtro por ano
   - `{{TABLE_ROWS}}`: Conteúdo da tabela

### Extensão de Funcionalidades

O design modular facilita a extensão das capacidades:

- `DomainDateDetector`: Adapte para outras fontes de dados históricos
- `ResourceManager`: Adicione suporte para novos tipos de recursos
- `HtmlProcessor`: Implemente processamento especializado para sites específicos
- `IndexBuilder`: Crie visualizações personalizadas para diferentes tipos de conteúdo

---

## 📄 Licença

Este projeto está licenciado sob a [Licença GPL-3.0](LICENSE) - veja o arquivo LICENSE para detalhes.

---

Criado com ❤️ para preservação digital de conteúdo histórico da web
