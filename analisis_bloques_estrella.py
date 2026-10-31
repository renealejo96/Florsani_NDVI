#!/usr/bin/env python3
"""
PyGan AgroSat - Calibración y Ranking de Bloques Estrella para Flores de Verano.
Analiza la serie temporal multiespectral de los bloques puros candidatos (sin ensayos ni divisiones)
para Gypsophila, Hypericum, Veronica, Solidago y Suelo/Tumba, mostrando sus rangos reales
de NDVI (Medio, P10, P90), SAVI y NDMI, además de sus variedades élite dominantes.
"""

import json
from pathlib import Path
import pandas as pd
import numpy as np

def rankear_candidatos_estrella(json_path="datos_procesados.json"):
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró {json_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    poligonos = data.get("poligonos", [])
    fechas = data.get("metadata", {}).get("fechas", [])

    filas = []
    for p in poligonos:
        c_estrella = p.get("candidato_estrella", False)
        cultivo = p.get("cultivo", "DESCONOCIDO")
        variedad = p.get("variedad", "SIN DATO")
        variedad_resumen = p.get("variedad_resumen", "")
        bloque = p.get("bloque_nombre", str(p.get("id")))

        # Extraer serie temporal
        ndvis, savis, ndmis, p90s, cvs = [], [], [], [], []
        for f in fechas:
            h = p.get("historial", {}).get(f)
            if h and h.get("ndvi_med", 0) > 0:
                ndvis.append(h["ndvi_med"])
                savis.append(h["savi_med"])
                ndmis.append(h["ndmi_med"])
                p90s.append(h.get("ndvi_p90", h["ndvi_med"]))
                cvs.append(h.get("cv_pct", 0))

        if len(ndvis) > 0:
            filas.append({
                "bloque": bloque,
                "cultivo": cultivo,
                "variedad": variedad,
                "variedad_resumen": variedad_resumen,
                "categoria": p.get("categoria_agronomica", ""),
                "camas_total": p.get("camas_total", 0),
                "camas_activas": p.get("camas_activas", 0),
                "candidato_estrella": c_estrella,
                "ndvi_prom_historico": round(float(np.mean(ndvis)), 3),
                "ndvi_max_historico": round(float(np.max(ndvis)), 3),
                "ndvi_p90_historico": round(float(np.mean(p90s)), 3),
                "savi_prom_historico": round(float(np.mean(savis)), 3),
                "ndmi_prom_historico": round(float(np.mean(ndmis)), 3),
                "cv_prom_historico": round(float(np.mean(cvs)), 1),
                "fechas_validas": len(ndvis)
            })

    df = pd.DataFrame(filas)
    return df

def imprimir_ranking(df):
    print("=" * 95)
    print("🌟 RANKING Y PERFILES ESPECTRALES DE BLOQUES CANDIDATOS A 'ESTRELLA' (POR CULTIVO Y VARIEDAD)")
    print("=" * 95)

    estrellas = df[df["candidato_estrella"]].copy()

    for cultivo in ["SOLIDAGO", "GYPSOPHILA", "VERONICA", "HYPERICUM"]:
        sub = estrellas[estrellas["cultivo"] == cultivo].sort_values("ndvi_prom_historico", ascending=False)
        print(f"\n🌸 {cultivo} (Total bloques puros: {len(sub)})")
        print("-" * 95)
        print(f"{'Bloque':<8} | {'Variedad Élite Dominante':<24} | {'Camas':<6} | {'NDVI Med':<9} | {'NDVI P90':<9} | {'SAVI':<7} | {'NDMI (Agua)':<11} | {'CV %':<6}")
        print("-" * 95)
        for _, r in sub.head(6).iterrows():
            print(f"{r['bloque']:<8} | {r['variedad'][:24]:<24} | {r['camas_activas']:<6} | {r['ndvi_prom_historico']:<9} | {r['ndvi_p90_historico']:<9} | {r['savi_prom_historico']:<7} | {r['ndmi_prom_historico']:<11} | {r['cv_prom_historico']}%")

    print("\n" + "=" * 95)
    print("🟫 LÍNEA BASE DE SUELO DESNUDO / TUMBA (100% VACÍO):")
    tumbas = df[df["categoria"] == "100% VACIO / TUMBA"]
    if len(tumbas) > 0:
        print(f"Total bloques en tumba evaluados: {len(tumbas)}")
        print(f"  * NDVI Promedio de Suelo:  {tumbas['ndvi_prom_historico'].mean():.3f} (Rango: {tumbas['ndvi_prom_historico'].min():.3f} a {tumbas['ndvi_prom_historico'].max():.3f})")
        print(f"  * SAVI Promedio de Suelo:  {tumbas['savi_prom_historico'].mean():.3f}")
        print(f"  * NDMI Promedio de Suelo:  {tumbas['ndmi_prom_historico'].mean():.3f}")
    print("=" * 95)

if __name__ == "__main__":
    df_eval = rankear_candidatos_estrella()
    imprimir_ranking(df_eval)
