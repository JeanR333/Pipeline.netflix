# Pipeline de Datos con Arquitectura Medallón (Bronze → Silver) + EDA — Netflix

Proyecto en Python que **extrae** el catálogo de Netflix (`netflix1.csv`, 8.790 títulos de Kaggle) a la capa **bronze**,
lo **analiza** con un EDA en Jupyter y lo **transforma** (limpieza y tipado) hacia la capa **silver**.
Cada ejecución queda registrada en `logs/`.

```
 data/source/            data/bronze/              data/silver/
 archivo Kaggle  ──►  EXTRACCIÓN  ──►  dato crudo  ──►  TRANSFORMACIÓN  ──►  dato limpio
 (.xlsx / .csv)    extract_excel.py   (+ metadatos)    clean_excel.py      (tipos, sin nulos,
                                                                           sin duplicados)
                         ▲                                   ▲
                         └───────── main.py (orquesta) ──────┘ ──► logs/ (log + reporte de calidad)
                                    notebooks/eda.ipynb → define las reglas de limpieza
```

## Estructura del proyecto

```
proyecto_pipeline/
├── config/
│   └── config.yaml              # TODAS las reglas: archivo fuente, rutas, limpieza
├── data/
│   ├── source/                  # ← netflix1.csv (archivo original de Kaggle)
│   ├── bronze/                  # capa 1: copia fiel del origen + metadatos
│   ├── silver/                  # capa 2: datos limpios y tipados
│   └── gold/                    # capa 3: (siguiente fase del curso)
├── logs/                        # pipeline_YYYYMMDD.log + quality_report_*.json
├── notebooks/
│   └── eda.ipynb                # Análisis Exploratorio de Datos
├── src/
│   ├── utils.py                 # config, logger y funciones compartidas
│   ├── extract/extract_excel.py # etapa de extracción  → bronze
│   ├── transform/clean_excel.py # etapa de transformación → silver
│   └── load/load_database.py    # etapa de carga (gold) - pendiente
├── tests/                       # pruebas con pytest
├── main.py                      # punto de entrada del pipeline
├── .env                         # variables de entorno (nivel de log)
├── .gitignore
└── requirements.txt
```

---

## Guía paso a paso en Visual Studio Code (Windows)

### Paso 0 — Requisitos
1. Instala **Python 3.10 o superior** desde python.org (marca *"Add Python to PATH"*).
2. Instala **Visual Studio Code**.
3. En VS Code, instala las extensiones **Python** y **Jupyter** (de Microsoft).

### Paso 1 — Abrir el proyecto
`File → Open Folder…` y selecciona la carpeta `proyecto_pipeline`.
Abre la terminal con **Ctrl + ñ** (o `Terminal → New Terminal`). Debe ser PowerShell.

> Si partes desde cero con los comandos del profesor (`mkdir …` / `New-Item …`), luego copia
> el contenido de cada archivo de este proyecto en el archivo vacío correspondiente.
> Archivos extra que agregamos: `src/utils.py`, `tests/conftest.py` y la carpeta `data/source/`.

### Paso 2 — Crear el entorno virtual e instalar librerías
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
- Si PowerShell bloquea la activación, ejecuta una vez:
  `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`
- Verás `(.venv)` al inicio de la línea cuando esté activo.
- En VS Code: `Ctrl + Shift + P → Python: Select Interpreter → .venv`.

### Paso 3 — Poner tu dataset
1. Descarga el dataset de Kaggle y cópialo a `data/source/`.
2. Abre `config/config.yaml` y cambia:
   ```yaml
   source:
     file_path: "data/source/TU_ARCHIVO.xlsx"   # o .csv
   output:
     dataset_name: "nombre_corto"
   ```
   *(Ya viene configurado para `data/source/netflix1.csv`.)*

### Paso 4 — Ejecutar el EDA
1. Abre `notebooks/eda.ipynb`.
2. Arriba a la derecha elige el kernel **.venv**.
3. Pulsa **Run All**.
4. Lee la sección **8. Hallazgos → reglas**: te dice qué columnas tienen nulos, tipos incorrectos,
   duplicados y outliers.

### Paso 5 — Ajustar las reglas de limpieza
En `config/config.yaml`, sección `transform`, ajusta según tu EDA (los nombres van en **snake_case**:
`"Precio Unitario"` → `precio_unitario`):

