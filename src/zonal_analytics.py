"""
Módulo de Estadísticas Zonales Agrícolas.
Extrae estadísticas descriptivas por cada parcela/bloque (media, mediana, desv_est, min, max)
y exporta capas vectoriales enriquecidas y reportes tabulares.
"""

from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.features import geometry_mask

from src.config import PipelineConfig
from src.aoi import AOIManager

class ZonalAnalytics:
    """Calcula y exporta estadísticas zonales sobre capas vectoriales de parcelas."""

    def __init__(self, aoi_manager: AOIManager, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.aoi_manager = aoi_manager

    @staticmethod
    def classify_ndvi_vigor(mean_ndvi: float) -> str:
        """Clasifica el estado vegetativo según umbrales agronómicos estándar de NDVI."""
        if np.isnan(mean_ndvi):
            return "Sin Datos / Nublado"
        elif mean_ndvi >= 0.70:
            return "Vigor Muy Alto (Dosel Denso)"
        elif mean_ndvi >= 0.50:
            return "Vigor Moderado a Alto"
        elif mean_ndvi >= 0.30:
            return "Vigor Bajo / Estrés Moderado"
        elif mean_ndvi >= 0.15:
            return "Vegetación Escasa / Suelo Parcial"
        else:
            return "Suelo Desnudo / Agua"

    def compute_zonal_stats(
        self,
        index_array: np.ndarray,
        affine_transform: rasterio.Affine,
        index_name: str = "ndvi"
    ) -> gpd.GeoDataFrame:
        """
        Calcula estadísticas zonales para cada uno de los lotes del shapefile.

        :param index_array: Matriz 2D del índice (float con np.nan en inválidos).
        :param affine_transform: Transformación afín del ráster.
        :param index_name: Nombre del índice analizado (ej: 'ndvi', 'ndre').
        :return: GeoDataFrame original enriquecido con las nuevas columnas de estadísticas.
        """
        gdf_result = self.aoi_manager.gdf.copy()

        means = []
        medians = []
        stds = []
        mins = []
        maxs = []
        valid_pixel_counts = []
        vigor_classes = []

        out_shape = index_array.shape

        for _, row in gdf_result.iterrows():
            geom = row.geometry
            # Crear máscara para el polígono individual del lote
            mask = geometry_mask(
                [geom],
                out_shape=out_shape,
                transform=affine_transform,
                invert=False  # True fuera del polígono, False dentro
            )

            # Extraer píxeles dentro del lote
            pixels_in_parcel = index_array[~mask]
            # Filtrar valores NaN (nubes o fondo)
            valid_pixels = pixels_in_parcel[~np.isnan(pixels_in_parcel)]

            count = len(valid_pixels)
            valid_pixel_counts.append(count)

            if count > 0:
                mean_val = float(np.mean(valid_pixels))
                median_val = float(np.median(valid_pixels))
                std_val = float(np.std(valid_pixels))
                min_val = float(np.min(valid_pixels))
                max_val = float(np.max(valid_pixels))
                vigor = self.classify_ndvi_vigor(mean_val)
            else:
                mean_val = np.nan
                median_val = np.nan
                std_val = np.nan
                min_val = np.nan
                max_val = np.nan
                vigor = "Sin Datos / Nublado"

            means.append(mean_val)
            medians.append(median_val)
            stds.append(std_val)
            mins.append(min_val)
            maxs.append(max_val)
            vigor_classes.append(vigor)

        # Asignar columnas con prefijo del índice
        gdf_result[f"{index_name}_mean"] = np.round(means, 4)
        gdf_result[f"{index_name}_median"] = np.round(medians, 4)
        gdf_result[f"{index_name}_std"] = np.round(stds, 4)
        gdf_result[f"{index_name}_min"] = np.round(mins, 4)
        gdf_result[f"{index_name}_max"] = np.round(maxs, 4)
        gdf_result[f"{index_name}_valid_pixels"] = valid_pixel_counts
        gdf_result[f"{index_name}_clasificacion"] = vigor_classes

        return gdf_result

    def export_stats(
        self,
        gdf_stats: gpd.GeoDataFrame,
        scene_id: str,
        index_name: str = "ndvi"
    ) -> Dict[str, Path]:
        """
        Exporta las estadísticas zonales a formatos estándar:
        1. GeoJSON (proyectado en WGS84 para visualización web / GIS).
        2. CSV (tabla plana para Excel / ERP agronómico).
        """
        self.config.ensure_directories()
        clean_scene_id = scene_id.split("_")[2] if len(scene_id.split("_")) > 2 else scene_id

        # 1. Exportar CSV
        csv_filename = f"zonal_{index_name}_{clean_scene_id}.csv"
        csv_path = self.config.outputs_dir / csv_filename
        df_export = gdf_stats.drop(columns="geometry")
        df_export.to_csv(csv_path, index=False, encoding="utf-8-sig")

        # 2. Exportar GeoJSON en EPSG:4326 para compatibilidad universal
        geojson_filename = f"zonal_{index_name}_{clean_scene_id}.geojson"
        geojson_path = self.config.outputs_dir / geojson_filename
        gdf_wgs84 = gdf_stats.to_crs(epsg=4326)
        gdf_wgs84.to_file(geojson_path, driver="GeoJSON")

        return {
            "csv": csv_path,
            "geojson": geojson_path
        }
