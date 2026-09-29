# Modelado de datos con dbt

El modelado de datos se realiza utilizando **dbt (data build tool)** y sigue una arquitectura por capas:

* **Staging:** preparación y estandarización de los datos provenientes de las fuentes.
* **Intermediate:** aplicación de transformaciones y reglas de negocio necesarias para el análisis.
* **Marts:** generación de los modelos finales que serán consumidos por los analistas de datos.

El objetivo de esta estructura es separar claramente las responsabilidades de cada etapa, facilitar el mantenimiento del proyecto y documentar el linaje de los datos.

---

## Detalles del modelado

El esquema utilizado para los modelos de dbt es `analytics`.

Por lo tanto, los modelos pueden consultarse desde PostgreSQL utilizando:

```sql
SELECT *

FROM analytics.nombre_del_modelo;
```

### Arquitectura

```text
raw.spotify_charts
        │
        ▼
stg_spotify_charts
        │
        ▼
int_spotify_charts_top200
        │
        ▼
int_spotify_charts_top200_processed
        │
        ▼
marts_spotify_charts_top200_annual
```

---

## Etapas

### Staging

#### `stg_spotify_charts`

Modelo que toma los datos provenientes de `raw.spotify_charts` y los expone dentro del proyecto dbt.

En esta etapa no se aplican reglas de negocio ni filtros sobre el contenido. Su objetivo principal es establecer una primera capa de acceso y estandarización sobre la fuente.

El modelo se materializa como **VIEW**.

---

### Intermediate

#### `int_spotify_charts_top200`

Modelo que contiene únicamente los registros correspondientes al chart `top200`.

Además, se incorpora la columna `year`, obtenida a partir de `date`.

Este modelo se materializa como **TABLE**, ya que contiene aproximadamente 20 millones de registros y es utilizado como base por las transformaciones posteriores.

Inicialmente se evaluó la creación de un índice sobre:

```text
(region, year)
```

para facilitar las operaciones posteriores relacionadas con la cobertura de regiones por año. Luego de las pruebas de rendimiento, el índice fue descartado.

---

#### `int_spotify_charts_top200_processed`

Aplica las reglas de negocio necesarias para determinar qué regiones serán consideradas válidas para el análisis.

Se mantienen únicamente las regiones que:

1. Aparecen en todos los años disponibles.
2. Alcanzan al menos **200 canciones distintas en cada año**.

La unicidad de una canción se determina mediante la combinación:

```text
(artist, title)
```

Si una región no cumple alguna de estas condiciones en cualquier año, se elimina completamente del conjunto de datos.

Este modelo se materializa como **VIEW**.

---

### Marts

#### `marts_spotify_charts_top200_annual`

Modelo final destinado al análisis.

Primero agrupa la información por:

- año
- región
- artista
- canción

y calcula la suma de `streams` para cada combinación.

A partir de esta agregación, se asigna un ranking mediante `row_number()` para cada combinación de año y región, ordenando las canciones por `total_streams` de forma descendente.

Finalmente, se conservan las **200 canciones con mayor cantidad de streams para cada combinación de año y región**.

La unicidad de una canción se determina mediante la combinación:

```text
(artist, title)
```

---

## Ejecución del proyecto

Una vez configurado el entorno virtual, ejecutar los modelos mediante:

```bash
uv run dbt run
```

Para ejecutar las pruebas definidas en el proyecto:

```bash
uv run dbt test
```

Para ejecutar ambos pasos:

```bash
uv run dbt build
```

### Documentación

Para generar la documentación de dbt:

```bash
uv run dbt docs generate
```

Luego se puede levantar un servidor web local:

```bash
uv run dbt docs serve
```

La documentación permite consultar información sobre los modelos, columnas, tests y el **linaje de datos (DAG)** del proyecto.

---

# Creación y evaluación de índices

Durante el modelado de `spotify_charts` se evaluó la creación de índices con el objetivo de mejorar el rendimiento de las transformaciones posteriores.

Se evaluaron dos alternativas:

1. Un índice parcial sobre la tabla `raw.spotify_charts` para acelerar el filtro `chart = 'top200'`.
2. Un índice sobre `region` y `year` en `int_spotify_charts_top200`, utilizado por las transformaciones posteriores.

Luego de realizar las pruebas de rendimiento, **ninguno de los dos índices fue incorporado al modelo definitivo**.

---

## Evaluación de un índice parcial sobre la tabla raw

También se evaluó la posibilidad de crear un índice parcial sobre `raw.spotify_charts` para acelerar el filtro:

```sql
WHERE chart = 'top200'
```

Se creó y evaluó el siguiente índice parcial:

```sql
CREATE INDEX idx_spotify_charts_top200

ON public.spotify_charts ((1))

WHERE chart = 'top200';
```

Para evaluar su utilidad se utilizó:

```sql
EXPLAIN (ANALYZE, BUFFERS)

SELECT 
    date,
    date_part('year', date) AS year,
    title,
    rank,
    artist,
    url,
    region,
    chart,
    trend,
    streams

FROM public.spotify_charts

WHERE chart = 'top200';
```

La tabla contiene aproximadamente **28,2 millones de registros**, de los cuales **20,3 millones corresponden a `top200`**, aproximadamente el **72% del total**.

### Resultado

