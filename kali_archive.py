#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import time
import json
import logging
import argparse
import urllib.parse
import asyncio
import aiohttp
import concurrent.futures
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Union, Any, Generator, Callable
from dataclasses import dataclass, field
from functools import lru_cache, wraps
from contextlib import asynccontextmanager, contextmanager
from collections import defaultdict

import requests
from bs4 import BeautifulSoup
from tqdm.asyncio import tqdm as async_tqdm
from tqdm import tqdm
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import diskcache
import hashlib
import psutil
import aiofiles
import signal
import sys
import weakref
import traceback
import uuid

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("kali_archive.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("kali_archive")

DEFAULT_DOMAIN = "ragezone.com.br"
WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"
WAYBACK_URL_PREFIX = "https://web.archive.org/web/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
MAX_RETRIES = 5
RETRY_BACKOFF = 0.5
MAX_WORKERS = 12
DOWNLOAD_DELAY = 0.5
CACHE_DIR = ".kali_cache"
MAX_SNAPSHOTS_PER_PAGE = 500
MEMORY_LIMIT_PERCENT = 85
CONN_LIMIT = 50
REQUEST_TIMEOUT = 30
FIXED_FALLBACK_DATE = "20000101"
DYNAMIC_FALLBACK_YEARS = 5

@dataclass
class Snapshot:
    timestamp: str
    original_url: str
    statuscode: str
    mimetype: str
    digest: Optional[str] = None
    content: Optional[bytes] = None
    processed: bool = False
    
    def __hash__(self):
        return hash((self.timestamp, self.original_url))
    
    def __eq__(self, other):
        if not isinstance(other, Snapshot):
            return False
        return (self.timestamp, self.original_url) == (other.timestamp, other.original_url)

@dataclass
class ResourceInfo:
    url: str
    type: str
    tag: str
    attr: str
    timestamp: str
    local_path: Optional[str] = None
    downloaded: bool = False
    
    def __hash__(self):
        return hash((self.url, self.timestamp))
    
    def __eq__(self, other):
        if not isinstance(other, ResourceInfo):
            return False
        return (self.url, self.timestamp) == (other.url, other.timestamp)

@dataclass
class MemoryStats:
    peak_usage: float = 0.0
    current_usage: float = 0.0
    total_memory: float = 0.0
    snapshots_processed: int = 0
    resources_processed: int = 0
    
    def update(self) -> None:
        memory = psutil.virtual_memory()
        self.current_usage = memory.percent
        self.total_memory = memory.total / (1024 * 1024 * 1024)  # GB
        self.peak_usage = max(self.peak_usage, self.current_usage)
        
    def __str__(self) -> str:
        return (f"Memória: {self.current_usage:.1f}% (pico: {self.peak_usage:.1f}%), "
                f"Total: {self.total_memory:.1f}GB, "
                f"Snapshots: {self.snapshots_processed}, "
                f"Recursos: {self.resources_processed}")

def memory_safe(threshold: float = MEMORY_LIMIT_PERCENT):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            memory = psutil.virtual_memory()
            if memory.percent >= threshold:
                logger.warning(f"Alto uso de memória detectado: {memory.percent}%. Pausando operação...")
                
                # Força coleta de lixo
                import gc
                gc.collect()
                
                # Aguarda até que a memória esteja abaixo do limite
                while psutil.virtual_memory().percent >= threshold - 5:
                    await asyncio.sleep(1)
                    gc.collect()
                
                logger.info(f"Uso de memória normalizado: {psutil.virtual_memory().percent}%. Retomando operação.")
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

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

@asynccontextmanager
async def create_async_session() -> aiohttp.ClientSession:
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    connector = aiohttp.TCPConnector(limit=CONN_LIMIT, limit_per_host=10, ttl_dns_cache=300)
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT}
    ) as session:
        yield session

@contextmanager
def timing(operation: str):
    start_time = time.time()
    try:
        yield
    finally:
        elapsed = time.time() - start_time
        logger.info(f"{operation} completado em {elapsed:.2f}s")

def is_memory_ok() -> bool:
    memory = psutil.virtual_memory()
    return memory.percent < MEMORY_LIMIT_PERCENT

def is_disk_space_ok(path: str, required_gb: float = 5.0) -> bool:
    try:
        disk_usage = psutil.disk_usage(path)
        available_gb = disk_usage.free / (1024 * 1024 * 1024)
        return available_gb >= required_gb
    except Exception as e:
        logger.warning(f"Não foi possível verificar o espaço em disco: {e}")
        return True

def setup_signal_handlers(cleanup_func: Callable):
    def signal_handler(sig, frame):
        logger.info("Interrupção detectada. Encerrando graciosamente...")
        cleanup_func()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

class DomainDateDetector:
    def __init__(self, domain: str, session: Optional[requests.Session] = None):
        self.domain = domain
        self.session = session or create_session()
    
    async def detect_earliest_date(self) -> Optional[str]:
        try:
            params = {
                "url": f"{self.domain}/*",
                "output": "json",
                "fl": "timestamp",
                "limit": 1,
                "sort": "timestamp:asc"
            }
            
            async with create_async_session() as session:
                async with session.get(WAYBACK_CDX_URL, params=params) as response:
                    if response.status != 200:
                        logger.warning(f"Falha ao detectar data inicial: status {response.status}")
                        return None
                    
                    data = await response.json()
                    if not data or len(data) <= 1:
                        logger.warning("Nenhum snapshot encontrado para o domínio")
                        return None
                    
                    # Formato dos dados: [["timestamp"], ["20010203123456"], ...]
                    timestamp = data[1][0]
                    if timestamp and len(timestamp) >= 8:
                        logger.info(f"Data inicial do domínio detectada: {timestamp[:8]}")
                        return timestamp[:8]
                    
                    return None
        except Exception as e:
            logger.error(f"Erro ao detectar data inicial: {e}")
            return None
    
    def get_dynamic_fallback_date(self) -> str:
        today = datetime.now()
        past_date = today - timedelta(days=365 * DYNAMIC_FALLBACK_YEARS)
        return past_date.strftime("%Y%m%d")
    
    async def get_start_date(self, 
                           user_date: Optional[str] = None, 
                           auto_detect: bool = True) -> str:
        if user_date:
            return user_date
        
        if auto_detect:
            detected_date = await self.detect_earliest_date()
            if detected_date:
                return detected_date
            
            logger.warning("Detecção automática falhou, usando fallback dinâmico")
        
        dynamic_fallback = self.get_dynamic_fallback_date()
        logger.info(f"Usando data dinâmica de fallback: {dynamic_fallback}")
        
        return dynamic_fallback

