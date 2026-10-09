"""
Utilidades compartidas por todo el pipeline:
- Rutas del proyecto
- Carga de configuración (config.yaml + .env)
- Configuración del logging (consola + archivo en logs/)
- Funciones de lectura/escritura de capas
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml
from dotenv import load_dotenv

# Raíz del proyecto = carpeta que contiene main.py (src/ está un nivel abajo)
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config" / "config.yaml"

load_dotenv(ROOT_DIR / ".env")


# ------------------------------------------------------------------
# Configuración
# ------------------------------------------------------------------
def load_config(path: Path | str = CONFIG_PATH) -> dict:
    """Lee config.yaml y devuelve un diccionario."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_path(relative: str | Path) -> Path:
    """Convierte una ruta relativa del config en ruta absoluta desde la raíz."""
    p = Path(relative)
    return p if p.is_absolute() else ROOT_DIR / p


# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------
_LOGGER_CONFIGURED = False


def get_logger(name: str = "pipeline") -> logging.Logger:
    """
    Devuelve un logger que escribe en consola y en logs/pipeline_YYYYMMDD.log.
    El nivel se toma de la variable LOG_LEVEL del archivo .env (INFO por defecto).
    """
    global _LOGGER_CONFIGURED
    logger = logging.getLogger("pipeline")

    if not _LOGGER_CONFIGURED:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(level)
        logger.propagate = False

        log_dir = ROOT_DIR / os.getenv("LOG_DIR", "logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"pipeline_{datetime.now():%Y%m%d}.log"

        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)-22s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(fmt)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(fmt)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        _LOGGER_CONFIGURED = True

    return logger if name == "pipeline" else logger.getChild(name)


# ------------------------------------------------------------------
# Texto
# ------------------------------------------------------------------
def strip_accents(text: str) -> str:
    """'Categoría' -> 'Categoria'."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def to_snake_case(name: str) -> str:
    """'Precio Unitario' -> 'precio_unitario', 'Descuento %' -> 'descuento'."""
    name = strip_accents(str(name)).strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


# ------------------------------------------------------------------
# Lectura / escritura de capas
# ------------------------------------------------------------------
def save_layer(df: pd.DataFrame, folder: Path, name: str, fmt: str = "parquet") -> Path:
    """Guarda un DataFrame en la carpeta de la capa (bronze/silver/gold)."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.{fmt}"
    if fmt == "parquet":
        df.to_parquet(path, index=False)
    elif fmt == "csv":
        df.to_csv(path, index=False, encoding="utf-8")
    else:
        raise ValueError(f"Formato no soportado: {fmt}")
    return path


def read_layer(folder: Path, name: str, fmt: str = "parquet") -> pd.DataFrame:
    """Lee un DataFrame de una capa."""
    path = folder / f"{name}.{fmt}"
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}. ¿Ejecutaste la etapa anterior?")
    return pd.read_parquet(path) if fmt == "parquet" else pd.read_csv(path)