| Regla | Para qué |
|---|---|
| `null_values` | textos que significan "sin dato" (`"N/A"`, `"?"`, `"-"`) |
| `drop_columns_null_pct` | eliminar columnas con más de X % de nulos |
| `required_columns` | filas sin estas columnas se eliminan |
| `primary_key` | llave para detectar duplicados |
| `dtypes` | forzar tipos: `int`, `float`, `datetime`, `category`, `string` |
| `valid_ranges` | valores fuera de rango → nulo (ej. edad 150) |
| `impute` | cómo rellenar nulos: mediana/media/cero y moda/"Desconocido" |
| `outliers` | `flag` (marcar), `remove` (eliminar) o `none` |

Las columnas que no pongas en `dtypes` se infieren automáticamente.

### Paso 6 — Ejecutar el pipeline
```powershell
python main.py                     # extracción + transformación
python main.py --stage extract     # solo bronze
python main.py --stage transform   # solo silver
```
Resultado:
- `data/bronze/<nombre>_bronze.parquet`
- `data/silver/<nombre>_silver.parquet`
- `logs/pipeline_YYYYMMDD.log` → cada paso con su resultado
- `logs/quality_report_*.json` → resumen: duplicados eliminados, nulos imputados, tipos, outliers

Vuelve a ejecutar la **sección 9** del notebook para comparar original vs. silver.

### Paso 7 — Ejecutar las pruebas
```powershell
pytest -v
```
- `test_extract.py` → lectura de Excel/CSV, errores, metadatos
- `test_transform.py` → cada regla de limpieza (incluye valor/unidad, multivalor, llave de negocio, outliers por grupo)
- `test_quality.py` → valida el archivo silver real (sin duplicados, llaves únicas, rangos)

---

## ¿Qué hace cada capa?

**Bronze (extracción).** Copia el dato *tal cual llegó*, todo como texto, y agrega
`_source_file` y `_ingestion_ts` para trazabilidad. No se limpia nada: si algo sale mal en
silver, siempre se puede reprocesar desde aquí.

**Silver (transformación).** En este orden:
1. Columnas a `snake_case` sin tildes
2. Espacios y nulos ocultos (`"Not Given"` → nulo)
3. Eliminación de columnas casi vacías
4. Duplicados exactos, por llave técnica (`show_id`) y por llave de negocio (mismo título con distinto ID)
5. Unificación de categorías (`"BOGOTA"`, `" bogota "` → `"Bogotá"`)
6. Columnas "valor + unidad": `"90 min"` → `duration_valor = 90`, `duration_unidad = "minutos"`
7. Columnas multivalor: `listed_in` → `listed_in_principal` + `listed_in_cantidad`
8. Conversión de tipos (`date_added` con formato `%m/%d/%Y`)
9. Año y mes derivados de la fecha
10. Valores fuera de rango → nulo
11. Filas sin columnas obligatorias
12. Imputación (`director`/`country` → `"Desconocido"`; las fechas no se inventan)
13. Outliers por IQR, calculados **por unidad** (minutos y temporadas por separado)
14. Reglas de negocio: `lanzamiento_posterior_a_ingreso` (año de estreno > año de ingreso)

### Resultado con Netflix
| | Original | Silver |
|---|---|---|
| Filas | 8.790 | 8.786 (4 duplicados de negocio eliminados) |
| Faltantes | 0 según pandas, pero 2.875 ocultos (`"Not Given"`) | 0 (marcados como `"Desconocido"`) |
| Columnas | 10 (9 de texto) | 21 con tipos correctos + metadatos y banderas |

## Problemas comunes
| Error | Solución |
|---|---|
| `ModuleNotFoundError: No module named 'src'` | Ejecuta `python main.py` desde la carpeta raíz del proyecto |
| `FileNotFoundError ... archivo fuente` | Revisa `source.file_path` en `config.yaml` |
| `UnicodeDecodeError` al leer CSV | Cambia `encoding: "latin-1"` en `config.yaml` |
| CSV con una sola columna | Tu separador es `;` → `csv_separator: ";"` |
| El notebook no encuentra librerías | Selecciona el kernel `.venv` |
