#!/usr/bin/env python3
"""
Consulta todas las escenas disponibles de Sentinel-2 L2A desde el 14 de agosto hasta octubre 2026.
"""
from datetime import datetime
import pystac_client
import planetary_computer

def main():
    print("=" * 70)
    print("🛰️ CONSULTA DE DISPONIBILIDAD GRATUITA SENTINEL-2 (AGOSTO - OCTUBRE 2026)")
    print("=" * 70)

    bbox = [-78.405976, 0.139019, -78.385796, 0.146912]
    stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
    
    catalog = pystac_client.Client.open(stac_url, modifier=planetary_computer.sign_inplace)

    # Buscar desde el 14 de agosto hasta el 18 de octubre de 2026
    date_range = "2026-08-14/2026-10-18"
    print(f"[+] Consultando catálogo STAC para el rango: {date_range}")

    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime=date_range,
        sortby=[{"field": "datetime", "direction": "desc"}]
    )

    items = list(search.items())
    print(f"[+] Total de pasadas satelitales gratuitas encontradas: {len(items)}\n")

    print(f"{'FECHA':<12} | {'SATÉLITE':<12} | {'NUBES ESCENA':<15} | {'ID ESCENA'}")
    print("-" * 75)
    for it in items:
        dt_str = it.datetime.strftime("%Y-%m-%d %H:%M")
        platform = it.properties.get("platform", "Sentinel-2")
        clouds = it.properties.get("eo:cloud_cover", 0.0)
        print(f"{dt_str:<12} | {platform:<12} | {clouds:>6.1f}%          | {it.id[:30]}...")

    print("=" * 70)

if __name__ == "__main__":
    main()
