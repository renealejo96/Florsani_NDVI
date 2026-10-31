#!/usr/bin/env python3
"""
Fase 1: Diagnóstico e Inspección del Shapefile pygan.shp exportado de ArcGIS.
"""
import json
from pathlib import Path
import geopandas as gpd

def main():
    shp_path = Path("satelital/pygan.shp")
    if not shp_path.exists():
        print(f"[-] Error: No existe el archivo {shp_path}")
        return

    gdf = gpd.read_file(shp_path)

    print("=" * 65)
    print("📋 REPORTE DE INSPECCIÓN GIS (ARCGIS SHAPEFILE)")
    print("=" * 65)
    
    # a) Cantidad de polígonos
    num_poligonos = len(gdf)
    print(f"\na) CANTIDAD DE REGISTROS / POLÍGONOS:")
    print(f"   -> Total de polígonos/lotes en el archivo: {num_poligonos}")
    
    # b) Sistema de Coordenadas (CRS / EPSG)
    crs_info = gdf.crs
    epsg_code = crs_info.to_epsg() if crs_info else None
    print(f"\nb) SISTEMA DE REFERENCIA DE COORDENADAS (CRS):")
    print(f"   -> Nombre del CRS: {crs_info.name if crs_info else 'No definido'}")
    print(f"   -> Código EPSG: EPSG:{epsg_code}" if epsg_code else f"   -> EPSG: {crs_info}")
    print(f"   -> Es proyectado (métrico): {crs_info.is_projected if crs_info else False}")
    print(f"   -> Unidades del sistema: {crs_info.axis_info[0].unit_name if crs_info else 'Desconocido'}")
    
    # c) Columnas y Primeras 5 Filas
    print(f"\nc) COLUMNAS DE LA TABLA DE ATRIBUTOS (.dbf):")
    cols = [col for col in gdf.columns if col != "geometry"]
    print(f"   -> Columnas ({len(cols)}): {cols}")
    print("\n   -> Muestra de las primeras 5 filas:")
    df_sample = gdf[cols].head(5)
    print(df_sample.to_string(index=True))

    print("\n" + "=" * 65)

if __name__ == "__main__":
    main()
