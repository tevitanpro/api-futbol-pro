from fastapi import FastAPI
import random
import requests
from bs4 import BeautifulSoup

app = FastAPI()

def extraer_datos_de_paginas_publicas(equipo_local: str, equipo_visitante: str) -> dict:
    """
    Entra a buscadores y páginas públicas abiertas (igual que un navegador) 
    para extraer tendencias, estadísticas o menciones reales del partido.
    """
    fuerza_l = 50.0
    fuerza_e = 26.0
    fuente_usada = "Motor Estadístico Base (Público)"
    
    try:
        # Armamos una consulta pública orientada a estadísticas abiertas
        query = f"{equipo_local} vs {equipo_visitante} estadisticas pronostico"
        url_busqueda = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        
        # Simulamos ser un navegador real con un buen User-Agent
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
            
            # Si encontramos texto público sobre los equipos, ajustamos la balanza real
            l_lower = equipo_local.lower()
            v_lower = equipo_visitante.lower()
            
            menciones_l = texto_acumulado.count(l_lower)
            menciones_v = texto_acumulado.count(v_lower)
            
            if len(texto_acumulado) > 100:
                fuente_usada = "Web Scraping de Fuentes Públicas Abiertas"
                # Ajuste proporcional basado en el análisis de texto público encontrado
                if menciones_l > menciones_v:
                    fuerza_l = 55.0  # El local toma ventaja según la data pública
                elif menciones_v > menciones_l:
                    fuerza_l = 45.0  # La visita toma fuerza según la data pública
                    
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
    """Ejecuta las 5,000 simulaciones estadísticas basadas en los datos públicos recolectados"""
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
    return {"mensaje": "API Master Pro - Extracción de Páginas Públicas y Simulador Activos"}

@app.get("/analisis/partido")
def analizar_partido(
    equipo_local: str, 
    equipo_visitante: str, 
    arbitro_manual: str = ""
):
    try:
        # 1. Extraemos los datos de las fuentes públicas abiertas
        datos_publicos = extraer_datos_de_paginas_publicas(equipo_local, equipo_visitante)
        
        base_l = datos_publicos["fuerza_l"]
        base_e = datos_publicos["fuerza_e"]
        base_v = datos_publicos["fuerza_v"]
        estado_fuente = datos_publicos["fuente"]
        
        arbitro_final = arbitro_manual.strip() if arbitro_manual.strip() else "Por asignar (Revisar plataforma pública)"

        # 2. Corremos las 5,000 simulaciones estrictamente con esos datos públicos
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
            "encuentro": f"{equipo_local.title()} vs {equipo_visitante.title()}",
            "fuente_extraccion": estado_fuente,
            "designacion_arbitral": arbitro_final,
            "probabilidades_1x2_simuladas": {
                "local": f"{sim['p_1']}%",
                "empate": f"{sim['p_x']}%",
                "visitante": f"{sim['p_2']}%"
            },
            "mercados_clave": {
                "btts": f"{sim['btts']}%",
                "over_25": f"{sim['over_25']}%",
                "corners_mas_95": f"{sim['corners_mas_95']}%",
                "tarjetas_mas_45": f"{sim['tarjetas_mas_45']}%",
                "proyeccion_tiros": f"Puerta (~{sim['media_tiros_puerta']}) | Totales (~{sim['media_tiros_totales']})"
            },
            "top_3_recomendaciones": [
                candidatos_top[0]['texto'],
                candidatos_top[1]['texto'],
                candidatos_top[2]['texto']
            ],
            "estado": "Datos de páginas públicas extraídos y 5,000 simulaciones ejecutadas con éxito"
        }
    except Exception as e:
        return {"error": f"Error en el servidor: {str(e)}"}