#!/usr/bin/env python3
"""
PyGan AgroSat - Descargador y Procesador Incremental de Nuevas Pasadas Sentinel-2.
Permite incorporar nuevas fechas satelitales a 'datos_procesados.json' sin necesidad
de reprocesar toda la serie histórica de meses anteriores.

Uso:
  python descargar_satelite.py 2026-10-27       # Descarga y procesa una fecha específica
  python descargar_satelite.py                  # Busca automáticamente pasadas recientes despejadas (<30% nubes)
"""

from datetime import datetime
import json
from pathlib import Path
import sys
import warnings
import numpy as np
import geopandas as gpd
from shapely.ops import unary_union
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds
from rasterio.features import geometry_mask
import pystac_client
import planetary_computer

warnings.filterwarnings("ignore", category=UserWarning)

def procesar_fecha_satelital(fecha_target, json_path="datos_procesados.json", force=False):
    json_file = Path(json_path)
    if not json_file.exists():
        print(f"❌ Error: No se encontró {json_path}. Debe existir para agregar nuevas fechas.")
        return False

    with open(json_file, "r", encoding="utf-8") as f:
        datos = json.load(f)

    fechas_actuales = datos.get("metadata", {}).get("fechas", [])
    if fecha_target in fechas_actuales and not force:
        print(f"ℹ️ La fecha {fecha_target} ya está procesada en el sistema.")
        return True

    # 1. Cargar geometrías de la finca
    shp_path = Path("satelital/Pygan.shp") if Path("satelital/Pygan.shp").exists() else Path("satelital/pygan.shp")
    if not shp_path.exists():
        found = list(Path("satelital").glob("*.shp"))
        if found:
            shp_path = found[0]
        else:
            print("❌ Error: No se encontró el archivo Shapefile en satelital/")
            return False

    gdf_utm = gpd.read_file(shp_path)
    target_crs = "EPSG:32717"
    if gdf_utm.crs is None or gdf_utm.crs.to_string() != target_crs:
        gdf_utm = gdf_utm.to_crs(target_crs)
    gdf_utm["geometry"] = gdf_utm.geometry.buffer(0)

    farm_geom = gdf_utm.union_all() if hasattr(gdf_utm, "union_all") else unary_union(gdf_utm.geometry)
    gdf_wgs84 = gdf_utm.to_crs(epsg=4326)
    minx_utm, miny_utm, maxx_utm, maxy_utm = gdf_utm.total_bounds
    buffer_m = 150.0
    crop_bounds_utm = (minx_utm - buffer_m, miny_utm - buffer_m, maxx_utm + buffer_m, maxy_utm + buffer_m)
    stac_bbox = [float(b) for b in gdf_wgs84.total_bounds]

    buffered_geometries = []
    for _, row in gdf_utm.iterrows():
        orig_geom = row.geometry
        neg_buf = orig_geom.buffer(-5.0)
        analysis_geom = neg_buf if (not neg_buf.is_empty and neg_buf.area > 40.0) else orig_geom
        buffered_geometries.append(analysis_geom)

    # 2. Conectar a Planetary Computer STAC
    print(f"\n📡 Conectando al catálogo STAC para la fecha: {fecha_target}...")
    stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
    catalog = pystac_client.Client.open(stac_url, modifier=planetary_computer.sign_inplace)

    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=stac_bbox,
        datetime=f"{fecha_target}/{fecha_target}",
        sortby=[{"field": "datetime", "direction": "asc"}]
    )
    items = list(search.items())
    if not items:
        print(f"❌ No se encontró ninguna pasada satelital de Sentinel-2 para el {fecha_target}.")
        return False

    # Filtrar que tenga las bandas requeridas
    valid_item = None
    for it in items:
        if all(b in it.assets for b in ["B04", "B08", "B11"]):
            valid_item = it
            break

    if not valid_item:
        print(f"❌ La escena encontrada para {fecha_target} no contiene las bandas necesarias (B04, B08, B11).")
        return False

    cloud_reg = round(float(valid_item.properties.get("eo:cloud_cover", 0.0)), 1)
    sat_name = valid_item.properties.get("platform", "Sentinel-2")
    print(f"🛰️ Escena confirmada: {valid_item.id}")
    print(f"   * Satélite: {sat_name} | Nubosidad Regional: {cloud_reg}%")

    c_minx, c_miny, c_maxx, c_maxy = crop_bounds_utm
    scale_factor = 10000.0
    cloud_classes = {3, 8, 9, 10}

    print("📥 Descargando ventanas raster de bandas espectrales (B04, B08, B11, SCL)...")
    # B08 (NIR 10m)
    with rasterio.open(valid_item.assets["B08"].href) as src_b08:
        with WarpedVRT(src_b08, crs=target_crs, resampling=Resampling.bilinear, src_nodata=0, nodata=0) as vrt:
            win = from_bounds(c_minx, c_miny, c_maxx, c_maxy, transform=vrt.transform).round_offsets().round_lengths()
            nir_raw = vrt.read(1, window=win).astype(np.float32)
            win_transform = vrt.window_transform(win)
            target_shape = nir_raw.shape

    # B04 (Red 10m)
    with rasterio.open(valid_item.assets["B04"].href) as src_b04:
        with WarpedVRT(src_b04, crs=target_crs, resampling=Resampling.bilinear, src_nodata=0, nodata=0) as vrt:
            win_b04 = from_bounds(c_minx, c_miny, c_maxx, c_maxy, transform=vrt.transform).round_offsets().round_lengths()
            red_raw = vrt.read(1, window=win_b04, out_shape=target_shape, resampling=Resampling.bilinear).astype(np.float32)

    # B11 (SWIR 20m -> 10m bilinear)
    with rasterio.open(valid_item.assets["B11"].href) as src_b11:
        with WarpedVRT(src_b11, crs=target_crs, resampling=Resampling.bilinear, src_nodata=0, nodata=0) as vrt:
            win_b11 = from_bounds(c_minx, c_miny, c_maxx, c_maxy, transform=vrt.transform).round_offsets().round_lengths()
            swir_raw = vrt.read(1, window=win_b11, out_shape=target_shape, resampling=Resampling.bilinear).astype(np.float32)

    local_cloud_pct = 0.0
    if "SCL" in valid_item.assets:
        try:
            with rasterio.open(valid_item.assets["SCL"].href) as src_scl:
                with WarpedVRT(src_scl, crs=target_crs, resampling=Resampling.nearest) as vrt:
                    win_scl = from_bounds(c_minx, c_miny, c_maxx, c_maxy, transform=vrt.transform).round_offsets().round_lengths()
                    scl_data = vrt.read(1, window=win_scl, out_shape=target_shape, resampling=Resampling.nearest)
                    out_mask = geometry_mask([farm_geom], out_shape=target_shape, transform=win_transform, invert=False)
                    farm_px = scl_data[~out_mask]
                    if len(farm_px) > 0:
                        clouds_found = np.isin(farm_px, list(cloud_classes)).sum()
                        local_cloud_pct = round(float((clouds_found / len(farm_px)) * 100.0), 1)
        except Exception as e:
            print(f"⚠️ Advertencia al leer SCL: {e}")

    nir = nir_raw / scale_factor
    red = red_raw / scale_factor
    swir = swir_raw / scale_factor

    invalid_px = (nir_raw == 0) | (red_raw == 0) | (swir_raw == 0)
    nir[invalid_px] = np.nan
    red[invalid_px] = np.nan
    swir[invalid_px] = np.nan

    with np.errstate(divide="ignore", invalid="ignore"):
        denom_ndvi = nir + red
        raster_ndvi = np.where(denom_ndvi > 0, (nir - red) / denom_ndvi, np.nan)
        raster_ndvi = np.clip(raster_ndvi, -1.0, 1.0)

        denom_savi = nir + red + 0.5
        raster_savi = np.where(denom_savi > 0, ((nir - red) / denom_savi) * 1.5, np.nan)
        raster_savi = np.clip(raster_savi, -1.0, 1.0)

        denom_ndmi = nir + swir
        raster_ndmi = np.where(denom_ndmi > 0, (nir - swir) / denom_ndmi, np.nan)
        raster_ndmi = np.clip(raster_ndmi, -1.0, 1.0)

    print(f"📊 Extrayendo estadísticas zonales (NDVI, SAVI, NDMI, P90) para {len(datos['poligonos'])} bloques...")
    for idx, p in enumerate(datos["poligonos"]):
        if idx >= len(buffered_geometries):
            continue
        geom_to_mask = buffered_geometries[idx]
        mask = geometry_mask([geom_to_mask], out_shape=target_shape, transform=win_transform, invert=False)

        poly_ndvi = raster_ndvi[~mask]
        poly_ndvi_valid = poly_ndvi[~np.isnan(poly_ndvi)]
        poly_savi = raster_savi[~mask]
        poly_savi_valid = poly_savi[~np.isnan(poly_savi)]
        poly_ndmi = raster_ndmi[~mask]
        poly_ndmi_valid = poly_ndmi[~np.isnan(poly_ndmi)]

        if len(poly_ndvi_valid) > 0:
            ndvi_med = float(np.mean(poly_ndvi_valid))
            ndvi_p10 = float(np.percentile(poly_ndvi_valid, 10))
            ndvi_p90 = float(np.percentile(poly_ndvi_valid, 90))
            std_ndvi = float(np.std(poly_ndvi_valid))
            cv_pct = float((std_ndvi / ndvi_med) * 100.0) if ndvi_med > 0 else 0.0
            crit_count = int(np.sum(poly_ndvi_valid < 0.35))
            area_critica_pct = float((crit_count / len(poly_ndvi_valid)) * 100.0)
        else:
            ndvi_med = 0.0
            ndvi_p10 = 0.0
            ndvi_p90 = 0.0
            cv_pct = 0.0
            area_critica_pct = 0.0

        savi_med = float(np.mean(poly_savi_valid)) if len(poly_savi_valid) > 0 else 0.0
        ndmi_med = float(np.mean(poly_ndmi_valid)) if len(poly_ndmi_valid) > 0 else 0.0

        p["historial"][fecha_target] = {
            "ndvi_med": round(ndvi_med, 4),
            "ndvi_p10": round(ndvi_p10, 4),
            "ndvi_p90": round(ndvi_p90, 4),
            "savi_med": round(savi_med, 4),
            "ndmi_med": round(ndmi_med, 4),
            "cv_pct": round(cv_pct, 2),
            "area_critica_pct": round(area_critica_pct, 2)
        }

    # Actualizar lista de fechas
    if fecha_target not in datos["metadata"]["fechas"]:
        datos["metadata"]["fechas"].append(fecha_target)
        datos["metadata"]["fechas"].sort()

    # Actualizar fechas_info
    info_fechas = [fi for fi in datos.get("fechas_info", []) if fi["fecha"] != fecha_target]
    info_fechas.append({
        "fecha": fecha_target,
        "scene_id": valid_item.id,
        "cloud_cover_region": cloud_reg,
        "cloud_cover_finca": local_cloud_pct,
        "tile": valid_item.properties.get("s2:mgrs_tile", "17NQA")
    })
    info_fechas.sort(key=lambda x: x["fecha"])
    datos["fechas_info"] = info_fechas
    datos["metadata"]["generado_en"] = datetime.now().isoformat()

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

    print(f"\n✅ ¡FECHA {fecha_target} INTEGRADA CON ÉXITO!")
    print(f"   * Nubosidad sobre la Finca : {local_cloud_pct}%")
    print(f"   * Nubosidad Regional       : {cloud_reg}%")
    print(f"   * Total fechas en sistema  : {len(datos['metadata']['fechas'])}")
    print(f"   * Rango histórico actual   : {datos['metadata']['fechas'][0]} al {datos['metadata']['fechas'][-1]}")
    return True