class ResourceManager:
    def __init__(self, 
                output_dir: Path,
                domain: str,
                cache: Optional[diskcache.Cache] = None,
                max_workers: int = MAX_WORKERS):
        self.output_dir = output_dir
        self.domain = domain
        self.cache = cache
        self.max_workers = max_workers
        
        self.resources_dir = output_dir / "resources"
        self.processed_urls: Set[str] = set()
        self.resource_queue: Set[ResourceInfo] = set()
        
        # Criar diretórios de recursos
        for resource_type in ["css", "js", "images", "fonts", "other"]:
            (self.resources_dir / resource_type).mkdir(parents=True, exist_ok=True)
    
    def add_resource(self, resource: ResourceInfo) -> None:
        self.resource_queue.add(resource)
    
    def clear_processed_urls(self) -> None:
        self.processed_urls.clear()
    
    def is_url_processed(self, url: str) -> bool:
        return url in self.processed_urls
    
    def mark_url_processed(self, url: str) -> None:
        self.processed_urls.add(url)
    
    @staticmethod
    def determine_resource_type(url: str, tag_name: str) -> str:
        url_lower = url.lower()
        
        if tag_name == "link" or url_lower.endswith((".css", ".scss", ".less")):
            return "css"
        elif tag_name == "script" or url_lower.endswith((".js", ".jsx", ".ts", ".tsx")):
            return "js"
        elif tag_name == "img" or url_lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp", ".ico")):
            return "images"
        elif url_lower.endswith((".woff", ".woff2", ".ttf", ".otf", ".eot")):
            return "fonts"
        else:
            return "other"
    
    @staticmethod
    def generate_safe_filename(url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.strip("/")
        if not path:
            path = "index"
        
        safe_filename = re.sub(r'[\\/*?:"<>|]', "_", path)
        safe_filename = safe_filename.replace('%', '_percent_')
        
        if len(safe_filename) > 120:
            name_part, ext_part = os.path.splitext(safe_filename)
            safe_filename = name_part[:115] + ext_part if ext_part else name_part[:120]
        
        if parsed.query:
            query_hash = hashlib.md5(parsed.query.encode()).hexdigest()[:10]
            safe_filename = f"{safe_filename}_{query_hash}"
        
        return safe_filename
    
    def get_local_resource_path(self, resource: ResourceInfo) -> str:
        safe_filename = self.generate_safe_filename(resource.url)
        return f"../resources/{resource.type}/{resource.timestamp}_{safe_filename}"
    
    @lru_cache(maxsize=1024)
    def _get_cached_response(self, url: str) -> Optional[bytes]:
        if not self.cache:
            return None
        return self.cache.get(url)

    def _set_cached_response(self, url: str, content: bytes) -> None:
        if self.cache:
            self.cache.set(url, content)
    
    @memory_safe()
    async def download_resource(self, resource: ResourceInfo) -> bool:
        if resource.url in self.processed_urls:
            return True
        
        self.processed_urls.add(resource.url)
        
        try:
            if resource.url.startswith(("http://", "https://")):
                wayback_url = f"{WAYBACK_URL_PREFIX}{resource.timestamp}id_/{resource.url}"
            else:
                base_url = f"http://{self.domain}"
                full_url = urllib.parse.urljoin(base_url, resource.url)
                wayback_url = f"{WAYBACK_URL_PREFIX}{resource.timestamp}id_/{full_url}"
            
            cache_key = f"resource_{resource.url}_{resource.timestamp}"
            
            if self.cache:
                cached_content = self._get_cached_response(cache_key)
                if cached_content:
                    safe_filename = self.generate_safe_filename(resource.url)
                    file_path = self.resources_dir / resource.type / f"{resource.timestamp}_{safe_filename}"
                    
                    async with aiofiles.open(file_path, "wb") as f:
                        await f.write(cached_content)
                    return True
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    async with create_async_session() as session:
                        async with session.get(wayback_url, timeout=REQUEST_TIMEOUT) as response:
                            if response.status != 200:
                                if response.status in (429, 503, 504):
                                    wait_time = DOWNLOAD_DELAY * (2 ** attempt)
                                    await asyncio.sleep(wait_time)
                                    continue
                                return False
                            
                            content = await response.read()
                            
                            if self.cache:
                                self._set_cached_response(cache_key, content)
                            
                            safe_filename = self.generate_safe_filename(resource.url)
                            file_path = self.resources_dir / resource.type / f"{resource.timestamp}_{safe_filename}"
                            
                            async with aiofiles.open(file_path, "wb") as f:
                                await f.write(content)
                            
                            resource.local_path = str(file_path)
                            resource.downloaded = True
                            
                            await asyncio.sleep(DOWNLOAD_DELAY)
                            return True
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    wait_time = DOWNLOAD_DELAY * (2 ** attempt)
                    await asyncio.sleep(wait_time)
            
            return False
        except Exception as e:
            logger.error(f"Erro ao baixar recurso {resource.url}: {str(e)}")
            return False
    
    @memory_safe()
    async def download_all_resources(self, stats: MemoryStats) -> None:
        if not self.resource_queue:
            logger.info("Nenhum recurso para baixar")
            return
        
        logger.info(f"Iniciando download de {len(self.resource_queue)} recursos...")
        
        semaphore = asyncio.Semaphore(self.max_workers)
        
        async def download_with_semaphore(resource):
            async with semaphore:
                result = await self.download_resource(resource)
                if result:
                    stats.resources_processed += 1
                    if stats.resources_processed % 100 == 0:
                        stats.update()
                        logger.info(f"Progresso: {stats.resources_processed}/{len(self.resource_queue)} recursos | {stats}")
                return result
        
        tasks = [download_with_semaphore(resource) for resource in self.resource_queue]
        
        with timing("Download de recursos"):
            results = await async_tqdm.gather(*tasks, desc="Baixando recursos", total=len(self.resource_queue))
        
        success_count = sum(1 for r in results if r)
        logger.info(f"Download de recursos concluído: {success_count}/{len(self.resource_queue)} ({success_count/len(self.resource_queue)*100:.1f}%)")
        
        self.resource_queue.clear()

class SnapshotFetcher:
    def __init__(self, 
                domain: str,
                start_date: Optional[str] = None,
                end_date: Optional[str] = None,
                max_snapshots: Optional[int] = None,
                all_versions: bool = True,
                memory_safe: bool = True):
        self.domain = domain
        self.start_date = start_date
        self.end_date = end_date
        self.max_snapshots = max_snapshots
        self.all_versions = all_versions
        self.memory_safe = memory_safe
    
    @staticmethod
    def _split_date_range(start_date: str, end_date: str) -> List[Tuple[str, str]]:
        try:
            start = datetime.strptime(start_date, "%Y%m%d")
            end = datetime.strptime(end_date, "%Y%m%d")
            
            if (end - start).days <= 90:
                return [(start_date, end_date)]
            
            date_ranges = []
            current = start
            
            while current < end:
                range_end = min(current + timedelta(days=90), end)
                date_ranges.append((
                    current.strftime("%Y%m%d"),
                    range_end.strftime("%Y%m%d")
                ))
                current = range_end + timedelta(days=1)
            
            return date_ranges
        except Exception as e:
            logger.error(f"Erro ao dividir intervalo de datas: {e}")
            return [(start_date, end_date)]
    
    @staticmethod
    def _deduplicate_snapshots(snapshots: List[Snapshot]) -> List[Snapshot]:
        seen = set()
        unique = []
        
        for snapshot in snapshots:
            key = f"{snapshot.original_url}_{snapshot.timestamp}"
            if key not in seen:
                seen.add(key)
                unique.append(snapshot)
        
        return unique
    
    async def _fetch_snapshot_batch(self, 
                                 collapse: Optional[str] = None, 
                                 from_date: Optional[str] = None, 
                                 to_date: Optional[str] = None) -> List[Snapshot]:
        params = {
            "url": self.domain + "/*",
            "output": "json",
            "fl": "timestamp,original,statuscode,mimetype,digest",
            "filter": "statuscode:200",
            "limit": MAX_SNAPSHOTS_PER_PAGE,
        }
        
        if collapse:
            params["collapse"] = collapse
        
        if from_date or self.start_date:
            params["from"] = from_date or self.start_date
        if to_date or self.end_date:
            params["to"] = to_date or self.end_date
        
        try:
            async with create_async_session() as session:
                async with session.get(WAYBACK_CDX_URL, params=params) as response:
                    if response.status != 200:
                        logger.error(f"Erro ao buscar snapshots: {response.status}")
                        return []
                    
                    data = await response.json()
                    if not data or len(data) <= 1:
                        return []
                    
                    headers = data[0]
                    timestamp_idx = headers.index("timestamp")
                    original_idx = headers.index("original")
                    statuscode_idx = headers.index("statuscode")
                    mimetype_idx = headers.index("mimetype")
                    digest_idx = headers.index("digest") if "digest" in headers else -1
                    
                    snapshots = []
                    for row in data[1:]:
                        if "text/html" in row[mimetype_idx]:
                            digest = row[digest_idx] if digest_idx >= 0 else None
                            snapshots.append(Snapshot(
                                timestamp=row[timestamp_idx],
                                original_url=row[original_idx],
                                statuscode=row[statuscode_idx],
                                mimetype=row[mimetype_idx],
                                digest=digest
                            ))
                    
                    return snapshots
        except Exception as e:
            logger.error(f"Erro ao buscar snapshots: {e}")
            return []
    
    async def fetch_all_snapshots(self) -> List[Snapshot]:
        logger.info(f"Buscando snapshots para o domínio: {self.domain}")
        
        all_snapshots = []
        
        if not self.all_versions:
            return await self._fetch_snapshot_batch(collapse="urlkey")
        
        from_date = self.start_date if self.start_date else "19960101"
        to_date = self.end_date if self.end_date else datetime.now().strftime("%Y%m%d")
        
        date_ranges = self._split_date_range(from_date, to_date)
        logger.info(f"Dividindo busca em {len(date_ranges)} períodos para captura completa")
        
        for start, end in date_ranges:
            logger.info(f"Buscando snapshots no período: {start} a {end}")
            batch = await self._fetch_snapshot_batch(from_date=start, to_date=end)
            logger.info(f"Encontrados {len(batch)} snapshots no período {start} a {end}")
            all_snapshots.extend(batch)
            
            if self.max_snapshots and len(all_snapshots) >= self.max_snapshots:
                logger.info(f"Limite de snapshots atingido ({self.max_snapshots})")
                break
            
            if self.memory_safe and not is_memory_ok():
                logger.warning("Alto uso de memória detectado. Forçando coleta de lixo...")
                import gc
                gc.collect()
        
        unique_snapshots = self._deduplicate_snapshots(all_snapshots)
        logger.info(f"Total de snapshots únicos: {len(unique_snapshots)}")
        return unique_snapshots
    
    @memory_safe()
    async def download_snapshot(self, snapshot: Snapshot, cache: Optional[diskcache.Cache] = None) -> bool:
        timestamp = snapshot.timestamp
        original_url = snapshot.original_url
        
        cache_key = f"{original_url}_{timestamp}"
        
        if cache:
            cached_content = cache.get(cache_key)
            if cached_content:
                snapshot.content = cached_content
                return True
        
        wayback_url = f"{WAYBACK_URL_PREFIX}{timestamp}id_/{original_url}"
        
        try:
            # Implementar backoff exponencial
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    async with create_async_session() as session:
                        async with session.get(wayback_url, timeout=REQUEST_TIMEOUT) as response:
                            if response.status != 200:
                                logger.warning(f"Erro ao baixar {wayback_url}: {response.status}")
                                if response.status in (429, 503, 504):
                                    wait_time = DOWNLOAD_DELAY * (2 ** attempt)
                                    logger.info(f"Aguardando {wait_time}s antes de tentar novamente...")
                                    await asyncio.sleep(wait_time)
                                    continue
                                return False
                            
                            content = await response.read()
                            snapshot.content = content
                            
                            if cache:
                                cache.set(cache_key, content)
                            
                            # Pausa estratégica para evitar sobrecarga do servidor
                            await asyncio.sleep(DOWNLOAD_DELAY)
                            return True
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    wait_time = DOWNLOAD_DELAY * (2 ** attempt)
                    logger.warning(f"Erro de conexão: {e}. Tentando novamente em {wait_time}s...")
                    await asyncio.sleep(wait_time)
            
            logger.error(f"Falhou após {max_retries} tentativas: {wayback_url}")
            return False
        except Exception as e:
            logger.error(f"Erro ao baixar {wayback_url}: {e}")
            return False

class HtmlProcessor:
    def __init__(self, 
                output_dir: Path,
                domain: str,
                resource_manager: ResourceManager):
        self.output_dir = output_dir
        self.domain = domain
        self.resource_manager = resource_manager
        
        self.html_dir = output_dir / "html"
        self.metadata_dir = output_dir / "metadata"
        
        # Garantir que os diretórios existam
        self.html_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
    
    @memory_safe()
    async def process_snapshot(self, snapshot: Snapshot) -> bool:
        if not snapshot.content:
            logger.error(f"Snapshot sem conteúdo: {snapshot.original_url}")
            return False
        
        original_url = snapshot.original_url
        content = snapshot.content
        timestamp = snapshot.timestamp
        
        try:
            # Gerar nome de arquivo seguro
            safe_filename = ResourceManager.generate_safe_filename(original_url)
            version_path = f"{timestamp}_{safe_filename}"
            
            # Definir caminho de arquivo
            if safe_filename.endswith((".html", ".htm")):
                file_path = self.html_dir / f"{version_path}"
            else:
                file_path = self.html_dir / f"{version_path}.html"
            
            # Processar o HTML para extração de recursos
            soup = BeautifulSoup(content, "html.parser")
            
            # Criar base URL para resolução de links relativos
            base_url = original_url
            if base_url.startswith(("http://", "https://")):
                base_parts = urllib.parse.urlparse(base_url)
                base_url = f"{base_parts.scheme}://{base_parts.netloc}"
            else:
                base_url = f"http://{self.domain}"
            
            # Ajustar URLs relativas no HTML
            base_tag = soup.find("base")
            if base_tag and "href" in base_tag.attrs:
                base_href = base_tag["href"]
                if not base_href.startswith(("http://", "https://")):
                    base_tag["href"] = urllib.parse.urljoin(base_url, base_href)
            
            # Extrair e processar recursos
            resources = []
            resources.extend(await self._process_links(soup, timestamp, "link", "href", ["stylesheet"], base_url))
            resources.extend(await self._process_links(soup, timestamp, "script", "src", None, base_url))
            resources.extend(await self._process_links(soup, timestamp, "img", "src", None, base_url))
            resources.extend(await self._process_links(soup, timestamp, "a", "href", None, base_url))
            resources.extend(await self._process_links(soup, timestamp, "source", "srcset", None, base_url))
            resources.extend(await self._process_links(soup, timestamp, "img", "srcset", None, base_url))
            resources.extend(await self._process_links(soup, timestamp, "video", "src", None, base_url))
            resources.extend(await self._process_links(soup, timestamp, "audio", "src", None, base_url))
            
            # Salvar conteúdo processado
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(soup.encode("utf-8"))
            
            # Salvar metadados
            metadata = {
                "original_url": original_url,
                "wayback_timestamp": timestamp,
                "wayback_url": f"{WAYBACK_URL_PREFIX}{timestamp}/{original_url}",
                "saved_path": str(file_path),
                "extracted_date": datetime.now().isoformat(),
                "version_path": version_path,
                "resources": [{"url": r.url, "type": r.type, "tag": r.tag, "attr": r.attr} for r in resources]
            }
            
            # Salvar metadados usando async IO
            async with aiofiles.open(self.metadata_dir / f"{version_path}.json", "w", encoding="utf-8") as f:
                await f.write(json.dumps(metadata, indent=2, ensure_ascii=False))
            
            # Liberar memória
            snapshot.content = None
            snapshot.processed = True
            
            return True
        except Exception as e:
            logger.error(f"Erro ao processar HTML {original_url}: {e}")
            # Listar o traceback para depuração
            traceback.print_exc()
            return False
    
    async def _process_links(self, 
                            soup: BeautifulSoup, 
                            timestamp: str, 
                            tag_name: str, 
                            attr_name: str, 
                            rel_values: Optional[List[str]] = None,
                            base_url: str = "") -> List[ResourceInfo]:
        resources = []
        
        for tag in soup.find_all(tag_name):
            if attr_name not in tag.attrs:
                continue
                
            url = tag[attr_name]
            
            # Para tags <link>, verificar o atributo rel se necessário
            if tag_name == "link" and rel_values:
                if "rel" not in tag.attrs or not any(rel in tag["rel"] for rel in rel_values):
                    continue
            
            # Ignorar URLs em base64 ou data URI
            if url.startswith(("data:", "javascript:", "#", "mailto:")):
                continue
            
            # Normalizar URL
            if not url.startswith(("http://", "https://")):
                url = urllib.parse.urljoin(base_url, url)
            
            # Processar apenas URLs absolutas ou relativas para o mesmo domínio
            parsed_url = urllib.parse.urlparse(url)
            if not parsed_url.netloc or self.domain not in parsed_url.netloc:
                continue
            
            # Adicionar à fila de recursos para download
            if not self.resource_manager.is_url_processed(url):
                resource_type = ResourceManager.determine_resource_type(url, tag_name)
                
                # Criar objeto ResourceInfo
                resource = ResourceInfo(
                    url=url,
                    type=resource_type,
                    tag=tag_name,
                    attr=attr_name,
                    timestamp=timestamp
                )
                
                # Adicionar à lista para download posterior
                self.resource_manager.add_resource(resource)
                resources.append(resource)
                
                # Atualizar o atributo para apontar para o local salvo
                local_path = self.resource_manager.get_local_resource_path(resource)
                tag[attr_name] = local_path
        
        return resources

class IndexBuilder:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.metadata_dir = output_dir / "metadata"
        self.index_template_path = Path(__file__).parent / "index_template.html"
    
    async def _organize_versions_by_url(self) -> Dict[str, List[Dict[str, Any]]]:
        versions = {}
        metadata_files = list(self.metadata_dir.glob("*.json"))
        
        for metadata_file in metadata_files:
            try:
                async with aiofiles.open(metadata_file, "r", encoding="utf-8") as f:
                    content = await f.read()
                    metadata = json.loads(content)
                
                original_url = metadata.get("original_url", "")
                if original_url not in versions:
                    versions[original_url] = []
                
                html_path = metadata.get("saved_path", "")
                html_path = html_path.replace(str(self.output_dir) + os.sep, "")
                
                timestamp = metadata.get("wayback_timestamp", "")
                if timestamp and len(timestamp) >= 8:
                    date_obj = datetime.strptime(timestamp[:8], "%Y%m%d")
                    formatted_date = date_obj.strftime("%d/%m/%Y")
                    if len(timestamp) > 8:
                        time_str = f"{timestamp[8:10]}:{timestamp[10:12]}:{timestamp[12:14] if len(timestamp) >= 14 else '00'}"
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
        
        # Ordenar por timestamp mais recente
        for url in versions:
            versions[url].sort(key=lambda x: x["timestamp"] if x["timestamp"] else "", reverse=True)
        
        return versions
    
    def _collect_stats(self, versions_by_url: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        total_versions = sum(len(versions) for versions in versions_by_url.values())
        
        url_types = {}
        years = {}
        months = {}
        
        for url, versions in versions_by_url.items():
            url_type = self._determine_url_type(url)
            if url_type not in url_types:
                url_types[url_type] = 0
            url_types[url_type] += 1
            
            for version in versions:
                timestamp = version.get("timestamp", "")
                if timestamp and len(timestamp) >= 8:
                    year = timestamp[:4]
                    if year not in years:
                        years[year] = 0
                    years[year] += 1
                    
                    if len(timestamp) >= 6:
                        month_key = f"{year}-{timestamp[4:6]}"
                        if month_key not in months:
                            months[month_key] = 0
                        months[month_key] += 1
        
        sorted_years = dict(sorted(years.items()))
        sorted_months = dict(sorted(months.items()))
        
        return {
            "total_urls": len(versions_by_url),
            "total_versions": total_versions,
            "url_types": url_types,
            "years": sorted_years,
            "months": sorted_months
        }
    
    def _determine_url_type(self, url: str) -> str:
        url_lower = url.lower()
        
        if re.search(r'(topic|thread|post|showthread|showpost)', url_lower):
            return "topics"
        elif re.search(r'(forum|board|forumdisplay)', url_lower):
            return "forums"
        elif re.search(r'(profile|member|user)', url_lower):
            return "profiles"
        elif re.search(r'(index\.php|\/|^https?:\/\/[^\/]+\/?$)', url_lower):
            return "index"
        elif re.search(r'(attachment|download|file)', url_lower):
            return "files"
        else:
            return "other"
    
    def _format_url_display(self, url: str) -> str:
        # Remover protocolo
        display = re.sub(r'^https?:\/\/', '', url)
        
        # Truncar se for muito longo
        if len(display) > 70:
            return f"{display[:35]}...{display[-30:]}"
        
        return display
    
    def _load_template(self) -> str:
        try:
            if self.index_template_path.exists():
                with open(self.index_template_path, "r", encoding="utf-8") as f:
                    return f.read()
            else:
                logger.warning("Arquivo de template não encontrado, usando fallback embutido")
                return self._get_fallback_template()
        except Exception as e:
            logger.error(f"Erro ao carregar template: {e}")
            return self._get_fallback_template()
    
    def _get_fallback_template(self) -> str:
        # Template inline minimalista, porém com todas as funcionalidades
        return """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kali Archive - Arquivo Digital</title>
    <meta name="description" content="Arquivo histórico de páginas recuperadas via Wayback Machine">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        .version-list {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease-in-out;
        }
        .version-list.show {
            max-height: 500px;
        }
        /* Dark mode */
        .dark {
            background-color: #1a202c;
            color: #f7fafc;
        }
        .dark .bg-white {
            background-color: #2d3748 !important;
        }
        .dark .bg-gray-100 {
            background-color: #374151 !important;
        }
        .dark .text-gray-600, .dark .text-gray-700 {
            color: #e2e8f0 !important;
        }
        .dark .border-gray-200 {
            border-color: #4a5568 !important;
        }
        .dark .bg-gray-200 {
            background-color: #4a5568 !important;
        }
        /* Animações */
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        .animate-fade-in {
            animation: fadeIn 0.5s ease-in-out;
        }
        /* Responsividade melhorada */
        @media (max-width: 640px) {
            .responsive-table {
                display: block;
                width: 100%;
                overflow-x: auto;
            }
        }
        /* Melhorias de usabilidade */
        .hover-effect:hover {
            transform: translateY(-2px);
            transition: transform 0.2s ease;
        }
    </style>
</head>
<body class="bg-gray-100 min-h-screen transition-colors duration-200">
    <div class="container mx-auto px-4 py-8">
        <header class="mb-8 animate-fade-in">
            <div class="flex justify-between items-center">
                <h1 class="text-4xl font-bold text-blue-800 dark:text-blue-400 mb-2">Kali Archive</h1>
                <button id="darkModeToggle" class="bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 rounded-lg p-2 transition-colors duration-200">
                    <i class="fas fa-moon"></i>
                </button>
            </div>
            <p class="text-center text-gray-600 dark:text-gray-300">Arquivo histórico de páginas recuperadas via Wayback Machine</p>
            <div class="text-center mt-4 text-sm text-gray-500 dark:text-gray-400">
                <p id="statsInfo">{{STATS_INFO}}</p>
            </div>
        </header>
        
        <div class="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-8 animate-fade-in">
            <div class="flex flex-col md:flex-row justify-between items-center mb-6">
                <div class="w-full md:w-1/2 mb-4 md:mb-0">
                    <div class="relative">
                        <span class="absolute inset-y-0 left-0 flex items-center pl-3">
                            <i class="fas fa-search text-gray-400"></i>
                        </span>
                        <input type="text" id="search" 
                            class="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                            placeholder="Buscar por URL ou título...">
                    </div>
                </div>
                <div class="flex flex-col sm:flex-row space-y-2 sm:space-y-0 sm:space-x-2">
                    <div class="relative">
                        <select id="filterType" class="bg-white dark:bg-gray-700 dark:text-white border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500">
                            <option value="all">Todos os tipos</option>
                            {{TYPE_OPTIONS}}
                        </select>
                    </div>
                    <div class="relative">
                        <select id="filterYear" class="bg-white dark:bg-gray-700 dark:text-white border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500">
                            <option value="all">Todos os anos</option>
                            {{YEAR_OPTIONS}}
                        </select>
                    </div>
                    <button id="toggleAllVersions" class="bg-blue-500 hover:bg-blue-600 dark:bg-blue-600 dark:hover:bg-blue-700 text-white rounded-lg px-4 py-2 transition duration-200 hover-effect">
                        <i class="fas fa-history mr-1"></i> Mostrar versões
                    </button>
                </div>
            </div>
            
            <div class="overflow-x-auto responsive-table">
                <table id="pagesTable" class="min-w-full bg-white dark:bg-gray-800 transition-colors duration-200">
                    <thead>
                        <tr class="bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-200 uppercase text-sm leading-normal">
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
                    <tbody class="text-gray-600 dark:text-gray-300 text-sm">
                        {{TABLE_ROWS}}
                    </tbody>
                </table>
            </div>
        </div>
        
        <footer class="text-center text-gray-500 dark:text-gray-400 text-sm py-4">
            <p>Gerado com Kali Archive</p>
        </footer>
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const toggleButtons = document.querySelectorAll('.toggle-versions');
            const toggleAllButton = document.getElementById('toggleAllVersions');
            const search = document.getElementById('search');
            const filterType = document.getElementById('filterType');
            const filterYear = document.getElementById('filterYear');
            const darkModeToggle = document.getElementById('darkModeToggle');
            let allVersionsVisible = false;
            
            // Verificar preferência do usuário para dark mode
            if (localStorage.getItem('darkMode') === 'true' || 
                window.matchMedia('(prefers-color-scheme: dark)').matches) {
                document.body.classList.add('dark');
                darkModeToggle.innerHTML = '<i class="fas fa-sun"></i>';
            }
            
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
                document.body.classList.toggle('dark');
                const icon = this.querySelector('i');
                if (document.body.classList.contains('dark')) {
                    icon.classList.remove('fa-moon');
                    icon.classList.add('fa-sun');
                    localStorage.setItem('darkMode', 'true');
                } else {
                    icon.classList.remove('fa-sun');
                    icon.classList.add('fa-moon');
                    localStorage.setItem('darkMode', 'false');
                }
            });
            
            search.addEventListener('keyup', filterTable);
            filterType.addEventListener('change', filterTable);
            filterYear.addEventListener('change', filterTable);
            
            function filterTable() {
                const searchValue = search.value.toLowerCase();
                const typeFilter = filterType.value;
                const yearFilter = filterYear.value;
                const rows = document.querySelectorAll('#pagesTable tbody tr');
                let visibleCount = 0;
                
                rows.forEach(row => {
                    const url = row.querySelector('td:first-child').textContent.toLowerCase();
                    const type = row.dataset.type;
                    const year = row.dataset.year;
                    
                    const matchesSearch = url.includes(searchValue);
                    const matchesType = typeFilter === 'all' || type === typeFilter;
                    const matchesYear = yearFilter === 'all' || year === yearFilter;
                    
                    if (matchesSearch && matchesType && matchesYear) {
                        row.style.display = '';
                        visibleCount++;
                    } else {
                        row.style.display = 'none';
                    }
                });
                
                document.getElementById('statsInfo').innerHTML = 
                    `Exibindo: <span class="font-semibold">${visibleCount}</span> de <span class="font-semibold">${rows.length}</span> URLs`;
            }
            
            // Inicializar contadores
            filterTable();
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
</html>"""

    def _generate_index_html(self, versions_by_url: Dict[str, List[Dict[str, Any]]], stats: Dict[str, Any]) -> str:
        template = self._load_template()
        
        # Substituir estatísticas
        stats_info = f"Total de URLs: <span class='font-semibold'>{stats['total_urls']}</span> | Total de versões: <span class='font-semibold'>{stats['total_versions']}</span>"
        template = template.replace("{{STATS_INFO}}", stats_info)
        
        # Gerar opções de tipo
        type_options = ""
        for url_type, count in stats["url_types"].items():
            type_options += f'<option value="{url_type}">{url_type.capitalize()} ({count})</option>\n'
        template = template.replace("{{TYPE_OPTIONS}}", type_options)
        
        # Gerar opções de ano
        year_options = ""
        for year, count in stats["years"].items():
            year_options += f'<option value="{year}">{year} ({count})</option>\n'
        template = template.replace("{{YEAR_OPTIONS}}", year_options)
        
        # Gerar linhas da tabela
        table_rows = ""
        for url, versions in versions_by_url.items():
            if not versions:
                continue
                
            latest = versions[0]
            url_type = self._determine_url_type(url)
            url_display = self._format_url_display(url)
            
            year = latest["timestamp"][:4] if latest["timestamp"] and len(latest["timestamp"]) >= 4 else ""
            
            table_rows += f"""
                    <tr class="border-b border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 transition duration-150" 
                        data-type="{url_type}" data-year="{year}" data-url="{url_display}">
                        <td class="py-3 px-6 text-left">
                            <div class="font-medium">{url_display}</div>
                        </td>
                        <td class="py-3 px-6 text-left whitespace-nowrap">{latest['formatted_date']}</td>
                        <td class="py-3 px-6 text-left">
                            <button class="toggle-versions bg-gray-200 hover:bg-gray-300 dark:bg-gray-600 dark:hover:bg-gray-500 dark:text-gray-200 text-gray-700 text-xs py-1 px-2 rounded transition duration-200">
                                <i class="fas fa-clock mr-1"></i> {len(versions)} versões
                            </button>
                            <div class="version-list mt-2 pl-2 border-l-2 border-gray-300 dark:border-gray-600 overflow-hidden max-h-0">
            """
            
            for version in versions:
                table_rows += f"""
                                <div class="py-1 flex flex-wrap">
                                    <span class="text-gray-500 dark:text-gray-400 mr-2 w-36">{version['formatted_date']}</span>
                                    <a href="{version['html_path']}" class="text-blue-500 dark:text-blue-400 hover:underline mr-2">Ver</a>
                                    <a href="{version['wayback_url']}" class="text-green-500 dark:text-green-400 hover:underline" target="_blank">
                                        <i class="fas fa-archive text-xs"></i> Wayback
                                    </a>
                                </div>
                """
            
            table_rows += f"""
                            </div>
                        </td>
                        <td class="py-3 px-6 text-center">
                            <div class="flex justify-center items-center space-x-2">
                                <a href="{latest['html_path']}" class="bg-blue-500 hover:bg-blue-600 dark:bg-blue-600 dark:hover:bg-blue-700 text-white py-1 px-3 rounded-lg text-xs transition duration-200 hover-effect">
                                    <i class="fas fa-eye mr-1"></i> Ver
                                </a>
                                <a href="{latest['wayback_url']}" target="_blank" class="bg-green-500 hover:bg-green-600 dark:bg-green-600 dark:hover:bg-green-700 text-white py-1 px-3 rounded-lg text-xs transition duration-200 hover-effect">
                                    <i class="fas fa-archive mr-1"></i> Wayback
                                </a>
                            </div>
                        </td>
                    </tr>
            """
        
        template = template.replace("{{TABLE_ROWS}}", table_rows)
        
        return template
    
    async def create_index(self) -> None:
        logger.info("Criando arquivo de índice...")
        
        try:
            versions_by_url = await self._organize_versions_by_url()
            
            # Obter estatísticas para os filtros
            stats = self._collect_stats(versions_by_url)
            
            # Gerar HTML para o índice
            index_html = self._generate_index_html(versions_by_url, stats)
            
            # Salvar o arquivo de índice
            async with aiofiles.open(self.output_dir / "index.html", "w", encoding="utf-8") as f:
                await f.write(index_html)
            
            logger.info(f"Índice criado com {len(versions_by_url)} URLs diferentes.")
            
        except Exception as e:
            logger.error(f"Erro ao criar índice: {e}")
            traceback.print_exc()

class KaliArchive:
    def __init__(self, 
                 output_dir: str = "kali_archive", 
                 domain: str = DEFAULT_DOMAIN,
                 start_date: Optional[str] = None,
                 end_date: Optional[str] = None,
                 max_pages: Optional[int] = None,
                 threads: int = MAX_WORKERS,
                 all_versions: bool = True,
                 cache_enabled: bool = True,
                 memory_safe: bool = True,
                 auto_detect_date: bool = True, #<-- Detecção automática da data inicial do domínio (Utilize False para desativar).
                 timeout: int = REQUEST_TIMEOUT):
        
        self.domain = domain
        self.output_dir = Path(output_dir)
        self.user_start_date = start_date
        self.end_date = self._parse_date(end_date)
        self.max_pages = max_pages
        self.threads = min(threads, MAX_WORKERS)
        self.all_versions = all_versions
        self.memory_safe = memory_safe
        self.timeout = timeout
        self.auto_detect_date = auto_detect_date
        
        self.session = create_session()
        self.stats = MemoryStats()
        
        if cache_enabled:
            self.cache = diskcache.Cache(CACHE_DIR, size_limit=10_000_000_000)
        else:
            self.cache = None
        
        # Inicializar componentes
        self.date_detector = DomainDateDetector(domain, self.session)
        self.resource_manager = ResourceManager(self.output_dir, domain, self.cache, threads)
        self.html_processor = HtmlProcessor(self.output_dir, domain, self.resource_manager)
        self.index_builder = IndexBuilder(self.output_dir)
        
        # Configurar manipuladores de sinal
        setup_signal_handlers(self._cleanup)
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[str]:
        if not date_str:
            return None
            
        patterns = [
            (r'^\d{8}$', lambda m: m.group(0)),  # YYYYMMDD
            (r'^\d{4}-\d{2}-\d{2}$', lambda m: m.group(0).replace('-', '')),  # YYYY-MM-DD
            (r'^\d{2}/\d{2}/\d{4}$', lambda m: f"{m.group(3)}{m.group(2)}{m.group(1)}"),  # DD/MM/YYYY
            (r'^\d{2}-\d{2}-\d{4}$', lambda m: f"{m.group(3)}{m.group(2)}{m.group(1)}"),  # DD-MM-YYYY
            (r'^\d{4}/\d{2}/\d{2}$', lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}"),  # YYYY/MM/DD
        ]
        
        for pattern, formatter in patterns:
            match = re.match(pattern, date_str)
            if match:
                return formatter(match)
        
        relative_dates = {
            "hoje": datetime.now(),
            "today": datetime.now(),
            "ontem": datetime.now() - timedelta(days=1),
            "yesterday": datetime.now() - timedelta(days=1),
            "semana_passada": datetime.now() - timedelta(weeks=1),
            "last_week": datetime.now() - timedelta(weeks=1),
            "mes_passado": datetime.now() - timedelta(days=30),
            "last_month": datetime.now() - timedelta(days=30),
            "ano_passado": datetime.now() - timedelta(days=365),
            "last_year": datetime.now() - timedelta(days=365)
        }
        
        date_str_lower = date_str.lower()
        if date_str_lower in relative_dates:
            return relative_dates[date_str_lower].strftime("%Y%m%d")
            
        try:
            for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y", "%Y.%m.%d"]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime("%Y%m%d")
                except ValueError:
                    continue
        except Exception:
            pass
            
        logger.warning(f"Data inválida: {date_str}. Usando formato padrão YYYYMMDD.")
        return FIXED_FALLBACK_DATE
    
    def _cleanup(self) -> None:
        logger.info("Realizando limpeza antes de encerrar...")
        if self.cache:
            try:
                self.cache.close()
            except Exception as e:
                logger.error(f"Erro ao fechar cache: {e}")
        
        # Força coleta de lixo
        import gc
        gc.collect()
    
    async def _initialize_dates(self) -> None:
        parsed_start_date = self._parse_date(self.user_start_date) if self.user_start_date else None
        
        if parsed_start_date:
            self.start_date = parsed_start_date
            logger.info(f"Usando data inicial especificada pelo usuário: {self.start_date}")
        elif self.auto_detect_date:
            logger.info("Tentando detectar automaticamente a data inicial do domínio...")
            detected_date = await self.date_detector.detect_earliest_date()
            
            if detected_date:
                self.start_date = detected_date
                logger.info(f"Data inicial detectada: {self.start_date}")
            else:
                logger.warning("Falha na detecção automática, usando fallback dinâmico")
                self.start_date = self.date_detector.get_dynamic_fallback_date()
                logger.info(f"Data dinâmica de fallback: {self.start_date}")
        else:
            self.start_date = FIXED_FALLBACK_DATE
            logger.info(f"Usando data fixa de fallback: {self.start_date}")
        
        if not self.end_date:
            self.end_date = datetime.now().strftime("%Y%m%d")
            logger.info(f"Data final: {self.end_date} (atual)")
    
    async def run(self) -> None:
        logger.info(f"Iniciando extração de {self.domain}")
        self.stats.update()
        
        # Verificar espaço em disco
        if not is_disk_space_ok(str(self.output_dir), required_gb=10.0):
            logger.error("Espaço em disco insuficiente (recomendado: 10GB). Operação abortada.")
            return
        
        try:
            # Inicializar datas
            await self._initialize_dates()
            
            # 1. Buscar snapshots
            with timing("Busca de snapshots"):
                snapshot_fetcher = SnapshotFetcher(
                    domain=self.domain,
                    start_date=self.start_date,
                    end_date=self.end_date,
                    max_snapshots=self.max_pages,
                    all_versions=self.all_versions,
                    memory_safe=self.memory_safe
                )
                
                snapshots = await snapshot_fetcher.fetch_all_snapshots()
                
                if not snapshots:
                    logger.error("Não foi possível encontrar snapshots. Abortando.")
                    return
            
            # 2. Baixar e processar snapshots HTML de forma assíncrona
            logger.info(f"Baixando {len(snapshots)} snapshots...")
            
            # Limitar o número de snapshots se especificado
            if self.max_pages and len(snapshots) > self.max_pages:
                snapshots = snapshots[:self.max_pages]
            
            # Usar semáforo para limitar o número de downloads simultâneos
            semaphore = asyncio.Semaphore(self.threads)
            
            async def process_snapshot(snapshot):
                async with semaphore:
                    success = await snapshot_fetcher.download_snapshot(snapshot, self.cache)
                    if success:
                        await self.html_processor.process_snapshot(snapshot)
                        self.stats.snapshots_processed += 1
                        if self.stats.snapshots_processed % 20 == 0:
                            self.stats.update()
                            logger.info(f"Progresso: {self.stats.snapshots_processed}/{len(snapshots)} snapshots | {self.stats}")
                        return True
                    return False
            
            with timing("Download e processamento de snapshots"):
                results = await async_tqdm.gather(
                    *[process_snapshot(snapshot) for snapshot in snapshots],
                    desc="Baixando snapshots",
                    total=len(snapshots)
                )
            
            successful_snapshots = sum(1 for r in results if r)
            logger.info(f"Downloads concluídos. {successful_snapshots} de {len(snapshots)} snapshots foram baixados e processados com sucesso.")
            
            # 3. Baixar recursos
            with timing("Download de recursos"):
                await self.resource_manager.download_all_resources(self.stats)
            
            # Atualizar estatísticas finais
            self.stats.update()
            logger.info(f"Estatísticas finais: {self.stats}")
            
            # 4. Criar índice
            with timing("Criação de índice"):
                await self.index_builder.create_index()
                
            logger.info(f"Extração concluída! Arquivos salvos em: {self.output_dir.absolute()}")
        
        except Exception as e:
            logger.error(f"Erro durante a execução: {str(e)}")
            traceback.print_exc()
        finally:
            self._cleanup()

async def main_async():
    parser = argparse.ArgumentParser(description="Kali Archive - Extrator avançado e reconstrutor de sites via Wayback Machine")
    
    parser.add_argument("--output", "-o", type=str, default="kali_archive",
                        help="Diretório de saída para salvar o conteúdo extraído")
    parser.add_argument("--domain", "-d", type=str, default=DEFAULT_DOMAIN,
                        help=f"Domínio a ser extraído (padrão: {DEFAULT_DOMAIN})")
    parser.add_argument("--start-date", type=str, 
                        help="Data inicial para snapshots (YYYYMMDD, YYYY-MM-DD, DD/MM/YYYY, etc)")
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
    parser.add_argument("--safe-memory", action="store_true",
                        help="Monitorar uso de memória e limitar extração em caso de uso elevado")
    parser.add_argument("--timeout", type=int, default=REQUEST_TIMEOUT,
                        help=f"Timeout para requisições em segundos (padrão: {REQUEST_TIMEOUT})")
    parser.add_argument("--no-auto-detect", action="store_true",
                        help="Desativar detecção automática de data inicial")
    
    args = parser.parse_args()
    
    archive = KaliArchive(
        output_dir=args.output,
        domain=args.domain,
        start_date=args.start_date,
        end_date=args.end_date,
        max_pages=args.max_pages,
        threads=args.threads,
        all_versions=not args.single_version,
        cache_enabled=not args.no_cache,
        memory_safe=args.safe_memory,
        auto_detect_date=not args.no_auto_detect,
        timeout=args.timeout
    )
    
    await archive.run()

def main():
    try:
        # Configurar detecção de loop de eventos existente
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Executar a função assíncrona principal
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        logger.info("Interrupção detectada. Encerrando...")
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 