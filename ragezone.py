#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import time
import json
import logging
import argparse
import urllib.parse
import concurrent.futures
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Union, Any
from dataclasses import dataclass
from functools import lru_cache

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import diskcache
import hashlib

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ragezone_extractor.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ragezone_extractor")

# Constantes
DEFAULT_DOMAIN = "ragezone.com.br"
WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"
WAYBACK_URL_PREFIX = "https://web.archive.org/web/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
MAX_RETRIES = 5
RETRY_BACKOFF = 0.5
MAX_WORKERS = 10
DOWNLOAD_DELAY = 1.0  # Delay entre requisições para evitar sobrecarga do servidor
CACHE_DIR = ".ragezone_cache"

@dataclass
class Snapshot:
    timestamp: str
    original_url: str
    statuscode: str
    mimetype: str

# Criar uma sessão HTTP com retry automático
def create_session() -> requests.Session:
    session = requests.Session()
    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session

class RageZoneExtractor:
    def __init__(self, 
                 output_dir: str = "ragezone_archive", 
                 domain: str = DEFAULT_DOMAIN,
                 start_date: Optional[str] = None,
                 end_date: Optional[str] = None,
                 max_pages: Optional[int] = None,
                 threads: int = MAX_WORKERS,
                 all_versions: bool = True,
                 cache_enabled: bool = True):
        
        self.domain = domain
        self.output_dir = Path(output_dir)
        self.start_date = self._parse_date(start_date)
        self.end_date = self._parse_date(end_date)
        self.max_pages = max_pages
        self.threads = min(threads, MAX_WORKERS)
        self.all_versions = all_versions
        self.session = create_session()
        self.processed_urls: Set[str] = set()
        self.url_timestamps: Dict[str, str] = {}
        self.resource_queue: List[Tuple[str, str, str]] = []
        
        # Criar diretórios de saída
        self.html_dir = self.output_dir / "html"
        self.resources_dir = self.output_dir / "resources"
        self.metadata_dir = self.output_dir / "metadata"
        
        self._create_directories()
        
        if cache_enabled:
            self.cache = diskcache.Cache(CACHE_DIR)
        else:
            self.cache = None
        
    def _parse_date(self, date_str: Optional[str]) -> Optional[str]:
        if not date_str:
            return None
            
        patterns = [
            r'^\d{8}$',                      # YYYYMMDD
            r'^\d{4}-\d{2}-\d{2}$',          # YYYY-MM-DD
            r'^\d{2}/\d{2}/\d{4}$',          # DD/MM/YYYY
            r'^\d{2}-\d{2}-\d{4}$'           # DD-MM-YYYY
        ]
        
        for pattern in patterns:
            if re.match(pattern, date_str):
                if pattern == r'^\d{8}$':
                    return date_str
                elif pattern == r'^\d{4}-\d{2}-\d{2}$':
                    return date_str.replace('-', '')
                elif pattern == r'^\d{2}/\d{2}/\d{4}$':
                    day, month, year = date_str.split('/')
                    return f"{year}{month}{day}"
                elif pattern == r'^\d{2}-\d{2}-\d{4}$':
                    day, month, year = date_str.split('-')
                    return f"{year}{month}{day}"
        
        relative_dates = {
            "today": datetime.now(),
            "yesterday": datetime.now() - timedelta(days=1),
            "last_week": datetime.now() - timedelta(weeks=1),
            "last_month": datetime.now() - timedelta(days=30),
            "last_year": datetime.now() - timedelta(days=365)
        }
        
        if date_str.lower() in relative_dates:
            return relative_dates[date_str.lower()].strftime("%Y%m%d")
            
        logger.warning(f"Data inválida: {date_str}. Usando formato padrão YYYYMMDD.")
        return None
        
    def _create_directories(self) -> None:
        """Cria os diretórios necessários para armazenar o conteúdo."""
        directories = [
            self.output_dir,
            self.html_dir,
            self.resources_dir,
            self.metadata_dir,
            self.resources_dir / "css",
            self.resources_dir / "js",
            self.resources_dir / "images",
            self.resources_dir / "other"
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def _generate_safe_filename(self, url: str) -> str:
        """Gera um nome de arquivo seguro baseado na URL."""
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.strip("/")
        if not path:
            path = "index"
        
        # Substituir caracteres problemáticos
        safe_filename = re.sub(r'[\\/*?:"<>|]', "_", path)
        # Limitar comprimento do nome de arquivo
        if len(safe_filename) > 120:
            safe_filename = safe_filename[:120]
        
        # Adicionar query como hash no final se existir
        if parsed.query:
            query_hash = hashlib.md5(parsed.query.encode()).hexdigest()[:8]
            safe_filename = f"{safe_filename}_{query_hash}"
        
        return safe_filename

    def fetch_snapshots(self) -> List[Snapshot]:
        """Busca todos os snapshots do domínio no Wayback Machine."""
        logger.info(f"Buscando snapshots para o domínio: {self.domain}")
        
        params = {
            "url": self.domain + "/*",
            "output": "json",
            "fl": "timestamp,original,statuscode,mimetype",
            "filter": "statuscode:200",
        }
        
        if not self.all_versions:
            params["collapse"] = "urlkey"
        
        if self.start_date:
            params["from"] = self.start_date
        if self.end_date:
            params["to"] = self.end_date
        
        response = self.session.get(WAYBACK_CDX_URL, params=params)
        
        if response.status_code != 200:
            logger.error(f"Erro ao buscar snapshots: {response.status_code}")
            return []
        
        try:
            data = response.json()
            if not data or len(data) <= 1:  # Primeira linha são apenas cabeçalhos
                logger.warning("Nenhum snapshot encontrado.")
                return []
            
            headers = data[0]
            timestamp_idx = headers.index("timestamp")
            original_idx = headers.index("original")
            statuscode_idx = headers.index("statuscode")
            mimetype_idx = headers.index("mimetype")
            
            snapshots = []
            for row in data[1:]:
                if self.max_pages and len(snapshots) >= self.max_pages:
                    break
                
                # Filtrar apenas páginas HTML
                if "text/html" in row[mimetype_idx]:
                    snapshots.append(Snapshot(
                        timestamp=row[timestamp_idx],
                        original_url=row[original_idx],
                        statuscode=row[statuscode_idx],
                        mimetype=row[mimetype_idx]
                    ))
            
            logger.info(f"Encontrados {len(snapshots)} snapshots HTML.")
            return snapshots
        
        except Exception as e:
            logger.error(f"Erro ao processar resposta do Wayback CDX: {e}")
            return []

    @lru_cache(maxsize=1024)
    def _get_cached_response(self, url: str) -> Optional[bytes]:
        if not self.cache:
            return None
        return self.cache.get(url)

    def _set_cached_response(self, url: str, content: bytes) -> None:
        if self.cache:
            self.cache.set(url, content)

    def download_snapshot(self, snapshot: Snapshot) -> Optional[Tuple[str, bytes, str]]:
        timestamp = snapshot.timestamp
        original_url = snapshot.original_url
        
        cache_key = f"{original_url}_{timestamp}"
        
        if self.cache:
            cached_content = self._get_cached_response(cache_key)
            if cached_content:
                return (original_url, cached_content, timestamp)
        
        wayback_url = f"{WAYBACK_URL_PREFIX}{timestamp}id_/{original_url}"
        logger.debug(f"Baixando: {wayback_url}")
        
        try:
            time.sleep(DOWNLOAD_DELAY)
            response = self.session.get(wayback_url)
            
            if response.status_code != 200:
                logger.warning(f"Erro ao baixar {wayback_url}: {response.status_code}")
                return None
            
            content = response.content
            if self.cache:
                self._set_cached_response(cache_key, content)
                
            return (original_url, content, timestamp)
        
        except Exception as e:
            logger.error(f"Erro ao baixar {wayback_url}: {e}")
            return None

    def process_html(self, original_url: str, content: bytes, timestamp: str) -> None:
        """Processa o conteúdo HTML, extrai recursos e salva localmente."""
        safe_filename = self._generate_safe_filename(original_url)
        version_path = f"{timestamp}_{safe_filename}"
        
        # Definir caminho de arquivo
        if safe_filename.endswith(".html") or safe_filename.endswith(".htm"):
            file_path = self.html_dir / f"{version_path}"
        else:
            file_path = self.html_dir / f"{version_path}.html"
        
        # Processar o HTML para extração de recursos
        try:
            soup = BeautifulSoup(content, "html.parser")
            
            # Extrair e processar recursos
            self._process_links(soup, timestamp, "link", "href", ["stylesheet"])
            self._process_links(soup, timestamp, "script", "src")
            self._process_links(soup, timestamp, "img", "src")
            self._process_links(soup, timestamp, "a", "href")
            
            # Salvar conteúdo processado
            with open(file_path, "wb") as f:
                f.write(soup.encode("utf-8"))
            
            # Salvar metadados
            metadata = {
                "original_url": original_url,
                "wayback_timestamp": timestamp,
                "wayback_url": f"{WAYBACK_URL_PREFIX}{timestamp}/{original_url}",
                "saved_path": str(file_path),
                "extracted_date": datetime.now().isoformat(),
                "version_path": version_path
            }
            
            with open(self.metadata_dir / f"{version_path}.json", "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"Erro ao processar HTML {original_url}: {e}")

    def _process_links(self, 
                       soup: BeautifulSoup, 
                       timestamp: str, 
                       tag_name: str, 
                       attr_name: str, 
                       rel_values: Optional[List[str]] = None) -> None:
        """Processa links no HTML e adiciona à fila de download."""
        for tag in soup.find_all(tag_name):
            if attr_name not in tag.attrs:
                continue
                
            url = tag[attr_name]
            
            # Para tags <link>, verificar o atributo rel se necessário
            if tag_name == "link" and rel_values:
                if "rel" not in tag.attrs or not any(rel in tag["rel"] for rel in rel_values):
                    continue
            
            # Processar apenas URLs absolutas ou relativas para o mesmo domínio
            if url.startswith(("http://", "https://")):
                parsed_url = urllib.parse.urlparse(url)
                if self.domain not in parsed_url.netloc:
                    continue
            
            # Adicionar à fila de recursos para download
            if url not in self.processed_urls:
                resource_type = self._determine_resource_type(url, tag_name)
                self.resource_queue.append((url, timestamp, resource_type))
                
                # Atualizar o atributo para apontar para o local salvo
                tag[attr_name] = self._get_local_resource_path(url, resource_type, timestamp)
    
    def _determine_resource_type(self, url: str, tag_name: str) -> str:
        """Determina o tipo de recurso com base na URL e tag."""
        url_lower = url.lower()
        
        if tag_name == "link" or url_lower.endswith((".css", ".scss", ".less")):
            return "css"
        elif tag_name == "script" or url_lower.endswith((".js", ".jsx", ".ts", ".tsx")):
            return "js"
        elif tag_name == "img" or url_lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp", ".ico")):
            return "images"
        else:
            return "other"
    
    def _get_local_resource_path(self, url: str, resource_type: str, timestamp: str) -> str:
        """Obtém o caminho local onde o recurso será salvo."""
        safe_filename = self._generate_safe_filename(url)
        return f"../resources/{resource_type}/{timestamp}_{safe_filename}"
    
    def download_resources(self) -> None:
        """Baixa todos os recursos na fila."""
        logger.info(f"Iniciando download de {len(self.resource_queue)} recursos...")
        
        def download_resource(resource_data: Tuple[str, str, str]) -> None:
            url, timestamp, resource_type = resource_data
            if url in self.processed_urls:
                return
            
            self.processed_urls.add(url)
            
            try:
                # Construir URL completa do Wayback Machine
                if url.startswith(("http://", "https://")):
                    wayback_url = f"{WAYBACK_URL_PREFIX}{timestamp}id_/{url}"
                else:
                    # URL relativa, construir URL completa
                    base_url = f"http://{self.domain}"
                    full_url = urllib.parse.urljoin(base_url, url)
                    wayback_url = f"{WAYBACK_URL_PREFIX}{timestamp}id_/{full_url}"
                
                time.sleep(DOWNLOAD_DELAY)
                response = self.session.get(wayback_url)
                
                if response.status_code != 200:
                    logger.warning(f"Erro ao baixar recurso {wayback_url}: {response.status_code}")
                    return
                
                # Salvar o recurso
                safe_filename = self._generate_safe_filename(url)
                resource_dir = self.resources_dir / resource_type
                file_path = resource_dir / f"{timestamp}_{safe_filename}"
                
                with open(file_path, "wb") as f:
                    f.write(response.content)
                
            except Exception as e:
                logger.error(f"Erro ao baixar recurso {url}: {e}")
        
        # Usar ThreadPoolExecutor para paralelizar downloads
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.threads) as executor:
            list(tqdm(
                executor.map(download_resource, self.resource_queue),
                total=len(self.resource_queue),
                desc="Baixando recursos"
            ))
        
        logger.info(f"Download de recursos concluído.")
    
    def _organize_versions_by_url(self) -> Dict[str, List[Dict[str, Any]]]:
        versions = {}
        metadata_files = list(self.metadata_dir.glob("*.json"))
        
        for metadata_file in metadata_files:
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                
                original_url = metadata.get("original_url", "")
                if original_url not in versions:
                    versions[original_url] = []
                
                html_path = metadata.get("saved_path", "")
                html_path = html_path.replace(str(self.output_dir) + os.sep, "")
                
                timestamp = metadata.get("wayback_timestamp", "")
                if len(timestamp) >= 8:
                    date_obj = datetime.strptime(timestamp[:8], "%Y%m%d")
                    formatted_date = date_obj.strftime("%d/%m/%Y")
                    if len(timestamp) > 8:
                        time_str = f"{timestamp[8:10]}:{timestamp[10:12]}:{timestamp[12:14]}"
                        formatted_date += f" {time_str}"
                else:
                    formatted_date = "N/A"
                
                versions[original_url].append({
                    "html_path": html_path,
                    "timestamp": timestamp,
                    "formatted_date": formatted_date,
                    "wayback_url": metadata.get("wayback_url", ""),
                    "version_path": metadata.get("version_path", "")
                })
            except Exception as e:
                logger.error(f"Erro ao processar metadata {metadata_file}: {e}")
        
        for url in versions:
            versions[url].sort(key=lambda x: x["timestamp"], reverse=True)
        
        return versions
    
    def create_index(self) -> None:
        """Cria um arquivo de índice com todas as páginas recuperadas."""
        logger.info("Criando arquivo de índice moderno...")
        
        try:
            versions_by_url = self._organize_versions_by_url()
            
            index_html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Arquivo RageZone Brasil</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        .version-list {{
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease-in-out;
        }}
        .version-list.show {{
            max-height: 500px;
        }}
        .dark-mode {{
            background-color: #1a202c;
            color: #e2e8f0;
        }}
        .dark-mode .bg-white {{
            background-color: #2d3748 !important;
        }}
        .dark-mode .text-gray-600 {{
            color: #cbd5e0 !important;
        }}
        .dark-mode .border-gray-200 {{
            border-color: #4a5568 !important;
        }}
        .dark-mode .bg-gray-100 {{
            background-color: #4a5568 !important;
        }}
        .dark-mode .hover\:bg-gray-100:hover {{
            background-color: #4a5568 !important;
        }}
        .dark-mode .text-gray-700 {{
            color: #e2e8f0 !important;
        }}
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <div class="container mx-auto px-4 py-8">
        <header class="mb-8">
            <div class="flex justify-between items-center">
                <h1 class="text-4xl font-bold text-blue-800 text-center mb-2">Arquivo RageZone Brasil</h1>
                <button id="darkModeToggle" class="bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg p-2">
                    <i class="fas fa-moon"></i>
                </button>
            </div>
            <p class="text-center text-gray-600">Acervo histórico de páginas recuperadas do fórum RageZone Brasil</p>
            <div class="text-center mt-4 text-sm text-gray-500">
                <p id="statsInfo">Total de URLs: <span class="font-semibold">{len(versions_by_url)}</span> | 
                Total de versões: <span class="font-semibold">{sum(len(v) for v in versions_by_url.values())}</span></p>
            </div>
        </header>
        
        <div class="bg-white rounded-lg shadow-md p-6 mb-8">
            <div class="flex flex-col md:flex-row justify-between items-center mb-6">
                <div class="w-full md:w-1/2 mb-4 md:mb-0">
                    <div class="relative">
                        <span class="absolute inset-y-0 left-0 flex items-center pl-3">
                            <i class="fas fa-search text-gray-400"></i>
                        </span>
                        <input type="text" id="search" 
                            class="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                            placeholder="Buscar por URL ou título...">
                    </div>
                </div>
                <div class="flex space-x-2">
                    <div class="relative">
                        <select id="filterType" class="bg-white border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500">
                            <option value="all">Todos os tipos</option>
                            <option value="topics">Tópicos</option>
                            <option value="forums">Fóruns</option>
                            <option value="profiles">Perfis</option>
                            <option value="other">Outros</option>
                        </select>
                    </div>
                    <button id="toggleAllVersions" class="bg-blue-500 hover:bg-blue-600 text-white rounded-lg px-4 py-2 transition duration-200">
                        <i class="fas fa-history mr-1"></i> Mostrar versões
                    </button>
                </div>
            </div>
            
            <div class="overflow-x-auto">
                <table id="pagesTable" class="min-w-full bg-white">
                    <thead>
                        <tr class="bg-gray-100 text-gray-600 uppercase text-sm leading-normal">
                            <th class="py-3 px-6 text-left cursor-pointer" onclick="sortTable(0)">
                                URL <i class="fas fa-sort text-gray-400 ml-1"></i>
                            </th>
                            <th class="py-3 px-6 text-left cursor-pointer" onclick="sortTable(1)">
                                Última Captura <i class="fas fa-sort text-gray-400 ml-1"></i>
                            </th>
                            <th class="py-3 px-6 text-left">Versões</th>
                            <th class="py-3 px-6 text-center">Ações</th>
                        </tr>
                    </thead>
                    <tbody class="text-gray-600 text-sm">
"""
            
            for url, versions in versions_by_url.items():
                if not versions:
                    continue
                    
                latest = versions[0]
                url_type = self._determine_url_type(url)
                url_display = self._format_url_display(url)
                
                index_html += f"""
                        <tr class="border-b border-gray-200 hover:bg-gray-100 transition duration-150" data-type="{url_type}">
                            <td class="py-3 px-6 text-left">
                                <div class="font-medium">{url_display}</div>
                            </td>
                            <td class="py-3 px-6 text-left">{latest['formatted_date']}</td>
                            <td class="py-3 px-6 text-left">
                                <button class="toggle-versions bg-gray-200 hover:bg-gray-300 text-gray-700 text-xs py-1 px-2 rounded">
                                    <i class="fas fa-clock mr-1"></i> {len(versions)} versões
                                </button>
                                <div class="version-list mt-2 pl-2 border-l-2 border-gray-300">
"""
                
                for version in versions:
                    index_html += f"""
                                    <div class="py-1">
                                        <span class="text-gray-500">{version['formatted_date']}</span> - 
                                        <a href="{version['html_path']}" class="text-blue-500 hover:underline">Ver local</a> | 
                                        <a href="{version['wayback_url']}" class="text-green-500 hover:underline" target="_blank">
                                            <i class="fas fa-archive text-xs"></i> Wayback
                                        </a>
                                    </div>
"""
                
                index_html += f"""
                                </div>
                            </td>
                            <td class="py-3 px-6 text-center">
                                <div class="flex justify-center items-center space-x-2">
                                    <a href="{latest['html_path']}" class="bg-blue-500 hover:bg-blue-600 text-white py-1 px-3 rounded-lg text-xs transition duration-200">
                                        <i class="fas fa-eye mr-1"></i> Ver
                                    </a>
                                    <a href="{latest['wayback_url']}" target="_blank" class="bg-green-500 hover:bg-green-600 text-white py-1 px-3 rounded-lg text-xs transition duration-200">
                                        <i class="fas fa-archive mr-1"></i> Wayback
                                    </a>
                                </div>
                            </td>
                        </tr>
"""
            
            index_html += """
                    </tbody>
                </table>
            </div>
        </div>
        
        <footer class="text-center text-gray-500 text-sm py-4">
            <p>Gerado com RageZone Extractor v2.0</p>
        </footer>
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const toggleButtons = document.querySelectorAll('.toggle-versions');
            const toggleAllButton = document.getElementById('toggleAllVersions');
            const search = document.getElementById('search');
            const filterType = document.getElementById('filterType');
            const darkModeToggle = document.getElementById('darkModeToggle');
            let allVersionsVisible = false;
            
            toggleButtons.forEach(button => {
                button.addEventListener('click', function(e) {
                    e.preventDefault();
                    const versionList = this.nextElementSibling;
                    versionList.classList.toggle('show');
                    e.stopPropagation();
                });
            });
            
            toggleAllButton.addEventListener('click', function() {
                allVersionsVisible = !allVersionsVisible;
                document.querySelectorAll('.version-list').forEach(list => {
                    if (allVersionsVisible) {
                        list.classList.add('show');
                        this.innerHTML = '<i class="fas fa-history mr-1"></i> Ocultar versões';
                    } else {
                        list.classList.remove('show');
                        this.innerHTML = '<i class="fas fa-history mr-1"></i> Mostrar versões';
                    }
                });
            });
            
            darkModeToggle.addEventListener('click', function() {
                document.body.classList.toggle('dark-mode');
                const icon = this.querySelector('i');
                if (document.body.classList.contains('dark-mode')) {
                    icon.classList.remove('fa-moon');
                    icon.classList.add('fa-sun');
                } else {
                    icon.classList.remove('fa-sun');
                    icon.classList.add('fa-moon');
                }
            });
            
            search.addEventListener('keyup', filterTable);
            filterType.addEventListener('change', filterTable);
            
            function filterTable() {
                const searchValue = search.value.toLowerCase();
                const typeFilter = filterType.value;
                const rows = document.querySelectorAll('#pagesTable tbody tr');
                let visibleCount = 0;
                
                rows.forEach(row => {
                    const url = row.querySelector('td:first-child').textContent.toLowerCase();
                    const type = row.dataset.type;
                    
                    const matchesSearch = url.includes(searchValue);
                    const matchesType = typeFilter === 'all' || type === typeFilter;
                    
                    if (matchesSearch && matchesType) {
                        row.style.display = '';
                        visibleCount++;
                    } else {
                        row.style.display = 'none';
                    }
                });
                
                document.getElementById('statsInfo').innerHTML = 
                    `Exibindo: <span class="font-semibold">${visibleCount}</span> de <span class="font-semibold">${rows.length}</span> URLs`;
            }
        });
        
        function sortTable(n) {
            let table, rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
            table = document.getElementById("pagesTable");
            switching = true;
            dir = "asc";
            
            while (switching) {
                switching = false;
                rows = table.rows;
                
                for (i = 1; i < (rows.length - 1); i++) {
                    shouldSwitch = false;
                    x = rows[i].getElementsByTagName("TD")[n];
                    y = rows[i + 1].getElementsByTagName("TD")[n];
                    
                    if (dir == "asc") {
                        if (x.innerHTML.toLowerCase() > y.innerHTML.toLowerCase()) {
                            shouldSwitch = true;
                            break;
                        }
                    } else if (dir == "desc") {
                        if (x.innerHTML.toLowerCase() < y.innerHTML.toLowerCase()) {
                            shouldSwitch = true;
                            break;
                        }
                    }
                }
                
                if (shouldSwitch) {
                    rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
                    switching = true;
                    switchcount++;
                } else {
                    if (switchcount == 0 && dir == "asc") {
                        dir = "desc";
                        switching = true;
                    }
                }
            }
            
            const headers = table.querySelectorAll("th");
            headers.forEach((header, index) => {
                const icon = header.querySelector("i");
                if (index === n) {
                    icon.className = dir === "asc" ? "fas fa-sort-up text-blue-500" : "fas fa-sort-down text-blue-500";
                } else {
                    if (icon) icon.className = "fas fa-sort text-gray-400 ml-1";
                }
            });
        }
    </script>
