#!/usr/bin/env python3
"""
PyGan AgroSat - Procesador y Agrupador de Cultivos y Variedades a Nivel de Camas.
Lee 'bq_sentinel.csv' (con detalle cama a cama por bloque y variedad élite), limpia los datos,
normaliza códigos de Hypericum y otros cultivos comerciales, identifica camas vacías (tumba),
ensayos (PROD.NUEVOS de 1 a 6 camas) y variedades comerciales (Gypsophila, Veronica, Hypericum, Solidago),
calculando la distribución por bloque y seleccionando los bloques candidatos 'estrella'.
"""

import json
from pathlib import Path
import pandas as pd

def normalizar_nombre_bloque(b):
    """Estandariza los identificadores de bloques para cruzar con el Shapefile."""
    b_str = str(b).strip().upper()
    # Casos especiales de nomenclatura (ej. 39D-1 vs 39D1)
    if b_str == "39D-1":
        return "39D1"
    return b_str

def normalizar_producto_maestro(prod_val, var_val=""):
    """
    Estandariza los nombres de productos/cultivos comerciales.
    Detecta automáticamente códigos de Hypericum (ej. 17091, H21-68-7, 18125-03, Magical...)
    que a veces el analista ingresa en la columna de Producto Maestro en vez de Hypericum.
    """
    p = str(prod_val).strip().upper()
    v = str(var_val).strip().upper()
    
    if p in ["VACIO", "TUMBA", "NAN", "", "NONE"]:
        return "VACIO"
    if "PROD.NUEVOS" in p or "ENSAYO" in p:
        return "PROD.NUEVOS"

    # Patrones conocidos de códigos y nombres de Hypericum
    hypericum_patterns = [
        "HYPERICUM", "MAGICAL", "H20-", "H21-", "17091", "17020", "17079", "18039", 
        "18125", "19088", "19089", "20099", "COD-S/N", "ROYAL RED", "150010", 
        "150020", "17088", "19114", "RED SEWEL", "20105", "SUNSET SEWET", "19098", 
        "IE-114", "20013"
    ]
    for pat in hypericum_patterns:
        if pat in p or pat in v:
            if "HYPERICUM" not in p and ("GYPSO" not in p and "VERONICA" not in p and "SOLIDAGO" not in p and "EUCALIPTO" not in p):
                return "HYPERICUM"

    return p

def normalizar_variedad(var_val, prod_val=""):
    """Limpia y estandariza el nombre de la variedad."""
    v = str(var_val).strip().upper()
    if v in ["NAN", "NONE", ""]:
        return "VACIO" if str(prod_val).strip().upper() == "VACIO" else "SIN VARIEDAD"
    return v

