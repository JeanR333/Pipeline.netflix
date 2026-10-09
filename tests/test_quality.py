"""
Pruebas de calidad sobre la capa SILVER real.
Se ejecutan después de 'python main.py'; si no existe silver, se omiten.
"""
import pandas as pd
import pytest

from src.utils import load_config, resolve_path

CFG = load_config()
SILVER = resolve_path(CFG["paths"]["silver"]) / f"{CFG['output']['dataset_name']}_silver.{CFG['output']['format']}"

pytestmark = pytest.mark.skipif(not SILVER.exists(), reason="Ejecuta primero: python main.py")


@pytest.fixture(scope="module")
def silver():
    return pd.read_parquet(SILVER) if SILVER.suffix == ".parquet" else pd.read_csv(SILVER)


def test_no_esta_vacio(silver):
    assert len(silver) > 0


def test_sin_duplicados(silver):
    cols = [c for c in silver.columns if not c.startswith("_")]
    assert not silver.duplicated(subset=cols).any()


def test_llave_primaria_unica(silver):
    pk = CFG["transform"].get("primary_key") or []
    if pk:
        assert not silver.duplicated(subset=pk).any()


def test_columnas_obligatorias_sin_nulos(silver):
    for c in CFG["transform"].get("required_columns", []):
        assert silver[c].notna().all(), f"{c} tiene nulos"


def test_columnas_snake_case(silver):
    for c in silver.columns:
        assert c == c.lower() and " " not in c


def test_rangos_validos(silver):
    for c, (lo, hi) in CFG["transform"].get("valid_ranges", {}).items():
        if c in silver.columns:
            assert silver[c].dropna().between(lo, hi).all(), f"{c} fuera de [{lo}, {hi}]"


def test_metadatos_presentes(silver):
    assert {"_source_file", "_ingestion_ts", "_processed_ts"} <= set(silver.columns)
