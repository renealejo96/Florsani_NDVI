# 🛰️ PyGan AgroSat: Documentación Técnica y Metodología del Sistema de Monitoreo Satelital

**Proyecto:** Sistema de Monitoreo Satelital Agrícola Multi-Temporal (Sentinel-2 L2A) de Alta Precisión  
**Predio:** Finca PyGan (250 Bloques | 7,565 Camas Físicas | 36.52 Hectáreas | Campo Abierto)  
**Ubicación:** Ecuador (Lat: `0.142241`, Lon: `-78.393670` | Tile MGRS: `17NQA`)  
**Sistema de Referencia:** WGS 84 / UTM Zone 17S (`EPSG:32717`)  
**Entorno de Producción:** Servidor VPS Ubuntu (Hostinger) en Docker con Gunicorn y Nginx Reverse Proxy (SSL)  
**URL de Producción:** [https://satelital.velezrapp.cloud](https://satelital.velezrapp.cloud)  
**Repositorio Oficial:** [renealejo96/Florsani_NDVI](https://github.com/renealejo96/Florsani_NDVI)  

---

## 📌 1. Resumen Ejecutivo y Alcance

El sistema **PyGan AgroSat** es una plataforma integral de ingeniería de datos geoespaciales y analítica agronómica diseñada para transformar datos satelitales ópticos e infrarrojos de la constelación europea **Sentinel-2** en **decisiones agronómicas operativas a nivel de bloque y cama en campo abierto**.

A diferencia de los enfoques tradicionales (descarga manual de escenas de varios gigabytes):
1. **Arquitectura Cloud-Native:** Extrae exclusivamente las ventanas geográficas (*Windowed Reads*) de los 250 bloques del predio desde el almacenamiento cloud de Microsoft Planetary Computer mediante Cloud-Optimized GeoTIFFs (COGs).
2. **Corrección de Bordes y Ruido Perimetral:** Aplica un búfer negativo de `-5.0 metros` en cada polígono para eliminar zanjas, postes y caminos de servidumbre.
3. **Multiespectralidad y Series Temporales:** Calcula en la misma cuadrícula de 10 metros los índices de vigor vegetal (**NDVI**, **SAVI**) y contenido hídrico de dosel (**NDMI**), además de percentiles de alta resolución (**NDVI P90 - Máximo de Cama**).
4. **Cruce Agronómico Detallado (7,565 Camas):** Procesa el reporte agronómico semanal (`bq_sentinel.csv`), identificando siembras, podas, camas vacías (tumba), ensayos y variedades comerciales.
5. **Detección Dinámica de "Bloques Estrella":** Clasifica automáticamente los bloques 100% puros y homogéneos por cultivo comercial para servir de calibración y verdad de campo.
6. **Mapeo de Cambio Temporal ($\Delta$ Vigor / $\Delta$ Humedad):** Detecta caídas bruscas entre pasadas satelitales consecutivas para priorizar inspecciones de campo.

---

## 🌐 2. Catálogos Satelitales y Fuentes de Datos

### A. Catálogo STAC de Microsoft Planetary Computer
* **Endpoint Base:** `https://planetarycomputer.microsoft.com/api/stac/v1`
* **Colección utilizada:** `sentinel-2-l2a` (Nivel 2A: reflectancia calibrada de fondo de atmósfera o *Bottom-Of-Atmosphere* BOA).
* **Autenticación Cloud:** Librería `planetary_computer.sign_inplace` para firma dinámica de tokens SAS (*Shared Access Signatures*) sobre Azure Blob Storage.
* **Bandas Espectrales Procesadas:**
  * **B04 (Red, 665 nm, 10m):** Absorción de clorofila.
  * **B08 (NIR, 842 nm, 10m):** Reflectancia de la estructura celular del mesófilo foliar.
  * **B11 (SWIR-1, 1610 nm, 20m $\rightarrow$ Remuestreada a 10m vía VRT bilineal):** Absorción por contenido de agua en los tejidos vegetales.
  * **SCL (Scene Classification Layer, 20m $\rightarrow$ Remuestreada a 10m vía vecino más cercano):** Máscara de nubes, sombras de nubes y clasificación de píxeles.

### B. Capa Cartográfica Base
* **Google Satellite / Hybrid:** Mosaicos aéreos de ultra-alta resolución integrados mediante Leaflet.js para comparación visual contra los polígonos vectoriales.

### C. Archivo Agronómico Semanal de Camas (`bq_sentinel.csv`)
* **Registros:** ~8,856 filas detallando actividad (`Siembra`, `Poda`, `VACIO`), cultivo (`PRODUCTO MAESTRO`), variedad élite (`VARIEDADES ELITE`) y número de cama (`# Cama`).
* **Universo Físico:** 230 bloques analizados, 7,565 camas físicas únicas consolidadas.

---

## 🏗️ 3. Arquitectura del Sistema y Módulos de Software

```
┌─────────────────────────────────┐
│       satelital/pygan.shp       │ ──> Geometrías de 250 bloques (ArcGIS EPSG:32717)
└─────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│     procesar_cultivos.py        │ ──> Agrupación cama a cama (7,565 camas),
│     (Cruce con bq_sentinel.csv) │     normalización de Hypericum y filtro de Bloques Estrella
└─────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│     descargar_satelite.py       │ ──> Conexión STAC, extracción de bandas B04/B08/B11/SCL,
│     (ETL Incremental Satelital) │     cálculo zonal NDVI/SAVI/NDMI/P90 por bloque
└─────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│      datos_procesados.json      │ ──> GeoJSON consolidado con 12 fechas históricas,
│     (Base de Datos del Modelo)  │     indicadores espectrales y metadata agronómica
└─────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                        app.py (Flask + Gunicorn)                │
│  - GET /                            : Dashboard Leaflet/Chart   │
│  - GET /api/datos                   : API GeoJSON Consolidada   │
│  - GET /api/satelite/pasadas-recientes : Radar STAC en Vivo     │
│  - GET /api/health                  : Healthcheck de Producción │
└─────────────────────────────────────────────────────────────────┘
```

### Componentes Principales:
1. [`procesar_cultivos.py`](file:////wsl.localhost/Debian/home/rvelez/proyectos/pygan%20%20ndvi/procesar_cultivos.py):
   * De-duplicación física por `# Cama` única para evitar inflar camas en lotes con ensayos o dobles registros.
   * Normalización inteligente de códigos alfanuméricos de *Hypericum* (ej. `17091`, `H21-68-7`, `18125-03`, `Magical...`) clasificándolos bajo el cultivo comercial correcto.
   * Aislamiento de categorías agronómicas: `CULTIVO HOMOGÉNEO`, `100% VACIO / TUMBA`, `SIEMBRA ESCALONADA (<=35% o ~5 camas)`, `COMERCIAL CON ENSAYO (1-6 camas)`, `MIXTO` y `ENSAYOS`.
2. [`descargar_satelite.py`](file:////wsl.localhost/Debian/home/rvelez/proyectos/pygan%20%20ndvi/descargar_satelite.py):
   * Motor incremental para descargar y calcular estadísticas zonales de una sola pasada satelital sin tener que reprocesar los meses previos.
   * Búsqueda automática de nuevas fechas despejadas ($<35\%$ nubes) desde la última registrada hasta hoy.
3. [`actualizar_semanal.py`](file:////wsl.localhost/Debian/home/rvelez/proyectos/pygan%20%20ndvi/actualizar_semanal.py):
   * Script automatizado de actualización agronómica semanal. Vincula los cambios del CSV con las geometrías GIS y, opcionalmente, busca o descarga la pasada satelital más reciente (`--satelite` o `--fecha YYYY-MM-DD`).
4. [`analisis_bloques_estrella.py`](file:////wsl.localhost/Debian/home/rvelez/proyectos/pygan%20%20ndvi/analisis_bloques_estrella.py):
   * Analiza la serie temporal multiespectral de los bloques puros candidatos para calibrar perfiles espectrales base por cultivo.

---

## 🧮 4. Fundamentación Matemática de los Índices Espectrales

$$\text{NDVI} = \frac{\text{NIR} - \text{RED}}{\text{NIR} + \text{RED}} = \frac{\text{B08} - \text{B04}}{\text{B08} + \text{B04}}$$

* **Rango:** $[-1.0, 1.0]$.
* **Propósito:** Mide biomasa fotosintéticamente activa.

$$\text{SAVI} = \frac{\text{NIR} - \text{RED}}{\text{NIR} + \text{RED} + L} \times (1 + L) \quad \text{con } L = 0.5$$

* **Propósito:** Ajuste de suelo para camas abiertas con suelo expuesto o cobertura vegetal intermedia, minimizando la influencia óptica del suelo.

$$\text{NDMI} = \frac{\text{NIR} - \text{SWIR}}{\text{NIR} + \text{SWIR}} = \frac{\text{B08} - \text{B11}}{\text{B08} + \text{B11}}$$

* **Propósito:** Detecta el contenido de agua en la cubierta vegetal y el estrés hídrico previo a que se manifiesten síntomas visuales de marchitamiento o necrosis.

$$\text{NDVI P90 (Máximo de Cama)} = \text{Percentil 90 del NDVI dentro del bloque}$$

* **Propósito:** En campo abierto con camas de $1\text{ m}$ y pasillos de tierra, el promedio general del bloque se diluye por el suelo expuesto. El **P90** captura exclusivamente el $10\%$ de píxeles con dosel vegetal más denso (la cresta de las camas activas), aislando el ruido de los pasillos sin requerir resolución de dron.

$$\Delta \text{ Cambio Temporal} = \text{Índice}(t_k) - \text{Índice}(t_{k-1})$$

* **Propósito:** Detecta caídas severas ($\Delta < -0.06$) ocasionadas por podas, tumbas o problemas sanitarios, y fuertes incrementos ($\Delta > +0.06$) correspondientes a brotes y floraciones.

---

## 🌸 5. Perfiles Espectrales Calibrados por Cultivo

A partir del análisis multitemporal de los **75 bloques puros (87 polígonos GIS)** sin ensayos ni divisiones, se establecieron los siguientes umbrales agronómicos en [`perfiles_calibrados.json`](file:////wsl.localhost/Debian/home/rvelez/proyectos/pygan%20%20ndvi/perfiles_calibrados.json):

| Cultivo Comercial | Bloques Estrella | NDVI Óptimo | Umbral Alerta NDVI | SAVI Típico | NDMI (Humedad) | CV % (Homogeneidad) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **SOLIDAGO** | 21 bloques (23 polígonos) | $0.38 - 0.46$ | $< 0.32$ | $0.32 - 0.37$ | $> 0.08$ | $5\% - 10\%$ (Muy uniforme) |
| **HYPERICUM** | 22 bloques (30 polígonos) | $0.42 - 0.58$ | $< 0.35$ | $0.35 - 0.40$ | $> 0.10$ | $6\% - 22\%$ (Dosel cerrado) |
| **VERONICA** | 16 bloques (16 polígonos) | $0.35 - 0.45$ | $< 0.29$ | $0.29 - 0.35$ | $> 0.06$ | $11\% - 20\%$ |
| **GYPSOPHILA** | 16 bloques (18 polígonos) | $0.27 - 0.33$ | $< 0.24$ | $0.22 - 0.26$ | $> 0.01$ | $3\% - 7\%$ (Follaje fino/blanco) |
| **SUELO / TUMBA** | 53 bloques en descanso | $0.12 - 0.26$ | -- | $0.18 - 0.21$ | $-0.05 \text{ a } 0.01$ | Suelo desnudo base |

---

## ☁️ 6. Historial Satelital y Resolución de la Paradoja de Nubes

El sistema evalúa la nubosidad mediante la banda **SCL** recortada exclusivamente sobre los polígonos de las **36.52 hectáreas** de la finca:

| Fecha Satelital | Satélite | Nubes Regionales (100x100 km) | Nubes Reales en Finca | Estado en Finca |
| :---: | :---: | :---: | :---: | :--- |
| **2026-06-19** | Sentinel-2C | 30.2% | **0.3%** | ☀️ Despejado |
| **2026-07-14** | Sentinel-2B | 45.9% | **0.0%** | ☀️ Cielo 100% Sol |
| **2026-07-29** | Sentinel-2C | 51.0% | **0.0%** | ☀️ Cielo 100% Sol |
| **2026-08-13** | Sentinel-2B | 35.7% | **0.0%** | ☀️ Cielo 100% Sol |
| **2026-09-12** | Sentinel-2B | 53.4% | **0.0%** | ☀️ Cielo 100% Sol |
| **2026-09-17** | Sentinel-2C | 69.1% | **16.4%** | ⛅ Claro Parcial |
| **2026-09-27** | Sentinel-2C | 83.6% | **0.0%** | ☀️ Cielo 100% Sol |
| **2026-09-29** | Sentinel-2A | 88.1% | **0.0%** | ☀️ Cielo 100% Sol |
| **2026-10-09** | Sentinel-2A | 65.6% | **14.9%** | ⛅ Claro Parcial |
| **2026-10-19** | Sentinel-2B | 54.8% | **0.0%** | ☀️ Cielo 100% Sol |
| **2026-10-22** | Sentinel-2B | 30.2% | **0.0%** | ☀️ Cielo 100% Sol |
| **2026-10-27** | Sentinel-2C | 10.1% | **0.0%** | ☀️ Cristalino (100% Sol) |

> **Conclusión Científica:** Un filtro regional tradicional habría descartado tomas espectaculares como el 27 y 29 de septiembre (con $>80\%$ regional). El análisis de píxeles SCL locales demostró que la finca tenía **0.0% de nubes**, recuperando observaciones cruciales de crecimiento.

---

## 🖥️ 7. Funcionalidades del Dashboard Frontend

1. **Mapa Interactivo Leaflet:**
   * **Modo Pantalla Completa:** Botón flotante para auditoría en reuniones o salas de control.
   * **Etiquetas Permanentes de Bloques:** Switch para encender/apagar nombres de bloques directamente sobre el mapa sin necesidad de hacer hover.
   * **Renderizado Inteligente de Tumbas:** Los bloques vacíos o en preparación se muestran transparentes con borde punteado tenue, evitando que el mapa se tiña de rojo falsamente.
   * **Mapa de Cambio ($\Delta$):** Rampa divergente de 5 colores (Verde: Crecimiento $\rightarrow$ Gris: Estable $\rightarrow$ Rojo: Caída) con tarjetas KPI dinámicas de lotes en aumento y pérdida.
2. **Tabla de Priorización Agronómica:**
   * Ordenamiento jerárquico automático de 3 niveles:
     1. Bloques en Alerta de Vigor / Estrés hídrico primero.
     2. Agrupación por Flor / Cultivo.
     3. Orden natural del número de bloque (ej. 1, 2, 10 en vez de 1, 10, 2).
3. **Modal de Bloques en Alerta con Redirección:**
   * Lista detallada de lotes comprometidos con botón **"Ver en Mapa"** que cierra el modal, centra el bloque con zoom automático y hace scroll suave directo al visor.
4. **Radar Satelital en Vivo:**
   * Consulta directa al catálogo STAC mostrando las próximas pasadas de Sentinel-2 para planificar la siguiente actualización.

---

## 🚀 8. Arquitectura de Despliegue en Producción

* **Entorno:** Servidor VPS Hostinger (Ubuntu 24.04 LTS).
* **Contenedorización:** Docker & Docker Compose con reinicio `unless-stopped`.
* **Servidor de Aplicaciones:** Gunicorn WSGI con 3 workers concurrentes (`--timeout 120`).
* **Puerto de Servicio:** `5055` (personalizado para evitar colisiones con puertos 80, 443, 3000, 5000, 8080).
* **Reverse Proxy:** Nginx gestionando el tráfico público en los puertos 80 y 443.
* **Seguridad SSL:** Certificados automáticos Let's Encrypt mediante Certbot con redirección HTTPS forzada en `https://satelital.velezrapp.cloud`.
* **Persistencia de Datos:** Volúmenes montados para `datos_procesados.json`, `bq_sentinel.csv`, `cultivos_por_bloque.json` y `satelital/`, permitiendo actualizaciones inmediatas con `git pull` sin necesidad de reconstruir la imagen de Docker.

---

## 🔬 9. Próxima Fase: Clasificación a Nivel de Píxel con Random Forest

### Estado Actual del Manejo de Suelo vs Cultivo:
1. El **Búfer Negativo de -5m** elimina el ruido exterior del polígono (caminos, zanjas).
2. El índice **SAVI** mitiga el efecto del fondo de suelo en lotes con cobertura parcial.
3. El **NDVI P90** extrae la reflectancia de las camas con mayor dosel foliar, aislando los pasillos interlínea.
4. Las reglas agronómicas aíslan lotes con $\le 35\%$ de siembra activa y lotes en tumba.

### Hoja de Ruta para el Modelo Random Forest:
Con los **75 bloques estrella puros** y los **53 bloques en tumba**, ya se cuenta con el **Ground Truth (verdad de campo etiquetada)** para entrenar un clasificador supervisado:
* **Entradas (Features):** Bandas $B04, B08, B11$, índices $NDVI, SAVI, NDMI$ y sus ratios espectrales.
* **Clases de Salida:**
  1. `VEGETACION_CULTIVO` (Dosel denso de flor de verano).
  2. `SUELO_DESNUDO_PASILLO` (Suelo interlínea y descanso).
  3. `SOMBRA_VEGETAL` (Zonas de sombra proyectada por el follaje).
* **Beneficio:** Permitirá calcular el porcentaje exacto de cobertura vegetal neta píxel a píxel dentro de cada bloque sin importar la separación de las camas.

---

*Documentación técnica actualizada para PyGan AgroSat (Finca PyGan / Florsani NDVI).*
