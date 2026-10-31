#!/usr/bin/env python3
"""
PyGan AgroSat - Inferencia de Cobertura Vegetal con Random Forest.
Aplica el modelo 'modelos/modelo_rf_cobertura.joblib' sobre los píxeles de cada bloque
para calcular el porcentaje exacto de cobertura vegetal neta (dosel foliar activo)
frente al suelo desnudo (pasillos y tumbas).

Uso:
  python evaluar_cobertura_rf.py [FECHA]       # Por defecto usa la fecha más reciente (ej. 2026-10-27)
"""

from datetime import datetime
import json
from pathlib import Path
import sys
import warnings
import joblib
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds
from rasterio.features import geometry_mask
import pystac_client
import planetary_computer

warnings.filterwarnings("ignore", category=UserWarning)

def evaluar_cobertura(fecha_target=None):
    model_file = Path("modelos/modelo_rf_cobertura.joblib")
    if not model_file.exists():
        print("❌ Error: No se encontró 'modelos/modelo_rf_cobertura.joblib'. Ejecute primero entrenar_random_forest.py.")
        return

    rf_model = joblib.load(model_file)

    json_path = Path("datos_procesados.json")
    with open(json_path, "r", encoding="utf-8") as f:
        datos = json.load(f)

    fechas = datos["metadata"]["fechas"]
    fecha = fecha_target if fecha_target else fechas[-1]
    print("=" * 80)
    print(f"🌲 INFERENCIA RANDOM FOREST: COBERTURA FOLIAR NETA VS SUELO (FECHA: {fecha})")
    print("=" * 80)

    shp_path = Path("satelital/Pygan.shp") if Path("satelital/Pygan.shp").exists() else Path("satelital/pygan.shp")
    gdf_utm = gpd.read_file(shp_path)
    target_crs = "EPSG:32717"
    if gdf_utm.crs is None or gdf_utm.crs.to_string() != target_crs:
        gdf_utm = gdf_utm.to_crs(target_crs)
    gdf_utm["geometry"] = gdf_utm.geometry.buffer(0)

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

    stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
    catalog = pystac_client.Client.open(stac_url, modifier=planetary_computer.sign_inplace)

    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=stac_bbox,
        datetime=f"{fecha}/{fecha}",
        sortby=[{"field": "datetime", "direction": "asc"}]
    )
    items = list(search.items())
    if not items:
        print(f"❌ No se encontró escena en STAC para la fecha {fecha}.")
        return
    item = items[0]

    c_minx, c_miny, c_maxx, c_maxy = crop_bounds_utm
    scale_factor = 10000.0

    print("📥 Descargando bandas espectrales para clasificar píxel a píxel...")
    # B08 (NIR)
    with rasterio.open(item.assets["B08"].href) as src_b08:
        with WarpedVRT(src_b08, crs=target_crs, resampling=Resampling.bilinear, src_nodata=0, nodata=0) as vrt:
            win_b08 = from_bounds(c_minx, c_miny, c_maxx, c_maxy, transform=vrt.transform).round_offsets().round_lengths()
            nir_raw = vrt.read(1, window=win_b08).astype(np.float32)
            win_transform = vrt.window_transform(win_b08)
            target_shape = nir_raw.shape

    # B04 (Red)
    with rasterio.open(item.assets["B04"].href) as src_b04:
        with WarpedVRT(src_b04, crs=target_crs, resampling=Resampling.bilinear, src_nodata=0, nodata=0) as vrt:
            win_b04 = from_bounds(c_minx, c_miny, c_maxx, c_maxy, transform=vrt.transform).round_offsets().round_lengths()
            red_raw = vrt.read(1, window=win_b04, out_shape=target_shape, resampling=Resampling.bilinear).astype(np.float32)

    # B11 (SWIR)
    with rasterio.open(item.assets["B11"].href) as src_b11:
        with WarpedVRT(src_b11, crs=target_crs, resampling=Resampling.bilinear, src_nodata=0, nodata=0) as vrt:
            win_b11 = from_bounds(c_minx, c_miny, c_maxx, c_maxy, transform=vrt.transform).round_offsets().round_lengths()
            swir_raw = vrt.read(1, window=win_b11, out_shape=target_shape, resampling=Resampling.bilinear).astype(np.float32)

    nir = nir_raw / scale_factor
    red = red_raw / scale_factor
    swir = swir_raw / scale_factor

    invalid_px = (nir_raw == 0) | (red_raw == 0) | (swir_raw == 0)
    nir[invalid_px] = np.nan
    red[invalid_px] = np.nan
    swir[invalid_px] = np.nan

    with np.errstate(divide="ignore", invalid="ignore"):
        denom_ndvi = nir + red
        ndvi_grid = np.where(denom_ndvi > 0, (nir - red) / denom_ndvi, np.nan)
        denom_savi = nir + red + 0.5
        savi_grid = np.where(denom_savi > 0, ((nir - red) / denom_savi) * 1.5, np.nan)
        denom_ndmi = nir + swir
        ndmi_grid = np.where(denom_ndmi > 0, (nir - swir) / denom_ndmi, np.nan)
        ratio_nir_red = np.where(red > 0, nir / red, np.nan)
        ratio_nir_swir = np.where(swir > 0, nir / swir, np.nan)

    resultados = []
    print("🔬 Clasificando cada uno de los 250 bloques...")
    for idx, p in enumerate(datos["poligonos"]):
        if idx >= len(buffered_geometries):
            continue
        geom = buffered_geometries[idx]
        mask = geometry_mask([geom], out_shape=target_shape, transform=win_transform, invert=False)

        px_b04 = red[~mask]
        px_b08 = nir[~mask]
        px_b11 = swir[~mask]
        px_ndvi = ndvi_grid[~mask]
        px_savi = savi_grid[~mask]
        px_ndmi = ndmi_grid[~mask]
        px_r_nir_red = ratio_nir_red[~mask]
        px_r_nir_swir = ratio_nir_swir[~mask]

        valid = ~np.isnan(px_b04) & ~np.isnan(px_b08) & ~np.isnan(px_b11) & ~np.isnan(px_ndvi)
        total_px = int(np.sum(valid))

        if total_px > 0:
            features = np.column_stack([
                px_b04[valid],
                px_b08[valid],
                px_b11[valid],
                px_ndvi[valid],
                px_savi[valid],
                px_ndmi[valid],
                px_r_nir_red[valid],
                px_r_nir_swir[valid]
            ])

            pred_bin = rf_model.predict(features)
            cultivo_px = int(np.sum(pred_bin == 1))
            suelo_px = int(np.sum(pred_bin == 0))
            pct_cobertura_rf = round(float((cultivo_px / total_px) * 100.0), 1)
            pct_suelo_rf = round(float((suelo_px / total_px) * 100.0), 1)
        else:
            pct_cobertura_rf = 0.0
            pct_suelo_rf = 100.0
            total_px = 0
            cultivo_px = 0

        # Guardar métrica en el historial del bloque en datos_procesados.json
        if fecha in p["historial"]:
            p["historial"][fecha]["cobertura_rf_pct"] = pct_cobertura_rf
            p["historial"][fecha]["suelo_rf_pct"] = pct_suelo_rf

        resultados.append({
            "bloque": p["bloque_nombre"],
            "cultivo": p.get("cultivo", "--"),
            "categoria": p.get("categoria_agronomica", "--"),
            "camas_activas": p.get("camas_activas", 0),
            "camas_total": p.get("camas_total", 0),
            "pct_camas_csv": p.get("pct_activa", 0.0),
            "pct_cobertura_rf": pct_cobertura_rf,
            "pct_suelo_rf": pct_suelo_rf,
            "pixeles_totales": total_px,
            "ndvi_med": p["historial"].get(fecha, {}).get("ndvi_med", 0.0),
            "ndvi_p90": p["historial"].get(fecha, {}).get("ndvi_p90", 0.0)
        })

    # Guardar en datos_procesados.json
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

    df_res = pd.DataFrame(resultados)
    output_csv = Path("modelos/cobertura_bloques_rf.csv")
    df_res.to_csv(output_csv, index=False, sep=";", encoding="utf-8")

    print("\n" + "=" * 80)
    print("🌿 EJEMPLO DE CORROBORACIÓN: CAMAS DEL CSV VS COBERTURA REAL RANDOM FOREST")
    print("=" * 80)
    print(f"{'Bloque':<8} | {'Cultivo':<13} | {'Camas CSV':<10} | {'% Camas':<9} | {'% Cobertura RF':<16} | {'% Suelo RF':<12} | {'Diagnóstico':<20}")
    print("-" * 80)
    
    # Muestra representativa de bloques
    muestra_bloques = ["11", "13D", "31A", "101", "22", "31", "127"]
    sub = df_res[df_res["bloque"].isin(muestra_bloques)].copy()
    for _, r in sub.iterrows():
        dif = abs(r['pct_camas_csv'] - r['pct_cobertura_rf'])
        if r['pct_camas_csv'] == 0:
            diag = "Suelo Confirmado"
        elif r['pct_cobertura_rf'] >= 80:
            diag = "Dosel Pleno / Sano"
        elif r['pct_camas_csv'] <= 35:
            diag = "Siembra Naciente"
        else:
            diag = "Cobertura Media"
        print(f"{r['bloque']:<8} | {r['cultivo']:<13} | {r['camas_activas']}/{r['camas_total']:<8} | {r['pct_camas_csv']:>6.1f}%  | {r['pct_cobertura_rf']:>11.1f}%    | {r['pct_suelo_rf']:>8.1f}%   | {diag}")

    print("=" * 80)
    print(f"✅ Inferencia completada. Resultados integrados en 'datos_procesados.json' y '{output_csv}'.")
    return df_res

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    evaluar_cobertura(target)
