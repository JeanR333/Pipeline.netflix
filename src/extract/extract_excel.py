"""
CAPA BRONZE - Extracción
------------------------
Lee el archivo original (Excel o CSV descargado de Kaggle) y lo guarda
en data/bronze SIN modificar su contenido. Solo se agregan columnas de
metadatos para trazabilidad:

    _source_file    -> archivo de origen
    _ingestion_ts   -> fecha y hora de la ingesta

Todos los valores se guardan como texto para conservar el dato "tal cual
llegó"; la conversión de tipos ocurre en la capa silver.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from src.utils import get_logger, load_config, resolve_path, save_layer

logger = get_logger("extract")

SUPPORTED = {".xlsx", ".xls", ".csv"}


def read_source(file_path: Path, sheet_name=0, sep: str = ",", encoding: str = "utf-8") -> pd.DataFrame:
    """Lee un Excel o CSV como texto (dtype=str) sin inferir tipos."""
    if not file_path.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo fuente: {file_path}. "
            "Colócalo en data/source/ y actualiza 'source.file_path' en config.yaml"
        )

    ext = file_path.suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f"Extensión {ext} no soportada. Usa: {', '.join(sorted(SUPPORTED))}")

    logger.info("Leyendo archivo fuente: %s", file_path.name)
    if ext == ".csv":
        df = pd.read_csv(file_path, sep=sep, encoding=encoding, dtype=str)
    else:
        df = pd.read_excel(file_path, sheet_name=sheet_name, dtype=str)

    return df


def add_metadata(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """Agrega columnas de linaje/auditoría."""
    df = df.copy()
    df["_source_file"] = source_name
    df["_ingestion_ts"] = datetime.now().isoformat(timespec="seconds")
    return df


def run_extract(config: dict | None = None) -> Path:
    """Ejecuta la etapa completa de extracción -> bronze. Devuelve la ruta del archivo generado."""
    config = config or load_config()
    src_cfg = config["source"]

    source_path = resolve_path(src_cfg["file_path"])
    df = read_source(
        source_path,
        sheet_name=src_cfg.get("sheet_name", 0),
        sep=src_cfg.get("csv_separator", ","),
        encoding=src_cfg.get("encoding", "utf-8"),
    )
    logger.info("Registros leídos: %s filas x %s columnas", f"{df.shape[0]:,}", df.shape[1])

    if df.empty:
        raise ValueError("El archivo fuente está vacío.")

    df = add_metadata(df, source_path.name)

    out = save_layer(
        df,
        resolve_path(config["paths"]["bronze"]),
        config["output"]["dataset_name"] + "_bronze",
        config["output"].get("format", "parquet"),
    )
    logger.info("Capa BRONZE guardada en: %s", out.relative_to(resolve_path(".")))
    return out


if __name__ == "__main__":
    run_extract()
