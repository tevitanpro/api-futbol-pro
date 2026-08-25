from fastapi import FastAPI
import random

app = FastAPI(
    title="API Master Pro - JackBusca Edition",
    description="Motor de simulación matemática avanzada de 5,000 escenarios sin sesgos web",
    version="2.0.0"
)

def simular_5000_escenarios(fuerza_local: float, fuerza_empate: float, fuerza_visitante: float, promedio_tarjetas_arbitro: float = 4.5) -> dict:
    # Normalización estricta para asegurar que la suma de fuerzas sea el 100% real
    total_fuerza = fuerza_local + fuerza_empate + fuerza_visitante
    p_local = (fuerza_local / total_fuerza) * 100.0
    p_empate = (fuerza_empate / total_fuerza) * 100.0
    p_visitante = (fuerza_visitante / total_fuerza) * 100.0

    exitos_1 = 0
    exitos_x = 0
    exitos_2 = 0
    
    over_25_goles = 0
    under_25_goles = 0
    over_35_goles = 0
    under_35_goles = 0
    
    t_over_35 = 0
    t_under_35 = 0
    t_over_45 = 0
    t_under_45 = 0
    
    corners_counts = {7.5: 0, 8.5: 0, 9.5: 0, 10.5: 0}
    corners_under_counts = {7.5: 0, 8.5: 0, 9.5: 0, 10.5: 0}

    # Sin random.seed fijo para garantizar aleatoriedad real y distinta en cada consulta
    for _ in range(5000):
        ritmo = random.gauss(1.0, 0.14)
        
        # Simulación de Goles
        goles_l = max(0, int(random.gauss(1.3, 0.8) * ritmo))
        goles_v = max(0, int(random.gauss(1.1, 0.7) * ritmo))
        total_goles = goles_l + goles_v
        
        if total_goles > 2.5: over_25_goles += 1
        else: under_25_goles += 1
        
        if total_goles > 3.5: over_35_goles += 1
        else: under_35_goles += 1

        # Simulación de Tarjetas (influenciadas por el árbitro)
        t_val = random.gauss(promedio_tarjetas_arbitro, 1.2) * ritmo
        if t_val > 3.5: t_over_35 += 1
        else: t_under_35 += 1
        
        if t_val > 4.5: t_over_45 += 1
        else: t_under_45 += 1

        # Simulación de Tiros de Esquina
        c_val = random.gauss(9.5, 2.2) * ritmo
        for linea in [7.5, 8.5, 9.5, 10.5]:
            if c_val > linea:
                corners_counts[linea] += 1
            else:
                corners_under_counts[linea] += 1

        # Simulación 1X2 Equilibrada basada en porcentajes reales
        dado = random.uniform(0, 100)
        if dado < p_local:
            exitos_1 += 1
        elif dado < (p_local + p_empate):
            exitos_x += 1
        else:
            exitos_2 += 1

    n = 5000.0
    return {
        "p_1": round((exitos_1 / n) * 100.0, 1),
        "p_x": round((exitos_x / n) * 100.0, 1),
        "p_2": round((exitos_2 / n) * 100.0, 1),
        "over_25": round((over_25_goles / n) * 100.0, 1),
        "under_25": round((under_25_goles / n) * 100.0, 1),
        "over_35": round((over_35_goles / n) * 100.0, 1),
        "under_35": round((under_35_goles / n) * 100.0, 1),
        "tarjetas_mas_35": round((t_over_35 / n) * 100.0, 1),
        "tarjetas_menos_35": round((t_under_35 / n) * 100.0, 1),
        "tarjetas_mas_45": round((t_over_45 / n) * 100.0, 1),
        "tarjetas_menos_45": round((t_under_45 / n) * 100.0, 1),
        "corners_mas": {k: round((v / n) * 100.0, 1) for k, v in corners_counts.items()},
        "corners_menos": {k: round((v / n) * 100.0, 1) for k, v in corners_under_counts.items()}
    }

@app.get("/")
def home():
    return {"mensaje": "API Master Pro - Listos para operar con simulador estocástico equilibrado"}