def auto_detectar_y_descargar(umbral_nubes_max=35.0, json_path="datos_procesados.json"):
    json_file = Path(json_path)
    if not json_file.exists():
        print(f"❌ Error: No se encontró {json_path}.")
        return

    with open(json_file, "r", encoding="utf-8") as f:
        datos = json.load(f)

    fechas_actuales = set(datos.get("metadata", {}).get("fechas", []))
    ultima_fecha = max(fechas_actuales) if fechas_actuales else "2026-06-01"

    bbox = [-78.405976, 0.139019, -78.385796, 0.146912]
    stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
    catalog = pystac_client.Client.open(stac_url, modifier=planetary_computer.sign_inplace)

    hoy = datetime.now().strftime("%Y-%m-%d")
    date_range = f"{ultima_fecha}/{hoy}"
    print(f"🔍 Buscando nuevas pasadas despejadas desde {ultima_fecha} hasta {hoy}...")

    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime=date_range,
        sortby=[{"field": "datetime", "direction": "asc"}]
    )

    items = list(search.items())
    nuevas_fechas = []
    for it in items:
        dt_str = it.datetime.strftime("%Y-%m-%d")
        clouds = it.properties.get("eo:cloud_cover", 100.0)
        if dt_str not in fechas_actuales and clouds <= umbral_nubes_max:
            nuevas_fechas.append((dt_str, clouds))

    if not nuevas_fechas:
        print(f"ℹ️ No hay pasadas satelitales nuevas despejadas (<{umbral_nubes_max}% nubes) posteriores al {ultima_fecha}.")
        return

    print(f"\n🎉 Se encontraron {len(nuevas_fechas)} nueva(s) pasada(s) despejada(s):")
    for f, c in nuevas_fechas:
        print(f"   -> {f} ({c:.1f}% nubes)")

    for f, _ in nuevas_fechas:
        procesar_fecha_satelital(f, json_path=json_path)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg_fecha = sys.argv[1].strip()
        procesar_fecha_satelital(arg_fecha)
    else:
        auto_detectar_y_descargar()
