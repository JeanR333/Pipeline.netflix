"""Permite importar 'src' desde las pruebas y define datos de prueba compartidos."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def raw_df():
    """DataFrame 'sucio' que simula la capa bronze (todo como texto)."""
    return pd.DataFrame({
        "ID Venta": ["1", "2", "3", "3", "4", "5"],
        "Fecha Venta": ["2025-01-01", "2025-02-15", "sin fecha", "sin fecha", "2025-03-10", "2025-04-01"],
        "Ciudad": ["Bogotá", "BOGOTA", " cali ", " cali ", None, "Cali"],
        "Cantidad": ["2", "N/A", "  3 ", "  3 ", "5", "1"],
        "Edad Cliente": ["30", "150", "45", "45", "28", "60"],
        "Columna Vacía": [None] * 6,
        "_source_file": ["test.xlsx"] * 6,
        "_ingestion_ts": ["2026-01-01T00:00:00"] * 6,
    })


@pytest.fixture
def transform_cfg():
    return {
        "null_values": ["", "N/A", "sin fecha"],
        "drop_columns_null_pct": 60,
        "required_columns": ["id_venta"],
        "primary_key": ["id_venta"],
        "dtypes": {"id_venta": "int", "fecha_venta": "datetime", "cantidad": "int",
                   "edad_cliente": "int", "ciudad": "category"},
        "valid_ranges": {"edad_cliente": [0, 110]},
        "impute": {"numeric": "median", "categorical": "mode"},
        "text": {"title_case": True, "remove_accents_for_matching": True},
        "outliers": {"method": "none"},
    }
