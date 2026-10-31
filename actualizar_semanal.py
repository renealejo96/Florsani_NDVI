#!/usr/bin/env python3
"""
PyGan AgroSat - Script de Actualización Semanal Automatizada.
Ejecuta la actualización del modelo cuando el analista entrega un nuevo CSV semanal
y, opcionalmente, descarga e integra nuevas pasadas satelitales despejadas de Sentinel-2.

Uso:
  python actualizar_semanal.py                      # Actualiza agronomía de camas y cultivos
  python actualizar_semanal.py --satelite           # Actualiza agronomía y busca automáticamente nuevas pasadas
  python actualizar_semanal.py --fecha 2026-10-27   # Actualiza agronomía y procesa esa fecha satelital específica
"""

from datetime import datetime
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

from procesar_cultivos import procesar_csv_cultivos, normalizar_nombre_bloque
from descargar_satelite import procesar_fecha_satelital, auto_detectar_y_descargar

def actualizar_semana(csv_path="bq_sentinel.csv", json_path="datos_procesados.json", perfiles_path="perfiles_calibrados.json", satelite_target=None):
    print("=" * 75)
    print("🔄 ACTUALIZACIÓN SEMANAL DE CULTIVOS Y MONITOREO - PYGAN AGROSAT")
    print("=" * 75)

    csv_file = Path(csv_path)
    json_file = Path(json_path)
    perfiles_file = Path(perfiles_path)

    if not csv_file.exists():
        print(f"❌ Error: No se encontró el archivo {csv_path}.")
        print("   Por favor coloca el CSV semanal en la carpeta del proyecto.")
        return False

    if not json_file.exists():
        print(f"❌ Error: No se encontró {json_path}. Ejecute etl_sentinel.py primero.")
        return False

    # 1. Cargar y procesar el nuevo CSV de camas y variedades
    print(f"\n[1/4] Procesando nuevo archivo de camas y variedades: {csv_path}...")
    cultivos_map, df_resumen = procesar_csv_cultivos(csv_file)
    print(f"   -> {len(df_resumen)} bloques y {df_resumen['total_camas'].sum():,} camas analizadas.")

    # 2. Cargar perfiles calibrados
    perfiles = {}
    if perfiles_file.exists():
        with open(perfiles_file, "r", encoding="utf-8") as f:
            perfiles = json.load(f).get("cultivos", {})
        print(f"[2/4] Perfiles calibrados cargados ({', '.join(perfiles.keys())}).")
    else:
        print("[2/4] Advertencia: No se encontró perfiles_calibrados.json, usando umbrales base.")

    # 3. Actualizar datos_procesados.json en memoria
    print(f"[3/4] Vinculando datos y variedades de la semana a las geometrías de la finca...")
    with open(json_file, "r", encoding="utf-8") as f:
        datos = json.load(f)

    poligonos = datos.get("poligonos", [])

    conteo_estados = {
        "Estrellas Vigentes": 0,
        "Siembra Escalonada": 0,
        "En Poda": 0,
        "En Tumba/Suelo": 0,
        "Con Ensayos": 0
    }

    for p in poligonos:
        b_key = normalizar_nombre_bloque(p["bloque_nombre"])
        c_info = cultivos_map.get(b_key, {})

        # Actualizar metadatos de agronomía y variedades
        p["cultivo"] = c_info.get("producto_principal", "SIN DATO")
        p["variedad"] = c_info.get("variedad_principal", "SIN DATO")
        p["variedad_resumen"] = c_info.get("variedad_resumen", "")
        p["variedades"] = c_info.get("variedades", {})
        p["variedades_lista"] = c_info.get("variedades_lista", [])
        p["num_variedades"] = c_info.get("num_variedades", 0)
        p["es_monovarietal"] = c_info.get("es_monovarietal", False)
        p["camas_variedad_principal"] = c_info.get("camas_variedad_principal", 0)
        p["categoria_agronomica"] = c_info.get("categoria_agronomica", "SIN DATO")
        p["camas_total"] = c_info.get("total_camas", 0)
        p["camas_activas"] = c_info.get("camas_activas", 0)
        p["camas_vacias"] = c_info.get("camas_vacio", 0)
        p["pct_activa"] = c_info.get("pct_activa", 0.0)
        p["tiene_ensayos"] = c_info.get("tiene_ensayos", False)
        p["candidato_estrella"] = c_info.get("candidato_estrella", False)

        if p["candidato_estrella"]:
            conteo_estados["Estrellas Vigentes"] += 1
        elif "SIEMBRA ESCALONADA" in p["categoria_agronomica"]:
            conteo_estados["Siembra Escalonada"] += 1
        elif "VACIO" in p["categoria_agronomica"]:
            conteo_estados["En Tumba/Suelo"] += 1
        elif p["tiene_ensayos"]:
            conteo_estados["Con Ensayos"] += 1
        elif c_info.get("camas_poda", 0) > c_info.get("camas_siembra", 0):
            conteo_estados["En Poda"] += 1

    datos["metadata"]["actualizado_semana_en"] = datetime.now().isoformat()
    datos["metadata"]["archivo_cultivos_fuente"] = csv_file.name

    # Guardar JSON actualizado
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

    print(f"[4/4] Guardado exitoso en {json_path}.")

    # Paso opcional: Descarga Satelital
    if satelite_target == "AUTO":
        print("\n🛰️ [OPCIONAL] Verificando nuevas pasadas satelitales despejadas...")
        auto_detectar_y_descargar(json_path=json_path)
    elif satelite_target:
        print(f"\n🛰️ [OPCIONAL] Descargando pasada satelital específica: {satelite_target}...")
        procesar_fecha_satelital(satelite_target, json_path=json_path)

    # Recargar datos para mostrar reporte final
    with open(json_file, "r", encoding="utf-8") as f:
        datos_actualizados = json.load(f)
    fechas = datos_actualizados.get("metadata", {}).get("fechas", [])

    print("\n" + "=" * 75)
    print("📊 RESUMEN DINÁMICO DE ESTA SEMANA EN FINCA:")
    print("=" * 75)
    for est, cnt in conteo_estados.items():
        print(f"   * {est:<22}: {cnt} bloques")

    estrellas = df_resumen[df_resumen["candidato_estrella"]]
    print("\n⭐ BLOQUES ESTRELLA VIGENTES ESTA SEMANA POR CULTIVO:")
    for flor in ["SOLIDAGO", "GYPSOPHILA", "VERONICA", "HYPERICUM"]:
        sub = estrellas[estrellas["producto_principal"] == flor]
        print(f"   * {flor:<12}: {len(sub)} bloques activos ({', '.join(sorted(sub['bloque'].tolist())[:6])}...)")

    print(f"\n📅 FECHAS SATELITALES DISPONIBLES EN EL DASHBOARD ({len(fechas)} pasadas):")
    print(f"   * Rango: {fechas[0]} ---> {fechas[-1]} (ÚLTIMA)")

    print("\n✅ ¡LISTO! El modelo y el Dashboard ya están actualizados.")
    print("=" * 75)
    return True

if __name__ == "__main__":
    satelite = None
    archivo = "bq_sentinel.csv"
    
    args = sys.argv[1:]
    if "--satelite" in args or "--auto-satelite" in args:
        satelite = "AUTO"
    elif "--fecha" in args:
        idx = args.index("--fecha")
        if idx + 1 < len(args):
            satelite = args[idx + 1]
    elif len(args) == 1 and not args[0].startswith("--"):
        if args[0].endswith(".csv"):
            archivo = args[0]
        elif len(args[0]) == 10 and args[0].count("-") == 2:
            # Es una fecha ej 2026-10-27
            satelite = args[0]

    actualizar_semana(csv_path=archivo, satelite_target=satelite)