</body>
</html>
"""
            
            with open(self.output_dir / "index.html", "w", encoding="utf-8") as f:
                f.write(index_html)
            
            logger.info(f"Índice moderno criado com {len(versions_by_url)} URLs diferentes.")
        
        except Exception as e:
            logger.error(f"Erro ao criar índice: {e}")
    
    def _determine_url_type(self, url: str) -> str:
        url_lower = url.lower()
        
        if re.search(r'(topic|thread|post|showthread|showpost)', url_lower):
            return "topics"
        elif re.search(r'(forum|board|forumdisplay)', url_lower):
            return "forums"
        elif re.search(r'(profile|member|user)', url_lower):
            return "profiles"
        else:
            return "other"
    
    def _format_url_display(self, url: str) -> str:
        if len(url) > 70:
            return f"{url[:35]}...{url[-30:]}"
        return url
    
    def run(self) -> None:
        """Executa todo o processo de extração e reconstrução."""
        logger.info("Iniciando extração do RageZone Brasil")
        
        # 1. Buscar snapshots
        snapshots = self.fetch_snapshots()
        if not snapshots:
            logger.error("Não foi possível encontrar snapshots. Abortando.")
            return
        
        # 2. Baixar e processar snapshots HTML
        logger.info(f"Baixando {len(snapshots)} snapshots...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.threads) as executor:
            future_to_snapshot = {executor.submit(self.download_snapshot, snapshot): snapshot for snapshot in snapshots}
            
            completed = 0
            with tqdm(total=len(snapshots), desc="Baixando snapshots") as pbar:
                for future in concurrent.futures.as_completed(future_to_snapshot):
                    completed += 1
                    pbar.update(1)
                    result = future.result()
                    
                    if result:
                        original_url, content, timestamp = result
                        self.process_html(original_url, content, timestamp)
        
        # 3. Baixar recursos
        self.download_resources()
        
        # 4. Criar índice
        self.create_index()
        
        if self.cache:
            self.cache.close()
            
        logger.info(f"Extração concluída! Arquivos salvos em: {self.output_dir.absolute()}")


def main() -> None:
    """Função principal para execução direta do script."""
    parser = argparse.ArgumentParser(description="Extrator avançado e reconstrutor do fórum RageZone Brasil")
    
    parser.add_argument("--output", "-o", type=str, default="ragezone_archive",
                        help="Diretório de saída para salvar o conteúdo extraído")
    parser.add_argument("--domain", "-d", type=str, default=DEFAULT_DOMAIN,
                        help="Domínio a ser extraído (padrão: ragezonebrasil.com.br)")
    parser.add_argument("--start-date", type=str, 
                        help="Data inicial para snapshots (YYYYMMDD, YYYY-MM-DD, DD/MM/YYYY, ou 'today', 'yesterday', 'last_week', etc)")
    parser.add_argument("--end-date", type=str, 
                        help="Data final para snapshots (mesmo formato que start-date)")
    parser.add_argument("--max-pages", type=int, 
                        help="Número máximo de páginas a extrair")
    parser.add_argument("--threads", "-t", type=int, default=MAX_WORKERS,
                        help=f"Número de threads para download (padrão: {MAX_WORKERS})")
    parser.add_argument("--single-version", action="store_true",
                        help="Extrair apenas a versão mais recente de cada URL")
    parser.add_argument("--no-cache", action="store_true",
                        help="Desativar cache para economizar espaço em disco")
    
    args = parser.parse_args()
    
    extractor = RageZoneExtractor(
        output_dir=args.output,
        domain=args.domain,
        start_date=args.start_date,
        end_date=args.end_date,
        max_pages=args.max_pages,
        threads=args.threads,
        all_versions=not args.single_version,
        cache_enabled=not args.no_cache
    )
    
    extractor.run()


if __name__ == "__main__":
    main()

