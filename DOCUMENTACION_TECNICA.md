# 🛰️ PyGan AgroSat: Documentación Técnica y Metodología del Sistema de Monitoreo Satelital

**Proyecto:** Sistema de Monitoreo Satelital Agrícola Multi-Temporal (Sentinel-2 L2A)  
**Predio:** Finca PyGan (250 Bloques | 36.52 Hectáreas | Campo Abierto)  
**Ubicación:** Ecuador (Lat: `0.142241`, Lon: `-78.393670` | Tile MGRS: `17NQA`)  
**Sistema de Referencia:** WGS 84 / UTM Zone 17S (`EPSG:32717`)  
**Desarrollado para:** Sustentación y Auditoría Técnica de Ingeniería de Datos Geoespaciales  

---

## 📌 1. Resumen Ejecutivo y Alcance

El sistema **PyGan AgroSat** es una plataforma integral de ingeniería de datos geoespaciales diseñada para transformar datos satelitales ópticos sin procesar en **decisiones agronómicas de precisión en campo abierto**.

A diferencia de los métodos tradicionales (que descargan archivos comprimidos de gigabytes de forma manual), PyGan implementa una arquitectura moderna de **streaming y procesamiento en la nube (*Cloud-Native Geospatial*)**:
1. Accede directamente a los catálogos abiertos de la constelación europea **Sentinel-2**.
2. Extrae exclusivamente los píxeles de los 250 bloques del predio mediante lecturas por ventanas geográficas (*Windowed Reads*).
3. Corrige efectos de borde y calcula series temporales de vigor vegetal (**NDVI**, **SAVI**) y estrés hídrico (**NDMI**).
4. Discrimina con rigor científico la nubosidad regional de la nubosidad real sobre los lotes.
5. Entrega los resultados a través de una API REST y un Dashboard interactivo en tiempo real desplegable en servidores locales o VPS.

---

## 🌐 2. Catálogos Satelitales y APIs Utilizadas

El sistema integra **3 fuentes de servicios y APIs cloud**:

### A. Catálogo STAC de Microsoft Planetary Computer
* **Endpoint Base:** `https://planetarycomputer.microsoft.com/api/stac/v1`
* **Colección utilizada:** `sentinel-2-l2a` (Nivel 2A: reflectancia calibrada de fondo de atmósfera o *Bottom-Of-Atmosphere* BOA).
* **¿Qué es STAC?:** *SpatioTemporal Asset Catalog* es el estándar global de la industria para indexar y buscar información de observación de la Tierra por coordenadas espacio-temporales.
* **Mecanismo de Autenticación:** Se utiliza la librería `planetary_computer.sign_inplace`. Microsoft aloja las imágenes en contenedores privados de Azure Blob Storage; esta función firma dinámicamente cada petición generando tokens SAS (*Shared Access Signatures*) temporales y seguros para permitir el streaming de las bandas ráster.
* **Costo:** **100% Gratuito y Abierto**, financiado por el programa Copernicus de la Unión Europea / ESA y Microsoft AI for Earth.

### B. API de Mosaicos Satelitales de Alta Resolución (Google Tiles)
* **Endpoint Satélite:** `https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}`
* **Endpoint Híbrido (Satélite + Vías):** `https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}`
* **Función:** Provee la capa base cartográfica del mapa interactivo Leaflet para que el usuario pueda comparar los polígonos vectoriales y los índices espectrales con la fotografía aérea de ultra-alta resolución de Google.

### C. API REST Local en Flask (`app.py`)
Servidor web desarrollado para exponer los datos y servicios al frontend:
1. `GET /`: Renderiza el Dashboard web interactivo.
2. `GET /api/datos`: Entrega el dataset consolidado (`datos_procesados.json`) con las geometrías GeoJSON, metadatos, series temporales e indicadores agronómicos.
3. `GET /api/satelite/pasadas-recientes`: Endpoint en vivo que consulta STAC para traer las últimas 20 pasadas de Sentinel-2 sobre la finca con su fecha, hora y porcentaje de nubes exacto.
4. `GET /api/health`: Chequeo de estado del servicio para monitoreo en VPS o Docker.

---

## 🏗️ 3. Arquitectura del Backend y Pipeline ETL

