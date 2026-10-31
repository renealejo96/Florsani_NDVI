#!/usr/bin/env python3
"""
PyGan AgroSat - Servidor Web Flask para Monitoreo Satelital de Precisión.
Fase 3: Servicio de Dashboard interactivo, API de datos y Radar de Pasadas Satelitales.
Incluye políticas anti-caché y recarga automática de plantillas.
"""

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from flask import Flask, jsonify, render_template, abort, make_response
import pystac_client
import planetary_computer

app = Flask(__name__)

# Configuración estricta anti-caché y auto-recarga
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

DATA_FILE = Path(__file__).resolve().parent / "datos_procesados.json"

@app.after_request
def add_no_cache_headers(response):
    """Evita que el navegador web guarde copias viejas en caché."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route("/")
def index():
    """Ruta principal: Renderiza el Dashboard web interactivo."""
    return render_template("index.html")

@app.route("/api/datos")
def api_datos():
    """
    Endpoint REST: Retorna el dataset procesado de polígonos,
    geometrías GeoJSON, metadatos, nubes y series temporales.
    """
    if not DATA_FILE.exists():
        abort(404, description="No se encontró datos_procesados.json. Ejecute etl_sentinel.py primero.")
    
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return jsonify(data)

@app.route("/api/satelite/pasadas-recientes")
def pasadas_recientes():
    """
    Endpoint en vivo: Consulta el catálogo STAC de Sentinel-2 para el BBOX de la finca
    y devuelve las pasadas de los últimos 60 días con su porcentaje exacto de nubes.
    """
    try:
        bbox = [-78.405976, 0.139019, -78.385796, 0.146912]
        stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
        
        catalog = pystac_client.Client.open(stac_url, modifier=planetary_computer.sign_inplace)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=60)
        date_range = f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
        
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            datetime=date_range,
            sortby=[{"field": "datetime", "direction": "desc"}],
            max_items=20
        )
        
        items = list(search.items())
        pasadas = []
        for it in items:
            clouds = round(float(it.properties.get("eo:cloud_cover", 0.0)), 1)
            pasadas.append({
                "fecha": it.datetime.strftime("%Y-%m-%d"),
                "hora": it.datetime.strftime("%H:%M UTC"),
                "satelite": it.properties.get("platform", "Sentinel-2"),
                "nubes_pct": clouds,
                "estado_calidad": "Despejado (<30%)" if clouds < 30 else ("Parcial (30-60%)" if clouds <= 60 else "Muy Cubierto (>60%)"),
                "color_alerta": "success" if clouds < 30 else ("warning" if clouds <= 60 else "danger"),
                "scene_id": it.id
            })
        
        return jsonify({
            "status": "success",
            "total_pasadas": len(pasadas),
            "rango_fechas": date_range,
            "pasadas": pasadas
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/health")
def health():
    """Endpoint de comprobación de salud para despliegue en VPS / Kubernetes / Docker."""
    return jsonify({
        "status": "healthy",
        "data_ready": DATA_FILE.exists(),
        "service": "PyGan AgroSat Flask Engine"
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5055))
    print("=" * 65)
    print("🚀 INICIANDO SERVIDOR FLASK - PYGAN AGROSAT (PRODUCCIÓN / DEV)")
    print(f"   -> Puerto Configurado: {port}")
    print(f"   -> Acceso Local: http://127.0.0.1:{port}")
    print(f"   -> Acceso en Red / VPS: http://0.0.0.0:{port}")
    print("=" * 65)
    app.run(host="0.0.0.0", port=port, debug=False)
