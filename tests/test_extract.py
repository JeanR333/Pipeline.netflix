"""Pruebas de la capa BRONZE (extracción)."""
import pandas as pd
import pytest

from src.extract.extract_excel import add_metadata, read_source


def test_lee_excel_como_texto(tmp_path):
    path = tmp_path / "datos.xlsx"
    pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}).to_excel(path, index=False)
    df = read_source(path)
    assert df.shape == (2, 2)
    assert df["a"].tolist() == ["1", "2"]  # se conserva el dato crudo como texto


def test_lee_csv(tmp_path):
    path = tmp_path / "datos.csv"
    path.write_text("a;b\n1;x\n2;y\n", encoding="utf-8")
    df = read_source(path, sep=";")
    assert list(df.columns) == ["a", "b"]


def test_archivo_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_source(tmp_path / "no_existe.xlsx")


def test_extension_no_soportada(tmp_path):
    path = tmp_path / "datos.txt"
    path.write_text("hola")
    with pytest.raises(ValueError):
        read_source(path)


def test_metadatos(raw_df):
    df = add_metadata(raw_df.drop(columns=["_source_file", "_ingestion_ts"]), "origen.xlsx")
    assert {"_source_file", "_ingestion_ts"} <= set(df.columns)
    assert (df["_source_file"] == "origen.xlsx").all()
