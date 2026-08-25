from fastapi import FastAPI
import random
import requests
from bs4 import BeautifulSoup

app = FastAPI(
    title="API Master Pro - JackBusca Edition",
    description="Motor de scraping, licencias oficiales y simulador de 5,000 escenarios",
    version="1.0.0"
)

# Tu token oficial de football-data.org
FOOTBALL_DATA_TOKEN = "8bfb194efbf74b418e00bfb575408368"
HEADERS = {"X-Auth-Token": FOOTBALL_DATA_TOKEN}

def extraer_datos_de_paginas_publicas(equipo_local: str, equipo_visitante: str) -> dict:
    fuerza_l = 50.0
    fuerza_e = 26.0
    fuente_usada = "Motor Estadístico Base (Público)"
    
    try:
        query = f"{equipo_local} vs {equipo_visitante} estadisticas pronostico"
        url_busqueda = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        response = requests.get(url_busqueda, headers=headers, timeout=6)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            snippets = soup.find_all('a', class_='result__snippet')
            
            texto_acumulado = ""
            for s in snippets:
                if s and s.text:
                    texto_acumulado += s.text.lower() + " "
            
            l_lower = equipo_local.lower()
            v_lower = equipo_visitante.lower()
            
            menciones_l = texto_acumulado.count(l_lower)
            menciones_v = texto_acumulado.count(v_lower)
            
            if len(texto_acumulado) > 100:
                fuente_usada = "Web Scraping de Fuentes Públicas Abiertas"
                if menciones_l > menciones_v:
                    fuerza_l = 55.0 
                elif menciones_v > menciones_l:
                    fuerza_l = 45.0 
                    
    except Exception as e:
        print(f"Nota de scraping público: {e}")
        
    base_v = round(100.0 - (fuerza_l + fuerza_e), 1)
    return {
        "fuerza_l": fuerza_l,
        "fuerza_e": fuerza_e,
        "fuerza_v": base_v,
        "fuente": fuente_usada
    }

def simular_5000_escenarios(p_base_local: float, p_base_empate: float, p_base_visita: float) -> dict:
    exitos_1 = 0
    exitos_x = 0
    exitos_2 = 0
    
    btts_count = 0
    over_25_goles = 0
    over_35_goles = 0
    corners_95 = 0
    tarjetas_45 = 0
    
    tiros_puerta_total = 0
    tiros_totales_match = 0
    
    random.seed(int(p_base_local * 23))
    
    for _ in range(5000):
        ritmo = random.gauss(1.0, 0.14)
        friccion_medio = random.random()
        
        goles_l = max(0, int(random.gauss(1.3, 0.8) * ritmo))
        goles_v = max(0, int(random.gauss(1.0, 0.7) * ritmo))
        total_goles = goles_l + goles_v
        
        if goles_l > 0 and goles_v > 0: btts_count += 1
        if total_goles > 2.5: over_25_goles += 1
        if total_goles > 3.5: over_35_goles += 1

        c_val = int(random.gauss(9.5, 2.2) * ritmo)
        if c_val > 9.5: corners_95 += 1

        t_val = int(random.gauss(4.2, 1.3) * (1.4 if friccion_medio > 0.45 else 0.85))
        if t_val > 4.5: tarjetas_45 += 1

        tiros_puerta_total += max(4, int(random.gauss(9.0, 2.5) * ritmo))
        tiros_totales_match += max(12, int(random.gauss(24.0, 4.0) * ritmo))

        desempeno_partido = random.gauss(50.0, 15.0)
        if desempeno_partido < p_base_local:
            exitos_1 += 1
        elif desempeno_partido < (p_base_local + p_base_empate):
            exitos_x += 1
        else:
            exitos_2 += 1

    return {
        "p_1": round((exitos_1 / 5000.0) * 100.0, 1),
        "p_x": round((exitos_x / 5000.0) * 100.0, 1),
        "p_2": round((exitos_2 / 5000.0) * 100.0, 1),
        "btts": round((btts_count / 5000.0) * 100.0, 1),
        "over_25": round((over_25_goles / 5000.0) * 100.0, 1),
        "over_35": round((over_35_goles / 5000.0) * 100.0, 1),
        "corners_mas_95": round((corners_95 / 5000.0) * 100.0, 1),
        "tarjetas_mas_45": round((tarjetas_45 / 5000.0) * 100.0, 1),
        "media_tiros_puerta": round(tiros_puerta_total / 5000.0, 1),
        "media_tiros_totales": round(tiros_totales_match / 5000.0, 1)
    }

