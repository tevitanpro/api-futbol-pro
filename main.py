from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from datetime import datetime

app = FastAPI(
    title="API Master Pro - Pinnacle Optimized Edition",
    description="Motor de simulación matemática avanzada de 50,000 escenarios con base de datos e historial",
    version="6.0.0"
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
    # Tabla de Usuarios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            codigo_pago TEXT UNIQUE NOT NULL,
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
    password: str
    codigo_pago: str

class LoginSchema(BaseModel):
    usuario: str
    password: str

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
        # Verificar si el código de pago ya fue usado por otra persona
        cursor.execute("SELECT id FROM usuarios WHERE codigo_pago = ?", (data.codigo_pago,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Este código de pago ya está asociado a otra cuenta o ya fue utilizado.")
        
        # Insertar nuevo usuario
        cursor.execute(
            "INSERT INTO usuarios (usuario, password, codigo_pago) VALUES (?, ?, ?)",
            (data.usuario, data.password, data.codigo_pago)
        )
        conn.commit()
        return {"mensaje": "Registro exitoso", "usuario": data.usuario}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe o el código ya fue registrado.")
    finally:
        conn.close()

@app.post("/auth/login")
def login_usuario(data: LoginSchema):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, codigo_pago FROM usuarios WHERE usuario = ? AND password = ?", (data.usuario, data.password))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")
    
    return {
        "mensaje": "Login exitoso",
        "usuario": data.usuario,
        "codigo_pago": user[1]
    }

# ==========================================
# RUTAS DE HISTORIAL DE BÚSQUEDAS
# ==========================================
@app.post("/historial/guardar")
def guardar_historial(data: GuardarHistorialSchema):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO historial (usuario, fecha, partido_resumen, datos_json) VALUES (?, ?, ?, ?)",
        (data.usuario, fecha_actual, data.partido_resumen, data.datos_json)
    )
    conn.commit()
    conn.close()
    return {"mensaje": "Análisis guardado en el historial con éxito"}

@app.get("/historial/{usuario}")
def ver_historial(usuario: str):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT fecha, partido_resumen, datos_json FROM historial WHERE usuario = ? ORDER BY id DESC", (usuario,))
    resultados = cursor.fetchall()
    conn.close()
    
    historial_lista = [
        {"fecha": r[0], "partido": r[1], "detalles": r[2]} for r in resultados
    ]
    return {"usuario": usuario, "historial": historial_lista}


# ==========================================
# MOTOR DE SIMULACIÓN ESTOCÁSTICA (50k ESCENARIOS)
# ==========================================
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
        
        dado_1x2 = random.uniform(0, 100)
        if dado_1x2 < p_l:
            exitos_1 += 1
            goles_local = random.choice([1, 2, 3, 4])
            goles_visitante = random.choice([0, 1, 2])
        elif dado_1x2 < (p_l + p_e):
            exitos_x += 1
            goles_local = random.choice([0, 1, 2])
            goles_visitante = goles_local
        else:
            exitos_2 += 1
            goles_local = random.choice([0, 1, 2])
            goles_visitante = random.choice([1, 2, 3, 4])

        total_goles = goles_local + goles_visitante
        if total_goles > 2.5:
            over_25 += 1
        else:
            under_25 += 1

        if total_goles > 3.5:
            over_35 += 1
        else:
            under_35 += 1

        if goles_local > 0 and goles_visitante > 0:
            btts_si_count += 1
        else:
            btts_no_count += 1

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
            {"prob": sim['under_25'], "texto": f"Menos de 2.5 Goles: {sim['under_25']}%"},
            {"prob": sim['over_35'], "texto": f"Más de 3.5 Goles: {sim['over_35']}%"},
            {"prob": sim['under_35'], "texto": f"Menos de 3.5 Goles: {sim['under_35']}%"},
            {"prob": sim['btts_si'], "texto": f"Ambos Anotan (Sí): {sim['btts_si']}%"},
            {"prob": sim['btts_no'], "texto": f"Ambos Anotan (No): {sim['btts_no']}%"}
        ]
        candidatos_top.sort(key=lambda x: x["prob"], reverse=True)

        return {
            "aviso_legal_licencia": "NOTA: Análisis matemático estocástico avanzado de 50,000 iteraciones.",
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
            "top_3_recomendaciones": [
                candidatos_top[0]['texto'],
                candidatos_top[1]['texto'],
                candidatos_top[2]['texto']
            ],
            "estado": "Simulación completada con éxito (50k escenarios)"
        }
    except Exception as e:
        return {"error": f"Error en el servidor: {str(e)}"}

# --- RUTA 2: JACKBUSCA ---
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
    cuota_tarjetas_mas_55: float = 3.50,
    cuota_tarjetas_menos_55: float = 1.25,
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
            cuota_tarjetas_mas_55, cuota_tarjetas_menos_55,
            cuota_corners_mas_75, cuota_corners_menos_75,
            cuota_corners_mas_85, cuota_corners_menos_85,
            cuota_corners_mas_95, cuota_corners_menos_95,
            cuota_corners_mas_105, cuota_corners_menos_105
        )
        
        return {
            "origen": "JackBusca Fase 2 - Tarjetas y Córners (50k)",
            "arbitraje": {"promedio_tarjetas_referencia": promedio_tarjetas_arbitro},
            "mercados_tarjetas_explicados": {
                "mas_de_3.5_tarjetas": f"{sim['tarjetas_mas_35']}%",
                "menos_de_3.5_tarjetas": f"{sim['tarjetas_menos_35']}%",
                "mas_de_4.5_tarjetas": f"{sim['tarjetas_mas_45']}%",
                "menos_de_4.5_tarjetas": f"{sim['tarjetas_menos_45']}%",
                "mas_de_5.5_tarjetas": f"{sim['tarjetas_mas_55']}%",
                "menos_de_5.5_tarjetas": f"{sim['tarjetas_menos_55']}%"
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
            "estado": "JackBusca procesó con éxito"
        }
    except Exception as e:
        return {"error": f"Error en el servidor: {str(e)}"}
