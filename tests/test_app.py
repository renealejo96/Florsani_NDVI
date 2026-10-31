#!/usr/bin/env python3
"""
Test unitario de la aplicación Flask PyGan AgroSat (incluye Radar de Nubes).
"""
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from app import app

def main():
    client = app.test_client()

    print("=" * 60)
    print("🧪 VERIFICACIÓN DE ENDPOINTS FLASK + RADAR DE NUBES")
    print("=" * 60)

    # 1. Probar ruta raíz /
    res_index = client.get("/")
    assert res_index.status_code == 200, f"Error en /: {res_index.status_code}"
    print(f"[+] Ruta [GET /] -> Status {res_index.status_code} OK")

    # 2. Probar ruta /api/datos
    res_api = client.get("/api/datos")
    assert res_api.status_code == 200, f"Error en /api/datos: {res_api.status_code}"
    print(f"[+] Ruta [GET /api/datos] -> Status {res_api.status_code} OK")

    # 3. Probar ruta del radar satelital en vivo
    print("[*] Consultando /api/satelite/pasadas-recientes en catálogo STAC...")
    res_radar = client.get("/api/satelite/pasadas-recientes")
    assert res_radar.status_code == 200, f"Error en radar: {res_radar.status_code}"
    radar_data = res_radar.get_json()
    assert radar_data["status"] == "success", "Fallo en el servicio del radar"
    print(f"[+] Ruta [GET /api/satelite/pasadas-recientes] -> Status 200 OK")
    print(f"    - Pasadas satelitales devueltas: {radar_data['total_pasadas']}")
    if radar_data["total_pasadas"] > 0:
        ult = radar_data["pasadas"][0]
        print(f"    - Pasada más reciente: {ult['fecha']} | Nubes: {ult['nubes_pct']}% ({ult['estado_calidad']}) | Sat: {ult['satelite']}")

    print("=" * 60)
    print("✅ TODAS LAS PRUEBAS UNITARIAS PASARON EXITOSAMENTE")
    print("=" * 60)

if __name__ == "__main__":
    main()
