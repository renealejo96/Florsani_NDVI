"""
Módulo de Exportación de Rásters GeoTIFF.
Genera archivos GeoTIFF georreferenciados con compresión LZW, metadatos OGC y etiquetas descriptivas.
"""

from pathlib import Path
from typing import Dict, Optional
import numpy as np
import rasterio
from rasterio.crs import CRS

from src.config import PipelineConfig

class RasterExporter:
    """Exporta arrays de índices espectrales a formato GeoTIFF estándar."""

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.nodata_value = -9999.0

    def export_geotiff(
        self,
        array: np.ndarray,
        reference_profile: dict,
        scene_id: str,
        index_name: str = "ndvi",
        extra_metadata: Optional[Dict[str, str]] = None
    ) -> Path:
        """
        Exporta una matriz 2D a un archivo GeoTIFF con metadatos completos.

        :param array: Array 2D con los valores del índice (float con NaN).
        :param reference_profile: Perfil base obtenido de RasterLoader.
        :param scene_id: Identificador de la escena satelital.
        :param index_name: Nombre del índice (ej: 'ndvi', 'savi', 'ndre').
        :param extra_metadata: Diccionario opcional de etiquetas informativas.
        :return: Ruta del archivo GeoTIFF creado.
        """
        self.config.ensure_directories()
        clean_date_tag = scene_id.split("_")[2] if len(scene_id.split("_")) > 2 else scene_id
        output_filename = f"{index_name}_{clean_date_tag}.tif"
        output_path = self.config.outputs_dir / output_filename

        # Preparar array para guardado: reemplazar NaN por nodata_value
        export_array = np.nan_to_num(array, nan=self.nodata_value).astype(np.float32)

        # Configurar perfil de escritura
        profile = reference_profile.copy()
        profile.update({
            "driver": "GTiff",
            "dtype": "float32",
            "nodata": self.nodata_value,
            "count": 1,
            "compress": "lzw",
            "tiled": True,
            "blockxsize": 256,
            "blockysize": 256
        })

        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(export_array, 1)
            
            # Inyectar metadatos descriptivos en el encabezado del ráster
            tags = {
                "INDEX_NAME": index_name.upper(),
                "SCENE_ID": scene_id,
                "PLATFORM": "Sentinel-2",
                "PROCESSED_BY": "PyGan NDVI Geospatial Pipeline",
                "NODATA_VALUE": str(self.nodata_value)
            }
            if extra_metadata:
                tags.update(extra_metadata)
            dst.update_tags(**tags)

        return output_path
