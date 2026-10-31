#!/usr/bin/env python3
"""
Comprueba la nubosidad LOCAL real (SCL) sobre el perímetro de la finca PyGan
para las pasadas de agosto, septiembre y octubre de 2026.
"""
from datetime import datetime
import numpy as np
import geopandas as gpd
from shapely.ops import unary_union
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.windows import from_bounds
from rasterio.features import geometry_mask
import pystac_client
import planetary_computer

def main():
    print("=" * 70)
    print("🔍 AUDITORÍA DE NUBOSIDAD LOCAL REAL SOBRE LA FINCA PYGAN")
    print("=" * 70)

    # 1. Cargar geometría de la finca
    gdf = gpd.read_file("satelital/pygan.shp")
    if gdf.crs is None or gdf.crs.to_string() != "EPSG:32717":
        gdf = gdf.to_crs("EPSG:32717")
    
    farm_geom = gdf.union_all() if hasattr(gdf, "union_all") else unary_union(gdf.geometry)
    minx, miny, maxx, maxy = gdf.total_bounds
    crop_bounds = (minx - 100, miny - 100, maxx + 100, maxy + 100)

    gdf_wgs84 = gdf.to_crs(epsg=4326)
    bbox_wgs84 = list(gdf_wgs84.total_bounds)

    # 2. Conectar a STAC
    stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
    catalog = pystac_client.Client.open(stac_url, modifier=planetary_computer.sign_inplace)

    # Fechas de interés entre agosto y octubre 2026
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox_wgs84,
        datetime="2026-08-14/2026-10-18",
        sortby=[{"field": "datetime", "direction": "desc"}],
        max_items=12
    )

    items = list(search.items())
    print(f"[+] Evaluando las últimas {len(items)} pasadas satelitales a nivel de lote...\n")
    print(f"{'FECHA':<12} | {'NUBES PROVINCIA':<16} | {'NUBES FINCA REAL':<18} | {'ESTADO FINCA'}")
    print("-" * 75)

    # Códigos SCL de nubes y sombras: 3 (sombra), 8 (media prob), 9 (alta prob), 10 (cirro)
    cloud_classes = {3, 8, 9, 10}

    for item in items:
        dt_str = item.datetime.strftime("%Y-%m-%d")
        scene_cloud = item.properties.get("eo:cloud_cover", 0.0)

        if "SCL" not in item.assets:
            continue

        scl_url = item.assets["SCL"].href
        try:
            with rasterio.open(scl_url) as src:
                with WarpedVRT(src, crs="EPSG:32717", resampling=Resampling.nearest) as vrt:
                    win = from_bounds(*crop_bounds, transform=vrt.transform).round_offsets().round_lengths()
                    scl_data = vrt.read(1, window=win)
                    win_transform = vrt.window_transform(win)

            # Máscara dentro de la finca
            out_mask = geometry_mask([farm_geom], out_shape=scl_data.shape, transform=win_transform, invert=False)
            farm_pixels = scl_data[~out_mask]

            if len(farm_pixels) == 0:
                local_cloud_pct = 100.0
            else:
                cloud_count = np.isin(farm_pixels, list(cloud_classes)).sum()
                local_cloud_pct = (cloud_count / len(farm_pixels)) * 100.0

            if local_cloud_pct < 20.0:
                estado = "✅ DESPEJADO (APTA)"
            elif local_cloud_pct <= 50.0:
                estado = "⚠️ PARCIAL"
            else:
                estado = "❌ CUBIERTO POR NUBES"

            print(f"{dt_str:<12} | {scene_cloud:>6.1f}%          | {local_cloud_pct:>6.1f}%           | {estado}")

        except Exception as e:
            print(f"{dt_str:<12} | {scene_cloud:>6.1f}%          | Error al leer ráster")

    print("=" * 70)

if __name__ == "__main__":
    main()
