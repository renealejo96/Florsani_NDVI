"""
Módulo de Consulta al Catálogo STAC (SpatioTemporal Asset Catalog).
Permite buscar, filtrar y firmar escenas de Sentinel-2 L2A en Microsoft Planetary Computer.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple
import pystac
import pystac_client
import planetary_computer

from src.config import PipelineConfig

class STACService:
    """Cliente especializado para la búsqueda de imágenes Sentinel-2 L2A en Planetary Computer."""

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.client = pystac_client.Client.open(
            self.config.stac_api_url,
            modifier=planetary_computer.sign_inplace
        )

    def search_scenes(
        self,
        bbox: List[float],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days_back: int = 60,
        max_cloud_cover: Optional[float] = None
    ) -> List[pystac.Item]:
        """
        Busca escenas de Sentinel-2 L2A que intersecten el BBOX del predio.
        
        :param bbox: [min_lon, min_lat, max_lon, max_lat] en EPSG:4326.
        :param start_date: Fecha inicial en formato 'YYYY-MM-DD'.
        :param end_date: Fecha final en formato 'YYYY-MM-DD'.
        :param days_back: Si no se especifica start_date, busca los últimos N días.
        :param max_cloud_cover: Porcentaje máximo de nubes global en la escena (default: config).
        :return: Lista de objetos pystac.Item ordenados cronológicamente descendente.
        """
        max_clouds = max_cloud_cover if max_cloud_cover is not None else self.config.max_scene_cloud_cover

        # Resolver ventana de tiempo
        if end_date is None:
            end_dt = datetime.now()
        else:
            end_dt = datetime.fromisoformat(end_date)

        if start_date is None:
            start_dt = end_dt - timedelta(days=days_back)
        else:
            start_dt = datetime.fromisoformat(start_date)

        datetime_str = f"{start_dt.strftime('%Y-%m-%d')}/{end_dt.strftime('%Y-%m-%d')}"

        search = self.client.search(
            collections=[self.config.collection],
            bbox=bbox,
            datetime=datetime_str,
            query={"eo:cloud_cover": {"lt": max_clouds}},
            sortby=[{"field": "datetime", "direction": "desc"}]
        )

        items = list(search.items())
        
        # Filtrar que contengan las bandas esenciales (Rojo, NIR y SCL)
        valid_items = []
        essential_assets = {"B04", "B08", "SCL"}
        for item in items:
            if essential_assets.issubset(set(item.assets.keys())):
                valid_items.append(item)

        return valid_items

    @staticmethod
    def get_asset_url(item: pystac.Item, asset_key: str) -> str:
        """
        Retorna la URL firmada de un asset (banda ráster).
        Planetary Computer ya adjunta el token SAS al haber usado sign_inplace.
        """
        if asset_key not in item.assets:
            raise KeyError(f"El asset '{asset_key}' no está disponible en la escena {item.id}")
        return item.assets[asset_key].href

    @staticmethod
    def get_scene_summary(item: pystac.Item) -> dict:
        """Extrae un resumen legible de los metadatos de la escena satelital."""
        return {
            "id": item.id,
            "datetime": item.datetime.isoformat() if item.datetime else "N/A",
            "cloud_cover_scene": item.properties.get("eo:cloud_cover", 0.0),
            "mgrs_tile": item.properties.get("s2:mgrs_tile", "N/A"),
            "platform": item.properties.get("platform", "Sentinel-2"),
            "sun_elevation": item.properties.get("view:sun_elevation", "N/A"),
        }