def procesar_csv_cultivos(csv_path="bq_sentinel.csv"):
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo {csv_path}")

    # Cargar CSV (con soporte para BOM utf-8-sig o latin1)
    try:
        df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(path, sep=";", encoding="latin1")
    
    # Limpiar columnas
    df.columns = [c.strip() for c in df.columns]
    
    # Detectar columna de variedad si existe
    var_col = next((c for c in df.columns if "VARIEDAD" in c.upper()), None)
    
    df["BLQ_NORM"] = df["BLQ"].apply(normalizar_nombre_bloque)
    df["Ac"] = df["Ac"].astype(str).str.strip()
    
    if var_col:
        df["VARIEDAD_NORM"] = df.apply(lambda r: normalizar_variedad(r[var_col], r.get("PRODUCTO MAESTRO", "")), axis=1)
    else:
        df["VARIEDAD_NORM"] = "SIN VARIEDAD"

    df["PRODUCTO MAESTRO"] = df.apply(lambda r: normalizar_producto_maestro(r["PRODUCTO MAESTRO"], r["VARIEDAD_NORM"]), axis=1)

    resumen_bloques = {}
    registros_tabla = []

    for blq, grp in df.groupby("BLQ_NORM"):
        # AGRUPACIÓN A NIVEL DE CAMAS FÍSICAS ÚNICAS (# Cama)
        cama_grp = grp.groupby("# Cama")
        total_camas = grp["# Cama"].nunique()

        siembra = 0
        poda = 0
        vacio = 0
        ensayos = 0
        comerciales_counts = {}
        variedades_counts = {}

        for c_id, c_rows in cama_grp:
            acs = c_rows["Ac"].tolist()
            prods = c_rows["PRODUCTO MAESTRO"].tolist()
            vars_c = c_rows["VARIEDAD_NORM"].tolist()

            is_siembra = any(a == "Siembra" for a in acs)
            is_poda = any(a == "Poda" for a in acs) and not is_siembra
            is_vacio = all(a == "VACIO" for a in acs)
            has_ensayo = any(p == "PROD.NUEVOS" for p in prods)

            if is_siembra:
                siembra += 1
            elif is_poda:
                poda += 1
            elif is_vacio:
                vacio += 1
            else:
                siembra += 1

            if has_ensayo:
                ensayos += 1

            # Contabilizar cultivos comerciales presentes en la cama física
            comm_prods = set(p for p in prods if p not in ["VACIO", "PROD.NUEVOS"])
            for cp in comm_prods:
                comerciales_counts[cp] = comerciales_counts.get(cp, 0) + 1

            # Contabilizar variedades comerciales presentes en la cama física
            comm_vars = set(v for v in vars_c if v not in ["VACIO", "PROD.NUEVOS", "SIN VARIEDAD", ""])
            for cv in comm_vars:
                variedades_counts[cv] = variedades_counts.get(cv, 0) + 1

        activas = siembra + poda
        tiene_ensayos = ensayos > 0
        num_cultivos = len(comerciales_counts)
        num_variedades = len(variedades_counts)

        # Determinar producto y actividad dominante
        if num_cultivos > 0:
            sorted_prods = sorted(comerciales_counts.items(), key=lambda x: x[1], reverse=True)
            producto_principal = sorted_prods[0][0]
            camas_prod_principal = sorted_prods[0][1]
            pct_prod_principal = round((camas_prod_principal / total_camas) * 100.0, 1)
        elif vacio == total_camas:
            producto_principal = "VACIO / TUMBA"
            camas_prod_principal = vacio
            pct_prod_principal = 100.0
        elif tiene_ensayos:
            producto_principal = "ENSAYOS (PROD.NUEVOS)"
            camas_prod_principal = ensayos
            pct_prod_principal = round((ensayos / total_camas) * 100.0, 1)
        else:
            producto_principal = "OTRO"
            camas_prod_principal = 0
            pct_prod_principal = 0.0

        # Determinar variedad principal y desglose
        if num_variedades > 0:
            sorted_vars = sorted(variedades_counts.items(), key=lambda x: x[1], reverse=True)
            variedad_principal = sorted_vars[0][0]
            camas_var_principal = sorted_vars[0][1]
            pct_var_principal = round((camas_var_principal / total_camas) * 100.0, 1)
            es_monovarietal = (num_variedades == 1)
            if es_monovarietal:
                variedad_resumen = variedad_principal
            else:
                partes = [f"{v} ({cnt})" for v, cnt in sorted_vars]
                variedad_resumen = ", ".join(partes)
        elif vacio == total_camas:
            variedad_principal = "VACIO / TUMBA"
            camas_var_principal = vacio
            pct_var_principal = 100.0
            es_monovarietal = True
            variedad_resumen = "VACIO / TUMBA"
        elif tiene_ensayos and num_variedades == 0:
            variedad_principal = "ENSAYO"
            camas_var_principal = ensayos
            pct_var_principal = round((ensayos / total_camas) * 100.0, 1)
            es_monovarietal = True
            variedad_resumen = "ENSAYO"
        else:
            variedad_principal = "SIN VARIEDAD"
            camas_var_principal = 0
            pct_var_principal = 0.0
            es_monovarietal = False
            variedad_resumen = "SIN VARIEDAD"

        pct_activa = round((activas / total_camas) * 100.0, 1) if total_camas > 0 else 0.0
        pct_vacia = round((vacio / total_camas) * 100.0, 1) if total_camas > 0 else 0.0

        # Clasificación agronómica jerárquica
        if vacio == total_camas:
            categoria = "100% VACIO / TUMBA"
            candidato_estrella = False
        elif activas > 0 and (activas <= 8 or pct_activa <= 35.0):
            # Siembra escalonada (ej. bloque 22 con 3 camas activas de 26)
            categoria = "SIEMBRA ESCALONADA (Parcial <=35% / 5 camas)"
            candidato_estrella = False
        elif tiene_ensayos and ensayos <= 6 and num_cultivos == 1 and vacio == 0:
            categoria = "COMERCIAL CON ENSAYO (1-6 camas)"
            candidato_estrella = False
        elif tiene_ensayos:
            categoria = "ENSAYOS / PROD.NUEVOS"
            candidato_estrella = False
        elif num_cultivos > 1:
            categoria = "MIXTO (VARIOS CULTIVOS)"
            candidato_estrella = False
        elif vacio > 0 and activas > 0:
            categoria = "PARCIALMENTE ACTIVO (>35% activo)"
            candidato_estrella = False
        elif vacio == 0 and num_cultivos == 1 and not tiene_ensayos:
            # Bloque 100% comercial sin divisiones ni ensayos
            categoria = "CULTIVO HOMOGÉNEO"
            candidato_estrella = producto_principal in ["GYPSOPHILA", "HYPERICUM", "VERONICA", "SOLIDAGO"]
        else:
            categoria = "OTRO"
            candidato_estrella = False

        info = {
            "bloque": blq,
            "total_camas": total_camas,
            "camas_siembra": siembra,
            "camas_poda": poda,
            "camas_vacio": vacio,
            "camas_activas": activas,
            "pct_activa": pct_activa,
            "pct_vacia": pct_vacia,
            "camas_ensayos": ensayos,
            "tiene_ensayos": tiene_ensayos,
            "cultivos_comerciales": comerciales_counts,
            "num_cultivos_comerciales": num_cultivos,
            "producto_principal": producto_principal,
            "camas_producto_principal": camas_prod_principal,
            "pct_producto_principal": pct_prod_principal,
            "variedad_principal": variedad_principal,
            "camas_variedad_principal": camas_var_principal,
            "pct_variedad_principal": pct_var_principal,
            "variedades": variedades_counts,
            "variedades_lista": list(variedades_counts.keys()),
            "num_variedades": num_variedades,
            "es_monovarietal": es_monovarietal,
            "variedad_resumen": variedad_resumen,
            "categoria_agronomica": categoria,
            "candidato_estrella": candidato_estrella
        }

        resumen_bloques[blq] = info
        registros_tabla.append(info)

    # Exportar a JSON
    output_json = Path("cultivos_por_bloque.json")
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(resumen_bloques, f, ensure_ascii=False, indent=2)

    # Exportar a CSV resumen
    df_resumen = pd.DataFrame(registros_tabla)
    output_csv = Path("cultivos_resumen_bloques.csv")
    df_resumen.to_csv(output_csv, index=False, sep=";", encoding="utf-8")

    return resumen_bloques, df_resumen

