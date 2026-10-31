"""
Módulo de Gestión del Área de Interés (AOI).
Carga, valida y prepara geometrías vectoriales de parcelas agrícolas para su uso en consultas satelitales y estadísticas zonales.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import geopandas as gpd
from shapely.geometry import box, mapping
from shapely.ops import unary_union

from src.config import PipelineConfig

class AOIManager:
    """Administra la carga, reproyección y extracción de geometrías del predio agrícola."""

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.shapefile_path = self.config.shapefile_path
        self._gdf: Optional[gpd.GeoDataFrame] = None
        self._gdf_wgs84: Optional[gpd.GeoDataFrame] = None
        self._load_and_validate()

    def _load_and_validate(self) -> None:
        """Carga el shapefile, verifica su integridad y valida el CRS."""
        if not self.shapefile_path.exists():
            raise FileNotFoundError(f"No se encontró el archivo de predio: {self.shapefile_path}")

        self._gdf = gpd.read_file(self.shapefile_path)

        # Validar y asignar CRS si viniese indefinido
        if self._gdf.crs is None:
            self._gdf.set_crs(self.config.target_crs, inplace=True)
        elif self._gdf.crs.to_string() != self.config.target_crs:
            self._gdf = self._gdf.to_crs(self.config.target_crs)

        # Corregir geometrías no válidas si existiesen (buffer 0 es un truco estándar en GIS)
        if not self._gdf.is_valid.all():
            self._gdf["geometry"] = self._gdf.geometry.buffer(0)

        # Generar versión en EPSG:4326 (WGS84 lat/lon) para consultas STAC
        self._gdf_wgs84 = self._gdf.to_crs(epsg=4326)

    @property
    def gdf(self) -> gpd.GeoDataFrame:
        """Retorna el GeoDataFrame de lotes en el CRS métrico nativo (EPSG:32717)."""
        return self._gdf

    @property
    def gdf_wgs84(self) -> gpd.GeoDataFrame:
        """Retorna el GeoDataFrame de lotes proyectado en WGS84 (EPSG:4326)."""
        return self._gdf_wgs84

    @property
    def total_parcels(self) -> int:
        """Cantidad total de lotes/parcelas."""
        return len(self._gdf)

    @property
    def total_area_ha(self) -> float:
        """Área total del predio en hectáreas."""
        return float(self._gdf.geometry.area.sum() / 10000.0)

    def get_unified_geometry(self) -> Any:
        """Retorna la geometría unificada de toda la propiedad en CRS nativo."""
        # Compatibilidad con versiones recientes de GeoPandas
        if hasattr(self._gdf, "union_all"):
            return self._gdf.union_all()
        return unary_union(self._gdf.geometry)

    def get_bbox_utm(self, buffer_meters: float = 100.0) -> Tuple[float, float, float, float]:
        """
        Retorna los límites (minx, miny, maxx, maxy) en CRS nativo métrico,
        con un búfer de seguridad para evitar pérdida de píxeles en los bordes.
        """
        minx, miny, maxx, maxy = self._gdf.total_bounds
        return (
            minx - buffer_meters,
            miny - buffer_meters,
            maxx + buffer_meters,
            maxy + buffer_meters,
        )

    def get_bbox_wgs84(self, buffer_meters: float = 100.0) -> List[float]:
        """
        Retorna el BBOX en WGS84 [min_lon, min_lat, max_lon, max_lat]
        calculado a partir del polígono bufferizado en metros para máxima precisión.
        """
        minx, miny, maxx, maxy = self.get_bbox_utm(buffer_meters=buffer_meters)
        buffered_box = gpd.GeoSeries([box(minx, miny, maxx, maxy)], crs=self.config.target_crs)
        buffered_box_wgs84 = buffered_box.to_crs(epsg=4326)
        min_lon, min_lat, max_lon, max_lat = buffered_box_wgs84.total_bounds
        return [float(min_lon), float(min_lat), float(max_lon), float(max_lat)]

    def get_geojson_footprint_wgs84(self) -> Dict[str, Any]:
        """Retorna la geometría unificada del predio en formato GeoJSON en WGS84."""
        if hasattr(self._gdf_wgs84, "union_all"):
            unified = self._gdf_wgs84.union_all()
        else:
            unified = unary_union(self._gdf_wgs84.geometry)
        return mapping(unified)