# --- RUTA 1: NÚCLEO DEL PARTIDO (Local, Empate, Visitante y Goles) ---
@app.get("/analisis/partido")
def analizar_partido(
    equipo_local: str, 
    equipo_visitante: str, 
    fuerza_local_manual: float = 45.0,
    fuerza_empate_manual: float = 25.0,
    fuerza_visitante_manual: float = 30.0
):
    try:
        sim = simular_5000_escenarios(fuerza_local_manual, fuerza_empate_manual, fuerza_visitante_manual)
        
        candidatos_top = [
            {"prob": sim['p_1'], "texto": f"Victoria {equipo_local.title()}: {sim['p_1']}%"},
            {"prob": sim['p_x'], "texto": f"Empate Técnico: {sim['p_x']}%"},
            {"prob": sim['p_2'], "texto": f"Victoria {equipo_visitante.title()}: {sim['p_2']}%"},
            {"prob": sim['over_25'], "texto": f"Más de 2.5 Goles: {sim['over_25']}%"},
            {"prob": sim['under_25'], "texto": f"Menos de 2.5 Goles: {sim['under_25']}%"}
        ]
        candidatos_top.sort(key=lambda x: x["prob"], reverse=True)

        return {
            "aviso_legal_licencia": "NOTA: Motor de análisis matemático estocástico avanzado de 5,000 escenarios sin sesgos web.",
            "encuentro": f"{equipo_local.title()} vs {equipo_visitante.title()}",
            "origen": "Simulador Fase 1 - 1X2 y Goles Completos",
            "probabilidades_1x2_simuladas": {
                "local": f"{sim['p_1']}%",
                "empate": f"{sim['p_x']}%",
                "visitante": f"{sim['p_2']}%"
            },
            "mercados_clave_goles": {
                "mas_de_2.5_goles": f"{sim['over_25']}% (Probabilidad de superar los 2.5 goles totales)",
                "menos_de_2.5_goles": f"{sim['under_25']}% (Probabilidad de 2 goles o menos en el encuentro)",
                "mas_de_3.5_goles": f"{sim['over_35']}% (Probabilidad de superar los 3.5 goles totales)",
                "menos_de_3.5_goles": f"{sim['under_35']}% (Probabilidad de 3 goles o menos en el encuentro)"
            },
            "top_3_recomendaciones": [
                candidatos_top[0]['texto'],
                candidatos_top[1]['texto'],
                candidatos_top[2]['texto']
            ],
            "estado": "Simulación de Goles y 1X2 completada con éxito"
        }
    except Exception as e:
        return {"error": f"Error en el servidor: {str(e)}"}


# --- RUTA 2: JACKBUSCA / PROFUNDIDAD (Tarjetas y Tiros de Esquina) ---
@app.get("/jackbusca/partido")
def jackbusca_partido(
    equipo_local: str, 
    equipo_visitante: str, 
    competencia: str = "Liga Local / Torneo Nacional",
    ultimos_5_local_resumen: str = "Ej: 3 Ganados, 1 Empate, 1 Perdido (Buen Local)",
    ultimos_5_visitante_resumen: str = "Ej: 1 Ganado, 1 Empate, 3 Perdidos (Mal Visitante)",
    arbitro_asignado: str = "Por definir",
    promedio_tarjetas_arbitro: float = 4.5,
    fuerza_local_manual: float = 45.0,
    fuerza_empate_manual: float = 25.0,
    fuerza_visitante_manual: float = 30.0
):
    try:
        sim = simular_5000_escenarios(fuerza_local_manual, fuerza_empate_manual, fuerza_visitante_manual, promedio_tarjetas_arbitro)
        
        return {
            "origen": "JackBusca Simulador Especializado - Tarjetas y Córners",
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
            "mercados_tarjetas_explicados": {
                "mas_de_3.5_tarjetas": f"{sim['tarjetas_mas_35']}%",
                "menos_de_3.5_tarjetas": f"{sim['tarjetas_menos_35']}%",
                "mas_de_4.5_tarjetas": f"{sim['tarjetas_mas_45']}%",
                "menos_de_4.5_tarjetas": f"{sim['tarjetas_menos_45']}%"
            },
            "mercados_tiros_de_esquina": {
                "mas_de": {
                    "7.5": f"{sim['corners_mas'][7.5]}%",
                    "8.5": f"{sim['corners_mas'][8.5]}%",
                    "9.5": f"{sim['corners_mas'][9.5]}%",
                    "10.5": f"{sim['corners_mas'][10.5]}%"
                },
                "menos_de": {
                    "7.5": f"{sim['corners_menos'][7.5]}%",
                    "8.5": f"{sim['corners_menos'][8.5]}%",
                    "9.5": f"{sim['corners_menos'][9.5]}%",
                    "10.5": f"{sim['corners_menos'][10.5]}%"
                }
            },
            "estado": "JackBusca procesó los mercados secundarios con éxito"
        }
    except Exception as e:
        return {"error": f"Error en el servidor: {str(e)}"}
