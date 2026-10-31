#!/usr/bin/env python3
"""
Script de diagnóstico e inspección del Área de Interés (AOI).
Analiza el shapefile de parcelas agrícolas: geometría, proyección (CRS),
integridad topológica y coordenadas WGS84 para catálogos satelitales.
"""

from pathlib import Path
import geopandas as gpd

def main():
    aoi_path = Path("satelital/pygan.shp")
    if not aoi_path.exists():
        print(f"[-] Error: No se encontró el archivo {aoi_path}")
        return

    print("=" * 60)
    print("📡 DIAGNÓSTICO GEOESPACIAL DEL ÁREA DE INTERÉS (AOI)")
    print("=" * 60)

    # 1. Carga del shapefile
    gdf = gpd.read_file(aoi_path)
    print(f"[+] Archivo: {aoi_path.name}")
    print(f"[+] Cantidad de geometrías (lotes/parcelas): {len(gdf)}")
    print(f"[+] Sistema de Referencia de Coordenadas (CRS): {gdf.crs}")

    # 2. Validación topológica
    valid_geoms = gdf.is_valid.all()
    print(f"[+] ¿Todas las geometrías son topológicamente válidas?: {valid_geoms}")
    if not valid_geoms:
        invalid_count = (~gdf.is_valid).sum()
        print(f"[!] Advertencia: {invalid_count} geometrías tienen auto-intersecciones o errores de anillo.")

    # 3. Cálculo de Superficie
    # Dado que el CRS original es EPSG:32717 (UTM 17S, metros), el cálculo de área es directo
    area_m2 = gdf.geometry.area.sum()
    area_ha = area_m2 / 10000.0
    print(f"[+] Superficie total del predio: {area_ha:,.2f} hectáreas ({area_m2:,.2f} m²)")

    # 4. Límites espaciales en coordenadas nativas (UTM)
    minx_utm, miny_utm, maxx_utm, maxy_utm = gdf.total_bounds
    print(f"[+] BBOX UTM 17S: X [{minx_utm:.1f}, {maxx_utm:.1f}], Y [{miny_utm:.1f}, {maxy_utm:.1f}]")

    # 5. Transformación a EPSG:4326 (WGS84 Lat/Lon) para APIs STAC
    gdf_wgs84 = gdf.to_crs(epsg=4326)
    min_lon, min_lat, max_lon, max_lat = gdf_wgs84.total_bounds
    print("\n" + "-" * 60)
    print("🌐 COORDENADAS PARA BÚSQUEDA SATELITAL (EPSG:4326 WGS84)")
    print("-" * 60)
    print(f"[+] Bounding Box: [{min_lon:.6f}, {min_lat:.6f}, {max_lon:.6f}, {max_lat:.6f}]")
    
    # Centroide consolidado
    centroid = gdf_wgs84.unary_union.centroid
    print(f"[+] Centroide del predio: Latitud {centroid.y:.6f}, Longitud {centroid.x:.6f}")
    print(f"[+] Enlace Google Maps de referencia: https://maps.google.com/?q={centroid.y:.6f},{centroid.x:.6f}")

    # 6. Tabla de atributos
    print("\n" + "-" * 60)
    print("📋 COLUMNAS Y MUESTRA DE ATRIBUTOS")
    print("-" * 60)
    print(f"[+] Columnas: {list(gdf.columns)}")
    cols_to_show = [c for c in gdf.columns if c != "geometry"]
    print(gdf[cols_to_show].head())

if __name__ == "__main__":
    main()
