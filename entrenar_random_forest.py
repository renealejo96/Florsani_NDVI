#!/usr/bin/env python3
"""
PyGan AgroSat - Módulo de Machine Learning (Random Forest)
Clasificador Espectral Píxel a Píxel: Dosel Vegetal Activo vs. Suelo Desnudo / Pasillo.

Objetivo:
Entrenar un modelo de bosque aleatorio (Random Forest) utilizando como verdad de campo
(Ground Truth) los 87 polígonos puros de Bloques Estrella (Gypsophila, Hypericum, Veronica, Solidago)
frente a los 53 polígonos de Suelo Desnudo / Tumba.

Salida:
1. 'modelos/modelo_rf_cobertura.joblib' : Modelo binario (Cultivo vs Suelo).
2. 'modelos/modelo_rf_multiclase.joblib' : Modelo multiclase (Hypericum, Solidago, Veronica, Gypsophila, Suelo).
3. 'modelos/reporte_entrenamiento_rf.json': Métricas, matrices de confusión e importancia de bandas.
"""

from datetime import datetime
import json
from pathlib import Path
import warnings
import joblib
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.ops import unary_union
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds
from rasterio.features import geometry_mask
import pystac_client
import planetary_computer

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, f1_score

warnings.filterwarnings("ignore", category=UserWarning)

def extraer_pixeles_entrenamiento(fechas_entrenamiento=["2026-10-27", "2026-10-22", "2026-08-13"]):
    json_path = Path("datos_procesados.json")
    if not json_path.exists():
        raise FileNotFoundError(f"No se encontró {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        datos = json.load(f)

    poligonos = datos["poligonos"]

    # Identificar polígonos de referencia pura
    bloques_estrella = [p for p in poligonos if p.get("candidato_estrella")]
    bloques_tumba = [p for p in poligonos if p.get("categoria_agronomica") == "100% VACIO / TUMBA" or p.get("cultivo") == "VACIO / TUMBA"]

    print(f"📌 Base de Entrenamiento Ground Truth:")
    print(f"   * Polígonos Estrella (Cultivo Puro) : {len(bloques_estrella)}")
    print(f"   * Polígonos Tumba (Suelo Desnudo)   : {len(bloques_tumba)}")

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

    buffered_geometries = {}
    for idx, row in gdf_utm.iterrows():
        orig_geom = row.geometry
        neg_buf = orig_geom.buffer(-5.0)
        analysis_geom = neg_buf if (not neg_buf.is_empty and neg_buf.area > 40.0) else orig_geom
        buffered_geometries[idx] = analysis_geom

    stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
    catalog = pystac_client.Client.open(stac_url, modifier=planetary_computer.sign_inplace)

    c_minx, c_miny, c_maxx, c_maxy = crop_bounds_utm
    scale_factor = 10000.0

    registros = []

    for fecha in fechas_entrenamiento:
        print(f"\n📡 Extrayendo firmas espectrales de la fecha: {fecha}...")
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=stac_bbox,
            datetime=f"{fecha}/{fecha}",
            sortby=[{"field": "datetime", "direction": "asc"}]
        )
        items = list(search.items())
        if not items:
            print(f"   ⚠️ No se encontró escena para {fecha}, omitiendo...")
            continue
        item = items[0]

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

        # 1. Extraer píxeles de Cultivos Estrella (Clase CULTIVO / FLOR)
        for p in bloques_estrella:
            idx = p["id"]
            flor = str(p.get("cultivo", "OTRO")).upper()
            geom = buffered_geometries.get(idx)
            if geom is None:
                continue

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
            
            # Filtro de pureza agronómica: Píxeles con dosel vegetal activo
            # (evita entrenar la clase 'cultivo' con píxeles que caen justo sobre los pasillos de tierra entre camas)
            umbral_dosel = 0.24 if "GYPSO" in flor else 0.30
            filtro_cultivo = valid & (px_ndvi >= umbral_dosel)

            for i in range(len(px_b04[filtro_cultivo])):
                registros.append({
                    "fecha": fecha,
                    "bloque": p["bloque_nombre"],
                    "b04_red": float(px_b04[filtro_cultivo][i]),
                    "b08_nir": float(px_b08[filtro_cultivo][i]),
                    "b11_swir": float(px_b11[filtro_cultivo][i]),
                    "ndvi": float(px_ndvi[filtro_cultivo][i]),
                    "savi": float(px_savi[filtro_cultivo][i]),
                    "ndmi": float(px_ndmi[filtro_cultivo][i]),
                    "ratio_nir_red": float(px_r_nir_red[filtro_cultivo][i]),
                    "ratio_nir_swir": float(px_r_nir_swir[filtro_cultivo][i]),
                    "clase_binaria": "CULTIVO",
                    "etiqueta_binaria": 1,
                    "clase_cultivo": flor
                })

        # 2. Extraer píxeles de Tumbas / Suelo Desnudo (Clase SUELO)
        for p in bloques_tumba:
            idx = p["id"]
            geom = buffered_geometries.get(idx)
            if geom is None:
                continue

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
            # Filtro de pureza de suelo: Suelo limpio sin malezas nacientes
            filtro_suelo = valid & (px_ndvi <= 0.28)

            for i in range(len(px_b04[filtro_suelo])):
                registros.append({
                    "fecha": fecha,
                    "bloque": p["bloque_nombre"],
                    "b04_red": float(px_b04[filtro_suelo][i]),
                    "b08_nir": float(px_b08[filtro_suelo][i]),
                    "b11_swir": float(px_b11[filtro_suelo][i]),
                    "ndvi": float(px_ndvi[filtro_suelo][i]),
                    "savi": float(px_savi[filtro_suelo][i]),
                    "ndmi": float(px_ndmi[filtro_suelo][i]),
                    "ratio_nir_red": float(px_r_nir_red[filtro_suelo][i]),
                    "ratio_nir_swir": float(px_r_nir_swir[filtro_suelo][i]),
                    "clase_binaria": "SUELO",
                    "etiqueta_binaria": 0,
                    "clase_cultivo": "SUELO_DESNUDO"
                })

    df = pd.DataFrame(registros)
    print(f"\n📊 Total de píxeles puros extraídos para entrenamiento: {len(df):,}")
    print(df["clase_binaria"].value_counts().to_string())
    print("\nDesglose por clase de flor / suelo:")
    print(df["clase_cultivo"].value_counts().to_string())
    return df

