from fastapi import FastAPI
import random
from concurrent.futures import ThreadPoolExecutor

app = FastAPI(
    title="API Master Pro - Pinnacle Optimized Edition",
    description="Motor de simulación matemática avanzada de 50,000 escenarios con procesamiento paralelo",
    version="5.1.0"
)

# Función auxiliar que corre un bloque de simulaciones en paralelo
def _bloque_simulacion(iteraciones, prob_1x2, prob_over_25, prob_over_35, promedio_tarjetas_arbitro, p_t35_base, p_t45_base, corners_bases):
    p_l, p_e, p_v = prob_1x2
    exitos_1 = exitos_x = exitos_2 = 0
    over_25 = under_25 = over_35 = under_35 = 0
    t_over_35 = t_under_35 = t_over_45 = t_under_45 = 0
    corners_counts = {7.5: 0, 8.5: 0, 9.5: 0, 10.5: 0}
    corners_under_counts = {7.5: 0, 8.5: 0, 9.5: 0, 10.5: 0}

    for _ in range(iteraciones):
        ritmo = random.gauss(1.0, 0.14)
        
        # 1X2
        dado_1x2 = random.uniform(0, 100)
        if dado_1x2 < p_l:
            exitos_1 += 1
        elif dado_1x2 < (p_l + p_e):
            exitos_x += 1
        else:
            exitos_2 += 1

        # Goles
        if random.uniform(0, 100) < prob_over_25 * ritmo:
            over_25 += 1
        else:
            under_25 += 1

        if random.uniform(0, 100) < prob_over_35 * ritmo:
            over_35 += 1
        else:
            under_35 += 1

        # Tarjetas
        t_val = random.gauss(promedio_tarjetas_arbitro, 1.2) * ritmo
        if random.uniform(0, 100) < p_t35_base * (t_val / promedio_tarjetas_arbitro):
            t_over_35 += 1
        else:
            t_under_35 += 1

        if random.uniform(0, 100) < p_t45_base * (t_val / promedio_tarjetas_arbitro):
            t_over_45 += 1
        else:
            t_under_45 += 1

        # Córners
        c_val = random.gauss(9.5, 2.2) * ritmo
        for linea in [7.5, 8.5, 9.5, 10.5]:
            if random.uniform(0, 100) < corners_bases[linea] * (c_val / 9.5):
                corners_counts[linea] += 1
            else:
                corners_under_counts[linea] += 1

    return (exitos_1, exitos_x, exitos_2, over_25, under_25, over_35, under_35, 
            t_over_35, t_under_35, t_over_45, t_under_45, corners_counts, corners_under_counts)

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

    # 2. Simulación estocástica paralela de 50,000 escenarios dividida en 4 hilos (aprovechando el i7)
    total_escenarios = 50000
    hilos = 4
    bloque = total_escenarios // hilos

    prob_1x2 = (p_local_real, p_empate_real, p_visitante_real)
    resultados_hilos = []

    with ThreadPoolExecutor(max_workers=hilos) as executor:
        futures = [
            executor.submit(_bloque_simulacion, bloque, prob_1x2, prob_over_25_base, prob_over_35_base, promedio_tarjetas_arbitro, p_t35_base, p_t45_base, corners_bases)
            for _ in range(hilos)
        ]
        for f in futures:
            resultados_hilos.append(f.result())

    # Consolidar resultados
    exitos_1 = sum(r[0] for r in resultados_hilos)
    exitos_x = sum(r[1] for r in resultados_hilos)
    exitos_2 = sum(r[2] for r in resultados_hilos)
    over_25_goles = sum(r[3] for r in resultados_hilos)
    under_25_goles = sum(r[4] for r in resultados_hilos)
    over_35_goles = sum(r[5] for r in resultados_hilos)
    under_35_goles = sum(r[6] for r in resultados_hilos)
    t_over_35 = sum(r[7] for r in resultados_hilos)
    t_under_35 = sum(r[8] for r in resultados_hilos)
    t_over_45 = sum(r[9] for r in resultados_hilos)
    t_under_45 = sum(r[10] for r in resultados_hilos)
    
    corners_counts = {k: sum(r[11][k] for r in resultados_hilos) for k in [7.5, 8.5, 9.5, 10.5]}
    corners_under_counts = {k: sum(r[12][k] for r in resultados_hilos) for k in [7.5, 8.5, 9.5, 10.5]}

    n = float(total_escenarios)
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
    return {"mensaje": "API Master Pro - Motor Estocástico de 50,000 Escenarios con Cuotas Manuales de Pinnacle"}

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
            "aviso_legal_licencia": "NOTA: Análisis matemático estocástico avanzado de 50,000 iteraciones basado en cuotas madre de Pinnacle.",
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
            "estado": "Simulación de Fase 1 completada con éxito (50k escenarios)"
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
            "origen": "JackBusca Fase 2 - Tarjetas y Córners (Motor Estocástico Pinnacle 50k)",
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
            "estado": "JackBusca procesó los mercados secundarios con éxito (50k escenarios)"
        }
    except Exception as e:
        return {"error": f"Error en el servidor: {str(e)}"}
