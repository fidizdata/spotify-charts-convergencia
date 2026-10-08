{% docs __overview__ %}

# Modelo de datos — Spotify Charts

Este proyecto contiene el modelado y transformación de datos históricos de **Spotify Charts**, utilizando **dbt** y **PostgreSQL**.

El objetivo es transformar los datos provenientes de las fuentes originales en modelos estructurados, documentados y preparados para su utilización en análisis posteriores.

---

## Arquitectura

El proyecto utiliza una arquitectura de datos organizada por capas, con responsabilidades diferenciadas para cada etapa:

* **Raw:** datos provenientes de las fuentes originales.
* **Staging:** estandarización y preparación inicial de las fuentes.
* **Intermediate:** transformaciones y aplicación de reglas de negocio.
* **Marts:** modelos finales orientados al análisis y consumo de los datos.

Esta arquitectura funciona como una **convención de organización y no como una estructura rígida**. No todos los conjuntos de datos necesariamente deben atravesar todas las capas, y distintos modelos pueden seguir flujos diferentes según sus necesidades.

### Flujo actual — Spotify Charts

Para el dominio de Spotify Charts, el flujo actualmente implementado es:

`raw.spotify_charts`
&nbsp;&nbsp;&nbsp;&nbsp;→&nbsp;&nbsp;&nbsp;&nbsp;
`stg_spotify_charts`
&nbsp;&nbsp;&nbsp;&nbsp;→&nbsp;&nbsp;&nbsp;&nbsp;
`int_spotify_charts_top200`
&nbsp;&nbsp;&nbsp;&nbsp;→&nbsp;&nbsp;&nbsp;&nbsp;
`int_spotify_charts_top200_processed`
&nbsp;&nbsp;&nbsp;&nbsp;→&nbsp;&nbsp;&nbsp;&nbsp;
`marts_spotify_charts_top200_annual`

Este flujo representa los modelos actualmente implementados para este conjunto de datos y podrá ampliarse a medida que se incorporen nuevos modelos analíticos.

---

## Capas del proyecto

### Raw

Contiene los datos provenientes de las fuentes originales.

En el caso de Spotify Charts, la tabla principal es:

`raw.spotify_charts`

Esta capa es administrada por el proceso de ingestión y constituye el punto de entrada de los datos al proyecto.

### Staging

La capa `staging` establece una primera capa de acceso y estandarización sobre las fuentes.

Los modelos de esta capa buscan mantener una transformación mínima, evitando incorporar reglas de negocio específicas.

Modelo actual:

`stg_spotify_charts`

### Intermediate

La capa `intermediate` contiene transformaciones necesarias para preparar los datos antes de su exposición en los modelos finales.

En Spotify Charts actualmente se utilizan:

`int_spotify_charts_top200`

Contiene únicamente los registros correspondientes al chart `top200` e incorpora el año a partir de la fecha del chart.

`int_spotify_charts_top200_processed`

Aplica las reglas de negocio necesarias para determinar las regiones que serán consideradas válidas para el análisis histórico.

### Marts

La capa `marts` contiene los modelos finales orientados al consumo analítico.

Actualmente se encuentra implementado:

`marts_spotify_charts_top200_annual`

Este modelo calcula los streams acumulados por año, región, artista y canción. A partir de esta agregación, selecciona las 200 canciones con mayor cantidad de streams para cada combinación de año y región.

La capa podrá incorporar nuevos marts a medida que se desarrollen nuevos casos de análisis sobre los datos de Spotify.

---

## Reglas principales del modelo actual

Para el análisis histórico del Top 200 se consideran únicamente las regiones que cumplen las siguientes condiciones:

* aparecen en todos los años disponibles;
* cuentan con al menos 200 canciones distintas en cada año;
* una canción se identifica mediante la combinación `(artist, title)`.

Si una región no cumple alguna de estas condiciones en cualquiera de los años disponibles, se elimina completamente del conjunto utilizado para el análisis.

Sobre este conjunto de regiones válidas, el modelo `marts_spotify_charts_top200_annual` calcula los streams acumulados por canción y selecciona las 200 canciones con mayor cantidad de streams para cada combinación de año y región.

Estas reglas buscan generar un conjunto de regiones comparable a lo largo del período analizado.
---

## Materialización

Los modelos utilizan diferentes estrategias de materialización según su función dentro del flujo:

| Capa         | Modelo                                | Materialización |
| ------------ | ------------------------------------- | --------------- |
| Staging      | `stg_spotify_charts`                  | VIEW            |
| Intermediate | `int_spotify_charts_top200`           | TABLE           |
| Intermediate | `int_spotify_charts_top200_processed` | VIEW            |
| Marts        | `marts_spotify_charts_top200_annual`  | TABLE           |

Durante la etapa de desarrollo algunos modelos pueden utilizar `VIEW` para facilitar las pruebas y ajustes. La estrategia de materialización puede modificarse cuando las necesidades de rendimiento o consumo del proyecto lo requieran.

---

## Documentación y calidad de datos

La documentación del proyecto se genera mediante **dbt Docs** y permite consultar:

* descripción de los modelos;
* descripción de las columnas;
* tests de calidad de datos;
* dependencias entre modelos;
* linaje de los datos;
* estructura del DAG.

Las definiciones de modelos, columnas y tests se mantienen junto con el código del proyecto, permitiendo que la documentación evolucione junto con los modelos.

---

## Navegación

Para explorar el proyecto se recomienda comenzar por el DAG y seguir las dependencias desde las fuentes hacia los modelos finales.

Cada modelo contiene información adicional sobre su propósito, columnas y validaciones asociadas.



{% enddocs %}