**Sin índice:**

```text
Seq Scan on spotify_charts

Rows: 20.321.904

Rows Removed by Filter: 5.851.610

Execution Time: 6777 ms
```

**Con el índice parcial:**

```text
Seq Scan on spotify_charts

Rows: 20.321.904

Rows Removed by Filter: 5.851.610

Execution Time: 2438 ms
```

En ambos casos PostgreSQL eligió un **Sequential Scan**, por lo que el índice no fue utilizado.

La reducción del tiempo de ejecución no se tomó como evidencia de una mejora producida por el índice, ya que el plan de ejecución permaneció sin cambios y la segunda ejecución pudo beneficiarse de datos que ya se encontraban en caché.

### Decisión

No se incorporó el índice parcial a `raw.spotify_charts`.

La principal razón es que `top200` representa aproximadamente el **72% de la tabla**, por lo que recorrer secuencialmente la tabla resulta una estrategia razonable para recuperar un porcentaje tan elevado de sus registros.

Además, `raw.spotify_charts` es una tabla administrada por el proceso de **ingestion** y no por dbt. Incorporar índices en esta capa agregaría mantenimiento al proceso de carga sin que se haya demostrado un beneficio de rendimiento.

---

## Evaluación de un índice en `int_spotify_charts_top200`

El modelo `int_spotify_charts_top200` se materializa como una **TABLE**, ya que representa el subconjunto `top200` que será utilizado por los modelos posteriores.

Inicialmente se evaluó la creación de un índice sobre `region` y `year`:

```sql
{{ config(
    materialized='table',
    indexes=[
        {'columns': ['region', 'year']}
    ]
) }}
```

La elección se basó en que las transformaciones posteriores trabajan principalmente con estas dimensiones, especialmente para validar la cobertura de las regiones a través de los años.

Para determinar si el índice aportaba una mejora real, se ejecutó la transformación completa de `int_spotify_charts_top200_processed` con y sin el índice, utilizando:

```sql
EXPLAIN (ANALYZE, BUFFERS)
```

### Resultado

**Con índice `(region, year)`:**

```text
Seq Scan on int_spotify_charts_top200

Rows: 20.321.904

Execution Time: 21.734 s
```

**Sin índice:**

```text
Seq Scan on int_spotify_charts_top200

Rows: 20.321.904

Execution Time: 21.711 s
```

En ambos casos PostgreSQL utilizó un **Sequential Scan**.

La diferencia de aproximadamente **23 ms (0,1%)** se considera despreciable y no representa una mejora significativa atribuible al índice.

Además, el análisis del plan mostró que el principal costo de la transformación se encuentra en las operaciones de agregación y deduplicación sobre:

```text
year, region, artist, title
```

Una de estas operaciones llegó a utilizar aproximadamente **1 GB de almacenamiento temporal en disco**, por lo que el índice sobre `region` y `year` no ataca el principal cuello de botella de la transformación.

### Decisión

El índice `(region, year)` fue descartado y **no forma parte de la configuración definitiva del modelo**.

La configuración final de `int_spotify_charts_top200` queda simplemente como:

```sql
{{ config(
    materialized='table'
) }}
```

---

## Decisión final

Luego de evaluar ambas alternativas, se decidió **no incorporar índices adicionales** al modelo.

La arquitectura final queda:

```text
raw.spotify_charts
        │
        ▼
stg_spotify_charts
        │
        │ WHERE chart = 'top200'
        ▼
int_spotify_charts_top200
        │
        ▼
int_spotify_charts_top200_processed
        │
        │ Regiones válidas
        ▼
marts_spotify_charts_top200_annual
        │
        │ Agregación + ranking + Top 200
        ▼
Resultado analítico
```

El filtro `chart = 'top200'` se aplica durante la materialización de `int_spotify_charts_top200`.

Las transformaciones posteriores trabajan sobre esta tabla materializada sin índices adicionales. Esta decisión se basa en los resultados obtenidos mediante `EXPLAIN (ANALYZE, BUFFERS)` y evita agregar estructuras de mantenimiento cuyo beneficio no fue demostrado.

---

## Materialización de los modelos

Durante la etapa de desarrollo y validación, algunos modelos se mantienen como `VIEW` para facilitar las pruebas y ajustes de las transformaciones. Una vez finalizado el modelado, los modelos de la capa `marts` se materializarán como `TABLE`, ya que constituyen la capa final de consumo analítico.

La estrategia de materialización adoptada es:

| Modelo                                | Capa         | Materialización | Objetivo                                          |
| ------------------------------------- | ------------ | --------------- | --------------------------------------------------|
| `stg_spotify_charts`                  | Staging      | VIEW            | Exponer y estandarizar la fuente                  |
| `int_spotify_charts_top200`           | Intermediate | TABLE           | Persistir el subconjunto `top200`                 |
| `int_spotify_charts_top200_processed` | Intermediate | VIEW            | Aplicar reglas de negocio                         |
| `marts_spotify_charts_top200_annual`  | Marts        | TABLE           | Generar el Top 200 anual por región para análisis |

Esta decisión busca evitar materializaciones innecesarias y, al mismo tiempo, persistir como tabla el conjunto intermedio de gran volumen que es reutilizado por las transformaciones posteriores.

---

[Volver al inicio](../README.md)
