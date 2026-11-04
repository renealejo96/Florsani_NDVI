import json
from shapely.geometry import shape

print("Cargando datos_procesados.json...")
with open('datos_procesados.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Diccionario maestro de calicatas (Anexos 1 y 2 del informe Pantoja 2026)
calicatas_info = [
    {
        "id": 1,
        "bloque": "154",
        "condicion": "Sembrado",
        "cultivo": "Flor Comercial",
        "profundidad_a_cm": 30,
        "textura_a": "Limo-Arenoso (LA)",
        "estructura_a": "Bloques y Gránulos (BG)",
        "horizonte_b": "Masiva compactada a 70 cm (LA / LAr)",
        "tdr_antes": 27.7,
        "tdr_despues": 27.4,
        "humedad_lab_antes": 29.33,
        "humedad_lab_despues": 30.72,
        "densidad_aparente": 1.28,
        "porosidad_pct": 48.25,
        "diagnostico": "Capa arable de 30 cm con horizonte B1 masivo compactado a 70 cm. Retención adecuada pero requiere respetar lámina máxima de 3.18 mm."
    },
    {
        "id": 2,
        "bloque": "103",
        "condicion": "Subsolado en el pasado",
        "cultivo": "Renovación",
        "profundidad_a_cm": 30,
        "textura_a": "Limoso (L)",
        "estructura_a": "Bloques, Gránulos y Migajosa (BGM)",
        "horizonte_b": "Limoso masivo a 70 cm; LA a 100+ cm",
        "tdr_antes": 9.9,
        "tdr_despues": 26.7,
        "humedad_lab_antes": 19.43,
        "humedad_lab_despues": 40.54,
        "densidad_aparente": 1.32,
        "porosidad_pct": 49.92,
        "diagnostico": "Respuesta muy favorable al subsolado previo; excelente incremento de infiltración (TDR subió de 9.9% a 26.7% post-riego)."
    },
    {
        "id": 3,
        "bloque": "13B",
        "condicion": "Sembrado",
        "cultivo": "Verónica",
        "profundidad_a_cm": 30,
        "textura_a": "Limo-Arenoso (LA)",
        "estructura_a": "Bloques, Gránulos y Migajosa (BGM)",
        "horizonte_b": "Arcillo-Limoso masivo a 80 cm",
        "tdr_antes": 11.5,
        "tdr_despues": 18.3,
        "humedad_lab_antes": 17.05,
        "humedad_lab_despues": 34.27,
        "densidad_aparente": 1.36,
        "porosidad_pct": 51.46,
        "diagnostico": "Cultivo de Verónica. Transición a arcillo-limoso en B1. Mantener ciclos cortos de riego."
    },
    {
        "id": 4,
        "bloque": "74",
        "condicion": "En descanso",
        "cultivo": "VACIO / TUMBA",
        "profundidad_a_cm": 40,
        "textura_a": "Limo-Arenoso (LA)",
        "estructura_a": "Bloques, Gránulos y Migajosa (BGM)",
        "horizonte_b": "Limo-arenoso masivo a 90 cm; Limoso a 110+ cm",
        "tdr_antes": 15.6,
        "tdr_despues": 10.8,
        "humedad_lab_antes": 18.67,
        "humedad_lab_despues": 13.78,
        "densidad_aparente": 1.32,
        "porosidad_pct": 49.95,
        "diagnostico": "Capa superficial profunda (40 cm). En descanso. Drenaje rápido, requiere enriquecimiento de MO."
    },
    {
        "id": 5,
        "bloque": "92",
        "condicion": "En descanso",
        "cultivo": "VACIO / TUMBA",
        "profundidad_a_cm": 50,
        "textura_a": "Limoso (L)",
        "estructura_a": "Bloques, Gránulos y Migajosa (BGM)",
        "horizonte_b": "Limoso masivo a 80 cm",
        "tdr_antes": 22.6,
        "tdr_despues": 22.8,
        "humedad_lab_antes": 26.41,
        "humedad_lab_despues": 25.67,
        "densidad_aparente": 1.13,
        "porosidad_pct": 42.57,
        "diagnostico": "Excelente horizonte A profundo (50 cm). Estabilidad hídrica alta y buena capacidad de retención."
    },
    {
        "id": 6,
        "bloque": "84",
        "condicion": "Con Cascajo",
        "cultivo": "En descanso",
        "profundidad_a_cm": 50,
        "textura_a": "Limoso (L)",
        "estructura_a": "Bloques, Gránulos y Migajosa (BGM)",
        "horizonte_b": "Limo-arenoso a 80 cm; Arena-limosa con cascajo a 100+ cm",
        "tdr_antes": 22.2,
        "tdr_despues": 24.9,
        "humedad_lab_antes": 24.19,
        "humedad_lab_despues": 29.03,
        "densidad_aparente": 1.29,
        "porosidad_pct": 48.74,
        "diagnostico": "Presencia de cascajo y gravilla en profundidad. Drenaje acelerado en B2."
    },
    {
        "id": 7,
        "bloque": "31E",
        "condicion": "En descanso",
        "cultivo": "SOLIDAGO / VACIO",
        "profundidad_a_cm": 20,
        "textura_a": "Arena-Limosa (AL)",
        "estructura_a": "Bloques, Gránulos y Migajosa (BGM)",
        "horizonte_b": "Arena-limosa a 50 cm; Arena pura masiva a 90+ cm",
        "tdr_antes": 12.5,
        "tdr_despues": 14.5,
        "humedad_lab_antes": 16.04,
        "humedad_lab_despues": 16.54,
        "densidad_aparente": 1.17,
        "porosidad_pct": 44.22,
        "diagnostico": "ALERTA: Capa arable muy delgada (20 cm) y muy arenosa. Retención de agua mínima (AFD < 12 mm). Requiere pulsos de riego ultra-cortos (<2.0 mm) y adición urgente de MO."
    },
    {
        "id": 8,
        "bloque": "38",
        "condicion": "Subsolado y Sembrado",
        "cultivo": "Flor Comercial",
        "profundidad_a_cm": 30,
        "textura_a": "Limoso (L)",
        "estructura_a": "Bloques, Gránulos y Migajosa (BGM)",
        "horizonte_b": "Limo-arcilloso masivo a 90 cm; Limo-arenoso a 110+ cm",
        "tdr_antes": 8.9,
        "tdr_despues": 12.1,
        "humedad_lab_antes": 13.83,
        "humedad_lab_despues": 16.83,
        "densidad_aparente": 1.00,
        "porosidad_pct": 37.91,
        "diagnostico": "Subsolado y sembrado. Densidad aparente baja y óptima (1.00 g/mL). Buena aireación radicular."
    },
    {
        "id": 9,
        "bloque": "41H",
        "condicion": "Subsolado y Sembrado",
        "cultivo": "Flor Comercial",
        "profundidad_a_cm": 30,
        "textura_a": "Limoso (L)",
        "estructura_a": "Bloques, Gránulos y Migajosa (BGM)",
        "horizonte_b": "Limo-arcilloso masivo a 70 cm; Arcilloso a 100+ cm",
        "tdr_antes": 16.9,
        "tdr_despues": 24.7,
        "humedad_lab_antes": 21.90,
        "humedad_lab_despues": 30.76,
        "densidad_aparente": 1.49,
        "porosidad_pct": 56.36,
        "diagnostico": "Suelo subsolado con sustrato profundo arcilloso (100+ cm). Retención alta, vigilar drenaje en época húmeda."
    },
    {
        "id": 10,
        "bloque": "51C",
        "condicion": "Sin sembrar",
        "cultivo": "VACIO / TUMBA",
        "profundidad_a_cm": 30,
        "textura_a": "Limo-Arcilloso (LAr)",
        "estructura_a": "Bloques y Gránulos (BG)",
        "horizonte_b": "Limo-arenoso masivo a 70 cm; Arcillo-limoso a 100+ cm",
        "tdr_antes": 21.2,
        "tdr_despues": 22.7,
        "humedad_lab_antes": 19.31,
        "humedad_lab_despues": 25.96,
        "densidad_aparente": 1.21,
        "porosidad_pct": 45.77,
        "diagnostico": "Textura Limo-Arcillosa con mayor contenido de finos. Buena retención hídrica."
    },
    {
        "id": 11,
        "bloque": "135",
        "condicion": "Sin sembrar",
        "cultivo": "VACIO / TUMBA",
        "profundidad_a_cm": 40,
        "textura_a": "Limo-Arcilloso (LAr)",
        "estructura_a": "Bloques y Gránulos (BG)",
        "horizonte_b": "Horizonte C de arena pura suelta a 60 cm; Limoso a 100+ cm",
        "tdr_antes": 32.9,
        "tdr_despues": 30.3,
        "humedad_lab_antes": 32.86,
        "humedad_lab_despues": 31.52,
        "densidad_aparente": 1.35,
        "porosidad_pct": 51.12,
        "diagnostico": "Perfil atípico con horizonte C de arena pura entre 40 y 60 cm. Pérdida hídrica vertical acelerada a partir de los 40 cm."
    },
    {
        "id": 12,
        "bloque": "224",
        "condicion": "Sin sembrar",
        "cultivo": "VACIO / TUMBA",
        "profundidad_a_cm": 30,
        "textura_a": "Limoso (L)",
        "estructura_a": "Bloques, Gránulos y Migajosa (BGM)",
        "horizonte_b": "Limo-arcilloso masivo a 60 cm; Limo-arenoso a 90+ cm",
        "tdr_antes": 28.2,
        "tdr_despues": 29.0,
        "humedad_lab_antes": 37.19,
        "humedad_lab_despues": 32.17,
        "densidad_aparente": 1.47,
        "porosidad_pct": 55.42,
        "diagnostico": "Densidad aparente elevada (1.47 g/mL) y pie de arado en B1. Subsoleo prioritario antes de sembrar."
    },
    {
        "id": 13,
        "bloque": "217",
        "condicion": "Sin sembrar",
        "cultivo": "VACIO / TUMBA",
        "profundidad_a_cm": 30,
        "textura_a": "Limo-Arenoso (LA)",
        "estructura_a": "Bloques, Gránulos y Migajosa (BGM)",
        "horizonte_b": "Limoso masivo a 70 cm; Arena-limosa a 110+ cm",
        "tdr_antes": 14.9,
        "tdr_despues": 25.4,
        "humedad_lab_antes": 20.98,
        "humedad_lab_despues": 24.02,
        "densidad_aparente": 1.28,
        "porosidad_pct": 48.43,
        "diagnostico": "Buena respuesta al agua aplicada pero horizonte B muy compactado. Subsoleo recomendado."
    },
    {
        "id": 14,
        "bloque": "26",
        "condicion": "Sin sembrar",
        "cultivo": "VACIO / TUMBA",
        "profundidad_a_cm": 40,
        "textura_a": "Limoso (L)",
        "estructura_a": "Bloques, Gránulos y Migajosa (BGM)",
        "horizonte_b": "Limoso masivo a 80 cm; Limo-arenoso a 100+ cm",
        "tdr_antes": 26.2,
        "tdr_despues": 28.2,
        "humedad_lab_antes": 28.02,
        "humedad_lab_despues": 29.55,
        "densidad_aparente": 1.38,
        "porosidad_pct": 52.00,
        "diagnostico": "Capa superficial profunda (40 cm). Compactación incipiente a 80 cm. Ideal para cultivos de raíz profunda."
    }
]

# Mapa por bloque para búsqueda rápida
mapa_calicatas = {c['bloque'].upper(): c for c in calicatas_info}

calicatas_geojson = []
vinculados = 0

for p in data['poligonos']:
    b_nom = str(p.get('bloque_nombre', '')).strip().upper()
    es_vacio = 'VACIO' in str(p.get('cultivo', '')).upper() or 'TUMBA' in str(p.get('cultivo', '')).upper()
    
    # 1. Si es vacío / tumba, añadir recomendación agronómica de mecanización
    if es_vacio:
        p['pie_de_arado'] = {
            'estado': 'Vulnerable / Pie de arado probable',
            'accion_requerida': 'Subsoleo con cincel a 40-50 cm antes del armado de camas y siembra.',
            'justificacion': 'Suelos franco-arenosos andinos con compactación histórica por arado de disco en horizonte B.'
        }
    
    # 2. Si coincide con una calicata muestreada
    if b_nom in mapa_calicatas:
        c = dict(mapa_calicatas[b_nom])
        geo = p['geojson']
        geom = shape(geo['geometry'] if 'geometry' in geo else geo)
        centroid = geom.centroid
        c['lat'] = round(centroid.y, 6)
        c['lon'] = round(centroid.x, 6)
        p['calicata'] = c
        vinculados += 1
        
        # Evitar duplicados en calicatas_geojson si un bloque tiene más de un polígono
        if not any(cg['id'] == c['id'] for cg in calicatas_geojson):
            calicatas_geojson.append(c)

print(f"Polígonos vinculados con calicata: {vinculados}")
print(f"Calicatas únicas geo-localizadas: {len(calicatas_geojson)}")

# Guardar la lista de calicatas a nivel raíz de datos_procesados.json
data['calicatas'] = sorted(calicatas_geojson, key=lambda x: x['id'])

# Guardar metadatos del estudio de suelos
data['metadata']['estudio_suelos_2026'] = {
    "fecha": "2026-10-01",
    "consultor": "José L. Pantoja, Ph.D. (ANALYTIC S.A.S. / AGNLatam S.A.)",
    "predio": "FLORSANI - Finca Pygan (San José de Minas)",
    "textura_media": {
        "arena_pct": 62.0,
        "limo_pct": 29.0,
        "arcilla_pct": 9.0,
        "clasificacion": "Franco-arenoso a Arenoso-limoso"
    },
    "materia_organica_pct": 2.1,
    "densidad_aparente_media_g_ml": 1.22,
    "porosidad_media_pct": 47.0,
    "constantes_hidricas_horizonte_a": {
        "profundidad_media_cm": 17.0,
        "capacidad_campo_pct_grav": 16.71,
        "capacidad_campo_mm": 56.81,
        "punto_marchitez_pct_grav": 7.37,
        "punto_marchitez_mm": 25.06,
        "agua_disponible_ad_mm": 31.75,
        "agua_facilmente_disponible_afd_mm": 15.87,
        "reposicion_maxima_riego_mm": 3.18
    },
    "calibracion_tdr_150": {
        "ecuacion_logaritmica_general": "y = 15.967 * ln(x) - 22.375",
        "ecuacion_antes_riego": "y = 14.247 * ln(x) - 17.898",
        "ecuacion_despues_riego": "y = 17.759 * ln(x) - 27.399",
        "correccion_materia_organica": "+2 unidades TDR por cada 1% MO (+4.2 unidades para Finca Pygan)",
        "tdr_optimo_capacidad_campo": 25.0,
        "tdr_umbral_antes_regar": 26.0,
        "tdr_limite_tarde_peligro_gutacion": 25.0
    }
}

with open('datos_procesados.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("¡datos_procesados.json enriquecido con éxito!")
