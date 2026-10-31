#!/usr/bin/env python3
"""
Pipeline ETL Satelital Sentinel-2 L2A para Monitoreo Agrícola (PyGan).
Fase 2 Ampliada: Procesa la serie temporal completa (Junio a Octubre 2026)
calculando la nubosidad real LOCAL de la finca (SCL) y la regional.
"""

from datetime import datetime
import json
from pathlib import Path
import warnings
import numpy as np
import geopandas as gpd
from shapely.geometry import mapping
from shapely.ops import unary_union
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds
from rasterio.features import geometry_mask
import pystac_client
import planetary_computer

from procesar_cultivos import procesar_csv_cultivos, normalizar_nombre_bloque

warnings.filterwarnings("ignore", category=UserWarning)

def main():
    print("=" * 70)
    print("🛰️ PIPELINE ETL SATELITAL MULTI-TEMPORAL CON NUBOSIDAD LOCAL Y REGIONAL")
    print("=" * 70)

    shp_path = Path("satelital/Pygan.shp") if Path("satelital/Pygan.shp").exists() else Path("satelital/pygan.shp")
    if not shp_path.exists():
        # Fallback de búsqueda insensible a mayúsculas
        found = list(Path("satelital").glob("*.shp"))
        if found:
            shp_path = found[0]
        else:
            raise FileNotFoundError("No se encontró ningún archivo .shp en la carpeta satelital/")
    gdf_utm = gpd.read_file(shp_path)
    target_crs = "EPSG:32717"
    if gdf_utm.crs is None or gdf_utm.crs.to_string() != target_crs:
        gdf_utm = gdf_utm.to_crs(target_crs)

    gdf_utm["geometry"] = gdf_utm.geometry.buffer(0)
    gdf_utm["area_ha"] = np.round(gdf_utm.geometry.area / 10000.0, 4)
    total_area_ha = float(gdf_utm["area_ha"].sum())
    total_poligonos = len(gdf_utm)
    farm_geom = gdf_utm.union_all() if hasattr(gdf_utm, "union_all") else unary_union(gdf_utm.geometry)

    gdf_wgs84 = gdf_utm.to_crs(epsg=4326)
    minx_utm, miny_utm, maxx_utm, maxy_utm = gdf_utm.total_bounds
    buffer_m = 150.0
    crop_bounds_utm = (minx_utm - buffer_m, miny_utm - buffer_m, maxx_utm + buffer_m, maxy_utm + buffer_m)
    stac_bbox = [float(b) for b in gdf_wgs84.total_bounds]

    centroid = gdf_wgs84.union_all().centroid if hasattr(gdf_wgs84, "union_all") else gdf_wgs84.unary_union.centroid
    centroid_info = {"lat": round(float(centroid.y), 6), "lon": round(float(centroid.x), 6)}

    print("\n[+] Conectando al catálogo STAC de Microsoft Planetary Computer...")
    stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
    catalog = pystac_client.Client.open(stac_url, modifier=planetary_computer.sign_inplace)

    fechas_objetivo = [
        "2026-06-19",
        "2026-07-14",
        "2026-07-29",
        "2026-08-13",
        "2026-09-12",
        "2026-09-17",
        "2026-09-27",
        "2026-09-29",
        "2026-10-09",
        "2026-10-19",
        "2026-10-22"
    ]

    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=stac_bbox,
        datetime="2026-06-01/2026-10-24",
        sortby=[{"field": "datetime", "direction": "asc"}]
    )

    items = list(search.items())
    valid_items_map = {}
    for it in items:
        dt_str = it.datetime.strftime("%Y-%m-%d")
        if dt_str in fechas_objetivo and dt_str not in valid_items_map:
            if all(b in it.assets for b in ["B04", "B08", "B11"]):
                valid_items_map[dt_str] = it

    valid_items = [valid_items_map[d] for d in fechas_objetivo if d in valid_items_map]
    selected_dates = [it.datetime.strftime("%Y-%m-%d") for it in valid_items]

    # Cargar información agronómica y de camas desde bq_sentinel.csv
    cultivos_map = {}
    csv_cultivos_path = Path("bq_sentinel.csv")
    if csv_cultivos_path.exists():
        print("\n[+] Procesando y cruzando detalle de camas de bq_sentinel.csv...")
        cultivos_map, _ = procesar_csv_cultivos(csv_cultivos_path)
    elif Path("cultivos_por_bloque.json").exists():
        with open("cultivos_por_bloque.json", "r", encoding="utf-8") as f:
            cultivos_map = json.load(f)

    processed_polygons = []
    buffered_geometries = []
    for idx, row in gdf_utm.iterrows():
        orig_geom = row.geometry
        neg_buf = orig_geom.buffer(-5.0)
        analysis_geom = neg_buf if (not neg_buf.is_empty and neg_buf.area > 40.0) else orig_geom
        buffered_geometries.append(analysis_geom)

        bloque_nom = str(row.get("Bloque_1", row.get("Bloque", f"Lote_{idx}")))
        bloque_key = normalizar_nombre_bloque(bloque_nom)
        c_info = cultivos_map.get(bloque_key, {})

        processed_polygons.append({
            "id": int(idx),
            "bloque": int(row.get("Bloque", 0)),
            "bloque_nombre": bloque_nom,
            "cultivo": c_info.get("producto_principal", "SIN DATO"),
            "categoria_agronomica": c_info.get("categoria_agronomica", "SIN DATO"),
            "camas_total": c_info.get("total_camas", 0),
            "camas_activas": c_info.get("camas_activas", 0),
            "camas_vacias": c_info.get("camas_vacio", 0),
            "pct_activa": c_info.get("pct_activa", 0.0),
            "tiene_ensayos": c_info.get("tiene_ensayos", False),
            "candidato_estrella": c_info.get("candidato_estrella", False),
            "area_m2": round(float(row.get("AREA", row.geometry.area)), 2),
            "area_ha": float(row["area_ha"]),
            "calicata": int(row.get("Calicata", 0)),
            "sonda": int(row.get("SONDA", 0)),
            "tecnico": int(row.get("Técnico", 0)),
            "geojson": mapping(gdf_wgs84.geometry.iloc[idx]),
            "historial": {}
        })

    c_minx, c_miny, c_maxx, c_maxy = crop_bounds_utm
    scale_factor = 10000.0
    fechas_info = []
    cloud_classes = {3, 8, 9, 10}

    for item in valid_items:
        date_str = item.datetime.strftime("%Y-%m-%d")
        print(f"\n   -> Procesando fecha: {date_str}...")

        url_b04 = item.assets["B04"].href
        url_b08 = item.assets["B08"].href
        url_b11 = item.assets["B11"].href

        # B08 (NIR 10m)
        with rasterio.open(url_b08) as src_b08:
            with WarpedVRT(src_b08, crs=target_crs, resampling=Resampling.bilinear, src_nodata=0, nodata=0) as vrt:
                win = from_bounds(c_minx, c_miny, c_maxx, c_maxy, transform=vrt.transform).round_offsets().round_lengths()
                nir_raw = vrt.read(1, window=win).astype(np.float32)
                win_transform = vrt.window_transform(win)
                target_shape = nir_raw.shape

        # B04 (Red 10m)
        with rasterio.open(url_b04) as src_b04:
            with WarpedVRT(src_b04, crs=target_crs, resampling=Resampling.bilinear, src_nodata=0, nodata=0) as vrt:
                win = from_bounds(c_minx, c_miny, c_maxx, c_maxy, transform=vrt.transform).round_offsets().round_lengths()
                red_raw = vrt.read(1, window=win, out_shape=target_shape, resampling=Resampling.bilinear).astype(np.float32)

        # B11 (SWIR 20m -> 10m bilinear)
        with rasterio.open(url_b11) as src_b11:
            with WarpedVRT(src_b11, crs=target_crs, resampling=Resampling.bilinear, src_nodata=0, nodata=0) as vrt:
                win = from_bounds(c_minx, c_miny, c_maxx, c_maxy, transform=vrt.transform).round_offsets().round_lengths()
                swir_raw = vrt.read(1, window=win, out_shape=target_shape, resampling=Resampling.bilinear).astype(np.float32)

        # Calcular nubes locales en la finca con SCL si está disponible
        local_cloud_pct = 0.0
        if "SCL" in item.assets:
            try:
                with rasterio.open(item.assets["SCL"].href) as src_scl:
                    with WarpedVRT(src_scl, crs=target_crs, resampling=Resampling.nearest) as vrt:
                        scl_data = vrt.read(1, window=win, out_shape=target_shape, resampling=Resampling.nearest)
                        out_mask = geometry_mask([farm_geom], out_shape=target_shape, transform=win_transform, invert=False)
                        farm_px = scl_data[~out_mask]
                        if len(farm_px) > 0:
                            clouds_found = np.isin(farm_px, list(cloud_classes)).sum()
                            local_cloud_pct = round(float((clouds_found / len(farm_px)) * 100.0), 1)
            except Exception:
                local_cloud_pct = 0.0

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

        # Umbral base dinámico 0.35 para campo abierto
        for idx in range(total_poligonos):
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

            processed_polygons[idx]["historial"][date_str] = {
                "ndvi_med": round(ndvi_med, 4),
                "ndvi_p10": round(ndvi_p10, 4),
                "ndvi_p90": round(ndvi_p90, 4),
                "savi_med": round(savi_med, 4),
                "ndmi_med": round(ndmi_med, 4),
                "cv_pct": round(cv_pct, 2),
                "area_critica_pct": round(area_critica_pct, 2)
            }

        fechas_info.append({
            "fecha": date_str,
            "scene_id": item.id,
            "cloud_cover_region": round(float(item.properties.get("eo:cloud_cover", 0.0)), 1),
            "cloud_cover_finca": local_cloud_pct,
            "tile": item.properties.get("s2:mgrs_tile", "17NQA")
        })

    output_data = {
        "metadata": {
            "proyecto": "PyGan NDVI - Monitoreo Satelital Agrícola",
            "total_poligonos": total_poligonos,
            "area_total_ha": round(total_area_ha, 2),
            "crs_nativo": target_crs,
            "centroide": centroid_info,
            "bbox_wgs84": stac_bbox,
            "fechas": selected_dates,
            "indicadores": ["ndvi_med", "ndvi_p10", "ndvi_p90", "savi_med", "ndmi_med", "cv_pct", "area_critica_pct"],
            "generado_en": datetime.now().isoformat()
        },
        "fechas_info": fechas_info,
        "poligonos": processed_polygons
    }

    output_file = Path("datos_procesados.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print(f"✅ DATASET ACTUALIZADO CON NUBES LOCALES Y REGIONALES")
    for fi in fechas_info:
        print(f"   * {fi['fecha']}: Finca {fi['cloud_cover_finca']}% nubes | Región {fi['cloud_cover_region']}%")
    print("=" * 70)

if __name__ == "__main__":
    main()
