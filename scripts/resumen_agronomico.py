#!/usr/bin/env python3
"""
Resumen agronómico del archivo datos_procesados.json.
"""
import json
import numpy as np

def main():
    with open("datos_procesados.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    fechas = data["metadata"]["fechas"]
    poligonos = data["poligonos"]

    print("=" * 70)
    print("🌾 AUDITORÍA AGRONÓMICA SATELITAL - FINCA PYGAN")
    print("=" * 70)

    print("\n1. EVOLUCIÓN TEMPORAL DEL PREDIO COMPLETO (250 BLOQUES):")
    for f in fechas:
        ndvis = [p["historial"][f]["ndvi_med"] for p in poligonos if p["historial"][f]["ndvi_med"] > 0]
        savis = [p["historial"][f]["savi_med"] for p in poligonos if p["historial"][f]["ndvi_med"] > 0]
        ndmis = [p["historial"][f]["ndmi_med"] for p in poligonos if p["historial"][f]["ndvi_med"] > 0]
        crit_pcts = [p["historial"][f]["area_critica_pct"] for p in poligonos if p["historial"][f]["ndvi_med"] > 0]

        en_alerta = sum(1 for c in crit_pcts if c > 30.0)
        optimos = sum(1 for n in ndvis if n >= 0.65)
        print(f"   * Fecha {f}:")
        print(f"     - NDVI Medio: {np.mean(ndvis):.3f} | SAVI Medio: {np.mean(savis):.3f} | NDMI Medio: {np.mean(ndmis):.3f}")
        print(f"     - Bloques en Alerta (>30% área crítica): {en_alerta} de 250")
        print(f"     - Bloques con Vigor Óptimo (NDVI >= 0.65): {optimos} de 250")

    f_reciente = fechas[-1]
    print(f"\n2. TOP 5 BLOQUES MÁS CRÍTICOS A LA FECHA RECIENTE ({f_reciente}):")
    sorted_crit = sorted(poligonos, key=lambda x: x["historial"][f_reciente]["area_critica_pct"], reverse=True)
    for i, p in enumerate(sorted_crit[:5]):
        h = p["historial"][f_reciente]
        print(f"   [{i+1}] Bloque {p['bloque_nombre']} (Área: {p['area_m2']:.0f} m² | Técnico: {p['tecnico']})")
        print(f"       -> % Área Crítica: {h['area_critica_pct']:.1f}% | NDVI Med: {h['ndvi_med']:.3f} | P10: {h['ndvi_p10']:.3f} | NDMI: {h['ndmi_med']:.3f}")

    print(f"\n3. TOP 5 BLOQUES CON MEJOR VIGOR VEGETAL ({f_reciente}):")
    sorted_opt = sorted(poligonos, key=lambda x: x["historial"][f_reciente]["ndvi_med"], reverse=True)
    for i, p in enumerate(sorted_opt[:5]):
        h = p["historial"][f_reciente]
        print(f"   [{i+1}] Bloque {p['bloque_nombre']} (Área: {p['area_m2']:.0f} m² | Técnico: {p['tecnico']})")
        print(f"       -> NDVI Med: {h['ndvi_med']:.3f} | SAVI: {h['savi_med']:.3f} | NDMI: {h['ndmi_med']:.3f} | Área Crítica: {h['area_critica_pct']:.1f}%")

    print("=" * 70)

if __name__ == "__main__":
    main()
