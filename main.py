from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
import math
import bisect
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from datetime import datetime, timedelta

app = FastAPI(
    title="API Master Pro - Pinnacle Optimized Edition",
    description="Motor de simulación matemática avanzada de 50,000 escenarios con base de datos e historial",
    version="8.3.0"
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# CONFIGURACIÓN DE LA BASE DE DATOS (SQLite)
# ==========================================
def inicializar_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    # Tabla de Usuarios (Registro gratuito con usuario, correo y contraseña)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            correo TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            plan TEXT DEFAULT 'gratis',
            fecha_expiracion TEXT,
            activo INTEGER DEFAULT 1
        )
    """)
    
    # Tabla de Historial de Análisis
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL,
            fecha TEXT NOT NULL,
            partido_resumen TEXT NOT NULL,
            datos_json TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

inicializar_db()

# Modelos Pydantic para las peticiones HTTP
class RegistroSchema(BaseModel):
    usuario: str
    correo: str
    password: str

class LoginSchema(BaseModel):
    usuario: str
    password: str

class ActivarPlanSchema(BaseModel):
    usuario: str
    tipo_plan: str  # '1_mes', '3_meses', '12_meses'

class GuardarHistorialSchema(BaseModel):
    usuario: str
    partido_resumen: str
    datos_json: str

# ==========================================
# RUTAS DE AUTENTICACIÓN Y GESTIÓN DE USUARIOS
# ==========================================
@app.post("/auth/register")
def registrar_usuario(data: RegistroSchema):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    try:
        # La cuenta se crea gratis sin fecha de expiración forzosa inicial (o plan 'gratis')
        cursor.execute(
            "INSERT INTO usuarios (usuario, correo, password, plan) VALUES (?, ?, ?, ?)",
            (data.usuario, data.correo, data.password, 'gratis')
        )
        conn.commit()
        return {
            "mensaje": "¡Cuenta creada con éxito! Ya puedes ver tu historial.",
            "usuario": data.usuario,
            "correo": data.correo
        }
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="El nombre de usuario o el correo electrónico ya se encuentran registrados.")
    finally:
        conn.close()

@app.post("/auth/login")
def login_usuario(data: LoginSchema):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, correo, plan, fecha_expiracion FROM usuarios WHERE usuario = ? AND password = ?", (data.usuario, data.password))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")
    
    return {
        "mensaje": "Login exitoso",
        "usuario": data.usuario,
        "correo": user[1],
        "plan": user[2],
        "fecha_expiracion": user[3]
    }

# ==========================================
# CONTROL DE PAGOS Y PLANES (1 Mes: 12k, 3 Meses: 36k, 12 Meses: 100k)
# ==========================================
@app.post("/suscripcion/activar")
def activar_plan(data: ActivarPlanSchema):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM usuarios WHERE usuario = ?", (data.usuario,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    
    base_fecha = datetime.now()
    if data.tipo_plan == '1_mes':
        nueva_exp = base_fecha + timedelta(days=30)
    elif data.tipo_plan == '3_meses':
        nueva_exp = base_fecha + timedelta(days=90)
    elif data.tipo_plan == '12_meses':
        nueva_exp = base_fecha + timedelta(days=365)
    else:
        conn.close()
        raise HTTPException(status_code=400, detail="Plan no válido.")

    cursor.execute(
        "UPDATE usuarios SET plan = ?, fecha_expiracion = ? WHERE usuario = ?",
        (data.tipo_plan, nueva_exp.strftime("%Y-%m-%d %H:%M:%S"), data.usuario)
    )
    conn.commit()
    conn.close()
    
    return {
        "mensaje": f"Plan {data.tipo_plan} activado correctamente.",
        "nueva_expiracion": nueva_exp.strftime("%Y-%m-%d")
    }

# ==========================================
# RUTAS DE HISTORIAL (MÁXIMO LOS ÚLTIMOS 20 PARTIDOS)
# ==========================================
@app.post("/historial/guardar")
def guardar_historial(data: GuardarHistorialSchema):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Guardamos la nueva búsqueda
    cursor.execute(
        "INSERT INTO historial (usuario, fecha, partido_resumen, datos_json) VALUES (?, ?, ?, ?)",
        (data.usuario, fecha_actual, data.partido_resumen, data.datos_json)
    )
    conn.commit()
    
    # Opcional para mantener limpia la BD: conservar solo registros recientes si se desea, 
    # pero el endpoint de lectura ya limita a los últimos 20.
    conn.close()
    return {"mensaje": "Análisis guardado con éxito"}

@app.get("/historial/{usuario}")
def ver_historial(usuario: str):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    # Limitamos estrictamente a los últimos 20 partidos buscados por el usuario
    cursor.execute("SELECT fecha, partido_resumen, datos_json FROM historial WHERE usuario = ? ORDER BY id DESC LIMIT 20", (usuario,))
    resultados = cursor.fetchall()
    conn.close()
    
    historial_lista = [
        {"fecha": r[0], "partido": r[1], "detalles": r[2]} for r in resultados
    ]
    return {"usuario": usuario, "historial": historial_lista}


# ==========================================
# MOTOR DE SIMULACIÓN ESTOCÁSTICA (50k ESCENARIOS)
# ==========================================
#
# V8.1 - Corrección del modelo de goles y ranking:
# 1) Las cuotas 1X2 + Over/Under calibran un modelo de goles Poisson.
# 2) BTTS NO se usa para fabricar los goles; se usa como mercado independiente
#    para validar la predicción derivada de 1X2 + líneas de goles.
# 3) Las 50.000 simulaciones se mantienen.
# 4) El Top 3 ya no es simplemente "los tres porcentajes más altos":
#    considera probabilidad, edge frente a Pinnacle y penalización por contradicción.
# ==========================================

def _probabilidades_poisson(lambda_local, lambda_visitante, max_goles=8):
    """Construye probabilidades de marcadores 0..max_goles x 0..max_goles."""
    def poisson_probs(lam):
        probs = [math.exp(-lam)]
        for k in range(1, max_goles + 1):
            probs.append(probs[-1] * lam / k)
        resto = max(0.0, 1.0 - sum(probs))
        probs[-1] += resto
        return probs

    pl = poisson_probs(lambda_local)
    pv = poisson_probs(lambda_visitante)
    resultados = []
    for gl, pgl in enumerate(pl):
        for gv, pgv in enumerate(pv):
            resultados.append((gl, gv, pgl * pgv))

    total = sum(x[2] for x in resultados)
    return [(gl, gv, p / total) for gl, gv, p in resultados]


def _metricas_modelo(lambda_local, lambda_visitante):
    """Probabilidades analíticas del modelo, sin necesidad de simular."""
    dist = _probabilidades_poisson(lambda_local, lambda_visitante)
    p1 = px = p2 = over25 = over35 = btts = 0.0
    for gl, gv, p in dist:
        if gl > gv:
            p1 += p
        elif gl == gv:
            px += p
        else:
            p2 += p
        if gl + gv >= 3:
            over25 += p
        if gl + gv >= 4:
            over35 += p
        if gl > 0 and gv > 0:
            btts += p
    return {
        "p_1": p1 * 100.0,
        "p_x": px * 100.0,
        "p_2": p2 * 100.0,
        "over_25": over25 * 100.0,
        "under_25": (1.0 - over25) * 100.0,
        "over_35": over35 * 100.0,
        "under_35": (1.0 - over35) * 100.0,
        "btts_si": btts * 100.0,
        "btts_no": (1.0 - btts) * 100.0,
    }


def _ajustar_probabilidades_cuota(c1, c2):
    """Convierte dos cuotas del mismo mercado en probabilidades sin margen."""
    if c1 <= 1.0 or c2 <= 1.0:
        raise ValueError("Las cuotas deben ser mayores que 1.00")
    p1 = 1.0 / c1
    p2 = 1.0 / c2
    total = p1 + p2
    return p1 / total, p2 / total


def _ajustar_1x2(c_local, c_empate, c_visitante):
    if min(c_local, c_empate, c_visitante) <= 1.0:
        raise ValueError("Las cuotas 1X2 deben ser mayores que 1.00")
    bruto = [1.0 / c_local, 1.0 / c_empate, 1.0 / c_visitante]
    total = sum(bruto)
    return tuple(x / total for x in bruto)


def _probabilidades_casa_1x2(c_local, c_empate, c_visitante):
    """Probabilidades sin margen de la casa donde se apuesta (1X2)."""
    return _ajustar_1x2(c_local, c_empate, c_visitante)


def _ajuste_poisson_objetivo(lh, lv, objetivo_1x2, objetivo_over25, objetivo_over35):
    m = _metricas_modelo(lh, lv)
    error_1x2 = sum((a - b) ** 2 for a, b in zip(
        (m["p_1"] / 100.0, m["p_x"] / 100.0, m["p_2"] / 100.0), objetivo_1x2
    ))
    error_goles = (
        1.35 * ((m["over_25"] / 100.0) - objetivo_over25) ** 2 +
        1.00 * ((m["over_35"] / 100.0) - objetivo_over35) ** 2
    )
    return error_1x2 + error_goles


def _calibrar_lambdas(cuota_local, cuota_empate, cuota_visitante,
                      cuota_mas_25, cuota_menos_25,
                      cuota_mas_35, cuota_menos_35):
    """Estima goles esperados local/visitante usando mercados distintos de BTTS.

    Esto es deliberado: BTTS queda como mercado de validación independiente.
    Así evitamos que el propio BTTS obligue al motor a elegir BTTS Sí.
    """
    objetivo_1x2 = _ajustar_1x2(cuota_local, cuota_empate, cuota_visitante)
    objetivo_o25, _ = _ajustar_probabilidades_cuota(cuota_mas_25, cuota_menos_25)
    objetivo_o35, _ = _ajustar_probabilidades_cuota(cuota_mas_35, cuota_menos_35)

    mejor = (float("inf"), 1.35, 1.05)

    # Primera pasada: búsqueda estable y rápida.
    for lh_i in range(20, 421, 5):
        lh = lh_i / 100.0
        for lv_i in range(20, 421, 5):
            lv = lv_i / 100.0
            err = _ajuste_poisson_objetivo(
                lh, lv, objetivo_1x2, objetivo_o25, objetivo_o35
            )
            if err < mejor[0]:
                mejor = (err, lh, lv)

    # Segunda pasada: refinamiento alrededor del mejor punto.
    _, centro_l, centro_v = mejor
    inicio_l = max(0.20, centro_l - 0.12)
    fin_l = min(4.50, centro_l + 0.12)
    inicio_v = max(0.20, centro_v - 0.12)
    fin_v = min(4.50, centro_v + 0.12)

    paso = 0.01
    l = inicio_l
    while l <= fin_l + 1e-9:
        v = inicio_v
        while v <= fin_v + 1e-9:
            err = _ajuste_poisson_objetivo(
                l, v, objetivo_1x2, objetivo_o25, objetivo_o35
            )
            if err < mejor[0]:
                mejor = (err, l, v)
            v += paso
        l += paso

    return mejor[1], mejor[2], mejor[0]


def _preparar_cdf_marcadores(lambda_local, lambda_visitante):
    dist = _probabilidades_poisson(lambda_local, lambda_visitante)
    acumuladas = []
    marcadores = []
    acumulado = 0.0
    for gl, gv, p in dist:
        acumulado += p
        marcadores.append((gl, gv))
        acumuladas.append(acumulado)
    acumuladas[-1] = 1.0
    return marcadores, acumuladas


def _bloque_simulacion(iteraciones, marcadores, cdf_marcadores,
                       promedio_tarjetas_arbitro, p_t35_base, p_t45_base,
                       p_t55_base, corners_bases):
    exitos_1 = exitos_x = exitos_2 = 0
    over_25 = under_25 = over_35 = under_35 = 0
    btts_si_count = btts_no_count = 0
    t_over_35 = t_under_35 = t_over_45 = t_under_45 = t_over_55 = t_under_55 = 0

    lineas_corners = [7.5, 8.5, 9.5, 10.5]
    corners_counts = {l: 0 for l in lineas_corners}
    corners_under_counts = {l: 0 for l in lineas_corners}

    for _ in range(iteraciones):
        ritmo = max(0.50, random.gauss(1.0, 0.10))

        idx = bisect.bisect_left(cdf_marcadores, random.random())
        goles_local, goles_visitante = marcadores[idx]

        if goles_local > goles_visitante:
            exitos_1 += 1
        elif goles_local == goles_visitante:
            exitos_x += 1
        else:
            exitos_2 += 1

        total_goles = goles_local + goles_visitante
        if total_goles >= 3:
            over_25 += 1
        else:
            under_25 += 1

        if total_goles >= 4:
            over_35 += 1
        else:
            under_35 += 1

        if goles_local > 0 and goles_visitante > 0:
            btts_si_count += 1
        else:
            btts_no_count += 1

        t_val = max(0.1, random.gauss(promedio_tarjetas_arbitro, 1.2) * ritmo)
        factor_t = min(1.0, max(0.0, t_val / max(promedio_tarjetas_arbitro, 0.1)))

        if random.random() * 100 < min(100.0, p_t35_base * factor_t):
            t_over_35 += 1
        else:
            t_under_35 += 1

        if random.random() * 100 < min(100.0, p_t45_base * factor_t):
            t_over_45 += 1
        else:
            t_under_45 += 1

        if random.random() * 100 < min(100.0, p_t55_base * factor_t):
            t_over_55 += 1
        else:
            t_under_55 += 1

        c_val = max(0.1, random.gauss(9.5, 2.2) * ritmo)
        factor_c = min(1.0, max(0.0, c_val / 9.5))
        for linea in lineas_corners:
            if random.random() * 100 < min(100.0, corners_bases[linea] * factor_c):
                corners_counts[linea] += 1
            else:
                corners_under_counts[linea] += 1

    return (
        exitos_1, exitos_x, exitos_2, over_25, under_25, over_35, under_35,
        btts_si_count, btts_no_count,
        t_over_35, t_under_35, t_over_45, t_under_45, t_over_55, t_under_55,
        corners_counts, corners_under_counts
    )


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
    c_c_mas_105: float = 2.40, c_c_menos_105: float = 1.55,
    cuota_btts_si: float = None, cuota_btts_no: float = None,
    # Cuotas de la casa donde el usuario apuesta. NO calibran el modelo;
    # solo se usan para calcular valor/EV contra el precio disponible.
    casa_local: float = None, casa_empate: float = None, casa_visitante: float = None,
    casa_mas_25: float = None, casa_menos_25: float = None,
    casa_mas_35: float = None, casa_menos_35: float = None,
    casa_btts_si: float = None, casa_btts_no: float = None
) -> dict:
    # Probabilidades de mercado sin margen.
    p_local_real, p_empate_real, p_visitante_real = _ajustar_1x2(
        cuota_local, cuota_empate, cuota_visitante
    )
    prob_over_25_base, prob_under_25_base = _ajustar_probabilidades_cuota(
        cuota_mas_25, cuota_menos_25
    )
    prob_over_35_base, prob_under_35_base = _ajustar_probabilidades_cuota(
        cuota_mas_35, cuota_menos_35
    )

    # Nuevo núcleo: inferencia de goles coherente con 1X2 + líneas de goles.
    lambda_local, lambda_visitante, error_calibracion = _calibrar_lambdas(
        cuota_local, cuota_empate, cuota_visitante,
        cuota_mas_25, cuota_menos_25,
        cuota_mas_35, cuota_menos_35
    )
    metricas_base = _metricas_modelo(lambda_local, lambda_visitante)
    marcadores, cdf_marcadores = _preparar_cdf_marcadores(lambda_local, lambda_visitante)

    p_t35_base, _ = _ajustar_probabilidades_cuota(c_t_mas_35, c_t_menos_35)
    p_t45_base, _ = _ajustar_probabilidades_cuota(c_t_mas_45, c_t_menos_45)
    p_t55_base, _ = _ajustar_probabilidades_cuota(c_t_mas_55, c_t_menos_55)

    corners_bases = {
        7.5: _ajustar_probabilidades_cuota(c_c_mas_75, c_c_menos_75)[0],
        8.5: _ajustar_probabilidades_cuota(c_c_mas_85, c_c_menos_85)[0],
        9.5: _ajustar_probabilidades_cuota(c_c_mas_95, c_c_menos_95)[0],
        10.5: _ajustar_probabilidades_cuota(c_c_mas_105, c_c_menos_105)[0]
    }

    total_escenarios = 50000
    hilos = 4
    bloque = total_escenarios // hilos
    resultados_hilos = []

    with ThreadPoolExecutor(max_workers=hilos) as executor:
        futures = [
            executor.submit(
                _bloque_simulacion,
                bloque, marcadores, cdf_marcadores,
                promedio_tarjetas_arbitro,
                p_t35_base * 100.0, p_t45_base * 100.0, p_t55_base * 100.0,
                {k: v * 100.0 for k, v in corners_bases.items()}
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
    sim = {
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

    # ------------------------------------------
    # RANKING MATEMATICAMENTE CORRECTO: PROBABILIDAD + EV + CONFIANZA
    # ------------------------------------------
    # Regla central:
    #   EV = (P_modelo * cuota) - 1
    #   Edge = P_modelo - P_mercado_sin_margen
    # Una probabilidad alta por sí sola NO es una recomendación.
    # Si no hay valor esperado suficiente, el sistema devuelve NO RECOMENDACIÓN.

    mercados = []

    rmse_calibracion_pp = math.sqrt(max(error_calibracion, 0.0) / 5.0) * 100.0
    confianza_ajuste = max(0.45, min(1.0, 1.0 - (rmse_calibracion_pp / 10.0)))

    def agregar(nombre, prob_modelo, prob_pinnacle, cuota_pinnacle,
                cuota_casa, prob_casa=None, prob_simulada=None):
        # La casa de apuesta es opcional para no romper consultas antiguas.
        # Si no se proporciona, el mercado queda como REFERENCIA, no como valuebet.
        if cuota_pinnacle is None or cuota_pinnacle <= 1.0:
            return

        p_modelo = max(0.0, min(1.0, prob_modelo / 100.0))
        p_pinnacle = max(0.0, min(1.0, prob_pinnacle))
        edge_pinnacle = (p_modelo - p_pinnacle) * 100.0

        if prob_simulada is None:
            confianza_sim = 1.0
        else:
            diferencia_sim_pp = abs(float(prob_simulada) - float(prob_modelo))
            confianza_sim = max(0.75, min(1.0, 1.0 - diferencia_sim_pp / 5.0))

        confianza = max(0.0, min(1.0, confianza_ajuste * confianza_sim))

        # Por defecto no recomendamos usando Pinnacle como si fuera la casa final.
        cuota_evaluada = cuota_casa if cuota_casa is not None and cuota_casa > 1.0 else cuota_pinnacle
        p_casa = None if prob_casa is None else max(0.0, min(1.0, prob_casa))
        edge_casa = None if p_casa is None else (p_modelo - p_casa) * 100.0
        ev_casa = (p_modelo * cuota_casa - 1.0) * 100.0 if cuota_casa is not None and cuota_casa > 1.0 else None
        ev_pinnacle = (p_modelo * cuota_pinnacle - 1.0) * 100.0

        # Si existe cuota de la casa, el ranking se hace contra ESA cuota.
        # Si no existe, no se fuerza una recomendación.
        if ev_casa is None or edge_casa is None:
            nivel = "PENDIENTE DE CUOTA DE APUESTA"
            accion = "NO EVALUABLE"
            score_valor = None
            explicacion = (
                f"El modelo estima {prob_modelo:.1f}%. Pinnacle sirve como referencia "
                f"({cuota_pinnacle:.2f}), pero falta la cuota de la casa donde vas a apostar; "
                f"por eso no se calcula una recomendación de valor."
            )
        else:
            score_valor = ev_casa * confianza
            if ev_casa >= 5.0 and edge_casa >= 3.0:
                nivel = "VALOR FUERTE"
                accion = "RECOMENDADO"
            elif ev_casa >= 3.0 and edge_casa >= 1.5:
                nivel = "VALOR BUENO"
                accion = "RECOMENDADO"
            elif ev_casa >= 1.5 and edge_casa >= 1.0:
                nivel = "VALOR LEVE"
                accion = "RECOMENDACIÓN CAUTELOSA"
            else:
                nivel = "SIN VALOR SUFICIENTE"
                accion = "NO RECOMENDADO"

            if ev_casa <= 0:
                explicacion = (
                    f"El modelo estima {prob_modelo:.1f}% y la cuota de tu casa {cuota_casa:.2f} "
                    f"no compensa el riesgo (EV {ev_casa:+.1f}%). Pinnacle: {cuota_pinnacle:.2f}."
                )
            elif edge_casa < 1.0:
                explicacion = (
                    f"La probabilidad del modelo ({prob_modelo:.1f}%) apenas supera la "
                    f"probabilidad implícita de tu casa ({p_casa*100:.1f}%). Edge {edge_casa:+.1f}%."
                )
            elif ev_casa < 1.5:
                explicacion = (
                    f"Hay ventaja frente a tu casa (edge {edge_casa:+.1f}%), pero el EV "
                    f"todavía es pequeño ({ev_casa:+.1f}%)."
                )
            else:
                explicacion = (
                    f"El modelo estima {prob_modelo:.1f}% frente a {p_casa*100:.1f}% "
                    f"implícito en tu casa: edge {edge_casa:+.1f}% y EV {ev_casa:+.1f}%. "
                    f"Pinnacle de referencia: {cuota_pinnacle:.2f}."
                )

        mercados.append({
            "nombre": nombre,
            "probabilidad": round(prob_modelo, 1),
            "probabilidad_simulada": round(float(prob_simulada), 1) if prob_simulada is not None else round(prob_modelo, 1),
            "probabilidad_pinnacle": round(p_pinnacle * 100.0, 1),
            "probabilidad_casa": round(p_casa * 100.0, 1) if p_casa is not None else None,
            "edge_pinnacle": round(edge_pinnacle, 1),
            "edge": round(edge_casa, 1) if edge_casa is not None else None,
            "cuota_pinnacle": cuota_pinnacle,
            "cuota_casa": cuota_casa,
            "cuota": cuota_evaluada,
            "ev_pinnacle": round(ev_pinnacle, 2),
            "ev": round(ev_casa, 2) if ev_casa is not None else None,
            "confianza": round(confianza * 100.0, 1),
            "score_valor": round(score_valor, 2) if score_valor is not None else None,
            "nivel": nivel,
            "accion": accion,
            "explicacion": explicacion
        })

    # Probabilidades analíticas para que el Top no dependa del azar de las 50k.
    casa_1x2 = None
    if all(x is not None and x > 1 for x in (casa_local, casa_empate, casa_visitante)):
        casa_1x2 = _ajustar_1x2(casa_local, casa_empate, casa_visitante)

    def casa_2way(a, b):
        if a is None or b is None or a <= 1 or b <= 1:
            return (None, None)
        return _ajustar_probabilidades_cuota(a, b)

    casa_o25, casa_u25 = casa_2way(casa_mas_25, casa_menos_25)
    casa_o35, casa_u35 = casa_2way(casa_mas_35, casa_menos_35)
    casa_btts_si_p, casa_btts_no_p = casa_2way(casa_btts_si, casa_btts_no)

    agregar("Victoria Local (1)", metricas_base["p_1"], p_local_real, cuota_local, casa_local, casa_1x2[0] if casa_1x2 else None, sim["p_1"])
    agregar("Empate (X)", metricas_base["p_x"], p_empate_real, cuota_empate, casa_empate, casa_1x2[1] if casa_1x2 else None, sim["p_x"])
    agregar("Victoria Visitante (2)", metricas_base["p_2"], p_visitante_real, cuota_visitante, casa_visitante, casa_1x2[2] if casa_1x2 else None, sim["p_2"])
    agregar("Más de 2.5 Goles", metricas_base["over_25"], prob_over_25_base, cuota_mas_25, casa_mas_25, casa_o25, sim["over_25"])
    agregar("Menos de 2.5 Goles", metricas_base["under_25"], prob_under_25_base, cuota_menos_25, casa_menos_25, casa_u25, sim["under_25"])
    agregar("Más de 3.5 Goles", metricas_base["over_35"], prob_over_35_base, cuota_mas_35, casa_mas_35, casa_o35, sim["over_35"])
    agregar("Menos de 3.5 Goles", metricas_base["under_35"], prob_under_35_base, cuota_menos_35, casa_menos_35, casa_u35, sim["under_35"])

    btts_disponible = cuota_btts_si is not None and cuota_btts_no is not None and cuota_btts_si > 1 and cuota_btts_no > 1
    if btts_disponible:
        p_btts_si_m, p_btts_no_m = _ajustar_probabilidades_cuota(cuota_btts_si, cuota_btts_no)
        agregar("Ambos Anotan (Sí)", metricas_base["btts_si"], p_btts_si_m, cuota_btts_si, casa_btts_si, casa_btts_si_p, sim["btts_si"])
        agregar("Ambos Anotan (No)", metricas_base["btts_no"], p_btts_no_m, cuota_btts_no, casa_btts_no, casa_btts_no_p, sim["btts_no"])
        btts_market = {
            "disponible": True,
            "si": round(p_btts_si_m * 100.0, 1),
            "no": round(p_btts_no_m * 100.0, 1),
            "cuota_si": cuota_btts_si,
            "cuota_no": cuota_btts_no,
            "edge_si": round((metricas_base["btts_si"] / 100.0 - p_btts_si_m) * 100.0, 1),
            "edge_no": round((metricas_base["btts_no"] / 100.0 - p_btts_no_m) * 100.0, 1),
            "cuota_casa_si": casa_btts_si,
            "cuota_casa_no": casa_btts_no
        }
    else:
        btts_market = {"disponible": False}

    # Solo llamamos RECOMENDACIÓN a mercados que superan los mínimos de valor.
    recomendables = [m for m in mercados if m["accion"] in ("RECOMENDADO", "RECOMENDACIÓN CAUTELOSA")]
    recomendables.sort(key=lambda x: (x["score_valor"], x["ev"], x["edge"]), reverse=True)

    candidatos = sorted(
        mercados,
        key=lambda x: (x["score_valor"] is not None, x["score_valor"] if x["score_valor"] is not None else -999, x["ev"] if x["ev"] is not None else -999),
        reverse=True
    )
    top_3_candidatos = candidatos[:3]
    top_3_recomendaciones = recomendables[:3]

    if top_3_recomendaciones:
        estado_recomendacion = "HAY VALOR DETECTADO"
        explicacion_general = (
            "El Top 3 solo incluye mercados que superan simultáneamente los mínimos "
            "de Edge y Valor Esperado (EV). Los demás quedan como candidatos, no como apuestas recomendadas."
        )
    else:
        estado_recomendacion = "NO RECOMENDACIÓN"
        explicacion_general = (
            "Ningún mercado superó los mínimos estadísticos de Edge y Valor Esperado. "
            "El sistema no fuerza un Top 3: cuando la ventaja no es suficiente, recomienda NO APOSTAR."
        )

    return {
        **sim,
        "lambda_local": round(lambda_local, 3),
        "lambda_visitante": round(lambda_visitante, 3),
        "error_calibracion": round(error_calibracion, 5),
        "mercados_valor": candidatos[:9],
        "top_3_detallado": top_3_recomendaciones,
        "top_3_candidatos": top_3_candidatos,
        "btts_referencia_pinnacle": btts_market,
        "estado_recomendacion": estado_recomendacion,
        "explicacion_recomendacion": explicacion_general,
        "confianza_modelo": round(confianza_ajuste * 100.0, 1),
        "rmse_calibracion_puntos_porcentuales": round(rmse_calibracion_pp, 2),
        "modelo_metodo": "Poisson calibrado con Pinnacle (1X2 + Over/Under); 50k escenarios; ranking por EV + Edge + confianza usando la cuota de la casa donde se apuesta",
        "escenarios": total_escenarios
    }

@app.get("/")
def home():
    return {"mensaje": "API Master Pro - Motor Estocástico con Base de Datos e Historial Activo"}

# --- RUTA 1: FASE SUPERIOR ---
@app.get("/analisis/partido")
def analizar_partido(
    cuota_local: float = 3.03,
    cuota_empate: float = 3.26,
    cuota_visitante: float = 2.56,
    cuota_mas_25_goles: float = 1.95,
    cuota_menos_25_goles: float = 1.85,
    cuota_mas_35_goles: float = 3.40,
    cuota_menos_35_goles: float = 1.32,
    cuota_btts_si: float = None,
    cuota_btts_no: float = None,
    casa_local: float = None,
    casa_empate: float = None,
    casa_visitante: float = None,
    casa_mas_25: float = None,
    casa_menos_25: float = None,
    casa_mas_35: float = None,
    casa_menos_35: float = None,
    casa_btts_si: float = None,
    casa_btts_no: float = None
):
    try:
        sim = simular_escenarios_con_pinnacle(
            cuota_local, cuota_empate, cuota_visitante,
            cuota_mas_25_goles, cuota_menos_25_goles,
            cuota_mas_35_goles, cuota_menos_35_goles,
            cuota_btts_si=cuota_btts_si,
            cuota_btts_no=cuota_btts_no,
            casa_local=casa_local, casa_empate=casa_empate, casa_visitante=casa_visitante,
            casa_mas_25=casa_mas_25, casa_menos_25=casa_menos_25,
            casa_mas_35=casa_mas_35, casa_menos_35=casa_menos_35,
            casa_btts_si=casa_btts_si, casa_btts_no=casa_btts_no
        )

        candidatos_top = [
            f"{m['nombre']}: {m['probabilidad']}% | Cuota {m['cuota']:.2f} | EV {m['ev']:+.1f}% | {m['nivel']}"
            for m in sim["top_3_detallado"]
        ]
        if not candidatos_top:
            candidatos_top = ["NO RECOMENDACIÓN: ningún mercado superó los mínimos de valor esperado y edge."]

        return {
            "aviso_legal_licencia": "NOTA: Análisis matemático estocástico avanzado de 50,000 iteraciones. No constituye garantía de resultado.",
            "origen": "Fase 1 - 1X2, Goles y BTTS (Pinnacle)",
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
            "top_3_recomendaciones": candidatos_top,
            "top_3_detallado": sim["top_3_detallado"],
            "top_3_candidatos": sim["top_3_candidatos"],
            "mercados_valor": sim["mercados_valor"],
            "estado_recomendacion": sim["estado_recomendacion"],
            "explicacion_recomendacion": sim["explicacion_recomendacion"],
            "btts_referencia_pinnacle": sim["btts_referencia_pinnacle"],
            "comparacion_casa_apuesta": {
                "descripcion": "Pinnacle calibra el modelo; la cuota de la casa donde apuestas se usa para EV/valor.",
                "cuotas_ingresadas": {
                    "local": casa_local, "empate": casa_empate, "visitante": casa_visitante,
                    "mas_25": casa_mas_25, "menos_25": casa_menos_25,
                    "mas_35": casa_mas_35, "menos_35": casa_menos_35,
                    "btts_si": casa_btts_si, "btts_no": casa_btts_no
                }
            },
            "modelo": {
                "metodo": sim["modelo_metodo"],
                "goles_esperados_local": sim["lambda_local"],
                "goles_esperados_visitante": sim["lambda_visitante"],
                "error_calibracion": sim["error_calibracion"],
                "confianza_modelo": sim["confianza_modelo"],
                "rmse_calibracion_puntos_porcentuales": sim["rmse_calibracion_puntos_porcentuales"]
            },
            "estado": "Simulación completada con éxito (50k escenarios + Poisson calibrado)"
        }
    except Exception as e:
        return {"error": f"Error en el servidor: {str(e)}"}

# ==========================================
# JACKBUSCA V8.4 - MOTOR INDEPENDIENTE Y FLEXIBLE
# ==========================================
# Principios:
# 1) Ningún dato es obligatorio salvo que se quiera analizar ese bloque.
# 2) Nunca se inventan cuotas ni promedios faltantes.
# 3) Tarjetas: el promedio del árbitro es una señal fuerte, pero opcional.
# 4) Córners: se puede inferir la distribución desde líneas O/U de Pinnacle,
#    sin exigir promedios por equipo.
# 5) Las cuotas de la casa donde se apuesta son opcionales y SOLO sirven
#    para valorar una oportunidad (Edge/EV); no alteran el modelo.
# 6) Si faltan datos suficientes, el motor informa "DATOS INSUFICIENTES".


def _cuota_valida(c):
    return c is not None and c > 1.0


def _prob_2way_opcional(over, under):
    if not (_cuota_valida(over) and _cuota_valida(under)):
        return None, None
    return _ajustar_probabilidades_cuota(over, under)


def _poisson_cdf_leq(lam, k):
    if lam <= 0:
        return 1.0
    p = math.exp(-lam)
    total = p
    for i in range(1, k + 1):
        p *= lam / i
        total += p
    return min(1.0, max(0.0, total))


def _poisson_over(lam, linea):
    # Para líneas .5, Over 3.5 equivale a P(X >= 4).
    k = int(math.floor(linea))
    return 1.0 - _poisson_cdf_leq(lam, k)


def _ajustar_lambda_a_linea(lam_inicial, objetivos):
    """Encuentra lambda que minimiza el error frente a líneas O/U disponibles."""
    if not objetivos:
        return None, None
    mejor_lam, mejor_err = None, float('inf')
    for i in range(20, 251):
        lam = i / 20.0  # 1.0 .. 12.5
        err = 0.0
        for linea, p_over in objetivos:
            err += (_poisson_over(lam, linea) - p_over) ** 2
        if err < mejor_err:
            mejor_lam, mejor_err = lam, err
    return mejor_lam, mejor_err


def _lambda_corners_desde_mercado(lineas):
    """Infiere lambda total de córners usando solo las líneas O/U disponibles."""
    objetivos = []
    for linea, over, under in lineas:
        po, pu = _prob_2way_opcional(over, under)
        if po is not None:
            objetivos.append((float(linea), po))
    if not objetivos:
        return None, None, 0
    lam, err = _ajustar_lambda_a_linea(9.5, objetivos)
    return lam, err, len(objetivos)


def _probabilidades_con_lambda_total(lam, lineas):
    salida_mas, salida_menos = {}, {}
    for linea in lineas:
        salida_mas[linea] = round(_poisson_over(lam, linea) * 100.0, 1)
        salida_menos[linea] = round((1.0 - _poisson_over(lam, linea)) * 100.0, 1)
    return salida_mas, salida_menos


def _lambda_tarjetas(promedio_arbitro, lineas):
    """Combina promedio del árbitro (si existe) con líneas O/U disponibles.
    Si existe el promedio, tiene mayor peso; si no, se intenta inferir desde mercado."""
    objetivos = []
    for linea, over, under in lineas:
        po, pu = _prob_2way_opcional(over, under)
        if po is not None:
            objetivos.append((float(linea), po))

    lam_mercado, err_mercado = _ajustar_lambda_a_linea(4.5, objetivos) if objetivos else (None, None)

    if promedio_arbitro is not None and promedio_arbitro > 0:
        if lam_mercado is not None:
            # Promedio arbitral = señal principal; mercado = calibración secundaria.
            lam = 0.70 * float(promedio_arbitro) + 0.30 * lam_mercado
            confianza = 0.85 if len(objetivos) >= 2 else 0.78
        else:
            lam = float(promedio_arbitro)
            confianza = 0.70
        return lam, confianza, 'PROMEDIO ÁRBITRO' + (' + MERCADO' if lam_mercado is not None else '')

    if lam_mercado is not None:
        confianza = 0.68 if len(objetivos) >= 3 else 0.58
        return lam_mercado, confianza, 'MERCADO O/U'

    return None, 0.0, 'SIN DATOS'


def _evaluar_mercado_jack(nombre, prob_modelo, cuota_ref, cuota_casa, confianza, nota=''):
    if prob_modelo is None:
        return None
    p = prob_modelo / 100.0
    resultado = {
        'nombre': nombre,
        'probabilidad': round(prob_modelo, 1),
        'cuota_pinnacle': cuota_ref,
        'cuota_casa': cuota_casa,
        'confianza': round(confianza * 100.0, 1),
        'edge': None,
        'ev': None,
        'nivel': 'SIN CUOTA DE APUESTA',
        'accion': 'NO EVALUABLE',
        'explicacion': nota or 'Probabilidad calculada, pero falta la cuota de la casa donde se apuesta.'
    }
    if _cuota_valida(cuota_casa):
        # Para una sola cuota, la probabilidad implícita directa es 1/cuota.
        # No se usa como calibración del modelo; solo como precio de apuesta.
        p_casa = 1.0 / cuota_casa
        edge = (p - p_casa) * 100.0
        ev = (p * cuota_casa - 1.0) * 100.0
        score = ev * confianza
        if ev >= 5 and edge >= 3:
            nivel, accion = 'VALOR FUERTE', 'RECOMENDADO'
        elif ev >= 3 and edge >= 1.5:
            nivel, accion = 'VALOR BUENO', 'RECOMENDADO'
        elif ev >= 1.5 and edge >= 1:
            nivel, accion = 'VALOR LEVE', 'RECOMENDACIÓN CAUTELOSA'
        else:
            nivel, accion = 'SIN VALOR SUFICIENTE', 'NO RECOMENDADO'
        resultado.update({
            'probabilidad_implicita_casa': round(p_casa * 100.0, 1),
            'edge': round(edge, 1),
            'ev': round(ev, 2),
            'score_valor': round(score, 2),
            'nivel': nivel,
            'accion': accion,
            'explicacion': (
                f'El modelo estima {prob_modelo:.1f}% y la cuota de la casa {cuota_casa:.2f} '
                f'implica {p_casa*100:.1f}%. Edge {edge:+.1f}% y EV {ev:+.2f}%. {nota}'
            ).strip()
        })
    return resultado


@app.get('/jackbusca/partido')
def jackbusca_partido(
    promedio_tarjetas_arbitro: float = None,
    promedio_esperado_corners: float = None,
    # Pinnacle tarjetas: todas opcionales.
    cuota_tarjetas_mas_35: float = None,
    cuota_tarjetas_menos_35: float = None,
    cuota_tarjetas_mas_45: float = None,
    cuota_tarjetas_menos_45: float = None,
    cuota_tarjetas_mas_55: float = None,
    cuota_tarjetas_menos_55: float = None,
    # Pinnacle córners: todas opcionales.
    cuota_corners_mas_75: float = None,
    cuota_corners_menos_75: float = None,
    cuota_corners_mas_85: float = None,
    cuota_corners_menos_85: float = None,
    cuota_corners_mas_95: float = None,
    cuota_corners_menos_95: float = None,
    cuota_corners_mas_105: float = None,
    cuota_corners_menos_105: float = None,
    # Cuotas de la casa donde apuesta el usuario: opcionales.
    casa_tarjetas_mas_35: float = None,
    casa_tarjetas_menos_35: float = None,
    casa_tarjetas_mas_45: float = None,
    casa_tarjetas_menos_45: float = None,
    casa_tarjetas_mas_55: float = None,
    casa_tarjetas_menos_55: float = None,
    casa_corners_mas_75: float = None,
    casa_corners_menos_75: float = None,
    casa_corners_mas_85: float = None,
    casa_corners_menos_85: float = None,
    casa_corners_mas_95: float = None,
    casa_corners_menos_95: float = None,
    casa_corners_mas_105: float = None,
    casa_corners_menos_105: float = None,
):
    try:
        lineas_t = [
            (3.5, cuota_tarjetas_mas_35, cuota_tarjetas_menos_35),
            (4.5, cuota_tarjetas_mas_45, cuota_tarjetas_menos_45),
            (5.5, cuota_tarjetas_mas_55, cuota_tarjetas_menos_55),
        ]
        lineas_c = [
            (7.5, cuota_corners_mas_75, cuota_corners_menos_75),
            (8.5, cuota_corners_mas_85, cuota_corners_menos_85),
            (9.5, cuota_corners_mas_95, cuota_corners_menos_95),
            (10.5, cuota_corners_mas_105, cuota_corners_menos_105),
        ]

        lam_t, conf_t, fuente_t = _lambda_tarjetas(promedio_tarjetas_arbitro, lineas_t)
        lam_c, err_c, n_c = _lambda_corners_desde_mercado(lineas_c)

        # Si el usuario aporta promedio de córners, se puede usar como señal secundaria,
        # pero nunca es obligatorio. El mercado sigue teniendo prioridad si existe.
        if lam_c is not None and promedio_esperado_corners is not None and promedio_esperado_corners > 0:
            lam_c = 0.75 * lam_c + 0.25 * float(promedio_esperado_corners)
            fuente_c = 'MERCADO O/U + PROMEDIO'
        elif lam_c is not None:
            fuente_c = 'MERCADO O/U'
        elif promedio_esperado_corners is not None and promedio_esperado_corners > 0:
            lam_c = float(promedio_esperado_corners)
            err_c = None
            fuente_c = 'PROMEDIO APORTADO'
        else:
            fuente_c = 'SIN DATOS'

        lineas = [3.5, 4.5, 5.5]
        tarjetas_mas = tarjetas_menos = {}
        if lam_t is not None:
            tarjetas_mas, tarjetas_menos = _probabilidades_con_lambda_total(lam_t, lineas)

        corners_lineas = [7.5, 8.5, 9.5, 10.5]
        corners_mas = corners_menos = {}
        if lam_c is not None:
            corners_mas, corners_menos = _probabilidades_con_lambda_total(lam_c, corners_lineas)

        mercados = []
        if lam_t is not None:
            for linea, over, under, casa_o, casa_u in [
                (3.5, cuota_tarjetas_mas_35, cuota_tarjetas_menos_35, casa_tarjetas_mas_35, casa_tarjetas_menos_35),
                (4.5, cuota_tarjetas_mas_45, cuota_tarjetas_menos_45, casa_tarjetas_mas_45, casa_tarjetas_menos_45),
                (5.5, cuota_tarjetas_mas_55, cuota_tarjetas_menos_55, casa_tarjetas_mas_55, casa_tarjetas_menos_55),
            ]:
                mercados.append(_evaluar_mercado_jack(f'Más {linea} Tarjetas', tarjetas_mas[linea], over, casa_o, conf_t, f'Fuente: {fuente_t}.'))
                mercados.append(_evaluar_mercado_jack(f'Menos {linea} Tarjetas', tarjetas_menos[linea], under, casa_u, conf_t, f'Fuente: {fuente_t}.'))

        if lam_c is not None:
            for linea, over, under, casa_o, casa_u in [
                (7.5, cuota_corners_mas_75, cuota_corners_menos_75, casa_corners_mas_75, casa_corners_menos_75),
                (8.5, cuota_corners_mas_85, cuota_corners_menos_85, casa_corners_mas_85, casa_corners_menos_85),
                (9.5, cuota_corners_mas_95, cuota_corners_menos_95, casa_corners_mas_95, casa_corners_menos_95),
                (10.5, cuota_corners_mas_105, cuota_corners_menos_105, casa_corners_mas_105, casa_corners_menos_105),
            ]:
                mercados.append(_evaluar_mercado_jack(f'Más {linea} Córners', corners_mas[linea], over, casa_o, 0.68 if n_c >= 3 else 0.58, f'Fuente: {fuente_c}.'))
                mercados.append(_evaluar_mercado_jack(f'Menos {linea} Córners', corners_menos[linea], under, casa_u, 0.68 if n_c >= 3 else 0.58, f'Fuente: {fuente_c}.'))

        mercados = [m for m in mercados if m]
        recomendables = [m for m in mercados if m['accion'] in ('RECOMENDADO', 'RECOMENDACIÓN CAUTELOSA')]
        recomendables.sort(key=lambda x: x.get('score_valor', -999), reverse=True)

        bloques = []
        if lam_t is None:
            bloques.append('Tarjetas: DATOS INSUFICIENTES. Aporta promedio del árbitro o al menos una línea O/U completa de tarjetas.')
        if lam_c is None:
            bloques.append('Córners: DATOS INSUFICIENTES. No se inventó un promedio; aporta una línea O/U de Pinnacle o, si la conoces, una media de córners.')
        if not bloques:
            bloques.append('Datos suficientes para ambos bloques.')

        return {
            'origen': 'JackBusca v8.4 - modelo flexible de Tarjetas y Córners',
            'regla_datos': 'Los datos son opcionales; el motor nunca inventa cuotas ni promedios faltantes.',
            'arbitraje': {
                'promedio_tarjetas_referencia': promedio_tarjetas_arbitro,
                'lambda_tarjetas': round(lam_t, 3) if lam_t is not None else None,
                'fuente': fuente_t,
                'confianza': round(conf_t * 100.0, 1)
            },
            'corners': {
                'promedio_aportado': promedio_esperado_corners,
                'lambda_total': round(lam_c, 3) if lam_c is not None else None,
                'lineas_pinnacle_disponibles': n_c,
                'fuente': fuente_c,
                'error_calibracion': round(err_c, 5) if err_c is not None else None,
                'confianza': round((0.68 if n_c >= 3 else 0.58) * 100.0, 1) if lam_c is not None else 0.0
            },
            'mercados_tarjetas_explicados': ({
                f'mas_de_{x}': f'{tarjetas_mas[x]}%' for x in lineas
            } | {
                f'menos_de_{x}': f'{tarjetas_menos[x]}%' for x in lineas
            }) if lam_t is not None else {},
            'mercados_tiros_de_esquina': {
                'mas_de': {str(x): f'{corners_mas[x]}%' for x in corners_lineas} if lam_c is not None else {},
                'menos_de': {str(x): f'{corners_menos[x]}%' for x in corners_lineas} if lam_c is not None else {}
            },
            'mercados_valor': mercados,
            'top_3_recomendaciones': recomendables[:3],
            'estado_recomendacion': 'HAY VALOR DETECTADO' if recomendables else 'NO RECOMENDACIÓN',
            'explicacion': ' '.join(bloques) + (' Si ninguna cuota de la casa fue introducida, se muestran probabilidades pero no se fuerza una recomendación de valor.' if mercados else ''),
            'escenarios': 50000
        }
    except Exception as e:
        return {'error': f'Error en JackBusca: {str(e)}'}