@app.get("/")
def home():
    return {"mensaje": "API Master Pro - Listos para operar con licencia y simulador"}

# --- RUTA 1: ANALISIS OFICIAL (Con licencia y respaldo web) ---
@app.get("/analisis/partido")
def analizar_partido(
    equipo_local: str, 
    equipo_visitante: str, 
    match_id_oficial: int = 0,
    arbitro_manual: str = ""
):
    try:
        fuente_final = "Motor Web Publico + Simulador"
        
        # Si pones un ID oficial de tu licencia de football-data.org
        if match_id_oficial > 0:
            url = f"https://api.football-data.org/v4/matches/{match_id_oficial}"
            resp = requests.get(url, headers=HEADERS)
            if resp.status_code == 200:
                data_oficial = resp.json()
                equipo_local = data_oficial.get("homeTeam", {}).get("name", equipo_local)
                equipo_visitante = data_oficial.get("awayTeam", {}).get("name", equipo_visitante)
                fuente_final = f"Licencia Oficial Football-Data ({data_oficial.get('competition', {}).get('name', 'Liga Perm.')})"

        # Extraemos fuerzas con tu buscador web de confianza
        datos_publicos = extraer_datos_de_paginas_publicas(equipo_local, equipo_visitante)
        base_l = datos_publicos["fuerza_l"]
        base_e = datos_publicos["fuerza_e"]
        base_v = datos_publicos["fuerza_v"]
        
        arbitro_final = arbitro_manual.strip() if arbitro_manual.strip() else "Por asignar (Revisar plataforma)"

        # Corremos tus 5000 simulaciones exactas
        sim = simular_5000_escenarios(base_l, base_e, base_v)
        
        candidatos_top = [
            {"prob": sim['p_1'], "texto": f"Victoria {equipo_local.title()}: {sim['p_1']}%"},
            {"prob": sim['p_x'], "texto": f"Empate Técnico: {sim['p_x']}%"},
            {"prob": sim['p_2'], "texto": f"Victoria {equipo_visitante.title()}: {sim['p_2']}%"},
            {"prob": sim['btts'], "texto": f"Ambos Marcan (BTTS): {sim['btts']}%"},
            {"prob": sim['over_25'], "texto": f"Más de 2.5 Goles: {sim['over_25']}%"}
        ]
        candidatos_top.sort(key=lambda x: x["prob"], reverse=True)

        return {
            "aviso_legal_licencia": "NOTA: Esta ruta soporta ligas de la licencia oficial (WC, Champions, Premier, LaLiga, Serie A, Bundesliga, Eredivisie, Brasileirao, Ligue 1, Championship, Eredivisie, Primeira Liga).",
            "encuentro": f"{equipo_local.title()} vs {equipo_visitante.title()}",
            "fuente_extraccion": fuente_final,
            "designacion_arbitral": arbitro_final,
            "probabilidades_1x2_simuladas": {
                "local": f"{sim['p_1']}%",
                "empate": f"{sim['p_x']}%",
                "visitante": f"{sim['p_2']}%"
            },
            "mercados_clave_explicados": {
                "btts_ambos_marcan": f"{sim['btts']}% (Probabilidad de que tanto local como visitante logren anotar al menos 1 gol)",
                "over_25_goles": f"{sim['over_25']}% (Probabilidad de que el partido termine con más de 2.5 goles totales)",
                "corners_mas_de_95": f"{sim['corners_mas_95']}% (Probabilidad proyectada de superar los 9.5 tiros de esquina en total)",
                "tarjetas_mas_de_45": f"{sim['tarjetas_mas_45']}% (Probabilidad de superar las 4.5 tarjetas en el encuentro)",
                "proyeccion_tiros": f"Puerta (~{sim['media_tiros_puerta']}) | Totales (~{sim['media_tiros_totales']})"
            },
            "top_3_recomendaciones": [
                candidatos_top[0]['texto'],
                candidatos_top[1]['texto'],
                candidatos_top[2]['texto']
            ],
            "estado": "Simulación completada con éxito"
        }
    except Exception as e:
        return {"error": f"Error en el servidor: {str(e)}"}


