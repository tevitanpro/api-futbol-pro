from fastapi import FastAPI
import random

app = FastAPI(
    title="API Master Pro - Pinnacle Manual Edition",
    description="Motor de simulación matemática avanzada de 5,000 escenarios basado 100% en cuotas manuales de Pinnacle",
    version="4.5.0"
)

def simular_escenarios_con_pinnacle(
    cuota_local: float, cuota_empate: float, cuota_visitante: float,
    cuota_mas_25: float, cuota_menos_25: float,
    cuota_mas_35: float, cuota_menos_35: float,
    promedio_tarjetas_arbitro: float = 4.5,
    c_t_mas_35: float = 1.80, c_t_menos_35: float = 2.00,
    c_t_mas_45: float = 2.50, c_t_menos_45: float = 1.50,
    c_c_mas_75: float = 1.20, c_c_menos_75: float = 4.00,
    c_c_mas_85: float = 1.45, c_c_menos_85: float = 2.60,
    c_c_mas_95: float = 1.85, c_c_menos_95: float = 1.90,
    c_c_mas_105: float = 2.40, c_c_menos_105: float = 1.55
) -> dict:
    
    # 1. Normalización de probabilidades implícitas puras de 1X2 (quitando el vig de Pinnacle)
    p_l_bruta = 1.0 / cuota_local
    p_e_bruta = 1.0 / cuota_empate
    p_v_bruta = 1.0 / cuota_visitante
    suma_1x2 = p_l_bruta + p_e_bruta + p_v_bruta
    
    p_local_real = (p_l_bruta / suma_1x2) * 100.0
    p_empate_real = (p_e_bruta / suma_1x2) * 100.0
    p_visitante_real = (p_v_bruta / suma_1x2) * 100.0

    # Probabilidades puras para Goles
    p_o25_bruta = 1.0 / cuota_mas_25
    p_u25_bruta = 1.0 / cuota_menos_25
    suma_g25 = p_o25_bruta + p_u25_bruta
    prob_over_25_base = (p_o25_bruta / suma_g25) * 100.0

    p_o35_bruta = 1.0 / cuota_mas_35
    p_u35_bruta = 1.0 / cuota_menos_35
    suma_g35 = p_o35_bruta + p_u35_bruta
    prob_over_35_base = (p_o35_bruta / suma_g35) * 100.0

    # Probabilidades puras para Tarjetas y Córners
    def get_prob_over(c_o, c_u):
        po = 1.0 / c_o
        pu = 1.0 / c_u
        return (po / (po + pu)) * 100.0

    p_t35_base = get_prob_over(c_t_mas_35, c_t_menos_35)
    p_t45_base = get_prob_over(c_t_mas_45, c_t_menos_45)

    corners_bases = {
        7.5: get_prob_over(c_c_mas_75, c_c_menos_75),
        8.5: get_prob_over(c_c_mas_85, c_c_menos_85),
        9.5: get_prob_over(c_c_mas_95, c_c_menos_95),
        10.5: get_prob_over(c_c_mas_105, c_c_menos_105)
    }

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

    # 2. Simulación estocástica de los 5,000 escenarios calibrada con Pinnacle
    for _ in range(5000):
        ritmo = random.gauss(1.0, 0.14)
        
        # Simulación 1X2
        dado_1x2 = random.uniform(0, 100)
        if dado_1x2 < p_local_real:
            exitos_1 += 1
        elif dado_1x2 < (p_local_real + p_empate_real):
            exitos_x += 1
        else:
            exitos_2 += 1

        # Simulación Goles basada en la tendencia de sus cuotas
        dado_g25 = random.uniform(0, 100)
        if dado_g25 < prob_over_25_base * ritmo:
            over_25_goles += 1
        else:
            under_25_goles += 1

        dado_g35 = random.uniform(0, 100)
        if dado_g35 < prob_over_35_base * ritmo:
            over_35_goles += 1
        else:
            under_35_goles += 1

        # Simulación Tarjetas influenciada por el árbitro y cuotas
        t_val = random.gauss(promedio_tarjetas_arbitro, 1.2) * ritmo
        dado_t35 = random.uniform(0, 100)
        if dado_t35 < p_t35_base * (t_val / promedio_tarjetas_arbitro):
            t_over_35 += 1
        else:
            t_under_35 += 1

        dado_t45 = random.uniform(0, 100)
        if dado_t45 < p_t45_base * (t_val / promedio_tarjetas_arbitro):
            t_over_45 += 1
        else:
            t_under_45 += 1

        # Simulación Tiros de Esquina
        c_val = random.gauss(9.5, 2.2) * ritmo
        for linea in [7.5, 8.5, 9.5, 10.5]:
            dado_c = random.uniform(0, 100)
            if dado_c < corners_bases[linea] * (c_val / 9.5):
                corners_counts[linea] += 1
            else:
                corners_under_counts[linea] += 1

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
    return {"mensaje": "API Master Pro - Motor Estocástico con Cuotas Manuales de Pinnacle"}

