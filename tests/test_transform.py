"""Pruebas de cada regla de la capa SILVER (transformación)."""
import pandas as pd

from src.transform.clean_excel import (
    normalize_categories,
    remove_duplicates,
    standardize_columns,
    transform,
)


def test_snake_case(raw_df):
    df = standardize_columns(raw_df)
    assert "id_venta" in df.columns and "columna_vacia" in df.columns
    assert "_source_file" in df.columns  # metadatos no se renombran


def test_duplicados():
    df = pd.DataFrame({"id": [1, 1, 2], "v": ["a", "a", "b"]})
    out, exactos, por_llave = remove_duplicates(df, ["id"])
    assert len(out) == 2 and exactos == 1 and por_llave == 0


def test_normaliza_categorias():
    s = pd.Series(["Bogotá", "BOGOTA", " bogota".strip(), "cali", None])
    out = normalize_categories(s)
    assert out.dropna().tolist() == ["Bogotá", "Bogotá", "Bogotá", "Cali"]


def test_transform_completo(raw_df, transform_cfg):
    df, report = transform(raw_df, transform_cfg)
    assert len(df) == 5                                   # 1 duplicado eliminado
    assert "columna_vacia" not in df.columns              # columna 100% nula eliminada
    assert str(df["id_venta"].dtype) == "Int64"
    assert pd.api.types.is_datetime64_any_dtype(df["fecha_venta"])
    assert df["edad_cliente"].max() <= 110                # 150 fuera de rango -> imputado
    assert df["cantidad"].isna().sum() == 0               # "N/A" imputado
    assert set(df["ciudad"]) == {"Bogotá", "Cali"}        # texto unificado y nulo imputado
    assert report["duplicados_exactos"] == 1


# ---------------- Reglas agregadas para el dataset de Netflix ----------------
from src.transform.clean_excel import (  # noqa: E402
    add_business_flags,
    handle_outliers,
    split_multi_value,
    split_value_unit,
)


def test_separa_valor_y_unidad():
    df = pd.DataFrame({"duration": ["90 min", "2 Seasons", "1 Season"]})
    cfg = {"duration": {"unit_map": {"min": "minutos", "season": "temporadas", "seasons": "temporadas"}}}
    out, nuevas = split_value_unit(df, cfg)
    assert nuevas == ["duration_valor", "duration_unidad"]
    assert out["duration_valor"].tolist() == ["90", "2", "1"]
    assert out["duration_unidad"].tolist() == ["minutos", "temporadas", "temporadas"]
    assert "duration" not in out.columns


def test_multivalor():
    df = pd.DataFrame({"listed_in": ["Dramas, Comedies", "Documentaries", None]})
    out = split_multi_value(df, {"listed_in": ","})
    assert out["listed_in_principal"].tolist()[:2] == ["Dramas", "Documentaries"]
    assert out["listed_in_cantidad"].tolist() == [2, 1, 0]


def test_llave_de_negocio():
    df = pd.DataFrame({"id": ["s1", "s2"], "title": ["A", "A"], "year": [2020, 2020]})
    out, exactos, por_llave = remove_duplicates(df, ["id"], ["title", "year"])
    assert len(out) == 1 and por_llave == 1


def test_outliers_por_grupo():
    df = pd.DataFrame({"valor": [90, 95, 100, 92, 300, 1, 2, 1, 2, 15],
                       "unidad": ["min"] * 5 + ["temp"] * 5})
    out, rep = handle_outliers(df, {"method": "flag", "columns": ["valor"], "group_by": {"valor": "unidad"}})
    # 300 min y 15 temporadas son atípicos dentro de su propio grupo
    assert out.loc[out["valor_es_outlier"], "valor"].tolist() == [300, 15]


def test_regla_de_negocio():
    df = pd.DataFrame({"release_year": [2020, 2022], "date_added_anio": [2021, 2021]})
    out, rep = add_business_flags(df, {"inconsistente": "release_year > date_added_anio"})
    assert out["inconsistente"].tolist() == [False, True] and rep["inconsistente"] == 1
