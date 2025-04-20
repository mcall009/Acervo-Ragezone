# Acervo-Ragezone

# Documentação do RageZone Extractor

## Sumário
1. [Introdução](#introdução)
2. [Requisitos e Instalação](#requisitos-e-instalação)
3. [Visão Geral do Funcionamento](#visão-geral-do-funcionamento)
4. [Parâmetros e Opções](#parâmetros-e-opções)
5. [Exemplos de Uso](#exemplos-de-uso)
6. [Estrutura de Saída](#estrutura-de-saída)
7. [Interface Web](#interface-web)
8. [Otimização de Recursos](#otimização-de-recursos)
9. [Solução de Problemas](#solução-de-problemas)
10. [Limitações e Considerações](#limitações-e-considerações)

## Introdução

O RageZone Extractor é uma ferramenta robusta desenvolvida para arquivar e reconstruir o fórum RageZone Brasil a partir do Wayback Machine. Este script permite capturar todas as versões históricas do fórum, incluindo páginas HTML, recursos associados (imagens, CSS, JavaScript) e organizar tudo em uma interface navegável localmente.

A ferramenta foi projetada para preservar a história completa do fórum, permitindo consultar diferentes versões de conteúdo sem necessidade de conexão com a internet após a extração inicial.

## Requisitos e Instalação

### Requisitos de Sistema
- Python 3.6 ou superior
- Acesso à internet para a extração inicial
- Espaço em disco suficiente para armazenar o conteúdo extraído

### Dependências
As seguintes bibliotecas Python são necessárias:
```
requests>=2.28.1
beautifulsoup4>=4.11.1
tqdm>=4.64.0
diskcache>=5.4.0
urllib3>=1.26.12
```

### Instalação
1. Clone ou baixe o repositório contendo o script `ragezone.py`
2. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```

## Visão Geral do Funcionamento

O RageZone Extractor opera em quatro etapas principais:

1. **Busca de Snapshots**: Consulta o Wayback Machine CDX Server para localizar todos os snapshots disponíveis do domínio `ragezone.com.br`.

2. **Extração de Páginas HTML**: Baixa e processa cada snapshot HTML encontrado, mantendo a organização por timestamp para preservar o histórico completo.

3. **Extração de Recursos**: Identifica e baixa todos os recursos referenciados nas páginas HTML (imagens, CSS, JavaScript) para garantir a visualização correta.

4. **Criação do Índice**: Gera uma interface web moderna que organiza o conteúdo extraído, permitindo navegar entre as diferentes páginas e versões.

## Parâmetros e Opções

O script suporta os seguintes parâmetros de linha de comando:

| Parâmetro | Alias | Descrição | Padrão |
|-----------|-------|-----------|--------|
| `--output` | `-o` | Diretório de saída para o conteúdo extraído | `ragezone_archive` |
| `--domain` | `-d` | Domínio a ser extraído | `ragezone.com.br` |
| `--start-date` | - | Data inicial para snapshots (diversos formatos) | Desde o primeiro snapshot |
| `--end-date` | - | Data final para snapshots (diversos formatos) | Até o último snapshot |
| `--max-pages` | - | Número máximo de páginas a extrair | Sem limite |
| `--threads` | `-t` | Número de threads para download simultâneo | 10 |
| `--single-version` | - | Extrair apenas a versão mais recente de cada URL | Desativado (extrai todas as versões) |
| `--no-cache` | - | Desativar o sistema de cache | Ativado (usa cache) |

### Formatos de Data Suportados
O script aceita os seguintes formatos de data:
- `YYYYMMDD` (Ex: 20210315)
- `YYYY-MM-DD` (Ex: 2021-03-15)
- `DD/MM/YYYY` (Ex: 15/03/2021)
- `DD-MM-YYYY` (Ex: 15-03-2021)
- Termos relativos: `today`, `yesterday`, `last_week`, `last_month`, `last_year`

## Exemplos de Uso

### Extração Básica
Para extrair todo o conteúdo disponível com configurações padrão:
```
python ragezone.py
```

### Limitando por Data
Para extrair conteúdo de um período específico:
```
python ragezone.py --start-date 01/01/2019 --end-date 31/12/2020
```

### Extrair Apenas as Versões Mais Recentes
Para economizar espaço e tempo, extraindo apenas a versão mais recente de cada página:
```
python ragezone.py --single-version
```

### Ajustar Desempenho
Para ajustar o número de downloads simultâneos (útil para conexões mais rápidas):
```
python ragezone.py --threads 15
```

### Extrair para um Diretório Específico
```
python ragezone.py --output ./meu_arquivo_ragezone
```

### Combinando Opções
```
python ragezone.py --output ./forum_2020 --start-date 01/01/2020 --end-date 31/12/2020 --threads 12 --single-version
```

## Estrutura de Saída

Após a execução, o script cria a seguinte estrutura de diretórios:

```
ragezone_archive/
├── html/                 # Páginas HTML extraídas
│   └── [timestamp]_[arquivo].html
├── resources/            # Recursos como imagens, CSS, JS
│   ├── css/
│   ├── js/
│   ├── images/
│   └── other/
├── metadata/             # Metadados de cada página extraída
│   └── [timestamp]_[arquivo].json
├── index.html            # Interface de navegação
└── .ragezone_cache/      # Diretório de cache (se habilitado)
```

Cada arquivo HTML e recurso é nomeado usando o formato `[timestamp]_[nome_seguro]`, onde:
- `timestamp` é o timestamp do Wayback Machine (formato YYYYMMDDhhmmss)
- `nome_seguro` é um nome de arquivo derivado da URL original

## Interface Web

O script gera um arquivo `index.html` que oferece uma interface moderna para navegar pelo conteúdo extraído.

### Recursos da Interface
- **Tema Claro/Escuro**: Alterne entre modos de visualização
- **Filtragem por Tipo**: Filtre páginas por categoria (tópicos, fóruns, perfis, etc.)
- **Histórico de Versões**: Visualize todas as versões históricas de cada URL
- **Busca Integrada**: Pesquise por URLs ou títulos específicos
- **Ordenação Dinâmica**: Organize o conteúdo por URL ou data
- **Estatísticas ao Vivo**: Visualize contagens de páginas e versões

## Otimização de Recursos

### Sistema de Cache
O script implementa um sistema de cache em dois níveis:
1. **Cache em Memória**: Utilizando `lru_cache` para reduzir acessos repetidos aos mesmos recursos
2. **Cache em Disco**: Utilizando `diskcache` para persistir dados entre execuções

O cache pode ser desativado com a opção `--no-cache` para economizar espaço em disco.

### Gerenciamento de Memória
- As requisições são processadas em lotes controlados para evitar sobrecarga de memória
- Os recursos são baixados usando um pool de threads para otimizar o desempenho
- URLs duplicadas são detectadas e processadas apenas uma vez

## Solução de Problemas

### Logs Detalhados
O script gera logs detalhados no arquivo `ragezone_extractor.log` que podem ser úteis para diagnosticar problemas:
- Informações sobre o progresso da extração
- Avisos sobre recursos não encontrados
- Erros de conexão ou processamento

### Problemas Comuns

#### Nenhum Snapshot Encontrado
- Verifique se o domínio está correto
- Confira se o intervalo de datas possui snapshots disponíveis
- Teste com a opção `--domain` para especificar subdomínios

#### Erros de Conexão
O script possui retentativas automáticas, mas em caso de problemas persistentes:
- Aumente o valor de `MAX_RETRIES` (linha 39) no código-fonte
- Verifique sua conexão com a internet
- Tente diminuir o número de `--threads` para reduzir a carga

#### Alto Consumo de Memória
- Reduza o número de `--threads`
- Execute com a opção `--single-version` para limitar a quantidade de dados
- Desative o cache com `--no-cache` se estiver com pouco espaço em disco

## Limitações e Considerações

### Considerações Éticas
- Respeite as políticas do Wayback Machine mantendo um intervalo razoável entre requisições
- Use a ferramenta apenas para fins educacionais e de preservação

### Limitações Técnicas
- Alguns recursos podem não estar disponíveis no Wayback Machine
- Páginas dinâmicas que dependiam de JavaScript complexo podem não funcionar corretamente
- O script não pode recuperar conteúdo que nunca foi arquivado pelo Wayback Machine

### Desempenho
- A extração completa pode ser demorada dependendo da quantidade de conteúdo
- O espaço em disco necessário pode ser significativo, especialmente ao extrair todas as versões históricas
- Recomenda-se iniciar com um período de tempo limitado para testar antes de extrair todo o conteúdo

---

Esta documentação foi criada para ajudar a utilizar o RageZone Extractor de forma eficiente. Para questões adicionais, analise o código-fonte que contém comentários explicativos sobre cada função.
