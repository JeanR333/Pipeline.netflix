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
   *(Mientras eliges uno, el proyecto trae `ventas_ejemplo.xlsx`, un dataset sucio de prueba).*

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
- `test_transform.py` → cada regla de limpieza
- `test_quality.py` → valida el archivo silver real (sin duplicados, llaves únicas, rangos)

---

## ¿Qué hace cada capa?

**Bronze (extracción).** Copia el dato *tal cual llegó*, todo como texto, y agrega
`_source_file` y `_ingestion_ts` para trazabilidad. No se limpia nada: si algo sale mal en
silver, siempre se puede reprocesar desde aquí.

**Silver (transformación).** En este orden:
1. Columnas a `snake_case` sin tildes
2. Espacios y nulos ocultos (`"N/A"` → nulo)
3. Eliminación de columnas casi vacías
4. Duplicados exactos y por llave primaria
5. Unificación de categorías (`"BOGOTA"`, `" bogota "` → `"Bogotá"`)
6. Conversión de tipos
7. Valores fuera de rango → nulo
8. Filas sin columnas obligatorias
9. Imputación (mediana numérica, moda categórica; las fechas no se inventan)
10. Marca de outliers por IQR

## Problemas comunes
| Error | Solución |
|---|---|
| `ModuleNotFoundError: No module named 'src'` | Ejecuta `python main.py` desde la carpeta raíz del proyecto |
| `FileNotFoundError ... archivo fuente` | Revisa `source.file_path` en `config.yaml` |
| `UnicodeDecodeError` al leer CSV | Cambia `encoding: "latin-1"` en `config.yaml` |
| CSV con una sola columna | Tu separador es `;` → `csv_separator: ";"` |
| El notebook no encuentra librerías | Selecciona el kernel `.venv` |
