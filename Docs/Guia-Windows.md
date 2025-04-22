## 🪟 Guia para Usuários Windows

O Kali Archive funciona perfeitamente em ambientes Windows, mas requer algumas configurações específicas para garantir o melhor desempenho. Esta seção apresenta um guia detalhado para usuários Windows.

### Requisitos Específicos para Windows

- **Python 3.7+**: Baixe e instale a versão mais recente do [Python para Windows](https://www.python.org/downloads/windows/)
- **Git para Windows**: Recomendado para clonar o repositório, disponível em [Git SCM](https://git-scm.com/download/win)
- **Microsoft Visual C++ Build Tools**: Necessário para algumas dependências que precisam ser compiladas
  - [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
  - Durante a instalação, selecione "Ferramentas de build para C++"

### Instalação no Windows

1. **Abra o PowerShell como Administrador**:
   - Clique com o botão direito no menu Iniciar e selecione "Windows PowerShell (Admin)"

2. **Clone o repositório**:
   ```powershell
   git clone https://github.com/yourusername/kali-archive.git
   cd kali-archive
   ```

3. **Crie e ative o ambiente virtual**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
   
   Se você receber um erro sobre políticas de execução, execute:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
   .\venv\Scripts\Activate.ps1
   ```

4. **Instale as dependências**:
   ```powershell
   pip install -r requirements.txt
   ```
   
   Se você encontrar erros durante a instalação de módulos com componentes nativos como `lxml` ou `psutil`, você pode instalar versões pré-compiladas:
   ```powershell
   pip install --only-binary :all: lxml psutil
   ```

5. **Configure a pasta do cache** (recomendado):
   ```powershell
   mkdir .kali_cache
   ```

### Execução no Windows

Para executar o script no Windows:

```powershell
# Ative o ambiente virtual (se ainda não estiver ativo)
.\venv\Scripts\Activate.ps1

# Execute o script
python kali_archive.py --domain exemplo.com.br
```

### Considerações de Desempenho para Windows

- **Caminho de Arquivo**: Evite diretórios com nomes muito longos ou caracteres especiais, pois o Windows tem limitação de 260 caracteres para caminhos completos
  
- **Antivírus**: Software antivírus pode desacelerar significativamente as operações de I/O. Considere adicionar a pasta do projeto às exceções do antivírus

- **PowerShell vs CMD**: PowerShell geralmente oferece melhor desempenho para este tipo de aplicação do que o Prompt de Comando (CMD)

- **Memória e Paginação**: Ajuste o parâmetro `--threads` baseado na quantidade de RAM disponível:
  - Para sistemas com 8GB RAM: `--threads 8`
  - Para sistemas com 16GB RAM: `--threads 16`
  - Para sistemas com 32GB+ RAM: `--threads 20`

### Problemas Comuns no Windows e Soluções

| Problema | Solução |
|----------|---------|
| Erro "O caminho do arquivo é muito longo" | Use `--output` para especificar um caminho mais curto ou ative o suporte a caminhos longos no Windows 10+ |
| Erros "async/await" | Certifique-se de usar Python 3.7 ou superior |
| Travamento do sistema | Reduza `--threads` e ative `--safe-memory` |
| Lentidão extrema | Verifique o antivírus e desative o rastreamento em tempo real para a pasta do projeto |
| Erro de permissão `PermissionError` | Execute o PowerShell como administrador |
| Erro de pasta bloqueada | Feche todos os exploradores de arquivos que possam estar acessando a pasta de destino |

### Exemplo de Script PowerShell para Execução Automatizada

Você pode criar um script PowerShell (`run_kali.ps1`) para automação:

```powershell
# Exemplo de script para execução automatizada
# Salve como run_kali.ps1

$dominio = "exemplo.com.br"
$pastaDestino = "C:\Archivos\$dominio"

# Ativar ambiente virtual
$ScriptDir = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
Set-Location $ScriptDir
.\venv\Scripts\Activate.ps1

# Executar script com monitoramento
$startTime = Get-Date
Write-Host "Iniciando extração de $dominio em $(Get-Date)"

python kali_archive.py --domain $dominio --output $pastaDestino --threads 12 --safe-memory

$endTime = Get-Date
$duration = $endTime - $startTime
Write-Host "Extração concluída em $duration"

# Desativar ambiente virtual
deactivate
```

Execute com:
```powershell
.\run_kali.ps1
```