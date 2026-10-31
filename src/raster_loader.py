"""
Módulo de Lectura y Preprocesamiento Ráster Remoto (Cloud-Optimized GeoTIFF).
Ejecuta lecturas por ventana (windowed reads), reproyección al vuelo y armonización
de resoluciones espaciales (10m vs 20m).
"""

from typing import Dict, Optional, Tuple
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds, reproject
from rasterio.windows import from_bounds
import pystac

from src.config import PipelineConfig, SCLClasses
from src.aoi import AOIManager
from src.stac_service import STACService

class RasterLoader:
    """Carga y procesa bandas satelitales directamente desde la nube mediante COGs y VRTs."""

    def __init__(self, aoi_manager: AOIManager, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.aoi_manager = aoi_manager
        self.target_crs = self.config.target_crs

    def load_scene_bands(
        self,
        item: pystac.Item,
        bands_to_load: Optional[list] = None
    ) -> Tuple[Dict[str, np.ndarray], rasterio.Affine, dict]:
        """
        Carga las bandas especificadas para la extensión del AOI de forma optimizada.
        Armoniza todas las bandas a una cuadrícula común de 10 metros en el CRS de destino.

        :param item: Objeto pystac.Item firmado.
        :param bands_to_load: Lista de nombres lógicos ('red', 'nir', 'scl', 'blue', etc.).
        :return: Tupla (diccionario_de_arrays_float, affine_transform, perfil_raster)
        """
        if bands_to_load is None:
            bands_to_load = ["red", "nir", "scl", "blue", "green"]

        # Obtener BBOX del predio en el CRS objetivo (EPSG:32717) con buffer de seguridad
        aoi_bounds = self.aoi_manager.get_bbox_utm(buffer_meters=150.0)
        minx, miny, maxx, maxy = aoi_bounds

        # Definir la cuadrícula de referencia (10m) usando la banda NIR (B08)
        nir_asset_key = self.config.band_assets["nir"]
        nir_url = STACService.get_asset_url(item, nir_asset_key)

        reference_profile = None
        reference_transform = None
        target_shape = None

        # Paso 1: Leer la banda NIR a través de un WarpedVRT para establecer la cuadrícula maestra
        with rasterio.open(nir_url) as src:
            with WarpedVRT(
                src,
                crs=self.target_crs,
                resampling=Resampling.bilinear,
                src_nodata=0,
                nodata=0
            ) as vrt:
                # Calcular la ventana dentro del VRT reproyectado
                window = from_bounds(minx, miny, maxx, maxy, transform=vrt.transform)
                # Redondear ventana a números enteros de píxeles
                window = window.round_offsets().round_lengths()
                
                nir_data = vrt.read(1, window=window).astype(np.float32)
                reference_transform = vrt.window_transform(window)
                target_shape = nir_data.shape
                
                reference_profile = {
                    "driver": "GTiff",
                    "dtype": "float32",
                    "nodata": -9999.0,
                    "width": target_shape[1],
                    "height": target_shape[0],
                    "count": 1,
                    "crs": self.target_crs,
                    "transform": reference_transform
                }

        loaded_bands = {}

        # Paso 2: Leer el resto de las bandas requeridas alineándolas exactamente a la cuadrícula de referencia
        for band_alias in bands_to_load:
            if band_alias not in self.config.band_assets:
                continue
            asset_key = self.config.band_assets[band_alias]
            if asset_key not in item.assets:
                print(f"[!] Banda {asset_key} ({band_alias}) no presente en la escena. Se omite.")
                continue

            asset_url = STACService.get_asset_url(item, asset_key)
            is_categorical = (band_alias == "scl")
            resampling_method = Resampling.nearest if is_categorical else Resampling.bilinear

            with rasterio.open(asset_url) as src:
                with WarpedVRT(
                    src,
                    crs=self.target_crs,
                    resampling=resampling_method,
                    src_nodata=0 if not is_categorical else None,
                    nodata=0 if not is_categorical else None
                ) as vrt:
                    window = from_bounds(minx, miny, maxx, maxy, transform=vrt.transform)
                    window = window.round_offsets().round_lengths()
                    
                    data = vrt.read(
                        1,
                        window=window,
                        out_shape=target_shape,
                        resampling=resampling_method
                    )

                    if is_categorical:
                        # La banda SCL se mantiene como enteros de clasificación
                        loaded_bands[band_alias] = data.astype(np.uint8)
                    else:
                        # Las bandas de reflectancia se convierten a float 0.0 - 1.0
                        float_data = data.astype(np.float32) / self.config.reflectance_scale_factor
                        float_data[data == 0] = np.nan
                        loaded_bands[band_alias] = float_data

        return loaded_bands, reference_transform, reference_profile
