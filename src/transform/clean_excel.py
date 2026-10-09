"""
CAPA SILVER - Transformación
----------------------------
Toma la capa bronze y aplica limpieza basada en los hallazgos del EDA:

  1. Estandariza nombres de columnas (snake_case, sin tildes)
  2. Limpia espacios y convierte textos tipo "N/A", "?" ... en nulos
  3. Elimina columnas con demasiados nulos
  4. Elimina duplicados (exactos, por llave primaria y por llave de negocio)
  5. Normaliza texto en columnas categóricas ("BOGOTA" / " bogotá " -> "Bogotá")
  6. Separa columnas "valor + unidad" ("90 min" -> 90 | minutos)
  7. Extrae información de columnas multivalor ("Dramas, Comedias" -> principal + cantidad)
  8. Corrige tipos de datos (int, float, datetime, category, string)
  9. Deriva año y mes de columnas de fecha
 10. Convierte valores fuera de rango en nulos
 11. Elimina filas sin columnas obligatorias
 12. Imputa nulos (mediana / moda / "Desconocido")
 13. Marca o elimina outliers (IQR, opcionalmente por grupo)
 14. Marca inconsistencias de negocio (reglas configurables)

Cada paso queda registrado en el log y en un reporte de calidad JSON (logs/).
Todas las reglas se controlan desde config/config.yaml.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src.utils import (
    get_logger,
    load_config,
    read_layer,
    resolve_path,
    save_layer,
    strip_accents,
    to_snake_case,
)

logger = get_logger("transform")

META_COLS = ["_source_file", "_ingestion_ts"]


def _is_text(s: pd.Series) -> bool:
    """True si la serie es de texto (compatible con pandas 2 y 3)."""
    return pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)


def _data_cols(df: pd.DataFrame) -> list[str]:
    """Columnas de negocio (sin metadatos)."""
    return [c for c in df.columns if not c.startswith("_")]


# ------------------------------------------------------------------
# 1. Nombres de columnas
# ------------------------------------------------------------------
def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    new_cols, seen = [], {}
    for c in df.columns:
        if c in META_COLS:
            new_cols.append(c)
            continue
        name = to_snake_case(c) or "columna"
        if name in seen:  # evita nombres repetidos
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        new_cols.append(name)
    renamed = {o: n for o, n in zip(df.columns, new_cols) if o != n}
    if renamed:
        logger.info("Columnas renombradas: %s", renamed)
    df = df.copy()
    df.columns = new_cols
    return df


# ------------------------------------------------------------------
# 2. Espacios y textos nulos
# ------------------------------------------------------------------
def clean_whitespace_and_nulls(df: pd.DataFrame, null_values: list[str]) -> pd.DataFrame:
    df = df.copy()
    tokens = {v.strip().lower() for v in null_values}
    for c in _data_cols(df):
        if _is_text(df[c]):
            s = df[c].astype("object").where(df[c].notna(), None)
            s = s.map(lambda v: v.strip() if isinstance(v, str) else v)
            s = s.map(lambda v: None if isinstance(v, str) and v.lower() in tokens else v)
            df[c] = s
    return df


# ------------------------------------------------------------------
# 3. Columnas con muchos nulos
# ------------------------------------------------------------------
def drop_high_null_columns(df: pd.DataFrame, max_pct: float) -> tuple[pd.DataFrame, list[str]]:
    pct = df[_data_cols(df)].isna().mean() * 100
    to_drop = pct[pct > max_pct].index.tolist()
    if to_drop:
        logger.info("Columnas eliminadas por > %s%% nulos: %s", max_pct, to_drop)
    return df.drop(columns=to_drop), to_drop


# ------------------------------------------------------------------
# 4. Duplicados
# ------------------------------------------------------------------
def remove_duplicates(
    df: pd.DataFrame, primary_key: list[str], business_key: list[str] | None = None
) -> tuple[pd.DataFrame, int, int]:
    cols = _data_cols(df)
    before = len(df)
    df = df.drop_duplicates(subset=cols, keep="first")
    exact = before - len(df)

    by_key = 0
    pk = [c for c in primary_key if c in df.columns]
    if pk:
        before_pk = len(df)
        df = df.drop_duplicates(subset=pk, keep="first")
        by_key = before_pk - len(df)

    bk = [c for c in (business_key or []) if c in df.columns]
    if bk:
        before_bk = len(df)
        df = df.drop_duplicates(subset=bk, keep="first")
        n_bk = before_bk - len(df)
        by_key += n_bk
        logger.info("Duplicados por llave de negocio %s: %s", bk, n_bk)

    logger.info("Duplicados eliminados -> exactos: %s | por llave %s: %s", exact, pk or "-", by_key)
    return df.reset_index(drop=True), exact, by_key


# ------------------------------------------------------------------
# 5. Normalización de texto categórico
# ------------------------------------------------------------------
def normalize_categories(s: pd.Series, title_case: bool = True, unify_accents: bool = True) -> pd.Series:
    """
    Unifica variantes de la misma categoría.
    Ej: ['Bogotá', 'BOGOTA', ' bogota '] -> todas pasan a la forma más frecuente con tilde: 'Bogotá'.
    """
    s = s.astype("object")
    vals = s.dropna().astype(str)
    if title_case:
        vals = vals.str.title()
    if unify_accents:
        keys = vals.map(lambda v: strip_accents(v).lower())
        # para cada clave, la variante con tilde (si existe) y más frecuente
        mapping = {}
        for key, group in vals.groupby(keys):
            counts = group.value_counts()
            with_accent = [v for v in counts.index if v != strip_accents(v)]
            mapping[key] = with_accent[0] if with_accent else counts.index[0]
        vals = keys.map(mapping)
    out = s.copy()
    out.loc[vals.index] = vals
    return out


# ------------------------------------------------------------------
# 6. Columnas "valor + unidad"
# ------------------------------------------------------------------
def split_value_unit(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, list[str]]:
    """
    "90 min" -> <col>_valor=90, <col>_unidad="minutos".
    cfg = {columna: {"unit_map": {"min": "minutos", "season": "temporadas", ...}, "drop_original": bool}}
    """
    df = df.copy()
    nuevas = []
    for c, opts in (cfg or {}).items():
        if c not in df.columns:
            continue
        opts = opts or {}
        partes = df[c].astype("object").str.extract(r"^\s*([\d.,]+)\s*(.*?)\s*$")
        df[f"{c}_valor"] = partes[0].str.replace(",", ".", regex=False)
        unidades = partes[1].str.lower()
        unit_map = {k.lower(): v for k, v in (opts.get("unit_map") or {}).items()}
        if unit_map:
            unidades = unidades.map(lambda u: unit_map.get(u, u) if isinstance(u, str) else u)
        df[f"{c}_unidad"] = unidades
        nuevas += [f"{c}_valor", f"{c}_unidad"]
        no_parse = int(df[c].notna().sum() - df[f"{c}_valor"].notna().sum())
        logger.info("Columna '%s' separada en valor/unidad. Unidades: %s | no interpretables: %s",
                    c, df[f"{c}_unidad"].value_counts().to_dict(), no_parse)
        if opts.get("drop_original", True):
            df = df.drop(columns=[c])
    return df, nuevas


# ------------------------------------------------------------------
# 7. Columnas multivalor
# ------------------------------------------------------------------
def split_multi_value(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    "Dramas, Comedias, Thrillers" -> <col>_principal="Dramas", <col>_cantidad=3.
    La columna original se conserva para análisis posteriores (explode en gold).
    cfg = {columna: separador}
    """
    df = df.copy()
    for c, sep in (cfg or {}).items():
        if c not in df.columns:
            continue
        listas = df[c].astype("object").map(
            lambda v: [x.strip() for x in v.split(sep) if x.strip()] if isinstance(v, str) else None
        )
        df[f"{c}_principal"] = listas.map(lambda l: l[0] if l else None)
        df[f"{c}_cantidad"] = listas.map(lambda l: len(l) if l else 0)
        logger.info("Columna multivalor '%s': %s valores distintos en total, máx %s por fila",
                    c, listas.dropna().explode().nunique(), df[f"{c}_cantidad"].max())
    return df


