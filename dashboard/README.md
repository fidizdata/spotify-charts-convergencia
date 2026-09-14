# Módulo Dashboard - Proximidad Musical

Aplicación interactiva construida con **Dash** y **Plotly** para visualizar los patrones de similitud en los charts de Spotify, permitiendo comparar distintos países y clusters a lo largo de los años.

## Funcionalidades Principales
* **Mapa de Proximidad (MST):** Grafo interactivo basado en similitud de coseno y árboles de expansión mínima para visualizar la cercanía de gustos musicales entre países, con tamaños de nodo proporcionales al volumen de *streams*.
* **Filtros por Región y Año:** Sliders temporales y botones interactivos para aislar clústeres geográficos (América Latina, Europa, Norteamérica & Oceanía, Asia).
* **Paneles de Detalle:** Visualización en tiempo real del Top de Artistas y Top de Canciones correspondientes al país o nodo seleccionado en el grafo.

## Librerias
* **Dash**: Framework de la interfaz web.
* **Plotly**: Renderizado de gráficos interactivos.
* **Pandas**: Procesamiento y filtrado de datos tabulares.
* **Pathlib**: Manejo de rutas.

## Pipeline y Ejecución

Asegurate de estar posicionado en la carpeta `dashboard/` donde se encuentra el entorno de `uv`. El flujo recomendado es:

1. **Generar el dataset procesado:**
   Ejecutá el script de preprocesamiento para transformar los datos crudos (ubicados en `data/raw/`) y generar el archivo anual listo para consumir:
   ```bash
   uv run preprocesamiento_dataraw.py
2. **Levantar la aplicación:**
    Una vez generado el dataset, iniciá el servidor del dashboard ejecutando:
    ```bash
    uv run app.py