# --- RUTA 1: FASE SUPERIOR (Local, Empate, Visitante y Goles con cuotas Pinnacle) ---
@app.get("/analisis/partido")
def analizar_partido(
    cuota_local: float = 3.03,
    cuota_empate: float = 3.26,
    cuota_visitante: float = 2.56,
    cuota_mas_25_goles: float = 1.95,
    cuota_menos_25_goles: float = 1.85,
    cuota_mas_35_goles: float = 3.40,
    cuota_menos_35_goles: float = 1.32
):
    try:
        sim = simular_escenarios_con_pinnacle(
            cuota_local, cuota_empate, cuota_visitante,
            cuota_mas_25_goles, cuota_menos_25_goles,
            cuota_mas_35_goles, cuota_menos_35_goles
        )
        
        candidatos_top = [
            {"prob": sim['p_1'], "texto": f"Victoria Local (1): {sim['p_1']}%"},
            {"prob": sim['p_x'], "texto": f"Empate Técnico (X): {sim['p_x']}%"},
            {"prob": sim['p_2'], "texto": f"Victoria Visitante (2): {sim['p_2']}%"},
            {"prob": sim['over_25'], "texto": f"Más de 2.5 Goles: {sim['over_25']}%"},
            {"prob": sim['under_25'], "texto": f"Menos de 2.5 Goles: {sim['under_25']}%"}
        ]
        candidatos_top.sort(key=lambda x: x["prob"], reverse=True)

        return {
            "aviso_legal_licencia": "NOTA: Análisis matemático estocástico avanzado basado en cuotas madre de Pinnacle.",
            "origen": "Fase 1 - 1X2 y Goles (Cuotas Manuales Pinnacle)",
            "probabilidades_1x2_simuladas": {
                "local": f"{sim['p_1']}%",
                "empate": f"{sim['p_x']}%",
                "visitante": f"{sim['p_2']}%"
            },
            "mercados_clave_goles": {
                "mas_de_2.5_goles": f"{sim['over_25']}%",
                "menos_de_2.5_goles": f"{sim['under_25']}%",
                "mas_de_3.5_goles": f"{sim['over_35']}%",
                "menos_de_3.5_goles": f"{sim['under_35']}%"
            },
            "top_3_recomendaciones": [
                candidatos_top[0]['texto'],
                candidatos_top[1]['texto'],
                candidatos_top[2]['texto']
            ],
            "estado": "Simulación de Fase 1 completada con éxito"
        }
    except Exception as e:
        return {"error": f"Error en el servidor: {str(e)}"}


# --- RUTA 2: JACKBUSCA (Tarjetas, Promedio Árbitro y Tiros de Esquina con cuotas Pinnacle) ---
@app.get("/jackbusca/partido")
def jackbusca_partido(
    cuota_local: float = 3.03,
    cuota_empate: float = 3.26,
    cuota_visitante: float = 2.56,
    cuota_mas_25_goles: float = 1.95,
    cuota_menos_25_goles: float = 1.85,
    cuota_mas_35_goles: float = 3.40,
    cuota_menos_35_goles: float = 1.32,
    promedio_tarjetas_arbitro: float = 4.5,
    cuota_tarjetas_mas_35: float = 1.80,
    cuota_tarjetas_menos_35: float = 2.00,
    cuota_tarjetas_mas_45: float = 2.50,
    cuota_tarjetas_menos_45: float = 1.50,
    cuota_corners_mas_75: float = 1.20,
    cuota_corners_mas_85: float = 1.45,
    cuota_corners_mas_95: float = 1.85,
    cuota_corners_mas_105: float = 2.40,
    cuota_corners_menos_75: float = 4.00,
    cuota_corners_menos_85: float = 2.60,
    cuota_corners_menos_95: float = 1.90,
    cuota_corners_menos_105: float = 1.55
):
    try:
        sim = simular_escenarios_con_pinnacle(
            cuota_local, cuota_empate, cuota_visitante,
            cuota_mas_25_goles, cuota_menos_25_goles,
            cuota_mas_35_goles, cuota_menos_35_goles,
            promedio_tarjetas_arbitro,
            cuota_tarjetas_mas_35, cuota_tarjetas_menos_35,
            cuota_tarjetas_mas_45, cuota_tarjetas_menos_45,
            cuota_corners_mas_75, cuota_corners_menos_75,
            cuota_corners_mas_85, cuota_corners_menos_85,
            cuota_corners_mas_95, cuota_corners_menos_95,
            cuota_corners_mas_105, cuota_corners_menos_105
        )
        
        return {
            "origen": "JackBusca Fase 2 - Tarjetas y Córners (Motor Estocástico Pinnacle)",
            "arbitraje": {
                "promedio_tarjetas_referencia": promedio_tarjetas_arbitro
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