# ------------------------------------------------------------------
# 8. Tipos de datos
# ------------------------------------------------------------------
def _to_int(s: pd.Series) -> pd.Series:
    num = pd.to_numeric(s, errors="coerce")
    return num.round().astype("Int64")


def infer_type(s: pd.Series) -> str:
    """Infiera el tipo de una columna de texto: int, float, datetime, category o string."""
    non_null = s.dropna()
    if non_null.empty:
        return "string"
    num = pd.to_numeric(non_null, errors="coerce")
    if num.notna().mean() >= 0.9:
        return "int" if (num.dropna() % 1 == 0).all() else "float"
    if pd.to_datetime(non_null, errors="coerce", format="mixed").notna().mean() >= 0.9:
        return "datetime"
    n_unique = non_null.nunique()
    if n_unique <= 50 and n_unique / len(non_null) < 0.5:
        return "category"
    return "string"


def cast_types(df: pd.DataFrame, dtypes: dict, date_formats: dict | None = None) -> tuple[pd.DataFrame, dict, dict]:
    """Convierte cada columna a su tipo. Devuelve df, tipos finales y valores inválidos por columna."""
    df = df.copy()
    final_types, invalid = {}, {}

    for c in _data_cols(df):
        target = dtypes.get(c) or infer_type(df[c])
        before_nulls = df[c].isna().sum()

        if target == "int":
            df[c] = _to_int(df[c])
        elif target == "float":
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
        elif target == "datetime":
            fmt = (date_formats or {}).get(c, "mixed")
            df[c] = pd.to_datetime(df[c], errors="coerce", format=fmt)
        elif target in ("category", "string"):
            df[c] = df[c].astype("object")
        else:
            raise ValueError(f"Tipo '{target}' no soportado para la columna {c}")

        new_invalid = int(df[c].isna().sum() - before_nulls)
        if new_invalid > 0:
            invalid[c] = new_invalid
            logger.warning("Columna '%s': %s valores no convertibles a %s -> nulo", c, new_invalid, target)
        final_types[c] = target

    logger.info("Tipos asignados: %s", final_types)
    return df, final_types, invalid


