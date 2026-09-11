# Monitoreo de Infraestructura y Base de Datos

Stack de observabilidad automatizado con **cAdvisor**, **PostgreSQL Exporter**, **Prometheus** y **Grafana**, diseñado para inicializarse mediante aprovisionamiento declarativo sin intervención manual.

---

## 1. Requisitos para Windows / WSL 2 /

Para garantizar que cAdvisor pueda inspeccionar los subsistemas del kernel (**cgroups**) y que el montaje de volúmenes funcione correctamente en Windows:

* **Motor WSL 2 activado**:
  * Abrir Docker Desktop y dirigirse a **Settings > General**.
  * Comprobar que la casilla **Use the WSL 2 based engine** se encuentre tildada.
* **Integración con la distribución de Linux (solo en caso de encontrar problemas, sino dejar como está)**: 
  * En Docker Desktop, ir a **Settings > Resources > WSL Integration**.
  * Activar la casilla de la distribución correspondiente (por ejemplo, `Ubuntu`).
---

## 2. Documentación del Proceso Implementado

El flujo opera bajo un esquema de recopilación basado en sondeo (*pull*):

```text
[ cAdvisor ]           -> expone métricas en :8080 (CPU/RAM de contenedores)
[ postgres_exporter ]  -> expone métricas en :9187 (salud y carga de Postgres)
        │                         │
        └──────────────┬──────────┘
                       ▼ (scrape cada 5s)
               [ Prometheus :9090 ] (Base de datos de series temporales)
                       ▲
                       │ (consulta métricas vía http://prometheus:9090)
               [ Grafana :3000 ]    (Tablero aprovisionado por código)
```

### Componentes de la Arquitectura

1. **Recolección (*Exporters*)**:
* **cAdvisor**: Se ejecuta como contenedor con permisos elevados (`privileged: true`) y acceso de lectura a `/sys` y `/var/run/docker.sock`. Inspecciona los grupos de control del kernel (*cgroups*) para medir el consumo exacto de CPU y memoria de cada contenedor en tiempo de ejecución.
* **postgres_exporter**: Se conecta al motor de base de datos (`pgdatabase:5432`) mediante la variable de entorno `DATA_SOURCE_NAME`. Realiza consultas estadísticas periódicas a los catálogos del motor (`pg_stat_database`, `pg_stat_activity`, etc.) y las expone en `/metrics`.


2. **Almacenamiento (*Prometheus*)**:
* Configurado en `prometheus.yml` para sondear a intervalos regulares (`scrape_interval: 5s`) a los destinos `cadvisor:8080` y `postgres_exporter:9187`. Almacena estas series temporales para su consulta mediante PromQL.


3. **Automatización y Despliegue (*Grafana Provisioning*)**:
* **Datasource automático (`grafana/provisioning/datasources/datasources.yaml`)**: Registra la conexión interna a `http://prometheus:9090` de forma predeterminada al levantar el contenedor.
* **Dashboard automático (`grafana/provisioning/dashboards/dashboards.yaml`)**: Carga el archivo `tablero.json` dentro de Grafana al iniciar el stack, asegurando que cualquier miembro del equipo disponga del panel configurado con sus consultas agregadas (`sum(...) by (name)`).



---

## 3. Diccionario y Glosario de Paneles

### A. Recursos de Hardware por Contenedor (cAdvisor)

* **Uso de CPU por Contenedor (%)**: Porcentaje de tiempo de cómputo consumido por cada contenedor en una ventana móvil de 1 minuto. Permite identificar saturaciones en núcleos de procesador generadas por consultas pesadas o procesos de ingesta continua.


* **Uso de Memoria RAM por Contenedor**: Consumo total de memoria física residente y de página activa ocupada por cada contenedor (expresado en MiB/GiB). Permite vigilar el límite asignado al motor de base de datos y evitar terminaciones abruptas del proceso por falta de memoria (*Out Of Memory Killer*).



---

### B. Salud y Operación de Base de Datos (Dashboard 9628 - PostgreSQL)

#### Conexiones y Concurrencia

* **Active Connections / Connections in Use**: Cantidad de clientes y procesos conectados simultáneamente contra la base de datos en comparación con el límite configurado (`max_connections`).
* **Connection States (Active vs Idle)**: Distribución entre conexiones activas (procesando una consulta en el instante de muestreo) y conexiones inactivas (*idle*, a la espera de nuevas operaciones).
* **Idle in Transaction**: Conexiones que iniciaron un bloque transaccional (`BEGIN`) pero no ejecutaron un comando posterior ni cerraron con `COMMIT`/`ROLLBACK`. Representan un punto crítico de atención ya que retienen bloqueos de tablas y buffers en memoria.

#### Rendimiento y Flujo de Consultas

* **Transactions per Second (TPS)**: Tasa de operaciones confirmadas (`commit`) frente a operaciones abortadas o revertidas (`rollback`) por segundo. Mide la cadencia efectiva de procesamiento de la base de datos.
* **Tuples Read / Written**: Volumen de registros leídos (*fetched* o escaneados secuencialmente) frente a registros insertados, modificados o eliminados por segundo. Permite dimensionar la carga generada por las tareas de ingesta.
* **Cache Hit Ratio (Buffer Cache)**: Porcentaje de lecturas resueltas directamente desde la memoria RAM (*shared buffers*) sin acudir a operaciones de I/O en disco. Valores sostenidos por encima del 95-99% confirman una asignación de memoria adecuada para la carga de trabajo habitual.
* **Block I/O (Read vs Hit)**: Proporción por segundo de bloques de datos recuperados desde el disco rígido versus bloques servidos inmediatamente desde la caché.

#### Bloqueos e Integridad

* **Locks**: Cantidad y tipo de bloqueos concurrentes adquiridos sobre las tablas o índices. Un aumento abrupto en bloqueos exclusivos indica consultas compitiendo por los mismos recursos.
* **Deadlocks**: Frecuencia de interbloqueos mutuos entre dos o más transacciones donde ninguna puede continuar, obligando al motor a abortar una de ellas automáticamente.
* **Database Size**: Espacio total en disco ocupado por el conjunto de esquemas, tablas e índices de la base de datos.

---

## 4. Guía 

### Comandos de Operación y Verificación

* Visualizar los registros de inicio de Grafana:
```bash
docker compose logs grafana
```
### Acceso a las Interfaces

* **Grafana**: `http://localhost:3000` (Acceso al tablero en la sección **Dashboards** | User: admin Pass: admin).
* **Prometheus**: `http://localhost:9090` (Explorador de métricas y validación de *targets*).
* **cAdvisor**: `http://localhost:8080` (Métricas crudas del demonio Docker).