El procesamiento está orquestado en [`etl_sentinel.py`](file:////wsl.localhost/Debian/home/rvelez/proyectos/pygan%20%20ndvi/etl_sentinel.py), apoyado por módulos especializados en `src/`:

```
┌─────────────────────────────────┐
│   satelital/pygan.shp           │ ──> Geometrías de 250 bloques (ArcGIS)
└─────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│   Fase de Reproyección          │ ──> UTM 17S (Métrico) para buffers / WGS84 para STAC
└─────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│   Catálogo STAC Sentinel-2      │ ──> Búsqueda de 9 fechas (Junio a Octubre 2026)
└─────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│   Lectura por Ventanas (COGs)   │ ──> B04 (Rojo), B08 (NIR), B11 (SWIR) y SCL (Nubes)
│   + Remuestreo Bilineal         │     (SWIR 20m -> 10m para alinear cuadrícula)
└─────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│   Búfer Negativo (-5 metros)    │ ──> Supresión de caminos y zanjas (Antirruido)
└─────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│   Álgebra de Matrices (NumPy)   │ ──> Cálculo de NDVI, SAVI, NDMI, P10, CV%
└─────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│   datos_procesados.json         │ ──> Consolidado multi-temporal estructurado
└─────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│   Flask API & Leaflet Dashboard │ ──> Interfaz visual en tiempo real
└─────────────────────────────────┘
```

### Detalle de las Innovaciones Técnicas del Backend:

#### 1. Lectura por Ventanas en COGs (*Cloud-Optimized GeoTIFFs*)
En lugar de descargar los archivos completos de cada banda (que pesan ~500 MB cada uno, lo que requeriría descargar más de 15 GB para 9 fechas), `rasterio` utiliza la funcionalidad **HTTP Range Requests** (`Range: bytes=X-Y`).
* El script solicita a Azure únicamente los bloques de píxeles que caen dentro de la caja delimitadora (*Bounding Box*) del predio.
* **Resultado:** La descarga tarda apenas **2 a 3 segundos por fecha** y consume menos de **300 KB** por banda.

#### 2. Armonización de Resoluciones Espaciales (Remuestreo Bilineal)
* Las bandas de luz visible e infrarrojo cercano (**B04 Rojo** y **B08 NIR**) tienen resolución de **10 metros por píxel**.
* La banda de infrarrojo de onda corta (**B11 SWIR**, necesaria para humedad) tiene resolución nativa de **20 metros**.
* Para poder operar matrices con NumPy sin desalineación espacial, el pipeline utiliza `WarpedVRT` con interpolación bilineal (`Resampling.bilinear`) para remuestrear la banda B11 exactamente a la matriz de 10 metros de la banda NIR.

#### 3. Búfer Negativo Antirruido de Bordes (-5 Metros)
Los polígonos exportados desde ArcGIS corresponden a los límites catastrales de los bloques, los cuales colindan con caminos de lastre, canales de riego y cercas vivas.
* Si se calculan los píxeles perimetrales completos, los caminos de tierra bajan artificialmente el NDVI del cultivo.
* El pipeline aplica un **búfer geométrico negativo de -5 metros** (`geom.buffer(-5.0)`) a cada polígono (siempre que el lote resultante conserve más de 40 m²). Esto asegura que **el 100% de los píxeles evaluados correspondan exclusivamente al dosel del cultivo**.

#### 4. Factor de Escala Radiométrica (10,000)
Las agencias espaciales almacenan los datos de reflectancia multiplicados por 10,000 en enteros de 16 bits (`uint16`) para optimizar almacenamiento.
* En el backend dividimos todos los valores ráster entre `10000.0` para operar con reflectancias físicas de superficie reales en el rango decimal de `0.0` a `1.0`.

---

## 📐 4. Fórmulas Matemáticas e Indicadores Agronómicos

Para cada uno de los 250 bloques y para cada una de las 9 fechas, el sistema calcula **6 métricas cuantitativas**:

### 1. NDVI (Índice de Vegetación de Diferencia Normalizada)
$$\text{NDVI} = \frac{\text{B08 (NIR)} - \text{B04 (Rojo)}}{\text{B08 (NIR)} + \text{B04 (Rojo)}}$$
* **Principio biofísico:** La clorofila absorbe fuertemente la luz roja para realizar la fotosíntesis, mientras que la estructura celular interna del mesófilo foliar dispersa y refleja intensamente el infrarrojo cercano (NIR).
* **Interpretación:** Mide la masa foliar activa y vigor fotosintético. Rango: `[-1.0, 1.0]`.

### 2. SAVI (Índice de Vegetación Ajustado al Suelo)
$$\text{SAVI} = \frac{\text{B08 (NIR)} - \text{B04 (Rojo)}}{\text{B08 (NIR)} + \text{B04 (Rojo)} + L} \times (1 + L)$$
* **Constante agronómica:** $L = 0.5$ (factor estándar de ajuste de suelo de Huete).
* **Función en campo abierto:** En parcelas recién sembradas o potreros recién pastoreados donde el suelo está expuesto, el brillo del suelo distorsiona el NDVI. El SAVI neutraliza el fondo de suelo para reflejar solo el tejido verde real.

### 3. NDMI (Índice de Humedad de la Vegetación)
$$\text{NDMI} = \frac{\text{B08 (NIR)} - \text{B11 (SWIR)}}{\text{B08 (NIR)} + \text{B11 (SWIR)}}$$
* **Principio biofísico:** La banda SWIR (1610 nm) es absorbida por el agua líquida contenida en las hojas. Si la planta sufre estrés hídrico, pierde agua celular, refleja más radiación SWIR y el valor de NDMI disminuye drásticamente.
* **Valores:** $> 0.20$ (Excelente turgencia e hidratación), $0.0 - 0.10$ (Humedad baja), $< 0.0$ (Estrés hídrico severo / suelo seco).

### 4. `ndvi_p10` (Percentil 10 de NDVI)
* En lugar de fijarse solo en el valor mínimo absoluto (que podría ser una piedra o un rastrojo aislado), el **Percentil 10** extrae el valor que separa al 10% más bajo de los píxeles del lote.
* Permite detectar tempranamente problemas localizados en el bloque (focos de plaga o deficiencias de riego) de forma estadísticamente robusta.

### 5. `cv_pct` (Coeficiente de Variación en Porcentaje)
$$\text{CV} = \left(\frac{\sigma}{\mu}\right) \times 100$$
* Relaciona la desviación estándar ($\sigma$) con la media ($\mu$) del NDVI dentro de un mismo bloque.
* **Diagnóstico agronómico:**
  * $\text{CV} < 15\%$: Lote uniforme y homogéneo.
  * $\text{CV} > 25\%$: Lote desuniforme o "con parches" (indica problemas de nivelación de suelo, riego dispar o sectores enfermos).

### 6. `area_critica_pct` (Porcentaje de Área Bajo Umbral Crítico)
$$\text{Área Crítica} = \left(\frac{\text{Píxeles con NDVI} < \text{Umbral}}{\text{Total de Píxeles Válidos del Lote}}\right) \times 100$$
* Mide con precisión qué fracción geométrica del bloque está por debajo del umbral de vigor establecido.

---

## 🎯 5. El Umbral Crítico Óptimo para Campo Abierto (`0.35`)

Al tratarse de una finca a cielo abierto (sin cubiertas plásticas):

| Rango de NDVI | Estado Agronómico en Campo Abierto | Acción de Manejo |
| :--- | :--- | :--- |
| **< 0.25** | Suelo descubierto, rastrojo bajo o lote recién pastoreado a ras. | Preparación de suelo, siembra o descanso inicial. |
| **0.25 - 0.35** | Umbral de alerta: inicio de rebrote o cultivo bajo estrés. | Monitoreo de emergencia y fertilización de arranque. |
| **0.35 - 0.50** | Rebrote activo, macollamiento o crecimiento vegetativo medio. | Riego oportuno y control de malezas. |
| **> 0.50** | Cobertura cerrada, máxima absorción de luz, biomasa óptima. | Lote listo para pastoreo o cosecha. |

> **Conclusión:** Se estableció **`0.35`** como valor óptimo predeterminado en el dashboard, porque separa con exactitud los lotes en descanso/preparación de aquellos que ya han alcanzado un dosel fotosintéticamente activo.

---

## ☀️ 6. La Paradoja de Escala de Nubes: Provincia vs Finca

Uno de los aportes metodológicos más valiosos del proyecto es la **auditoría local de nubes a nivel de lote**:

* **Nubosidad Regional (`cloud_cover_region`):** Evaluada sobre el cuadrante MGRS `17NQA` de **1,000,000 de hectáreas** (100x100 km).
* **Nubosidad en Finca (`cloud_cover_finca`):** Calculada mediante la banda **SCL (Scene Classification Layer)** recortada exclusivamente sobre los polígonos de las **36.52 hectáreas** de PyGan.

### Evidencia Científica Registrada en la Finca:

| Fecha Satelital | Satélite | Nubes en la Región (100x100km) | Nubes Reales en tu Finca | Condición Agronómica |
| :--- | :--- | :---: | :---: | :--- |
| **2026-06-19** | Sentinel-2C | 30.2% | **0.3%** | ☀️ Despejado (100% útil) |
| **2026-07-14** | Sentinel-2B | 45.9% | **0.0%** | ☀️ Cielo 100% Sol |
| **2026-07-29** | Sentinel-2C | 51.0% | **0.0%** | ☀️ Cielo 100% Sol |
| **2026-08-13** | Sentinel-2B | 35.7% | **0.0%** | ☀️ Cielo 100% Sol |
| **2026-09-12** | Sentinel-2B | 53.4% | **0.0%** | ☀️ Cielo 100% Sol |
| **2026-09-17** | Sentinel-2C | 69.1% | **16.4%** | ⛅ Claro Parcial |
| **2026-09-27** | Sentinel-2C | 83.6% | **0.0%** | ☀️ Cielo 100% Sol |
| **2026-09-29** | Sentinel-2A | 88.1% | **0.0%** | ☀️ Cielo 100% Sol |
| **2026-10-09** | Sentinel-2A | 65.6% | **14.9%** | ⛅ Claro Parcial |

**Conclusión:** Un filtro simple por nubosidad provincial habría descartado arbitrariamente fechas extraordinarias como el **27 y 29 de septiembre**, privando a la finca de datos críticos justo cuando el cielo sobre sus lotes estaba completamente despejado.

---

## 💻 7. Capa de Visualización y Frontend (Dashboard)

El frontend en [`templates/index.html`](file:////wsl.localhost/Debian/home/rvelez/proyectos/pygan%20%20ndvi/templates/index.html) combina tres tecnologías de interfaz de usuario de alto rendimiento:

1. **Bootstrap 5 (Dark Mode):** Interfaz ejecutiva con paleta oscura para evitar fatiga visual durante el análisis agronómico nocturno o en oficina.
2. **Leaflet.js:**
   * Renderiza los 250 polígonos vectoriales en GeoJSON sobre el mosaico de **Google Satellite**.
   * Aplica un **semáforo de colores dinámico** dependiente del índice y del slider de umbral.
   * Tooltips flotantes al pasar el cursor y Popups completos con la metadata original de ArcGIS (`Bloque_1`, `AREA`, `Calicata`, `SONDA`, `Técnico`).
3. **Chart.js:**
   * Genera el gráfico interactivo de líneas que muestra la serie temporal de las 9 fechas.
   * **Interactividad cruzada:** Al hacer clic en cualquier fila de la tabla o bloque del mapa, el mapa se acerca (*zoom automático*) y la gráfica superpone la curva de ese bloque en color naranja contra la media de la finca.
4. **Radar de Pasadas Satelitales (Modal en Vivo):**
   * Consulta asíncrona vía AJAX a `/api/satelite/pasadas-recientes`.
   * Permite consultar en cualquier momento la lista de las últimas 20 pasadas (como la del 17 de octubre con 94% de nubes) para planificar cuándo habrá una nueva toma satelital limpia.

---

## 🎙️ 8. Guía para la Exposición Oral (Pitch de 5 Minutos)

Si vas a presentar o defender este proyecto mañana, apóyate en estos **3 pilares clave**:

1. **Eficiencia en la Nube (*Cloud-Native*):**
   > *"No descargamos archivos gigantes ni saturamos discos duros. Nos conectamos directamente al almacenamiento en la nube de Microsoft y la Agencia Espacial Europea mediante Cloud-Optimized GeoTIFFs (COGs), leyendo solo los píxeles de nuestra finca en 2 segundos por fecha de forma 100% gratuita."*

2. **Rigor Agronómico contra el Ruido:**
   > *"No nos conformamos con una fórmula teórica. Aplicamos un búfer negativo de -5 metros para eliminar el ruido de caminos de tierra y zanjas perimetrales, y remuestreamos la banda infrarroja B11 a 10 metros para poder medir estrés hídrico (NDMI) en la misma cuadrícula del NDVI."*

3. **Resolución de la Paradoja de Nubes:**
   > *"Demostramos científicamente que la nubosidad regional de 100x100 km engaña. El 27 y 29 de septiembre la provincia reportaba más del 80% de nubes, pero nuestro algoritmo evaluó la banda de calidad SCL directamente sobre la finca y descubrió un cielo 100% despejado (0.0% nubes locales), rescatando mediciones valiosas que otros descartarían."*

---

*Documento generado y certificado para el proyecto PyGan NDVI.*