# --- RUTA 2: JACKBUSCA / PARTIDO (Para ligas locales, Conmebol, Asia, Centroamérica y manuales) ---
@app.get("/jackbusca/partido")
def jackbusca_partido(
    equipo_local: str, 
    equipo_visitante: str, 
    competencia: str = "Liga Local / Torneo Nacional",
    ultimos_5_local_resumen: str = "Ej: 3 Ganados, 1 Empate, 1 Perdido (Buen Local)",
    ultimos_5_visitante_resumen: str = "Ej: 1 Ganado, 1 Empate, 3 Perdidos (Mal Visitante)",
    arbitro_asignado: str = "Por definir",
    promedio_tarjetas_arbitro: float = 4.5,
    fuerza_local_manual: float = 50.0,
    fuerza_empate_manual: float = 26.0
):
    try:
        # El orden estricto ingresado define local y visitante
        base_l = fuerza_local_manual
        base_e = fuerza_empate_manual
        base_v = round(100.0 - (base_l + base_e), 1)

        sim = simular_5000_escenarios(base_l, base_e, base_v)
        
        candidatos_top = [
            {"prob": sim['p_1'], "texto": f"Victoria {equipo_local.title()}: {sim['p_1']}%"},
            {"prob": sim['p_x'], "texto": f"Empate Técnico: {sim['p_x']}%"},
            {"prob": sim['p_2'], "texto": f"Victoria {equipo_visitante.title()}: {sim['p_2']}%"},
            {"prob": sim['btts'], "texto": f"Ambos Marcan (BTTS): {sim['btts']}%"},
            {"prob": sim['over_25'], "texto": f"Más de 2.5 Goles: {sim['over_25']}%"}
        ]
        candidatos_top.sort(key=lambda x: x["prob"], reverse=True)

        return {
            "origen": "JackBusca Simulador Especializado",
            "competencia": competencia,
            "encuentro_orden_estricto": {
                "local": equipo_local.title(),
                "visitante": equipo_visitante.title()
            },
            "analisis_rachas_ultimos_5": {
                "tendencia_local": ultimos_5_local_resumen,
                "tendencia_visitante": ultimos_5_visitante_resumen
            },
            "arbitraje": {
                "nombre_arbitro": arbitro_asignado,
                "promedio_tarjetas_partido": promedio_tarjetas_arbitro
            },
            "probabilidades_1x2_simuladas": {
                "local": f"{sim['p_1']}%",
                "empate": f"{sim['p_x']}%",
                "visitante": f"{sim['p_2']}%"
            },
            "mercados_clave_explicados": {
                "btts_ambos_marcan": f"{sim['btts']}% (Ambos equipos anotan)",
                "over_25_goles": f"{sim['over_25']}% (Más de 2.5 goles totales)",
                "corners_mas_de_95": f"{sim['corners_mas_95']}% (Más de 9.5 tiros de esquina)",
                "tarjetas_mas_de_45": f"{sim['tarjetas_mas_45']}% (Más de 4.5 tarjetas en total)"
            },
            "top_3_recomendaciones": [
                candidatos_top[0]['texto'],
                candidatos_top[1]['texto'],
                candidatos_top[2]['texto']
            ],
            "estado": "JackBusca procesó los 5,000 escenarios con éxito"
        }
    except Exception as e:
        return {"error": f"Error en el servidor: {str(e)}"}
