import pystac_client
import planetary_computer
import geopandas as gpd
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds
from rasterio.features import geometry_mask
from rasterio.enums import Resampling
import numpy as np

catalog = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=planetary_computer.sign_inplace)
bbox = [-78.406, 0.139, -78.386, 0.147]
search = catalog.search(
    collections=["sentinel-2-l2a"],
    bbox=bbox,
    datetime="2026-10-18/2026-10-24",
    sortby=[{"field": "datetime", "direction": "asc"}]
)
items = list(search.items())
print("Pasadas encontradas:", len(items))

gdf_utm = gpd.read_file("satelital/Pygan.shp").to_crs("EPSG:32717")
farm_geom = gdf_utm.union_all() if hasattr(gdf_utm, "union_all") else gdf_utm.unary_union
minx_utm, miny_utm, maxx_utm, maxy_utm = gdf_utm.total_bounds
crop_bounds_utm = (minx_utm - 150, miny_utm - 150, maxx_utm + 150, maxy_utm + 150)
c_minx, c_miny, c_maxx, c_maxy = crop_bounds_utm

for it in items:
    dt = it.datetime.strftime("%Y-%m-%d %H:%M UTC")
    dt_day = it.datetime.strftime("%Y-%m-%d")
    reg_clouds = it.properties.get("eo:cloud_cover", 0)
    plat = it.properties.get("platform", "")
    
    finca_clouds = "N/A"
    if "SCL" in it.assets:
        try:
            with rasterio.open(it.assets["SCL"].href) as src:
                with WarpedVRT(src, crs="EPSG:32717", resampling=Resampling.nearest) as vrt:
                    win = from_bounds(c_minx, c_miny, c_maxx, c_maxy, transform=vrt.transform).round_offsets().round_lengths()
                    scl = vrt.read(1, window=win)
                    win_transform = vrt.window_transform(win)
                    mask = geometry_mask([farm_geom], out_shape=scl.shape, transform=win_transform, invert=False)
                    farm_px = scl[~mask]
                    if len(farm_px) > 0:
                        clouds_cnt = np.isin(farm_px, [3, 8, 9, 10]).sum()
                        finca_clouds = round(float(clouds_cnt / len(farm_px) * 100.0), 1)
        except Exception as e:
            finca_clouds = f"Error: {e}"
            
    print(f"Fecha: {dt_day} ({dt} | {plat})")
    print(f"  * Nubes Región (100x100km): {reg_clouds:.1f}%")
    print(f"  * NUBES REALES EN FINCA (36.5 ha): {finca_clouds}%\n")
