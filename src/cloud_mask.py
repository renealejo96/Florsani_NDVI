"""
Módulo de Enmascaramiento de Nubes, Sombras y Calidad Radiométrica (SCL).
Filtra píxeles contaminados y calcula el porcentaje de nubosidad efectivo sobre el predio.
"""

from typing import Dict, Optional, Tuple
import numpy as np
import rasterio
from rasterio.features import geometry_mask
import geopandas as gpd

from src.config import PipelineConfig, SCLClasses
from src.aoi import AOIManager

class CloudMasker:
    """Aplica máscaras de calidad basadas en la banda SCL de Sentinel-2 L2A."""

    def __init__(self, aoi_manager: AOIManager, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.aoi_manager = aoi_manager

    def evaluate_aoi_quality(
        self,
        scl_array: np.ndarray,
        affine_transform: rasterio.Affine
    ) -> Dict[str, float]:
        """
        Calcula las estadísticas de cobertura de nubes, vegetación y suelo
        exclusivamente dentro de los polígonos del predio (AOI).

        :param scl_array: Array 2D con los valores de la banda SCL (10m).
        :param affine_transform: Matriz de transformación afín del ráster.
        :return: Diccionario con porcentajes de calidad y recomendación de uso.
        """
        # Crear máscara binaria de los lotes (False dentro de los polígonos, True fuera)
        farm_geom = self.aoi_manager.get_unified_geometry()
        out_of_farm_mask = geometry_mask(
            [farm_geom],
            out_shape=scl_array.shape,
            transform=affine_transform,
            invert=False  # True fuera de la finca, False dentro
        )

        inside_farm_pixels = scl_array[~out_of_farm_mask]
        total_farm_pixels = len(inside_farm_pixels)

        if total_farm_pixels == 0:
            return {"cloud_pct": 100.0, "usable": False, "reason": "No se encontraron píxeles dentro del predio"}

        # Conteo de categorías SCL dentro de la finca
        cloud_pixels = np.isin(inside_farm_pixels, list(SCLClasses.MASK_VALUES)).sum()
        cloud_shadow_pixels = (inside_farm_pixels == SCLClasses.CLOUD_SHADOWS).sum()
        cirrus_pixels = (inside_farm_pixels == SCLClasses.THIN_CIRRUS).sum()
        vegetation_pixels = (inside_farm_pixels == SCLClasses.VEGETATION).sum()
        soil_pixels = (inside_farm_pixels == SCLClasses.NOT_VEGETATED).sum()

        cloud_pct = float((cloud_pixels / total_farm_pixels) * 100.0)
        veg_pct = float((vegetation_pixels / total_farm_pixels) * 100.0)
        soil_pct = float((soil_pixels / total_farm_pixels) * 100.0)

        is_usable = cloud_pct <= self.config.max_aoi_cloud_cover

        return {
            "total_pixels_aoi": total_farm_pixels,
            "cloud_pct_aoi": round(cloud_pct, 2),
            "cloud_shadow_pixels": int(cloud_shadow_pixels),
            "cirrus_pixels": int(cirrus_pixels),
            "vegetation_pct_aoi": round(veg_pct, 2),
            "soil_pct_aoi": round(soil_pct, 2),
            "is_usable": is_usable,
            "max_allowed_cloud_pct": self.config.max_aoi_cloud_cover
        }

    def create_valid_pixel_mask(
        self,
        scl_array: np.ndarray,
        affine_transform: rasterio.Affine
    ) -> np.ndarray:
        """
        Crea una máscara booleana 2D de píxeles válidos:
        True: Píxel válido (dentro del predio y libre de nubes/sombras).
        False: Píxel fuera de la finca o contaminado por nubes/sombras.
        """
        farm_geom = self.aoi_manager.get_unified_geometry()
        out_of_farm = geometry_mask(
            [farm_geom],
            out_shape=scl_array.shape,
            transform=affine_transform,
            invert=False
        )

        is_cloud_or_bad = np.isin(scl_array, list(SCLClasses.MASK_VALUES))
        
        # Píxel válido: Está dentro de la finca Y no es nube ni sombra
        valid_mask = (~out_of_farm) & (~is_cloud_or_bad)
        return valid_mask
