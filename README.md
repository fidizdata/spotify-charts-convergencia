# Setup del proyecto — Spotify Charts

Guía para clonar el repo y dejar todo funcionando en tu PC: base de datos, ingesta del CSV y transformaciones con dbt.

## Objetivo del Proyecto
Construir un pipeline de datos robusto, contenerizado y reproducible para procesar, almacenar y transformar el histórico de los charts de Spotify. 

El flujo comprende:
1. **Ingesta y Almacenamiento:** Volcado automatizado de archivos CSV masivos hacia una base de datos relacional (PostgreSQL) usando contenedores de Docker.
2. **Modelado y Transformación:** Limpieza y estructuración de los datos mediante dbt para habilitar consultas analíticas complejas y eficientes.

## Requisitos previos

- Docker Desktop instalado y corriendo
- [uv](https://docs.astral.sh/uv/) instalado
- Git

## 1. Clonar el repo

```
git clone <url-del-repo>
cd <nombre-carpeta-proyecto>
```

## 2. Poner el CSV en su lugar

Copiá el archivo `spotify_charts.csv` dentro de:

```
data/raw/spotify_charts.csv
```

Esta carpeta no viene en el repo (está en `.gitignore` porque el archivo pesa varios GB), así que tenés que crearla vos si no existe.

## 3. Levantar Postgres y pgAdmin

Pará en la carpeta `infra/`:

```
cd infra
docker compose up -d
```

Esto levanta dos contenedores: la base Postgres y pgAdmin. El `-d` los deja corriendo en segundo plano.

Para chequear que están arriba:

```
docker ps
```

Deberías ver dos contenedores corriendo.

## 4. Configurar las variables de entorno de la ingesta

Andá a `infra/ingesta/` y creá un archivo `.env` (hay un `.env.example` como referencia, copialo y completalo):

```
cd ingesta
```

El `.env` debe tener:

```
DB_HOST=pgdatabase
DB_PORT=5432
DB_USER=admin
DB_PASSWORD=admin
DB_NAME=spotify_charts
DATA_DIR=/data
```

> Importante: `DB_HOST` acá va como el nombre del servicio de Docker (`pgdatabase` o el que hayan definido en el `docker-compose.yml`), **no** `localhost` — porque este `.env` lo va a leer un proceso que corre *dentro* de otro contenedor, en la misma red de Docker.

## 5. Construir la imagen de ingesta

Parado en `infra/ingesta/`:

```
docker build -t spotify_charts_ingest:latest .
```

## 6. Correr la ingesta

Todavía parado en `infra/ingesta/`:

```
docker run -it --rm --network=infra_default --env-file .env -v "${PWD}/../../data:/data" spotify_charts_ingest:latest
```

Esto carga el CSV completo en la tabla `spotify_charts` de Postgres. Con un archivo de varios GB puede tardar varios minutos — vas a ver una barra de progreso con el tiempo estimado. Podés correr este comando las veces que quieras: si la tabla ya existe, la vacía y la vuelve a cargar (no rompe nada si ya corriste dbt antes).

## 7. Configurar dbt

Andá a la carpeta del proyecto dbt:

```
cd ../../dbt_project
```

Sincronizá el entorno (instala dbt y todas las dependencias con las versiones exactas del lockfile):

```
uv sync
```

### Configurar la conexión de dbt

dbt necesita un archivo `profiles.yml` que **no viene en el repo** (tiene credenciales, por eso está afuera). Corré:

```
uv run dbt init
```

Cuando te pregunte, respondé:

- **host**: `localhost` (acá sí, porque dbt corre en tu PC, no dentro de Docker — se conecta al puerto que Postgres expone hacia afuera)
- **port**: `5432`
- **user**: `admin`
- **password**: `admin`
- **dbname**: `spotify_charts`
- **schema**: `analytics`
- **threads**: `1`

## 8. Probar la conexión

```
uv run dbt debug
```

Tiene que decir "All checks passed!" al final. Si falla, lo más común es un typo en host/puerto/usuario, o que Postgres no esté corriendo (revisá el paso 3).

## 9. Correr las transformaciones

```
uv run dbt build
```

Esto corre todos los modelos y todos los tests de una. Si todo pasa en verde, ya tenés la base completa transformada y lista para consultar (por ejemplo desde pgAdmin, en `http://localhost:<puerto-pgadmin>`, o directo con Python).

## Resumen del orden completo

```
docker compose up -d              (desde infra/)
docker build -t ... .             (desde infra/ingesta/)
docker run ...                    (desde infra/ingesta/, carga el CSV)
uv sync                           (desde dbt_project/)
uv run dbt init                   (una sola vez, configura profiles.yml)
uv run dbt debug                  (verifica conexión)
uv run dbt build                  (corre todo dbt)
```