def entrenar_modelos(df):
    modelos_dir = Path("modelos")
    modelos_dir.mkdir(exist_ok=True)

    feature_cols = [
        "b04_red",
        "b08_nir",
        "b11_swir",
        "ndvi",
        "savi",
        "ndmi",
        "ratio_nir_red",
        "ratio_nir_swir"
    ]

    X = df[feature_cols].values
    y_bin = df["etiqueta_binaria"].values
    y_multi = df["clase_cultivo"].values

    # =========================================================================
    # MODELO 1: CLASIFICADOR BINARIO (CULTIVO ACTIVO vs. SUELO DESNUDO)
    # =========================================================================
    print("\n" + "=" * 70)
    print("🌲 ENTRENANDO MODELO 1: RANDOM FOREST BINARIO (CULTIVO vs SUELO)")
    print("=" * 70)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_bin, test_size=0.25, random_state=42, stratify=y_bin
    )

    rf_bin = RandomForestClassifier(
        n_estimators=150,
        max_depth=10,
        min_samples_split=4,
        random_state=42,
        class_weight="balanced",
        n_jobs=-1
    )
    rf_bin.fit(X_train, y_train)

    y_pred = rf_bin.predict(X_test)
    acc_bin = accuracy_score(y_test, y_pred)
    f1_bin = f1_score(y_test, y_pred)

    print(f"✅ Exactitud Global (Accuracy) : {acc_bin * 100:.2f}%")
    print(f"✅ F1-Score Promedio            : {f1_bin * 100:.2f}%\n")
    print("Reporte de Clasificación:")
    report_bin = classification_report(y_test, y_pred, target_names=["SUELO (0)", "CULTIVO (1)"])
    print(report_bin)

    cm_bin = confusion_matrix(y_test, y_pred).tolist()
    print("Matriz de Confusión [Suelo, Cultivo]:")
    print(np.array(cm_bin))

    # Importancia de variables
    importancias_bin = dict(zip(feature_cols, [round(float(v), 4) for v in rf_bin.feature_importances_]))
    print("\nImportancia de Bandas e Índices en la Detección de Dosel:")
    for f_name, f_imp in sorted(importancias_bin.items(), key=lambda x: x[1], reverse=True):
        print(f"   * {f_name:<16}: {f_imp * 100:>5.2f}%")

    joblib.dump(rf_bin, modelos_dir / "modelo_rf_cobertura.joblib")
    print(f"💾 Guardado en: {modelos_dir / 'modelo_rf_cobertura.joblib'}")

    # =========================================================================
    # MODELO 2: CLASIFICADOR MULTICLASE (CADA FLOR vs SUELO)
    # =========================================================================
    print("\n" + "=" * 70)
    print("🌸 ENTRENANDO MODELO 2: RANDOM FOREST MULTICLASE POR CULTIVO")
    print("=" * 70)

    X_train_m, X_test_m, y_train_m, y_test_m = train_test_split(
        X, y_multi, test_size=0.25, random_state=42, stratify=y_multi
    )

    rf_multi = RandomForestClassifier(
        n_estimators=150,
        max_depth=12,
        min_samples_split=4,
        random_state=42,
        class_weight="balanced",
        n_jobs=-1
    )
    rf_multi.fit(X_train_m, y_train_m)

    y_pred_m = rf_multi.predict(X_test_m)
    acc_multi = accuracy_score(y_test_m, y_pred_m)

    print(f"✅ Exactitud Multiclase (Accuracy) : {acc_multi * 100:.2f}%\n")
    report_multi = classification_report(y_test_m, y_pred_m)
    print("Reporte Multiclase por Especie de Flor:")
    print(report_multi)

    joblib.dump(rf_multi, modelos_dir / "modelo_rf_multiclase.joblib")
    print(f"💾 Guardado en: {modelos_dir / 'modelo_rf_multiclase.joblib'}")

    # Guardar métricas en JSON para auditoría técnica
    reporte_final = {
        "fecha_entrenamiento": datetime.now().isoformat(),
        "total_pixeles_entrenamiento": len(df),
        "variables_entrada": feature_cols,
        "modelo_binario_cobertura": {
            "accuracy": round(float(acc_bin), 4),
            "f1_score": round(float(f1_bin), 4),
            "confusion_matrix": cm_bin,
            "importancia_variables": importancias_bin
        },
        "modelo_multiclase_cultivos": {
            "accuracy": round(float(acc_multi), 4),
            "clases": list(rf_multi.classes_)
        }
    }

    with open(modelos_dir / "reporte_entrenamiento_rf.json", "w", encoding="utf-8") as f:
        json.dump(reporte_final, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print("🎉 MODELOS RANDOM FOREST ENTRENADOS Y SERIALIZADOS EXITOSAMENTE")
    print("=" * 70)
    return reporte_final

if __name__ == "__main__":
    df_pixeles = extraer_pixeles_entrenamiento()
    entrenar_modelos(df_pixeles)