def imprimir_reporte(df_resumen):
    print("=" * 75)
    print("🌿 PYGAN AGROSAT - DISTRIBUCIÓN AGRONÓMICA DE CULTIVOS Y VARIEDADES")
    print("=" * 75)
    print(f"Total de Bloques Analizados: {len(df_resumen)}")
    print(f"Total de Camas en Finca:    {df_resumen['total_camas'].sum():,}")
    print(f"  * Camas en Siembra:       {df_resumen['camas_siembra'].sum():,} ({df_resumen['camas_siembra'].sum()/df_resumen['total_camas'].sum()*100:.1f}%)")
    print(f"  * Camas en Poda:          {df_resumen['camas_poda'].sum():,} ({df_resumen['camas_poda'].sum()/df_resumen['total_camas'].sum()*100:.1f}%)")
    print(f"  * Camas Vacías (Tumba):   {df_resumen['camas_vacio'].sum():,} ({df_resumen['camas_vacio'].sum()/df_resumen['total_camas'].sum()*100:.1f}%)")
    print(f"  * Camas de Ensayos:       {df_resumen['camas_ensayos'].sum():,} ({df_resumen['camas_ensayos'].sum()/df_resumen['total_camas'].sum()*100:.1f}%)")
    
    print("\n📊 CATEGORÍAS AGRONÓMICAS DE BLOQUES:")
    print(df_resumen["categoria_agronomica"].value_counts().to_string())

    print("\n🌺 DISTRIBUCIÓN POR CULTIVO PRINCIPAL:")
    print(df_resumen["producto_principal"].value_counts().to_string())

    print("\n🧬 DIVERSIDAD VARIETAL:")
    monos = df_resumen[df_resumen["es_monovarietal"] & (df_resumen["producto_principal"] != "VACIO / TUMBA")]
    polis = df_resumen[(~df_resumen["es_monovarietal"]) & (df_resumen["num_variedades"] > 1)]
    print(f"  * Bloques Monovarietales (1 sola variedad): {len(monos)}")
    print(f"  * Bloques Polivarietales (>1 variedad):     {len(polis)}")

    estrellas = df_resumen[df_resumen["candidato_estrella"]]
    print("\n" + "=" * 75)
    print(f"⭐ BLOQUES CANDIDATOS A 'ESTRELLA' (PUROS, 100% ACTIVOS, SIN ENSAYOS): {len(estrellas)}")
    print("=" * 75)
    
    for prod in ["SOLIDAGO", "GYPSOPHILA", "VERONICA", "HYPERICUM"]:
        sub = estrellas[estrellas["producto_principal"] == prod]
        bloques = sorted(sub["bloque"].tolist())
        print(f"\n🔹 {prod} ({len(sub)} bloques puros):")
        for b_id in bloques:
            b_info = sub[sub["bloque"] == b_id].iloc[0]
            v_res = b_info["variedad_principal"] if b_info["es_monovarietal"] else f"{b_info['variedad_principal']} (+{b_info['num_variedades']-1} vars)"
            print(f"   - Bloque {b_id:<5} ({b_info['camas_activas']} camas) -> {v_res}")

    print("\n" + "=" * 75)
    print("🌱 BLOQUES DETECTADOS CON SIEMBRA ESCALONADA (PARCIAL / ~5 CAMAS):")
    print("=" * 75)
    escalonadas = df_resumen[df_resumen["categoria_agronomica"] == "SIEMBRA ESCALONADA (Parcial <=35% / 5 camas)"]
    for _, row in escalonadas.iterrows():
        print(f"   * Bloque {row['bloque']}: {row['camas_siembra']} camas siembra, {row['camas_poda']} poda, {row['camas_vacio']} vacías ({row['pct_activa']}% activo) - {row['producto_principal']} ({row['variedad_principal']})")

if __name__ == "__main__":
    resumen, df_res = procesar_csv_cultivos()
    imprimir_reporte(df_res)