# ------------------------------------------------------------------
# 9. Partes de fecha
# ------------------------------------------------------------------
def add_date_parts(df: pd.DataFrame, cols: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """date_added -> date_added_anio, date_added_mes."""
    df = df.copy()
    nuevas = []
    for c in cols or []:
        if c in df.columns and pd.api.types.is_datetime64_any_dtype(df[c]):
            df[f"{c}_anio"] = df[c].dt.year.astype("Int64")
            df[f"{c}_mes"] = df[c].dt.month.astype("Int64")
            nuevas += [f"{c}_anio", f"{c}_mes"]
    if nuevas:
        logger.info("Columnas de fecha derivadas: %s", nuevas)
    return df, nuevas


# ------------------------------------------------------------------
# 14. Reglas de negocio (flags)
# ------------------------------------------------------------------
def add_business_flags(df: pd.DataFrame, rules: dict) -> tuple[pd.DataFrame, dict]:
    """
    Marca filas que incumplen una regla. cfg = {nombre_flag: "expresión pandas"}.
    Ej: {"lanzamiento_posterior_a_ingreso": "release_year > date_added_anio"}
    """
    df = df.copy()
    report = {}
    for name, expr in (rules or {}).items():
        try:
            mask = df.eval(expr).fillna(False).astype(bool)
        except Exception as e:  # columna inexistente o expresión inválida
            logger.warning("Regla '%s' (%s) no se pudo evaluar: %s", name, expr, e)
            continue
        df[name] = mask
        report[name] = int(mask.sum())
        logger.info("Regla '%s' [%s]: %s filas marcadas", name, expr, report[name])
    return df, report


# ------------------------------------------------------------------
# 10. Rangos válidos
# ------------------------------------------------------------------
def apply_valid_ranges(df: pd.DataFrame, ranges: dict) -> tuple[pd.DataFrame, dict]:
    df = df.copy()
    report = {}
    for c, (lo, hi) in (ranges or {}).items():
        if c not in df.columns:
            continue
        mask = df[c].notna() & ((df[c] < lo) | (df[c] > hi))
        n = int(mask.sum())
        if n:
            df.loc[mask, c] = pd.NA if str(df[c].dtype) == "Int64" else np.nan
            logger.warning("Columna '%s': %s valores fuera de [%s, %s] -> nulo", c, n, lo, hi)
        report[c] = n
    return df, report


# ------------------------------------------------------------------
# 11. Filas sin columnas obligatorias
# ------------------------------------------------------------------
def drop_missing_required(df: pd.DataFrame, required: list[str]) -> tuple[pd.DataFrame, int]:
    req = [c for c in required if c in df.columns]
    if not req:
        return df, 0
    before = len(df)
    df = df.dropna(subset=req).reset_index(drop=True)
    removed = before - len(df)
    logger.info("Filas eliminadas por nulos en columnas obligatorias %s: %s", req, removed)
    return df, removed


# ------------------------------------------------------------------
# 12. Imputación
# ------------------------------------------------------------------
def impute_nulls(df: pd.DataFrame, types: dict, cfg: dict) -> tuple[pd.DataFrame, dict]:
    df = df.copy()
    report = {}
    for c, t in types.items():
        if c not in df.columns:
            continue
        n_null = int(df[c].isna().sum())
        if n_null == 0:
            continue

        value = None
        if t in ("int", "float"):
            strategy = cfg.get("numeric", "median")
            if strategy == "median":
                value = df[c].median()
            elif strategy == "mean":
                value = df[c].mean()
            elif strategy == "zero":
                value = 0
            if value is not None and t == "int":
                value = int(round(value))
        elif t in ("category", "string"):
            strategy = cfg.get("categorical", "mode")
            if strategy == "mode" and t == "category" and not df[c].mode().empty:
                value = df[c].mode().iloc[0]
            elif strategy in ("mode", "unknown"):
                value = cfg.get("unknown_label", "Desconocido")
        # Fechas: no se imputan (inventar fechas sesga el análisis); se dejan nulas

        if value is not None:
            df[c] = df[c].fillna(value)
            report[c] = {"nulos": n_null, "valor_imputado": str(value)}
            logger.info("Columna '%s': %s nulos imputados con %s", c, n_null, value)
        else:
            logger.info("Columna '%s' (%s): %s nulos se mantienen", c, t, n_null)
    return df, report


# ------------------------------------------------------------------
# 13. Outliers
# ------------------------------------------------------------------
def handle_outliers(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    method = (cfg or {}).get("method", "none")
    if method == "none":
        return df, {}
    k = cfg.get("iqr_factor", 1.5)
    df = df.copy()
    report = {}
    group_by = cfg.get("group_by") or {}
    for c in cfg.get("columns", []):
        if c not in df.columns or not pd.api.types.is_numeric_dtype(df[c]):
            continue
        g = group_by.get(c)
        # Si la columna mezcla grupos (ej. minutos y temporadas) los límites se calculan por grupo
        grupos = df.groupby(g, observed=True)[c] if g in df.columns else [(None, df[c])]
        mask = pd.Series(False, index=df.index)
        report[c] = {}
        for key, serie in grupos:
            q1, q3 = serie.quantile([0.25, 0.75])
            iqr = q3 - q1
            lo, hi = q1 - k * iqr, q3 + k * iqr
            m = (serie < lo) | (serie > hi)
            mask.loc[serie.index] = m.fillna(False).astype(bool)
            etiqueta = str(key) if key is not None else "todos"
            report[c][etiqueta] = {"outliers": int(m.sum()), "limite_inferior": float(lo),
                                   "limite_superior": float(hi)}
            logger.info("Outliers en '%s'%s (IQR x%s, rango [%.2f, %.2f]): %s -> %s", c,
                        f" [{g}={key}]" if key is not None else "", k, lo, hi, int(m.sum()), method)
        n = int(mask.sum())
        if method == "flag":
            df[f"{c}_es_outlier"] = mask.fillna(False)
        elif method == "remove":
            df = df[~mask.fillna(False)].reset_index(drop=True)
    return df, report


# ------------------------------------------------------------------
# Orquestación de la etapa
# ------------------------------------------------------------------
def transform(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Aplica todas las reglas al DataFrame. Separado de la E/S para poder probarlo."""
    report = {"filas_entrada": int(len(df)), "columnas_entrada": int(df.shape[1])}

    df = standardize_columns(df)
    df = clean_whitespace_and_nulls(df, cfg.get("null_values", []))
    report["nulos_entrada"] = {k: int(v) for k, v in df[_data_cols(df)].isna().sum().items()}

    df, report["columnas_eliminadas"] = drop_high_null_columns(df, cfg.get("drop_columns_null_pct", 100))
    df, report["duplicados_exactos"], report["duplicados_por_llave"] = remove_duplicates(
        df, cfg.get("primary_key", []), cfg.get("business_key", [])
    )

    dtypes = cfg.get("dtypes", {}) or {}
    text_cfg = cfg.get("text", {})
    # columnas categóricas: las del config + las inferidas
    cat_cols = [c for c in _data_cols(df) if (dtypes.get(c) or infer_type(df[c])) == "category"]
    for c in cat_cols:
        df[c] = normalize_categories(
            df[c], text_cfg.get("title_case", True), text_cfg.get("remove_accents_for_matching", True)
        )

    df, _ = split_value_unit(df, cfg.get("split_value_unit", {}))
    df = split_multi_value(df, cfg.get("multi_value_columns", {}))

    df, types, report["valores_invalidos_por_tipo"] = cast_types(df, dtypes, cfg.get("date_formats", {}))
    df, date_cols = add_date_parts(df, cfg.get("date_parts", []))
    types.update({c: "int" for c in date_cols})
    report["tipos_finales"] = types
    df, report["fuera_de_rango"] = apply_valid_ranges(df, cfg.get("valid_ranges", {}))
    df, report["filas_sin_obligatorios"] = drop_missing_required(df, cfg.get("required_columns", []))
    df, report["imputacion"] = impute_nulls(df, types, cfg.get("impute", {}))
    df, report["outliers"] = handle_outliers(df, cfg.get("outliers", {}))
    df, report["reglas_negocio"] = add_business_flags(df, cfg.get("business_rules", {}))

    # tipos finales de categorías y metadatos
    for c, t in types.items():
        if c in df.columns and t == "category":
            df[c] = df[c].astype("category")
        elif c in df.columns and t == "string":
            df[c] = df[c].astype("string")
    if "_ingestion_ts" in df.columns:
        df["_ingestion_ts"] = pd.to_datetime(df["_ingestion_ts"])
    df["_processed_ts"] = pd.Timestamp.now().floor("s")

    report["filas_salida"] = int(len(df))
    report["columnas_salida"] = int(df.shape[1])
    report["nulos_salida"] = {k: int(v) for k, v in df[_data_cols(df)].isna().sum().items() if v}
    return df, report


def run_transform(config: dict | None = None) -> Path:
    """Lee bronze, transforma y guarda en silver + reporte de calidad en logs/."""
    config = config or load_config()
    name = config["output"]["dataset_name"]
    fmt = config["output"].get("format", "parquet")

    df = read_layer(resolve_path(config["paths"]["bronze"]), f"{name}_bronze", fmt)
    logger.info("BRONZE leído: %s filas x %s columnas", f"{df.shape[0]:,}", df.shape[1])

    df, report = transform(df, config["transform"])

    out = save_layer(df, resolve_path(config["paths"]["silver"]), f"{name}_silver", fmt)
    logger.info("Capa SILVER guardada en: %s (%s filas x %s columnas)",
                out.relative_to(resolve_path(".")), f"{df.shape[0]:,}", df.shape[1])

    report_path = resolve_path(config["paths"]["logs"]) / f"quality_report_{datetime.now():%Y%m%d_%H%M%S}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Reporte de calidad: %s", report_path.relative_to(resolve_path(".")))
    return out


if __name__ == "__main__":
    run_transform()
