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

### Database Overview (PostgreSQL)

* **Database Size**: Cuantifica el espacio total en disco ocupado por los archivos de la base de datos seleccionada. Permite dimensionar la tasa de crecimiento del almacenamiento y anticipar problemas de capacidad física en el volumen montado.

* **Cache Hit Ratio**: Mide el porcentaje de bloques de datos que el motor resuelve directamente desde la memoria RAM sin recurrir al almacenamiento persistente. Valores sostenidos superiores al 95-99% indican una operación óptima; caídas pronunciadas señalan que las consultas están forzando lecturas a disco por falta de memoria compartida (shared_buffers).

* **Connections by State**: Expone la cantidad de sesiones abiertas clasificadas por su condición operativa (active, idle, idle in transaction). Sirve para supervisar la concurrencia del motor y detectar fugas de conexiones o transacciones bloqueadas sin cerrar en la capa de aplicación.

* **Transactions per Second (TPS)**: Grafica el ritmo de transacciones confirmadas (commits) versus abortadas (rollbacks) por segundo. Permite evaluar el caudal de operaciones transaccionales y detectar anomalías o errores de ejecución en las aplicaciones cliente cuando la tasa de rollbacks se dispara.

* **Tuple Activity per Second**: Monitorea la tasa de filas procesadas por segundo desglosadas por operación (fetched, inserted, updated, deleted). Permite caracterizar la naturaleza de la carga de trabajo, identificando de inmediato si el motor atraviesa picos de lectura intensiva o ingestas masivas de datos.

---

### Infra & Containers (cAdvisor)

* **CPU Usage per Container**: Mide la tasa de procesamiento computacional consumida por cada contenedor en unidades de núcleos (cores). Un valor de 1.0 indica el uso sostenido equivalente a un procesador lógico completo saturado al 100%, lo que permite auditar y dimensionar los límites de CPU requeridos por cada servicio.

* **RAM Working Set per Container**: Refleja la memoria RAM efectiva de la cual el contenedor no puede prescindir sin degradar su ejecución o ser terminado por el sistema (OOM-Killer). A diferencia del uso bruto de memoria, excluye el caché de archivos inactivo del kernel para evitar falsos positivos de saturación.

* **Disk I/O Throughput per Container**: Mide el caudal de lectura y escritura física hacia el almacenamiento expresado en bytes por segundo para cada contenedor. Resulta indispensable para identificar cuellos de botella en operaciones de entrada/salida (I/O wait) originadas por la base de datos u otros servicios persistentes.

* **Network Traffic per Container**: Cuantifica el ancho de banda entrante (RX) y saliente (TX) que atraviesa las interfaces virtuales de red de cada contenedor. Permite auditar el volumen de datos intercambiado entre la base de datos, las herramientas de administración y los clientes de ingesta o consulta.

---

## 4. Guía 

### Comandos de Operación y Verificación

* Visualizar los registros de inicio de Grafana:
```bash
docker compose logs grafana
```
### Acceso a las Interfaces

* **Dashboard Grafana**: `http://localhost:3000` (Acceso al tablero en la sección **Dashboards** | User: admin Pass: admin).
* **Prometheus**: `http://localhost:9090` (Explorador de métricas y validación de *targets*).
* **cAdvisor**: `http://localhost:8080` (Métricas crudas del demonio Docker).