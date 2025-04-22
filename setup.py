#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from setuptools import setup
import os
import re
import sys

# Verificações essenciais
if sys.version_info < (3, 7):
    sys.exit('Erro: Python 3.7+ requerido')

if not os.path.exists('kali_archive.py'):
    sys.exit('Erro: kali_archive.py não encontrado')

# Extrair versão ou usar valor padrão
def get_version():
    try:
        with open('kali_archive.py', 'r', encoding='utf-8') as f:
            content = f.read()
            match = re.search(r'__version__\s*=\s*[\'"]([^\'"]*)[\'"]', content)
            return match.group(1) if match else "1.0.0"
    except Exception:
        return "1.0.0"

# Garantir que template existe
def ensure_template():
    if not os.path.exists('index_template.html'):
        try:
            with open('kali_archive.py', 'r', encoding='utf-8') as f:
                content = f.read()
                match = re.search(r'def _get_fallback_template.*?return \"\"\"(.*?)\"\"\"\s*$', 
                                 content, re.DOTALL | re.MULTILINE)
                if match:
                    with open('index_template.html', 'w', encoding='utf-8') as tf:
                        tf.write(match.group(1))
        except Exception:
            # Criar template vazio caso falhe
            with open('index_template.html', 'w', encoding='utf-8') as f:
                f.write('<!-- Template Placeholder -->')

# Ler requirements.txt ou usar lista padrão de dependências
def get_requirements():
    try:
        with open('requirements.txt', 'r', encoding='utf-8') as f:
            return [line.strip() for line in f 
                   if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        return [
            'aiohttp>=3.8.1', 'aiofiles>=0.8.0', 'beautifulsoup4>=4.10.0', 
            'requests>=2.27.1', 'urllib3>=1.26.9', 'tqdm>=4.64.0', 
            'psutil>=5.9.0', 'diskcache>=5.4.0', 'lxml>=4.8.0', 
            'bs4>=0.0.1', 'asyncio>=3.4.3'
        ]

ensure_template()

setup(
    name="kali-archive",
    version=get_version(),
    description="Ferramenta de extração e reconstrução de conteúdo web histórico",
    author="Kali Archive Team",
    py_modules=["kali_archive"],
    data_files=[('', ['index_template.html'])],
    entry_points={
        'console_scripts': ['kali-archive=kali_archive:main'],
    },
    install_requires=get_requirements(),
    python_requires=">=3.7",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: System :: Archiving",
    ],
)