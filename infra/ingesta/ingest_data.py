import os
import psycopg
import pandas as pd
from sqlalchemy import create_engine, inspect, text
from tqdm import tqdm
from pathlib import Path

# 1. Ruta y config.
BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = os.getenv("DATA_DIR")
if DATA_DIR:
    dir_csv = Path(DATA_DIR) / "raw" / "spotify_charts.csv"
else:
    dir_csv = BASE_DIR.parent.parent / "data" / "raw" / "spotify_charts.csv"

# --- CONFIGURACIÓN DINÁMICA MEDIANTE VARIABLES DE ENTORNO ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "admin")
DB_NAME = os.getenv("DB_NAME", "spotify_charts")

CONN_URL = f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(CONN_URL)

PSYCOPG_CONN_STRING = f"host={DB_HOST} port={DB_PORT} dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD}"
# -----------------------------------------------------------

TABLE_NAME = "spotify_charts"

dtype = {
    "title": "string",
    "rank": "Int64",
    "artist": "string",
    "url": "string",
    "region": "category",
    "chart": "category",
    "trend": "category",
    "streams": "Int64"
}
parse_dates = ["date"]

# 2. Leemos solo el primer chunk de 10 filas para conocer la estructura del CSV
df_primer_bloque = pd.read_csv(dir_csv, nrows=10, dtype=dtype, parse_dates=parse_dates)

# 3. Creamos la tabla SOLO si todavía no existe (primera corrida).
#    Si ya existe, la vaciamos con TRUNCATE en vez de recrearla con DROP,
#    porque DROP falla cuando hay vistas de dbt que dependen de esta tabla.
inspector = inspect(engine)
if not inspector.has_table(TABLE_NAME):
    df_primer_bloque.head(n=0).to_sql(
        name=TABLE_NAME,
        con=engine,
        if_exists='fail',
        index=False
    )
    print(f"¡Tabla '{TABLE_NAME}' creada por primera vez!")
else:
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {TABLE_NAME}"))
    print(f"Tabla '{TABLE_NAME}' ya existía: vaciada con TRUNCATE.")

# 4. PROCESO DE CARGA ULTRA RÁPIDO CON NATIVE COPY (Psycopg 3)
tamano_total = os.path.getsize(dir_csv)
tamano_bloque = 1024 * 1024  # bloques de 1MB

with psycopg.connect(PSYCOPG_CONN_STRING) as conn:
    with conn.cursor() as cur:
        with cur.copy(f"COPY {TABLE_NAME} FROM STDIN WITH (FORMAT CSV, HEADER true, DELIMITER ',')") as copy:
            with open(dir_csv, 'r', encoding='utf-8') as f:
                print("Iniciando la carga masiva nativa (COPY)...")

                with tqdm(
                    total=tamano_total,
                    unit='B',
                    unit_scale=True,
                    unit_divisor=1024,
                    desc="Cargando CSV a Postgres"
                ) as barra:
                    while chunk := f.read(tamano_bloque):
                        copy.write(chunk)
                        barra.update(len(chunk.encode('utf-8')))

print("¡Carga masiva completada con éxito!")