"""
Módulo de Configuración Centralizada para el Pipeline PyGan NDVI.
Define rutas, parámetros de satélite (Sentinel-2 L2A), códigos de bandas y metadatos.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set

@dataclass(frozen=True)
class SCLClasses:
    """
    Clasificación de Escena de Sentinel-2 L2A (Scene Classification Layer - SCL).
    Permite discernir nubes, sombras, vegetación y suelo a nivel de píxel (20m nativo).
    """
    NO_DATA: int = 0
    SATURATED_OR_DEFECTIVE: int = 1
    DARK_AREA_PIXELS: int = 2
    CLOUD_SHADOWS: int = 3
    VEGETATION: int = 4
    NOT_VEGETATED: int = 5
    WATER: int = 6
    UNCLASSIFIED: int = 7
    CLOUD_MEDIUM_PROBABILITY: int = 8
    CLOUD_HIGH_PROBABILITY: int = 9
    THIN_CIRRUS: int = 10
    SNOW: int = 11

    # Clases que representan nubes, sombras o datos inválidos que deben ser enmascarados (NaN)
    MASK_VALUES: Set[int] = field(default_factory=lambda: {0, 1, 3, 8, 9, 10, 11})

    # Clases confiables para vegetación y suelo agrícola
    CLEAR_LAND_VALUES: Set[int] = field(default_factory=lambda: {4, 5, 6, 7})


@dataclass
class PipelineConfig:
    """Configuración principal del pipeline de teledetección agrícola."""
    # Rutas base
    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    raw_data_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data" / "raw")
    processed_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data" / "processed")
    outputs_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data" / "outputs")
    
    # Insumo vectorial original de la finca (AOI)
    shapefile_path: Path = field(
        default_factory=lambda: (
            Path(__file__).resolve().parent.parent / "satelital" / "Pygan.shp"
            if (Path(__file__).resolve().parent.parent / "satelital" / "Pygan.shp").exists()
            else Path(__file__).resolve().parent.parent / "satelital" / "pygan.shp"
        )
    )

    # Catálogo STAC (Microsoft Planetary Computer)
    stac_api_url: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    collection: str = "sentinel-2-l2a"

    # Parámetros de búsqueda y filtros
    target_crs: str = "EPSG:32717"  # WGS 84 / UTM Zone 17S (CRS métrico nativo del predio)
    max_scene_cloud_cover: float = 60.0  # % máximo de nubes global en la escena (100x100km)
    max_aoi_cloud_cover: float = 25.0    # % máximo de nubes local sobre los lotes agrícolas

    # Mapeo de bandas de Sentinel-2 L2A requeridas para índices agrícolas
    # B02: Azul (490 nm, 10m) - EVI
    # B03: Verde (560 nm, 10m) - GNDVI
    # B04: Rojo (665 nm, 10m) - NDVI, EVI, SAVI
    # B05: Red Edge 1 (705 nm, 20m) - NDRE
    # B08: NIR Amplio (842 nm, 10m) - NDVI, EVI, SAVI, NDWI
    # B8A: NIR Estrecho (865 nm, 20m)
    # B11: SWIR 1 (1610 nm, 20m) - Humedad de dosel (NDMI/NDWI)
    # SCL: Scene Classification Layer (20m) - Máscara de calidad y nubes
    band_assets: Dict[str, str] = field(default_factory=lambda: {
        "blue": "B02",
        "green": "B03",
        "red": "B04",
        "rededge": "B05",
        "nir": "B08",
        "nir_narrow": "B8A",
        "swir": "B11",
        "scl": "SCL"
    })

    # Factor de escala de reflectancia de Sentinel-2 L2A (10,000 para convertir a rango 0.0 - 1.0)
    reflectance_scale_factor: float = 10000.0

    # Constantes agronómicas para índices
    savi_l_factor: float = 0.5  # Factor L de ajuste de suelo para SAVI
    evi_g_factor: float = 2.5   # Factor de ganancia para EVI
    evi_c1_factor: float = 6.0  # Coeficiente aerosol rojo para EVI
    evi_c2_factor: float = 7.5  # Coeficiente aerosol azul para EVI
    evi_l_factor: float = 1.0   # Ajuste de fondo de dosel para EVI

    def ensure_directories(self) -> None:
        """Crea los directorios de datos si no existen."""
        for path in [self.raw_data_dir, self.processed_dir, self.outputs_dir]:
            path.mkdir(parents=True, exist_ok=True)
