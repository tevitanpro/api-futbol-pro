from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import random
from concurrent.futures import ThreadPoolExecutor

app = FastAPI(
    title="API Master Pro - Pinnacle Optimized Edition",
    description="Motor de simulación matemática avanzada de 50,000 escenarios con procesamiento paralelo",
    version="5.3.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _bloque_simulacion(iteraciones, prob_1x2, prob_over_25, prob_over_35, promedio_tarjetas_arbitro, p_t35_base, p_t45_base, p_t55_base, corners_bases):
    p_l, p_e, p_v = prob_1x2
    exitos_1 = exitos_x = exitos_2 = 0
    over_25 = under_25 = over_35 = under_35 = 0
    btts_si_count = btts_no_count = 0
    
    t_over_35 = t_under_35 = t_over_45 = t_under_45 = t_over_55 = t_under_55 = 0
    
    lineas_corners = [7.5, 8.5, 9.5, 10.5]
    corners_counts = {l: 0 for l in lineas_corners}
    corners_under_counts = {l: 0 for l in lineas_corners}

    for _ in range(iteraciones):
        ritmo = random.gauss(1.0, 0.14)
        
        # 1. Simulación del 1X2 y asignación de goles esperados aproximados por equipo según el resultado
        dado_1x2 = random.uniform(0, 100)
        if dado_1x2 < p_l:
            exitos_1 += 1
            goles_local = random.choice([1, 2, 3, 4])
            goles_visitante = random.choice([0, 1, 2])
        elif dado_1x2 < (p_l + p_e):
            exitos_x += 1
            goles_local = random.choice([0, 1, 2])
            goles_visitante = goles_local # Empate
        else:
            exitos_2 += 1
            goles_local = random.choice([0, 1, 2])
            goles_visitante = random.choice([1, 2, 3, 4])

        # 2. Goles totales y BTTS basados en el desarrollo estocástico
        total_goles = goles_local + goles_visitante
        if total_goles > 2.5:
            over_25 += 1
        else:
            under_25 += 1

        if total_goles > 3.5:
            over_35 += 1
        else:
            under_35 += 1

        # Criterio estocástico puro para Ambos Anotan
        if goles_local > 0 and goles_visitante > 0:
            btts_si_count += 1
        else:
            btts_no_count += 1

        # 3. Tarjetas
        t_val = random.gauss(promedio_tarjetas_arbitro, 1.2) * ritmo
        if random.uniform(0, 100) < p_t35_base * (t_val / promedio_tarjetas_arbitro):
            t_over_35 += 1
        else:
            t_under_35 += 1

        if random.uniform(0, 100) < p_t45_base * (t_val / promedio_tarjetas_arbitro):
            t_over_45 += 1
        else:
            t_under_45 += 1

        if random.uniform(0, 100) < p_t55_base * (t_val / promedio_tarjetas_arbitro):
            t_over_55 += 1
        else:
            t_under_55 += 1

        # 4. Córners
        c_val = random.gauss(9.5, 2.2) * ritmo
        for linea in lineas_corners:
            if random.uniform(0, 100) < corners_bases[linea] * (c_val / 9.5):
                corners_counts[linea] += 1
            else:
                corners_under_counts[linea] += 1

    return (exitos_1, exitos_x, exitos_2, over_25, under_25, over_35, under_35, 
            btts_si_count, btts_no_count,
            t_over_35, t_under_35, t_over_45, t_under_45, t_over_55, t_under_55, 
            corners_counts, corners_under_counts)

def simular_escenarios_con_pinnacle(
    cuota_local: float, cuota_empate: float, cuota_visitante: float,
    cuota_mas_25: float, cuota_menos_25: float,
    cuota_mas_35: float, cuota_menos_35: float,
    promedio_tarjetas_arbitro: float = 4.5,
    c_t_mas_35: float = 1.80, c_t_menos_35: float = 2.00,
    c_t_mas_45: float = 2.50, c_t_menos_45: float = 1.50,
    c_t_mas_55: float = 3.50, c_t_menos_55: float = 1.25,
    c_c_mas_75: float = 1.20, c_c_menos_75: float = 4.00,
    c_c_mas_85: float = 1.45, c_c_menos_85: float = 2.60,
    c_c_mas_95: float = 1.85, c_c_menos_95: float = 1.90,
    c_c_mas_105: float = 2.40, c_c_menos_105: float = 1.55
) -> dict:
    
    p_l_bruta = 1.0 / cuota_local
    p_e_bruta = 1.0 / cuota_empate
    p_v_bruta = 1.0 / cuota_visitante
    suma_1x2 = p_l_bruta + p_e_bruta + p_v_bruta
    
    p_local_real = (p_l_bruta / suma_1x2) * 100.0
    p_empate_real = (p_e_bruta / suma_1x2) * 100.0
    p_visitante_real = (p_v_bruta / suma_1x2) * 100.0

    def get_prob_over(c_o, c_u):
        po = 1.0 / c_o
        pu = 1.0 / c_u
        return (po / (po + pu)) * 100.0

    prob_over_25_base = get_prob_over(cuota_mas_25, cuota_menos_25)
    prob_over_35_base = get_prob_over(cuota_mas_35, cuota_menos_35)

    p_t35_base = get_prob_over(c_t_mas_35, c_t_menos_35)
    p_t45_base = get_prob_over(c_t_mas_45, c_t_menos_45)
    p_t55_base = get_prob_over(c_t_mas_55, c_t_menos_55)

    corners_bases = {
        7.5: get_prob_over(c_c_mas_75, c_c_menos_75),
        8.5: get_prob_over(c_c_mas_85, c_c_menos_85),
        9.5: get_prob_over(c_c_mas_95, c_c_menos_95),
        10.5: get_prob_over(c_c_mas_105, c_c_menos_105)
    }

    total_escenarios = 50000
    hilos = 4
    bloque = total_escenarios // hilos

    prob_1x2 = (p_local_real, p_empate_real, p_visitante_real)
    resultados_hilos = []

    with ThreadPoolExecutor(max_workers=hilos) as executor:
        futures = [
            executor.submit(
                _bloque_simulacion, bloque, prob_1x2, prob_over_25_base, prob_over_35_base, 
                promedio_tarjetas_arbitro, p_t35_base, p_t45_base, p_t55_base, corners_bases
            )
            for _ in range(hilos)
        ]
        for f in futures:
            resultados_hilos.append(f.result())

    exitos_1 = sum(r[0] for r in resultados_hilos)
    exitos_x = sum(r[1] for r in resultados_hilos)
    exitos_2 = sum(r[2] for r in resultados_hilos)
    over_25_goles = sum(r[3] for r in resultados_hilos)
    under_25_goles = sum(r[4] for r in resultados_hilos)
    over_35_goles = sum(r[5] for r in resultados_hilos)
    under_35_goles = sum(r[6] for r in resultados_hilos)
    btts_si_tot = sum(r[7] for r in resultados_hilos)
    btts_no_tot = sum(r[8] for r in resultados_hilos)
    
    t_over_35 = sum(r[9] for r in resultados_hilos)
    t_under_35 = sum(r[10] for r in resultados_hilos)
    t_over_45 = sum(r[11] for r in resultados_hilos)
    t_under_45 = sum(r[12] for r in resultados_hilos)
    t_over_55 = sum(r[13] for r in resultados_hilos)
    t_under_55 = sum(r[14] for r in resultados_hilos)
    
    corners_counts = {k: sum(r[15][k] for r in resultados_hilos) for k in [7.5, 8.5, 9.5, 10.5]}
    corners_under_counts = {k: sum(r[16][k] for r in resultados_hilos) for k in [7.5, 8.5, 9.5, 10.5]}

    n = float(total_escenarios)
    return {
        "p_1": round((exitos_1 / n) * 100.0, 1),
        "p_x": round((exitos_x / n) * 100.0, 1),
        "p_2": round((exitos_2 / n) * 100.0, 1),
        "over_25": round((over_25_goles / n) * 100.0, 1),
        "under_25": round((under_25_goles / n) * 100.0, 1),
        "over_35": round((over_35_goles / n) * 100.0, 1),
        "under_35": round((under_35_goles / n) * 100.0, 1),
        "btts_si": round((btts_si_tot / n) * 100.0, 1),
        "btts_no": round((btts_no_tot / n) * 100.0, 1),
        "tarjetas_mas_35": round((t_over_35 / n) * 100.0, 1),
        "tarjetas_menos_35": round((t_under_35 / n) * 100.0, 1),
        "tarjetas_mas_45": round((t_over_45 / n) * 100.0, 1),
        "tarjetas_menos_45": round((t_under_45 / n) * 100.0, 1),
        "tarjetas_mas_55": round((t_over_55 / n) * 100.0, 1),
        "tarjetas_menos_55": round((t_under_55 / n) * 100.0, 1),
        "corners_mas": {k: round((v / n) * 100.0, 1) for k, v in corners_counts.items()},
        "corners_menos": {k: round((v / n) * 100.0, 1) for k, v in corners_under_counts.items()}
    }

@app.get("/")
def home():
    return {"mensaje": "API Master Pro - Motor Estocástico con BTTS Real"}

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
        
        # Criterio autónomo: La bolsa de candidatos compite de verdad por porcentaje matemático
        candidatos_top = [
            {"prob": sim['p_1'], "texto": f"Victoria Local (1): {sim['p_1']}%"},
            {"prob": sim['p_x'], "texto": f"Empate Técnico (X): {sim['p_x']}%"},
            {"prob": sim['p_2'], "texto": f"Victoria Visitante (2): {sim['p_2']}%"},
            {"prob": sim['over_25'], "texto": f"Más de 2.5 Goles: {sim['over_25']}%"},
            {"prob": sim['under_25'], "texto": f"Menos de 2.5 Goles: {sim['under_25']}%"},
            {"prob": sim['over_35'], "texto": f"Más de 3.5 Goles: {sim['over_35']}%"},
            {"prob": sim['under_35'], "texto": f"Menos de 3.5 Goles: {sim['under_35']}%"},
            {"prob": sim['btts_si'], "texto": f"Ambos Anotan (Sí): {sim['btts_si']}%"},
            {"prob": sim['btts_no'], "texto": f"Ambos Anotan (No): {sim['btts_no']}%"}
        ]
        # Ordenar de mayor a menor probabilidad real de las 50k simulaciones
        candidatos_top.sort(key=lambda x: x["prob"], reverse=True)

        return {
            "aviso_legal_licencia": "NOTA: Análisis matemático estocástico avanzado de 50,000 iteraciones basado en cuotas madre de Pinnacle.",
            "origen": "Fase 1 - 1X2, Goles y BTTS (Cuotas Manuales Pinnacle)",
            "probabilidades_1x2_simuladas": {
                "local": f"{sim['p_1']}%",
                "empate": f"{sim['p_x']}%",
                "visitante": f"{sim['p_2']}%"
            },
            "mercados_clave_goles": {
                "mas_de_2.5_goles": f"{sim['over_25']}%",
                "menos_de_2.5_goles": f"{sim['under_25']}%",
                "mas_de_3.5_goles": f"{sim['over_35']}%",
                "menos_de_3.5_goles": f"{sim['under_35']}%",
                "btts_si": f"{sim['btts_si']}%",
                "btts_no": f"{sim['btts_no']}%"
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
