from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
import math
import bisect
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from datetime import datetime, timedelta, timezone
import os
import secrets
import hashlib
import hmac
import json
import urllib.request
import urllib.error
import smtplib
from email.message import EmailMessage
from fastapi import Request
from fastapi.responses import HTMLResponse

app = FastAPI(
    title="API Master Pro - Pinnacle Optimized Edition",
    description="Motor de simulación matemática avanzada de 50,000 escenarios con base de datos e historial",
    version="8.8.0"
)

# ==========================================
# CONFIGURACIÓN COMERCIAL Y SEGURIDAD v8.5
# ==========================================
FREE_HISTORY_LIMIT = 10
PREMIUM_HISTORY_LIMIT = 100
SESSION_DAYS = 7
EMAIL_VERIFICATION_DAYS = int(os.getenv("EMAIL_VERIFICATION_DAYS", "1"))
PASSWORD_RESET_MINUTES = int(os.getenv("PASSWORD_RESET_MINUTES", "30"))
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://api-futbol-pro.onrender.com")
RESEND_FROM_EMAIL = os.getenv(
    "RESEND_FROM_EMAIL",
    "onboarding@resend.dev"
)
DEV_SHOW_EMAIL_TOKENS = os.getenv("DEV_SHOW_EMAIL_TOKENS", "0") == "1"
ADMIN_EMAIL = os.getenv("API_MASTER_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("API_MASTER_ADMIN_PASSWORD", "")
ADMIN_USERNAME = os.getenv("API_MASTER_ADMIN_USER", "admin")
NEQUI_NUMBER = os.getenv("NEQUI_NUMBER", "3007033243")
WOMPI_PUBLIC_KEY = os.getenv("WOMPI_PUBLIC_KEY", "")
WOMPI_INTEGRITY_SECRET = os.getenv("WOMPI_INTEGRITY_SECRET", "")
WOMPI_EVENT_SECRET = os.getenv("WOMPI_EVENT_SECRET", "")
WOMPI_ENV = os.getenv("WOMPI_ENV", "test")
IVA_RATE = float(os.getenv("IVA_RATE", "0.19"))
APPLY_IVA = os.getenv("APPLY_IVA", "1") == "1"
PLANS = {
    "1_mes": {"name": "1 mes", "days": 30, "base": 12000},
    "3_meses": {"name": "3 meses", "days": 90, "base": 35000},
    "12_meses": {"name": "1 año", "days": 365, "base": 100000},
}

def _password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240000)
    return "pbkdf2$240000$" + salt.hex() + "$" + digest.hex()

def _password_verify(password: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("pbkdf2$"):
        try:
            _, rounds, salt_hex, digest_hex = stored.split("$", 3)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
            return hmac.compare_digest(digest.hex(), digest_hex)
        except Exception:
            return False
    # Compatibilidad temporal con cuentas antiguas en texto plano; se migra al iniciar sesión.
    return hmac.compare_digest(password, stored)

def _new_session() -> str:
    return secrets.token_urlsafe(48)

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def _valid_email(email: str) -> bool:
    import re
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip()))

def _create_email_token(user_id: int, purpose: str, minutes: int) -> str:
    raw = secrets.token_urlsafe(48)
    now = datetime.now()
    exp = now + timedelta(minutes=minutes)
    conn = _db()
    conn.execute("DELETE FROM email_tokens WHERE usuario_id=? AND purpose=?", (user_id, purpose))
    conn.execute("INSERT INTO email_tokens(token_hash,usuario_id,purpose,creado_en,expires_at,used) VALUES(?,?,?,?,?,0)",
                 (_token_hash(raw), user_id, purpose, now.isoformat(), exp.isoformat()))
    conn.commit(); conn.close()
    return raw

def _consume_email_token(raw: str, purpose: str):
    if not raw:
        return None
    conn = _db()
    row = conn.execute("SELECT id,usuario_id,expires_at,used FROM email_tokens WHERE token_hash=? AND purpose=?",
                       (_token_hash(raw), purpose)).fetchone()
    if not row:
        conn.close(); return None
    try:
        expired = datetime.fromisoformat(row["expires_at"]) <= datetime.now()
    except Exception:
        expired = True
    if row["used"] or expired:
        conn.close(); return None
    conn.execute("UPDATE email_tokens SET used=1 WHERE id=?", (row["id"],))
    conn.commit(); conn.close()
    return row["usuario_id"]

def _send_verification_email(email: str, usuario: str, token: str):
    link = APP_BASE_URL.rstrip('/') + '/auth/verify-email?token=' + token
    return _send_email(email, 'API Master Pro: verifica tu correo',
                       f"Hola {usuario},\n\nConfirma tu correo para activar tu cuenta en API Master Pro:\n\n{link}\n\nEste enlace vence en {EMAIL_VERIFICATION_DAYS} día(s). Si no creaste esta cuenta, ignora este mensaje.")

def _send_reset_email(email: str, usuario: str, token: str):
    link = APP_BASE_URL.rstrip('/') + '/auth/reset-password?token=' + token
    return _send_email(email, 'API Master Pro: recuperación de contraseña',
                       f"Hola {usuario},\n\nRecibimos una solicitud para cambiar tu contraseña. Usa este enlace:\n\n{link}\n\nEl enlace vence en {PASSWORD_RESET_MINUTES} minutos. Si no solicitaste el cambio, ignora este mensaje.")

def _db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def _send_email(to_email: str, subject: str, body: str):
    api_key = os.getenv("RESEND_API_KEY")
    sender = RESEND_FROM_EMAIL

    if not api_key or not to_email or not sender:
        print(
            "RESEND ERROR: faltan RESEND_API_KEY, destinatario o remitente",
            flush=True
        )
        return False

    data = json.dumps({
        "from": sender,
        "to": [to_email],
        "subject": subject,
        "text": body
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
             "User-Agent": "API-Master-Pro/8.8"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            response_body = response.read().decode(
                "utf-8",
                errors="replace"
            )
            print(
                f"RESEND OK: {response.status} {response_body}",
                flush=True
            )
            return 200 <= response.status < 300

    except urllib.error.HTTPError as e:
        error_body = e.read().decode(
            "utf-8",
            errors="replace"
        )
        print(
            f"RESEND ERROR: HTTP {e.code}: {error_body}",
            flush=True
        )
        return False

    except Exception as e:
        print(
            f"RESEND ERROR: {type(e).__name__}: {e}",
            flush=True
        )
        return False
def _plan_amount(plan_id: str):
    plan = PLANS.get(plan_id)
    if not plan:
        raise HTTPException(status_code=400, detail="Plan no válido.")
    base = plan["base"]
    tax = round(base * IVA_RATE) if APPLY_IVA else 0
    return base + tax, base, tax

def _activate_plan_by_username(usuario: str, plan_id: str):
    if plan_id not in PLANS:
        raise HTTPException(status_code=400, detail="Plan no válido.")
    conn = _db()
    row = conn.execute("SELECT id, correo, plan, fecha_expiracion FROM usuarios WHERE usuario=?", (usuario,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    now = datetime.now()
    current_exp = None
    if row["fecha_expiracion"]:
        try:
            current_exp = datetime.fromisoformat(row["fecha_expiracion"])
        except Exception:
            current_exp = None
    start = current_exp if current_exp and current_exp > now else now
    expiration = start + timedelta(days=PLANS[plan_id]["days"])
    conn.execute("UPDATE usuarios SET plan=?, fecha_expiracion=? WHERE usuario=?", (plan_id, expiration.strftime("%Y-%m-%d %H:%M:%S"), usuario))
    conn.commit(); conn.close()
    return expiration

def _is_admin_user(user) -> bool:
    return bool(user and (user.get("rol") == "admin" or (ADMIN_EMAIL and user.get("correo", "").lower() == ADMIN_EMAIL.lower())))

def _get_user_from_token(token: str):
    if not token:
        return None
    conn = _db()
    row = conn.execute("SELECT u.id,u.usuario,u.correo,u.plan,u.fecha_expiracion,u.email_verificado,u.rol,s.expires_at FROM sesiones s JOIN usuarios u ON u.id=s.usuario_id WHERE s.token=?", (token,)).fetchone()
    if not row:
        conn.close(); return None
    try:
        exp = datetime.fromisoformat(row["expires_at"])
    except Exception:
        exp = datetime.min
    if exp <= datetime.now():
        conn.execute("DELETE FROM sesiones WHERE token=?", (token,)); conn.commit(); conn.close(); return None
    if row["fecha_expiracion"]:
        try:
            if datetime.fromisoformat(row["fecha_expiracion"]) <= datetime.now():
                conn.execute("UPDATE usuarios SET plan='gratis' WHERE id=?", (row["id"],)); conn.commit()
                plan='gratis'
            else:
                plan=row["plan"]
        except Exception: plan=row["plan"]
    else: plan=row["plan"]
    conn.close()
    return {"id": row["id"], "usuario": row["usuario"], "correo": row["correo"], "plan": plan, "fecha_expiracion": row["fecha_expiracion"], "email_verificado": bool(row["email_verificado"]), "rol": row["rol"] or "usuario", "es_admin": _is_admin_user({"rol": row["rol"], "correo": row["correo"]})}

def _optional_user(request: Request):
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    return _get_user_from_token(token) if token else None

def _history_count(usuario: str) -> int:
    conn = _db()
    row = conn.execute("SELECT COUNT(*) AS c FROM historial WHERE usuario=?", (usuario,)).fetchone()
    conn.close()
    return int(row["c"] or 0)

def _save_analysis_if_allowed(user, partido_resumen: str, datos: dict):
    if not user:
        return {"guardado": False, "motivo": "invitado"}
    limite = PREMIUM_HISTORY_LIMIT if user["plan"] in PLANS or _is_admin_user(user) else FREE_HISTORY_LIMIT
    usados = _history_count(user["usuario"])
    if usados >= limite:
        return {"guardado": False, "motivo": "limite_historial", "usados": usados, "limite": limite, "restantes": 0}
    conn = _db()
    conn.execute("INSERT INTO historial(usuario,fecha,partido_resumen,datos_json) VALUES(?,?,?,?)", (user["usuario"], datetime.now().strftime("%Y-%m-%d %H:%M:%S"), partido_resumen, json.dumps(datos, ensure_ascii=False)))
    conn.commit(); conn.close()
    usados += 1
    return {"guardado": True, "usados": usados, "limite": limite, "restantes": max(0, limite-usados)}

def _current_user(request: Request):
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    user = _get_user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada.")
    return user

def _require_premium(request: Request):
    user = _current_user(request)
    if user["plan"] not in PLANS and not _is_admin_user(user):
        raise HTTPException(status_code=402, detail="JackBusca requiere un plan activo.")
    return user

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
            activo INTEGER DEFAULT 1,
            email_verificado INTEGER DEFAULT 0
        )
    """)
    # Migración segura para instalaciones v8.6 existentes.
    cols = [r[1] for r in cursor.execute("PRAGMA table_info(usuarios)").fetchall()]
    if 'email_verificado' not in cols:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN email_verificado INTEGER DEFAULT 0")
        # Las cuentas existentes no pierden acceso; las nuevas sí requieren verificación.
        cursor.execute("UPDATE usuarios SET email_verificado=1 WHERE email_verificado IS NULL OR email_verificado=0")
    if 'rol' not in cols:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN rol TEXT DEFAULT 'usuario'")
        cursor.execute("UPDATE usuarios SET rol='usuario' WHERE rol IS NULL OR rol=''")
    
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
    cursor.execute("CREATE TABLE IF NOT EXISTS sesiones (token TEXT PRIMARY KEY, usuario_id INTEGER NOT NULL, creado_en TEXT NOT NULL, expires_at TEXT NOT NULL, FOREIGN KEY(usuario_id) REFERENCES usuarios(id))")
    cursor.execute("""CREATE TABLE IF NOT EXISTS email_tokens (id INTEGER PRIMARY KEY AUTOINCREMENT, token_hash TEXT UNIQUE NOT NULL, usuario_id INTEGER NOT NULL, purpose TEXT NOT NULL, creado_en TEXT NOT NULL, expires_at TEXT NOT NULL, used INTEGER DEFAULT 0, FOREIGN KEY(usuario_id) REFERENCES usuarios(id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS pagos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, referencia TEXT UNIQUE NOT NULL, usuario TEXT NOT NULL, plan TEXT NOT NULL,
        monto INTEGER NOT NULL, moneda TEXT NOT NULL DEFAULT 'COP', estado TEXT NOT NULL DEFAULT 'PENDING',
        wompi_id TEXT, creado_en TEXT NOT NULL, actualizado_en TEXT NOT NULL
    )""")
    pago_cols = [r[1] for r in cursor.execute("PRAGMA table_info(pagos)").fetchall()]
    if 'comprobante' not in pago_cols:
        cursor.execute("ALTER TABLE pagos ADD COLUMN comprobante TEXT")
    if 'notas_admin' not in pago_cols:
        cursor.execute("ALTER TABLE pagos ADD COLUMN notas_admin TEXT")
    if 'metodo_pago' not in pago_cols:
        cursor.execute("ALTER TABLE pagos ADD COLUMN metodo_pago TEXT DEFAULT 'WOMPI'")
    conn.commit()
    conn.close()

inicializar_db()

def inicializar_admin():
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return
    email=ADMIN_EMAIL.strip().lower()
    conn=_db()
    row=conn.execute("SELECT id FROM usuarios WHERE correo=?",(email,)).fetchone()
    if row:
        conn.execute("UPDATE usuarios SET rol='admin', activo=1, email_verificado=1 WHERE id=?",(row['id'],)); conn.commit(); conn.close(); return
    conflict=conn.execute("SELECT id FROM usuarios WHERE usuario=?",(ADMIN_USERNAME,)).fetchone()
    if conflict:
        conn.close(); raise RuntimeError("API_MASTER_ADMIN_USER ya está ocupado por otra cuenta.")
    conn.execute("INSERT INTO usuarios(usuario,correo,password,plan,activo,email_verificado,rol) VALUES(?,?,?,?,1,1,'admin')",(ADMIN_USERNAME,email,_password_hash(ADMIN_PASSWORD),'admin'))
    conn.commit(); conn.close()

inicializar_admin()

# Modelos Pydantic para las peticiones HTTP
class RegistroSchema(BaseModel):
    usuario: str
    correo: str
    password: str

class LoginSchema(BaseModel):
    usuario: str
    password: str

class EmailSchema(BaseModel):
    correo: str

class ResetPasswordSchema(BaseModel):
    token: str
    password: str

class ActivarPlanSchema(BaseModel):
    usuario: str
    tipo_plan: str  # '1_mes', '3_meses', '12_meses'

class SolicitarPagoSchema(BaseModel):
    tipo_plan: str

class AdminActivarPlanSchema(BaseModel):
    tipo_plan: str
    referencia_pago: str = ""

class AdminPagoSchema(BaseModel):
    nota: str = ""

class GuardarHistorialSchema(BaseModel):
    usuario: str
    partido_resumen: str
    datos_json: str

# ==========================================
# RUTAS DE AUTENTICACIÓN Y GESTIÓN DE USUARIOS
# ==========================================
@app.post("/auth/register")
def registrar_usuario(data: RegistroSchema):
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres.")
    email = data.correo.strip().lower()
    usuario = data.usuario.strip()
    if not usuario or len(usuario) < 3:
        raise HTTPException(status_code=400, detail="El usuario debe tener al menos 3 caracteres.")
    if not _valid_email(email):
        raise HTTPException(status_code=400, detail="Ingresa un correo electrónico válido.")
    conn = _db()
    try:
        conn.execute("INSERT INTO usuarios (usuario, correo, password, plan, email_verificado) VALUES (?, ?, ?, ?, 0)",
                     (usuario, email, _password_hash(data.password), 'gratis'))
        conn.commit()
        row = conn.execute("SELECT id FROM usuarios WHERE usuario=?", (usuario,)).fetchone()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="El nombre de usuario o el correo ya están registrados.")
    finally:
        conn.close()
    token = _create_email_token(row["id"], "verify_email", EMAIL_VERIFICATION_DAYS * 24 * 60)
    sent = False
    try:
        sent = _send_verification_email(email, usuario, token)
    except Exception as e:
        print(f"ERROR SMTP VERIFICACION: {type(e).__name__}: {e}", flush=True)
        sent = False
    response = {"mensaje":"Cuenta creada. Revisa tu correo para verificarla.", "usuario":usuario, "correo":email, "plan":"gratis", "email_verificado":False, "correo_enviado":sent}
    if DEV_SHOW_EMAIL_TOKENS and not sent:
        response["dev_verification_link"] = APP_BASE_URL.rstrip('/') + '/?verify_email=' + token
    return response

@app.get("/auth/verify-email")
def verificar_correo(token: str):
    user_id = _consume_email_token(token, "verify_email")
    if not user_id:
        raise HTTPException(status_code=400, detail="El enlace no existe, ya fue utilizado o expiró.")
    conn = _db()
    conn.execute("UPDATE usuarios SET email_verificado=1 WHERE id=?", (user_id,))
    row = conn.execute("SELECT usuario,correo FROM usuarios WHERE id=?", (user_id,)).fetchone()
    conn.commit(); conn.close()
    return HTMLResponse(f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Correo verificado - API Master Pro</title>
    <style>
        body {{
            margin: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #050817;
            color: white;
            font-family: Arial, sans-serif;
        }}
        .card {{
            width: min(90%, 480px);
            padding: 40px;
            text-align: center;
            background: #11182b;
            border: 1px solid #24304d;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,.45);
        }}
        .icon {{
            font-size: 64px;
            margin-bottom: 15px;
        }}
        h1 {{
            color: #20d89a;
            margin-bottom: 10px;
        }}
        p {{
            color: #cbd5e1;
            line-height: 1.6;
        }}
        .user {{
            color: #20d89a;
            font-weight: bold;
        }}
        a {{
            display: inline-block;
            margin-top: 20px;
            padding: 13px 25px;
            border-radius: 10px;
            background: #20d89a;
            color: #061018;
            text-decoration: none;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">✅</div>
        <h1>Correo verificado</h1>
        <p>Tu cuenta de API Master Pro ya está activa.</p>
        <p>Usuario: <span class="user">{row["usuario"]}</span></p>
        <p>Ya puedes iniciar sesión.</p>
        <a href="{APP_BASE_URL}">Ir a API Master Pro</a>
    </div>
</body>
</html>
""")

@app.post("/auth/resend-verification")
def reenviar_verificacion(data: EmailSchema):
    email = data.correo.strip().lower()
    conn = _db()
    row = conn.execute("SELECT id,usuario,email_verificado FROM usuarios WHERE correo=?", (email,)).fetchone()
    conn.close()
    # Respuesta neutra para no revelar si un correo está registrado.
    response = {"mensaje":"Si la cuenta existe y aún no está verificada, recibirás un nuevo enlace."}
    if not row or row["email_verificado"]:
        return response
    token = _create_email_token(row["id"], "verify_email", EMAIL_VERIFICATION_DAYS * 24 * 60)
    try:
        sent = _send_verification_email(email, row["usuario"], token)
    except Exception:
        sent = False
    if DEV_SHOW_EMAIL_TOKENS and not sent:
        response["dev_verification_link"] = APP_BASE_URL.rstrip('/') + '/?verify_email=' + token
    return response

@app.post("/auth/forgot-password")
def solicitar_recuperacion(data: EmailSchema):
    email = data.correo.strip().lower()
    conn = _db()
    row = conn.execute("SELECT id,usuario FROM usuarios WHERE correo=?", (email,)).fetchone()
    conn.close()
    response = {"mensaje":"Si existe una cuenta con ese correo, recibirás instrucciones para recuperar la contraseña."}
    if not row:
        return response
    token = _create_email_token(row["id"], "reset_password", PASSWORD_RESET_MINUTES)
    try:
        sent = _send_reset_email(email, row["usuario"], token)
    except Exception:
        sent = False
    if DEV_SHOW_EMAIL_TOKENS and not sent:
        response["dev_reset_link"] = APP_BASE_URL.rstrip('/') + '/?reset_password=' + token
    return response
@app.get("/auth/reset-password", response_class=HTMLResponse)
def mostrar_reset_password(token: str):
    return HTMLResponse(f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Restablecer contraseña - API Master Pro</title>
    <style>
        body {{
            margin: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #050817;
            color: white;
            font-family: Arial, sans-serif;
        }}
        .card {{
            width: min(90%, 430px);
            padding: 35px;
            background: #11182b;
            border: 1px solid #24304d;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,.45);
        }}
        h1 {{
            color: #20d89a;
            text-align: center;
        }}
        p {{
            color: #cbd5e1;
            text-align: center;
        }}
        label {{
            display: block;
            margin-top: 18px;
            margin-bottom: 7px;
        }}
        input {{
            width: 100%;
            box-sizing: border-box;
            padding: 13px;
            border-radius: 10px;
            border: 1px solid #34415f;
            background: #0a1020;
            color: white;
        }}
        button {{
            width: 100%;
            margin-top: 25px;
            padding: 14px;
            border: 0;
            border-radius: 10px;
            background: #20d89a;
            color: #061018;
            font-weight: bold;
            cursor: pointer;
        }}
        #mensaje {{
            margin-top: 15px;
            color: #ff6b6b;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>🔐 Recuperar contraseña</h1>
        <p>Escribe tu nueva contraseña.</p>

        <form id="resetForm">
            <label>Nueva contraseña</label>
            <input id="password" type="password" minlength="8" required>

            <button type="submit">Cambiar contraseña</button>
        </form>

        <div id="mensaje"></div>
    </div>

    <script>
        document.getElementById("resetForm").addEventListener("submit", async function(e) {{
            e.preventDefault();

            const password = document.getElementById("password").value;
            const mensaje = document.getElementById("mensaje");

            try {{
                const response = await fetch("/auth/reset-password", {{
                    method: "POST",
                    headers: {{
                        "Content-Type": "application/json"
                    }},
                    body: JSON.stringify({{
                        token: "{token}",
                        password: password
                    }})
                }});

                const html = await response.text();

                if (response.ok) {{
                    document.open();
                    document.write(html);
                    document.close();
                }} else {{
                    mensaje.textContent = html;
                }}
            }} catch (error) {{
                mensaje.textContent = "No se pudo completar la operación.";
            }}
        }});
    </script>
</body>
</html>
""")
@app.post("/auth/reset-password")
def resetear_password(data: ResetPasswordSchema):
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 8 caracteres.")
    user_id = _consume_email_token(data.token, "reset_password")
    if not user_id:
        raise HTTPException(status_code=400, detail="El enlace de recuperación no existe, ya fue utilizado o expiró.")
    conn = _db()
    conn.execute("UPDATE usuarios SET password=?, email_verificado=1 WHERE id=?", (_password_hash(data.password), user_id))
    conn.execute("DELETE FROM sesiones WHERE usuario_id=?", (user_id,))
    conn.commit(); conn.close()
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Contraseña actualizada - API Master Pro</title>
    <style>
        body {
            margin: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #050817;
            color: white;
            font-family: Arial, sans-serif;
        }
        .card {
            width: min(90%, 480px);
            padding: 40px;
            text-align: center;
            background: #11182b;
            border: 1px solid #24304d;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,.45);
        }
        .icon {
            font-size: 64px;
        }
        h1 {
            color: #20d89a;
        }
        p {
            color: #cbd5e1;
            line-height: 1.6;
        }
        a {
            display: inline-block;
            margin-top: 20px;
            padding: 13px 25px;
            border-radius: 10px;
            background: #20d89a;
            color: #061018;
            text-decoration: none;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">✅</div>
        <h1>Contraseña actualizada</h1>
        <p>Tu contraseña fue cambiada correctamente.</p>
        <p>Ya puedes iniciar sesión nuevamente.</p>
        <a href="/">Iniciar sesión</a>
    </div>
</body>
</html>
""")

@app.post("/auth/login")
def login_usuario(data: LoginSchema):
    conn = _db()
    row = conn.execute("SELECT id, usuario, correo, password, plan, fecha_expiracion, email_verificado, rol FROM usuarios WHERE usuario = ?", (data.usuario.strip(),)).fetchone()
    if not row or not _password_verify(data.password, row["password"]):
        conn.close(); raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")
    if not row["email_verificado"]:
        conn.close(); raise HTTPException(status_code=403, detail="Debes verificar tu correo antes de iniciar sesión.")
    if not row["password"].startswith("pbkdf2$"):
        conn.execute("UPDATE usuarios SET password=? WHERE id=?", (_password_hash(data.password), row["id"]))
    token = _new_session(); now=datetime.now(); exp=now+timedelta(days=SESSION_DAYS)
    conn.execute("INSERT INTO sesiones(token,usuario_id,creado_en,expires_at) VALUES(?,?,?,?)", (token,row["id"],now.isoformat(),exp.isoformat()))
    conn.commit(); conn.close()
    return {"mensaje":"Login exitoso","token":token,"usuario":row["usuario"],"correo":row["correo"],"plan":row["plan"],"fecha_expiracion":row["fecha_expiracion"],"email_verificado":True,"rol":row["rol"] or "usuario","es_admin": _is_admin_user({"rol":row["rol"],"correo":row["correo"]})}

@app.post("/auth/logout")
def logout_usuario(request: Request):
    auth=request.headers.get("Authorization",""); token=auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    conn=_db(); conn.execute("DELETE FROM sesiones WHERE token=?",(token,)); conn.commit(); conn.close()
    return {"mensaje":"Sesión cerrada."}

@app.get("/auth/me")
def auth_me(user=Depends(_current_user)):
    return user

# ==========================================
# COMERCIAL / PLANES / WOMPI
# ==========================================
@app.get("/planes")
def listar_planes():
    salida={}
    for pid,p in PLANS.items():
        total,base,tax=_plan_amount(pid)
        salida[pid]={"nombre":p["name"],"dias":p["days"],"precio_base":base,"iva":tax,"precio_total":total,"iva_aplicado":APPLY_IVA}
    return {"planes":salida,"moneda":"COP","metodo_pago":"Nequi","nequi_numero":NEQUI_NUMBER}

@app.post("/suscripcion/checkout")
def crear_checkout(plan_id: str, request: Request, user=Depends(_current_user)):
    if plan_id not in PLANS: raise HTTPException(status_code=400, detail="Plan no válido.")
    if not WOMPI_PUBLIC_KEY or not WOMPI_INTEGRITY_SECRET:
        raise HTTPException(status_code=503, detail="Wompi no está configurado en producción todavía.")
    amount,_,_= _plan_amount(plan_id)
    reference=f"AMP-{user['id']}-{secrets.token_hex(6).upper()}"
    integrity=hashlib.sha256(f"{reference}{amount*100}COP{WOMPI_INTEGRITY_SECRET}".encode()).hexdigest()
    now=datetime.now().isoformat()
    conn=_db(); conn.execute("INSERT INTO pagos(referencia,usuario,plan,monto,moneda,estado,creado_en,actualizado_en) VALUES(?,?,?,?,?,?,?,?)",(reference,user['usuario'],plan_id,amount*100,'COP','PENDING',now,now)); conn.commit(); conn.close()
    checkout_url="https://checkout.wompi.co/p/"
    return {"reference":reference,"plan":plan_id,"amount_in_cents":amount*100,"currency":"COP","public_key":WOMPI_PUBLIC_KEY,"integrity_signature":integrity,"checkout_url":checkout_url,"mensaje":"El plan se activa únicamente cuando Wompi confirme APPROVED mediante webhook."}

@app.post("/wompi/webhook")
async def wompi_webhook(request: Request):
    body=await request.json()
    if WOMPI_EVENT_SECRET:
        sig=body.get("signature",{})
        props=sig.get("properties",[])
        timestamp=body.get("timestamp")
        data=body.get("data",{})
        def get_path(obj,path):
            cur=obj
            for part in path.split('.'):
                if isinstance(cur,dict): cur=cur.get(part)
                else: return None
            return cur
        values=[]
        for prop in props:
            val=get_path(data,prop)
            if val is None: val=get_path(body,prop)
            values.append(str(val if val is not None else ''))
        payload=''.join(values)+str(timestamp)+WOMPI_EVENT_SECRET
        expected=hashlib.sha256(payload.encode()).hexdigest()
        received=request.headers.get('X-Event-Checksum') or sig.get('checksum','')
        if not received or not hmac.compare_digest(expected,received):
            raise HTTPException(status_code=401, detail="Firma Wompi inválida.")
    event=body.get('event')
    tx=body.get('data',{}).get('transaction',{})
    reference=tx.get('reference')
    status=tx.get('status')
    if event=='transaction.updated' and reference:
        conn=_db(); row=conn.execute("SELECT usuario,plan,monto,estado FROM pagos WHERE referencia=?",(reference,)).fetchone()
        if row:
            now=datetime.now().isoformat()
            conn.execute("UPDATE pagos SET estado=?,wompi_id=?,actualizado_en=? WHERE referencia=?",(status,tx.get('id'),now,reference)); conn.commit(); conn.close()
            if status=='APPROVED' and row['estado']!='APPROVED':
                expiration=_activate_plan_by_username(row['usuario'],row['plan'])
                # Notificación best-effort: no bloquea el webhook si SMTP no está configurado.
                conn2=_db(); u=conn2.execute("SELECT correo FROM usuarios WHERE usuario=?",(row['usuario'],)).fetchone(); conn2.close()
                if u:
                    try: _send_email(u['correo'], 'API Master Pro: pago aprobado', f"Tu plan {row['plan']} está activo hasta {expiration.strftime('%Y-%m-%d')}.")
                    except Exception: pass
    return {"ok":True}

@app.get("/admin/resumen")
def admin_resumen(request: Request):
    user=_current_user(request)
    if not _is_admin_user(user): raise HTTPException(status_code=403,detail="Acceso de administrador requerido.")
    conn=_db(); usuarios=conn.execute("SELECT COUNT(*) c FROM usuarios").fetchone()['c']; activos=conn.execute("SELECT COUNT(*) c FROM usuarios WHERE activo=1").fetchone()['c']; premium=conn.execute("SELECT COUNT(*) c FROM usuarios WHERE plan != 'gratis' AND plan != 'admin'").fetchone()['c']; aprobados=conn.execute("SELECT COUNT(*) c FROM pagos WHERE estado='APPROVED'").fetchone()['c']; pendientes=conn.execute("SELECT COUNT(*) c FROM pagos WHERE estado='PENDING'").fetchone()['c']; conn.close()
    return {"usuarios":usuarios,"activos":activos,"premium":premium,"pagos_aprobados":aprobados,"pagos_pendientes":pendientes}

@app.post("/pagos/solicitar")
def solicitar_pago(data: SolicitarPagoSchema, user=Depends(_current_user)):
    if data.tipo_plan not in PLANS: raise HTTPException(status_code=400,detail="Plan no válido.")
    amount,base,tax=_plan_amount(data.tipo_plan); reference=f"AMP-NEQUI-{user['id']}-{secrets.token_hex(5).upper()}"; now=datetime.now().isoformat()
    conn=_db(); conn.execute("INSERT INTO pagos(referencia,usuario,plan,monto,moneda,estado,wompi_id,comprobante,notas_admin,metodo_pago,creado_en,actualizado_en) VALUES(?,?,?,?,?,'PENDING',NULL,NULL,NULL,'NEQUI',?,?)",(reference,user['usuario'],data.tipo_plan,amount,'COP',now,now)); conn.commit(); conn.close()
    return {"ok":True,"referencia":reference,"plan":data.tipo_plan,"precio_base":base,"iva":tax,"monto":amount,"moneda":"COP","estado":"PENDING","nequi_numero":NEQUI_NUMBER,"mensaje":"Paga por Nequi al número indicado y conserva la referencia."}

@app.get("/pagos/mis-pagos")
def mis_pagos(user=Depends(_current_user)):
    conn=_db(); rows=conn.execute("SELECT referencia,plan,monto,moneda,estado,metodo_pago,comprobante,notas_admin,creado_en,actualizado_en FROM pagos WHERE usuario=? ORDER BY id DESC",(user['usuario'],)).fetchall(); conn.close(); return {"pagos":[dict(r) for r in rows]}

@app.get("/admin/usuarios")
def admin_usuarios(request:Request,q:str="",limit:int=50):
    user=_current_user(request)
    if not _is_admin_user(user): raise HTTPException(status_code=403,detail="Acceso de administrador requerido.")
    limit=max(1,min(limit,100)); term=f"%{q.strip()}%"; conn=_db(); rows=conn.execute("SELECT id,usuario,correo,rol,plan,fecha_expiracion,activo,email_verificado FROM usuarios WHERE usuario LIKE ? OR correo LIKE ? ORDER BY id DESC LIMIT ?",(term,term,limit)).fetchall(); conn.close(); return {"usuarios":[dict(r) for r in rows]}

@app.get("/admin/usuarios/{user_id}")
def admin_usuario_detalle(user_id:int,request:Request):
    user=_current_user(request)
    if not _is_admin_user(user): raise HTTPException(status_code=403,detail="Acceso de administrador requerido.")
    conn=_db(); row=conn.execute("SELECT id,usuario,correo,rol,plan,fecha_expiracion,activo,email_verificado FROM usuarios WHERE id=?",(user_id,)).fetchone()
    if not row: conn.close(); raise HTTPException(status_code=404,detail="Usuario no encontrado.")
    hist=conn.execute("SELECT id,fecha,partido_resumen,datos_json FROM historial WHERE usuario=? ORDER BY id DESC LIMIT 20",(row['usuario'],)).fetchall(); pagos=conn.execute("SELECT id,referencia,plan,monto,estado,metodo_pago,comprobante,notas_admin,creado_en,actualizado_en FROM pagos WHERE usuario=? ORDER BY id DESC LIMIT 20",(row['usuario'],)).fetchall(); conn.close(); return {"usuario":dict(row),"historial":[dict(x) for x in hist],"pagos":[dict(x) for x in pagos]}

@app.post("/admin/usuarios/{user_id}/estado")
def admin_cambiar_estado(user_id:int,request:Request,estado:str):
    admin=_current_user(request)
    if not _is_admin_user(admin): raise HTTPException(status_code=403,detail="Acceso de administrador requerido.")
    if estado not in {"ACTIVO","SUSPENDIDO"}: raise HTTPException(status_code=400,detail="Estado no válido.")
    conn=_db(); row=conn.execute("SELECT usuario FROM usuarios WHERE id=?",(user_id,)).fetchone()
    if not row: conn.close(); raise HTTPException(status_code=404,detail="Usuario no encontrado.")
    conn.execute("UPDATE usuarios SET activo=? WHERE id=?",(1 if estado=="ACTIVO" else 0,user_id)); conn.commit(); conn.close(); return {"ok":True,"usuario":row['usuario'],"estado":estado}

@app.post("/admin/usuarios/{user_id}/rol")
def admin_cambiar_rol(user_id:int,request:Request,rol:str):
    admin=_current_user(request)
    if not _is_admin_user(admin): raise HTTPException(status_code=403,detail="Acceso de administrador requerido.")
    if rol not in {"usuario","admin"}: raise HTTPException(status_code=400,detail="Rol no válido.")
    if user_id==admin['id'] and rol!='admin': raise HTTPException(status_code=400,detail="No puedes quitarte tu propio rol de administrador.")
    conn=_db(); row=conn.execute("SELECT usuario FROM usuarios WHERE id=?",(user_id,)).fetchone()
    if not row: conn.close(); raise HTTPException(status_code=404,detail="Usuario no encontrado.")
    conn.execute("UPDATE usuarios SET rol=? WHERE id=?",(rol,user_id)); conn.commit(); conn.close(); return {"ok":True,"usuario":row['usuario'],"rol":rol}

@app.post("/admin/usuarios/{user_id}/activar-plan")
def admin_activar_plan(user_id:int,request:Request,data:AdminActivarPlanSchema):
    admin=_current_user(request)
    if not _is_admin_user(admin): raise HTTPException(status_code=403,detail="Acceso de administrador requerido.")
    if data.tipo_plan not in PLANS: raise HTTPException(status_code=400,detail="Plan no válido.")
    conn=_db(); row=conn.execute("SELECT usuario FROM usuarios WHERE id=?",(user_id,)).fetchone()
    if not row: conn.close(); raise HTTPException(status_code=404,detail="Usuario no encontrado.")
    expiration=_activate_plan_by_username(row['usuario'],data.tipo_plan); pending=conn.execute("SELECT id FROM pagos WHERE usuario=? AND estado='PENDING' ORDER BY id DESC LIMIT 1",(row['usuario'],)).fetchone()
    if pending: conn.execute("UPDATE pagos SET estado='APPROVED',notas_admin=?,actualizado_en=? WHERE id=?",(f"Activado manualmente. Referencia: {data.referencia_pago}",datetime.now().isoformat(),pending['id'])); conn.commit()
    conn.close(); return {"ok":True,"usuario":row['usuario'],"plan":data.tipo_plan,"fecha_expiracion":expiration.isoformat()}

@app.get("/admin/pagos")
def admin_pagos(request:Request):
    admin=_current_user(request)
    if not _is_admin_user(admin): raise HTTPException(status_code=403,detail="Acceso de administrador requerido.")
    conn=_db(); rows=conn.execute("SELECT id,referencia,usuario,plan,monto,moneda,estado,metodo_pago,comprobante,notas_admin,creado_en,actualizado_en FROM pagos ORDER BY id DESC").fetchall(); conn.close(); return {"pagos":[dict(r) for r in rows]}

@app.post("/admin/pagos/{pago_id}/aprobar")
def admin_aprobar_pago(pago_id:int,request:Request,data:AdminPagoSchema):
    admin=_current_user(request)
    if not _is_admin_user(admin): raise HTTPException(status_code=403,detail="Acceso de administrador requerido.")
    conn=_db(); row=conn.execute("SELECT id,usuario,plan,estado FROM pagos WHERE id=?",(pago_id,)).fetchone()
    if not row: conn.close(); raise HTTPException(status_code=404,detail="Pago no encontrado.")
    if row['estado']=='APPROVED': conn.close(); return {"ok":True,"mensaje":"El pago ya estaba aprobado."}
    conn.execute("UPDATE pagos SET estado='APPROVED',notas_admin=?,actualizado_en=? WHERE id=?",(data.nota,datetime.now().isoformat(),pago_id)); conn.commit(); conn.close(); expiration=_activate_plan_by_username(row['usuario'],row['plan']); return {"ok":True,"mensaje":"Pago aprobado y plan activado.","fecha_expiracion":expiration.isoformat()}

@app.post("/admin/pagos/{pago_id}/rechazar")
def admin_rechazar_pago(pago_id:int,request:Request,data:AdminPagoSchema):
    admin=_current_user(request)
    if not _is_admin_user(admin): raise HTTPException(status_code=403,detail="Acceso de administrador requerido.")
    conn=_db(); row=conn.execute("SELECT id FROM pagos WHERE id=?",(pago_id,)).fetchone()
    if not row: conn.close(); raise HTTPException(status_code=404,detail="Pago no encontrado.")
    conn.execute("UPDATE pagos SET estado='REJECTED',notas_admin=?,actualizado_en=? WHERE id=?",(data.nota,datetime.now().isoformat(),pago_id)); conn.commit(); conn.close(); return {"ok":True,"mensaje":"Pago rechazado."}

# ==========================================
# RUTAS DE HISTORIAL
# ==========================================
# ==========================================
@app.post("/historial/guardar")
def guardar_historial(data: GuardarHistorialSchema, user=Depends(_current_user)):
    if data.usuario != user['usuario']:
        raise HTTPException(status_code=403, detail="No puedes guardar historial de otro usuario.")
    try:
        payload = json.loads(data.datos_json) if data.datos_json else {}
    except Exception:
        payload = {"detalle": data.datos_json}
    resultado = _save_analysis_if_allowed(user, data.partido_resumen, payload)
    if not resultado.get("guardado"):
        raise HTTPException(status_code=409, detail=f"Has alcanzado el límite de {resultado.get('limite', FREE_HISTORY_LIMIT)} análisis guardados para tu plan.")
    return {"mensaje":"Análisis guardado con éxito.", "historial": resultado}

@app.get("/historial/{usuario}")
def ver_historial(usuario: str, request: Request, user=Depends(_current_user)):
    # El usuario nunca puede consultar el historial de otra cuenta.
    if usuario != user['usuario']:
        raise HTTPException(status_code=403, detail="No autorizado.")
    limite = PREMIUM_HISTORY_LIMIT if user['plan'] in PLANS else FREE_HISTORY_LIMIT
    conn=_db()
    rows=conn.execute("SELECT id,fecha,partido_resumen,datos_json FROM historial WHERE usuario=? ORDER BY id DESC LIMIT ?",(usuario,limite)).fetchall()
    total=conn.execute("SELECT COUNT(*) c FROM historial WHERE usuario=?",(usuario,)).fetchone()['c']
    conn.close()
    historial=[]
    for r in rows:
        try:
            datos=json.loads(r['datos_json']) if r['datos_json'] else {}
        except Exception:
            datos={"detalle":r['datos_json']}
        historial.append({"id":r['id'],"fecha":r['fecha'],"partido":r['partido_resumen'],"datos":datos})
    return {"usuario":usuario,"plan":user['plan'],"limite":limite,"usados":min(int(total),limite),"restantes":max(0,limite-min(int(total),limite)),"historial":historial}

@app.get("/historial/item/{historial_id}")
def ver_item_historial(historial_id: int, user=Depends(_current_user)):
    conn=_db(); row=conn.execute("SELECT id,fecha,partido_resumen,datos_json FROM historial WHERE id=? AND usuario=?",(historial_id,user['usuario'])).fetchone(); conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Análisis no encontrado en tu historial.")
    try:
        datos=json.loads(row['datos_json']) if row['datos_json'] else {}
    except Exception:
        datos={"detalle":row['datos_json']}
    return {"id":row['id'],"fecha":row['fecha'],"partido":row['partido_resumen'],"datos":datos}

@app.delete("/historial/item/{historial_id}")
def eliminar_item_historial(historial_id: int, user=Depends(_current_user)):
    conn=_db()
    row=conn.execute("SELECT id FROM historial WHERE id=? AND usuario=?",(historial_id,user['usuario'])).fetchone()
    if not row:
        conn.close(); raise HTTPException(status_code=404, detail="Análisis no encontrado en tu historial.")
    conn.execute("DELETE FROM historial WHERE id=? AND usuario=?",(historial_id,user['usuario']))
    conn.commit(); conn.close()
    return {"ok":True,"mensaje":"Análisis eliminado de tu historial."}

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
    return HTMLResponse('\n<html lang="es">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n    <title>API Master Pro - Panel Táctico Estocástico v8.8</title>\n    <script src="https://cdn.tailwindcss.com"></script>\n</head>\n<body class="bg-slate-950 text-slate-100 font-sans p-4 md:p-8">\n\n    <!-- CONTENEDOR PRINCIPAL CON DISEÑO DE DOS COLUMNAS EN PANTALLAS GRANDES -->\n    <div class="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8">\n        \n        <!-- COLUMNA IZQUIERDA: Panel de Cuenta, Acceso e Historial (Diseño Elegante y Sutil) -->\n        <aside class="lg:col-span-4 space-y-6">\n            <!-- CAJA DE AUTENTICACIÓN (LOGIN / REGISTRO) -->\n            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-4">\n                <div class="flex items-center justify-between border-b border-slate-800 pb-3">\n                    <h3 class="text-sm font-bold text-emerald-400 flex items-center gap-2">\n                        <span>👤</span> Mi Cuenta Pro\n                    </h3>\n                    <span id="user-status-badge" class="bg-slate-800 text-slate-400 text-[10px] font-bold px-2 py-0.5 rounded-full">Modo Invitado</span>\n                </div>\n\n                <!-- Si no ha iniciado sesión: Formulario -->\n                <div id="auth-forms-container" class="space-y-3">\n                    <!-- Tabs para alternar entre Login y Registro -->\n                    <div class="flex bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">\n                        <button onclick="switchAuthTab(\'login\')" id="tab-login" class="flex-1 py-1.5 rounded-lg font-bold bg-slate-800 text-emerald-400 transition cursor-pointer">Ingresar</button>\n                        <button onclick="switchAuthTab(\'register\')" id="tab-register" class="flex-1 py-1.5 rounded-lg font-bold text-slate-400 transition cursor-pointer">Registrarse</button>\n                    </div>\n\n                    <!-- Formulario de Login -->\n                    <div id="form-login-box" class="space-y-2.5">\n                        <input type="text" id="login_username" placeholder="Usuario" class="w-full bg-slate-950 border border-slate-800 rounded-xl p-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500">\n                        <input type="password" id="login_password" placeholder="Contraseña" class="w-full bg-slate-950 border border-slate-800 rounded-xl p-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500">\n                        <button onclick="ejecutarLogin()" class="w-full bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-extrabold py-2.5 rounded-xl text-xs transition shadow-md cursor-pointer">\n                            Iniciar Sesión\n                        </button>\n                        <div class="flex justify-between gap-2 text-[10px]">\n                            <span class="text-[10px] text-slate-500">Registro inmediato · sin verificación por correo</span>\n                        </div>\n                    </div>\n\n                    <!-- Formulario de Registro (Oculto por defecto) -->\n                    <div id="form-register-box" class="space-y-2.5 hidden">\n                        <input type="text" id="reg_username" placeholder="Nuevo Usuario" class="w-full bg-slate-950 border border-slate-800 rounded-xl p-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500">\n                        <!-- Casilla de Correo Añadida -->\n                        <input type="email" id="reg_email" placeholder="Correo Electrónico" class="w-full bg-slate-950 border border-slate-800 rounded-xl p-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500">\n                        <input type="password" id="reg_password" placeholder="Contraseña Segura" class="w-full bg-slate-950 border border-slate-800 rounded-xl p-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500">\n                        <button onclick="ejecutarRegistro()" class="w-full bg-blue-600 hover:bg-blue-500 text-white font-extrabold py-2.5 rounded-xl text-xs transition shadow-md cursor-pointer">\n                            Crear Cuenta Gratis\n                        </button>\n                    </div>\n                    <span id="auth-msg" class="text-[10px] block text-center text-rose-400 hidden"></span>\n                </div>\n\n                <!-- Si ya inició sesión (Oculto hasta loguearse) -->\n                <div id="user-logged-box" class="hidden space-y-3">\n                    <div class="bg-slate-950 border border-slate-800 rounded-xl p-3 space-y-2">\n                        <div class="flex justify-between gap-3"><span class="text-[10px] text-slate-500">Usuario</span><b id="lbl-username" class="text-xs text-emerald-400 truncate"></b></div>\n                        <div class="flex justify-between gap-3"><span class="text-[10px] text-slate-500">Correo</span><b id="lbl-email" class="text-[10px] text-slate-300 truncate"></b></div>\n                        <div class="flex justify-between gap-3"><span class="text-[10px] text-slate-500">Plan</span><b id="lbl-plan" class="text-[10px] text-amber-300"></b></div>\n                        <div class="flex justify-between gap-3"><span class="text-[10px] text-slate-500">Historial</span><b id="lbl-history-count" class="text-[10px] text-violet-300">0/10</b></div>\n                    </div>\n                    <div id="payment-box" class="bg-slate-950 border border-amber-500/20 rounded-xl p-3 space-y-2">\n                        <div class="text-[10px] font-bold text-amber-300">💳 Activar plan por Nequi</div>\n                        <div class="text-[10px] text-slate-400">Paga al <b class="text-white">3007033243</b> y conserva la referencia.</div>\n                        <div id="planes-lista" class="space-y-2"></div>\n                        <div id="pago-msg" class="hidden text-[10px]"></div>\n                        <div id="mis-pagos" class="text-[10px] text-slate-400"></div>\n                    </div>\n                    <button id="btn-admin-panel" onclick="toggleAdminPanel()" class="hidden w-full bg-violet-700 hover:bg-violet-600 text-white font-bold py-2 rounded-xl text-xs transition cursor-pointer">🛡️ Abrir Panel Administrador</button>\n                    <button onclick="cerrarSesion()" class="w-full bg-slate-800 hover:bg-rose-950/40 hover:text-rose-400 hover:border-rose-800 border border-slate-700 text-slate-300 font-bold py-2 rounded-xl text-xs transition cursor-pointer">Cerrar Sesión</button>\n                </div>\n            </div>\n\n            <!-- PANEL ADMINISTRADOR: solo visible para rol admin -->\n            <div id="admin-panel" class="hidden bg-slate-900 border border-violet-500/30 rounded-2xl p-5 shadow-xl space-y-4">\n                <div class="flex items-center justify-between border-b border-slate-800 pb-3">\n                    <h3 class="text-sm font-bold text-violet-300">🛡️ Panel Administrador</h3>\n                    <span id="admin-role-badge" class="text-[10px] bg-violet-500/10 text-violet-300 border border-violet-500/20 px-2 py-1 rounded-full">ADMIN</span>\n                </div>\n                <div id="admin-stats" class="grid grid-cols-2 gap-2 text-[10px]"></div>\n                <div class="flex gap-2">\n                    <input id="admin-user-search" placeholder="Buscar usuario o correo" class="flex-1 bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs">\n                    <button onclick="cargarAdminUsuarios()" class="bg-violet-600 hover:bg-violet-500 px-3 rounded-lg text-xs font-bold">Buscar</button>\n                </div>\n                <div id="admin-users-list" class="space-y-2 max-h-[360px] overflow-y-auto"></div>\n                <div class="border-t border-slate-800 pt-3">\n                    <div class="flex items-center justify-between mb-2"><b class="text-amber-300 text-xs">💳 Solicitudes Nequi</b><button onclick="cargarAdminPagos()" class="text-[10px] text-slate-400 hover:text-emerald-400 underline">Actualizar</button></div>\n                    <div id="admin-pagos" class="space-y-2 max-h-[360px] overflow-y-auto"></div>\n                </div>\n                <div id="admin-user-detail" class="hidden bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs"></div>\n            </div>\n\n            <!-- SECCIÓN DE HISTORIAL DE ANÁLISIS -->\n            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-3">\n                <div class="flex items-center justify-between border-b border-slate-800 pb-2">\n                    <h3 class="text-xs font-bold text-amber-300 flex items-center gap-1.5">\n                        <span>📋</span> Historial de Análisis\n                    </h3>\n                    <button onclick="cargarHistorial()" class="text-[10px] text-slate-400 hover:text-emerald-400 transition underline cursor-pointer">Actualizar</button>\n                </div>\n                <div class="grid grid-cols-2 gap-2 mb-2">\n                    <select id="historial-filtro" onchange="renderHistorialFiltrado()" class="bg-slate-950 border border-slate-800 rounded-lg p-2 text-[10px] text-slate-300">\n                        <option value="todos">Todos los motores</option><option value="principal">Motor Principal</option><option value="jackbusca">JackBusca</option>\n                    </select>\n                    <input id="historial-busqueda" oninput="renderHistorialFiltrado()" placeholder="Buscar partido..." class="bg-slate-950 border border-slate-800 rounded-lg p-2 text-[10px] text-slate-300 focus:outline-none focus:border-emerald-500">\n                </div>\n                <div id="historial-container" class="space-y-2 max-h-[430px] overflow-y-auto pr-1 text-xs">\n                    <p class="text-slate-500 text-center py-4 text-[11px]">Inicia sesión para ver tu historial guardado.</p>\n                </div>\n                <div id="historial-detalle" class="hidden mt-3 bg-slate-950 border border-violet-500/20 rounded-xl p-3 text-[10px]"></div>\n            </div>\n        </aside>\n\n        <!-- COLUMNA DERECHA: Los motores y títulos originales intactos -->\n        <main class="lg:col-span-8 max-w-5xl space-y-8">\n            <!-- TITULARES Y COPYWRITING PERSUASIVO -->\n            <header class="text-center mb-6 space-y-3">\n                <h1 class="text-3xl md:text-4xl font-extrabold text-emerald-400">⚽ API Master Pro</h1>\n                <p class="text-lg font-bold text-amber-300">¿Cansado de no acertar una? ¿De ir con el corazón y no con la razón?</p>\n                <p class="text-slate-300 text-sm max-w-2xl mx-auto leading-relaxed">\n                    Deje de regalarle el dinero a las casas de apuestas a puro pálpito. Aquí la matemática estocástica no perdona y ningún detalle se escapa. Conecte las cuotas reales de <span class="text-emerald-400 font-semibold">Pinnacle</span> y empiece a facturar con base en datos duros.\n                </p>\n            </header>\n\n            <!-- GUÍA RÁPIDA GENERAL -->\n            <div class="bg-slate-900 border border-slate-800 p-4 rounded-xl text-xs text-slate-300 space-y-1">\n                <p class="font-bold text-emerald-400 mb-1">💡 Instrucciones de uso (Motor 1):</p>\n                <p>1. Busque las cuotas de su partido en Pinnacle (o su casa de confianza) para Local, Empate, Visitante y Goles.</p>\n                <p>2. Ingréselas en las casillas correspondientes y ejecute el análisis matemático de forma inmediata.</p>\n            </div>\n\n            <!-- BLOQUE 1: Motor Principal (1X2, Goles y Ambos Anotan) - GRATIS -->\n            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">\n                <h2 class="text-lg font-bold text-emerald-300 border-b border-slate-800 pb-2">1. Motor Principal: 1X2, Goles y Ambos Anotan</h2>\n                <div class="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">\n                    <div class="text-slate-500 font-bold p-2">MERCADO</div>\n                    <div class="bg-emerald-950/30 border border-emerald-500/20 rounded-lg p-2 text-center font-bold text-emerald-300">PINNACLE · REFERENCIA</div>\n                    <div class="bg-blue-950/30 border border-blue-500/20 rounded-lg p-2 text-center font-bold text-blue-300">CASA DONDE APUESTO</div>\n                    <div class="bg-slate-950/40 border border-slate-800 rounded-lg p-2 flex items-center">Local (1)</div>\n                    <div><input type="number" id="c_local" value="3.03" step="0.01" class="w-full bg-slate-800 border border-emerald-900/60 rounded-lg p-2 text-center font-bold text-emerald-400" title="Cuota Pinnacle de referencia"></div>\n                    <div><input type="number" id="c_casa_local" value="" step="0.01" min="1.01" placeholder="Cuota BetPlay / RushBet" class="w-full bg-slate-800 border border-blue-900/60 rounded-lg p-2 text-center font-bold text-blue-300" title="Cuota de la casa donde vas a apostar"></div>\n                    <div class="bg-slate-950/40 border border-slate-800 rounded-lg p-2 flex items-center">Empate (X)</div>\n                    <div><input type="number" id="c_empate" value="3.26" step="0.01" class="w-full bg-slate-800 border border-emerald-900/60 rounded-lg p-2 text-center font-bold text-emerald-400" title="Cuota Pinnacle de referencia"></div>\n                    <div><input type="number" id="c_casa_empate" value="" step="0.01" min="1.01" placeholder="Cuota BetPlay / RushBet" class="w-full bg-slate-800 border border-blue-900/60 rounded-lg p-2 text-center font-bold text-blue-300" title="Cuota de la casa donde vas a apostar"></div>\n                    <div class="bg-slate-950/40 border border-slate-800 rounded-lg p-2 flex items-center">Visitante (2)</div>\n                    <div><input type="number" id="c_visitante" value="2.56" step="0.01" class="w-full bg-slate-800 border border-emerald-900/60 rounded-lg p-2 text-center font-bold text-emerald-400" title="Cuota Pinnacle de referencia"></div>\n                    <div><input type="number" id="c_casa_visitante" value="" step="0.01" min="1.01" placeholder="Cuota BetPlay / RushBet" class="w-full bg-slate-800 border border-blue-900/60 rounded-lg p-2 text-center font-bold text-blue-300" title="Cuota de la casa donde vas a apostar"></div>\n                    <div class="bg-slate-950/40 border border-slate-800 rounded-lg p-2 flex items-center">Más 2.5 Goles</div>\n                    <div><input type="number" id="c_mas25" value="1.95" step="0.01" class="w-full bg-slate-800 border border-emerald-900/60 rounded-lg p-2 text-center font-bold text-emerald-400" title="Cuota Pinnacle de referencia"></div>\n                    <div><input type="number" id="c_casa_mas25" value="" step="0.01" min="1.01" placeholder="Cuota BetPlay / RushBet" class="w-full bg-slate-800 border border-blue-900/60 rounded-lg p-2 text-center font-bold text-blue-300" title="Cuota de la casa donde vas a apostar"></div>\n                    <div class="bg-slate-950/40 border border-slate-800 rounded-lg p-2 flex items-center">Menos 2.5 Goles</div>\n                    <div><input type="number" id="c_menos25" value="1.85" step="0.01" class="w-full bg-slate-800 border border-emerald-900/60 rounded-lg p-2 text-center font-bold text-emerald-400" title="Cuota Pinnacle de referencia"></div>\n                    <div><input type="number" id="c_casa_menos25" value="" step="0.01" min="1.01" placeholder="Cuota BetPlay / RushBet" class="w-full bg-slate-800 border border-blue-900/60 rounded-lg p-2 text-center font-bold text-blue-300" title="Cuota de la casa donde vas a apostar"></div>\n                    <div class="bg-slate-950/40 border border-slate-800 rounded-lg p-2 flex items-center">Más 3.5 Goles</div>\n                    <div><input type="number" id="c_mas35" value="3.40" step="0.01" class="w-full bg-slate-800 border border-emerald-900/60 rounded-lg p-2 text-center font-bold text-emerald-400" title="Cuota Pinnacle de referencia"></div>\n                    <div><input type="number" id="c_casa_mas35" value="" step="0.01" min="1.01" placeholder="Cuota BetPlay / RushBet" class="w-full bg-slate-800 border border-blue-900/60 rounded-lg p-2 text-center font-bold text-blue-300" title="Cuota de la casa donde vas a apostar"></div>\n                    <div class="bg-slate-950/40 border border-slate-800 rounded-lg p-2 flex items-center">Menos 3.5 Goles</div>\n                    <div><input type="number" id="c_menos35" value="1.32" step="0.01" class="w-full bg-slate-800 border border-emerald-900/60 rounded-lg p-2 text-center font-bold text-emerald-400" title="Cuota Pinnacle de referencia"></div>\n                    <div><input type="number" id="c_casa_menos35" value="" step="0.01" min="1.01" placeholder="Cuota BetPlay / RushBet" class="w-full bg-slate-800 border border-blue-900/60 rounded-lg p-2 text-center font-bold text-blue-300" title="Cuota de la casa donde vas a apostar"></div>\n                    <div class="bg-slate-950/40 border border-slate-800 rounded-lg p-2 flex items-center">Ambos Anotan (Sí)</div>\n                    <div><input type="number" id="c_btts_si" value="1.75" step="0.01" class="w-full bg-slate-800 border border-emerald-900/60 rounded-lg p-2 text-center font-bold text-emerald-400" title="Cuota Pinnacle de referencia"></div>\n                    <div><input type="number" id="c_casa_btts_si" value="" step="0.01" min="1.01" placeholder="Cuota BetPlay / RushBet" class="w-full bg-slate-800 border border-blue-900/60 rounded-lg p-2 text-center font-bold text-blue-300" title="Cuota de la casa donde vas a apostar"></div>\n                    <div class="bg-slate-950/40 border border-slate-800 rounded-lg p-2 flex items-center">Ambos Anotan (No)</div>\n                    <div><input type="number" id="c_btts_no" value="2.05" step="0.01" class="w-full bg-slate-800 border border-emerald-900/60 rounded-lg p-2 text-center font-bold text-emerald-400" title="Cuota Pinnacle de referencia"></div>\n                    <div><input type="number" id="c_casa_btts_no" value="" step="0.01" min="1.01" placeholder="Cuota BetPlay / RushBet" class="w-full bg-slate-800 border border-blue-900/60 rounded-lg p-2 text-center font-bold text-blue-300" title="Cuota de la casa donde vas a apostar"></div>\n                </div>\n                <div class="bg-slate-950/60 border border-slate-800 rounded-xl p-3 text-[10px] text-slate-400">\n                    <b class="text-emerald-300">Cómo funciona:</b> Pinnacle calibra el modelo y las 50.000 simulaciones. La cuota de BetPlay/RushBet se utiliza únicamente para calcular <b class="text-blue-300">Edge + EV + valor</b>. Así no mezclamos la casa de referencia con la casa donde realmente apuestas.\n                </div>\n                <button onclick="consultarGoles()" class="w-full bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-extrabold py-3 rounded-xl transition shadow-lg shadow-emerald-500/20 cursor-pointer">\n                    Ejecutar Análisis 1X2, Goles y BTTS\n                </button>\n                <div id="resultado-goles" class="hidden grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 border-t border-slate-800"></div>\n            </div>\n\n            <!-- BLOQUE 2: Motor JackBusca (Córners y Tarjetas) - FREEMIUM INTELIGENTE -->\n            <div class="bg-slate-900 border border-amber-500/30 rounded-2xl p-6 shadow-xl space-y-6">\n                \n                <div class="flex justify-between items-center border-b border-slate-800 pb-2">\n                    <div>\n                        <h2 class="text-lg font-bold text-amber-300">2. Motor JackBusca (Córners y Tarjetas)</h2>\n                        <p class="text-xs text-slate-400 mt-0.5">Análisis avanzado de arbitraje y saques de esquina basado en rangos de probabilidad. (Deja en blanco o 0 si la casa no ofrece la cuota).</p>\n                    </div>\n                    <span id="vip-status-badge" class="bg-amber-500/10 text-amber-400 text-[10px] font-bold px-2.5 py-1 rounded-full border border-amber-500/20">Modo Vista Previa 🔒</span>\n                </div>\n\n                <!-- GUÍA ESPECÍFICA PARA JACKBUSCA -->\n                <div class="bg-slate-950 border border-amber-500/20 p-4 rounded-xl text-xs text-slate-300 space-y-1">\n                    <p class="font-bold text-amber-400 mb-1">💡 ¿Cómo configurar el Motor JackBusca?</p>\n                    <p>1. <b>Tarjetas:</b> el promedio del árbitro es opcional. Si no lo tienes, el motor puede intentar inferirlo de líneas O/U disponibles.</p>\n                    <p>2. <b>Córners:</b> no necesitas buscar el promedio de cada equipo; si existen líneas O/U de Pinnacle, el motor estima una distribución a partir de ellas.</p>\n                    <p>3. <b>Datos faltantes:</b> déjalos vacíos. JackBusca nunca inventa cuotas ni promedios y mostrará <b>DATOS INSUFICIENTES</b> cuando no haya base matemática suficiente.</p>\n                    <p>4. <b>Casa donde apuestas:</b> también es opcional; solo se usa para calcular Edge/EV y detectar valor.</p>\n                </div>\n                \n                <!-- Parámetros Generales de Tarjetas y Árbitro -->\n                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">\n                    <div>\n                        <label class="block text-xs text-slate-400 mb-1">Promedio Tarjetas Árbitro</label>\n                        <input type="number" id="prom_tarjetas" value="" step="0.1" placeholder="Opcional" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-2 text-center font-bold text-amber-400">\n                    </div>\n                    <div>\n                        <label class="block text-xs text-slate-400 mb-1">Promedio Esperado de Córners</label>\n                        <input type="number" id="prom_corners" value="" step="0.1" placeholder="Opcional" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-2 text-center font-bold text-amber-400">\n                    </div>\n                </div>\n\n                <!-- Cuotas Específicas de Tarjetas -->\n                <div class="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-3">\n                    <p class="text-xs font-bold text-amber-400 uppercase tracking-wider">Cuotas Pinnacle de Tarjetas — Referencia (opcionales):</p>\n                    <div class="grid grid-cols-2 md:grid-cols-3 gap-3">\n                        <div>\n                            <label class="block text-[10px] text-slate-400 mb-1">Más 3.5 Tarjetas</label>\n                            <input type="number" id="c_t_mas35" value="1.80" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-sm font-bold text-amber-300" placeholder="Opcional">\n                        </div>\n                        <div>\n                            <label class="block text-[10px] text-slate-400 mb-1">Menos 3.5 Tarjetas</label>\n                            <input type="number" id="c_t_menos35" value="1.95" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-sm font-bold text-amber-300" placeholder="Opcional">\n                        </div>\n                        <div>\n                            <label class="block text-[10px] text-slate-400 mb-1">Más 4.5 Tarjetas</label>\n                            <input type="number" id="c_t_mas45" value="2.50" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-sm font-bold text-amber-300" placeholder="Opcional">\n                        </div>\n                        <div>\n                            <label class="block text-[10px] text-slate-400 mb-1">Menos 4.5 Tarjetas</label>\n                            <input type="number" id="c_t_menos45" value="1.50" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-sm font-bold text-amber-300" placeholder="Opcional">\n                        </div>\n                        <div>\n                            <label class="block text-[10px] text-slate-400 mb-1">Más 5.5 Tarjetas</label>\n                            <input type="number" id="c_t_mas55" value="3.80" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-sm font-bold text-amber-300" placeholder="Opcional">\n                        </div>\n                        <div>\n                            <label class="block text-[10px] text-slate-400 mb-1">Menos 5.5 Tarjetas</label>\n                            <input type="number" id="c_t_menos55" value="1.25" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-sm font-bold text-amber-300" placeholder="Opcional">\n                        </div>\n                    </div>\n                </div>\n\n                <!-- Cuotas Específicas de Córners -->\n                <div class="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-3">\n                    <p class="text-xs font-bold text-amber-400 uppercase tracking-wider">Cuotas Pinnacle de Córners — Referencia (opcionales):</p>\n                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">\n                        <div>\n                            <label class="block text-[10px] text-slate-400 mb-1">Más 7.5 Córners</label>\n                            <input type="number" id="c_corner_mas75" value="1.45" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-sm font-bold text-amber-300" placeholder="Opcional">\n                        </div>\n                        <div>\n                            <label class="block text-[10px] text-slate-400 mb-1">Menos 7.5 Córners</label>\n                            <input type="number" id="c_corner_menos75" value="2.60" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-sm font-bold text-amber-300" placeholder="Opcional">\n                        </div>\n                        <div>\n                            <label class="block text-[10px] text-slate-400 mb-1">Más 8.5 Córners</label>\n                            <input type="number" id="c_corner_mas85" value="1.75" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-sm font-bold text-amber-300" placeholder="Opcional">\n                        </div>\n                        <div>\n                            <label class="block text-[10px] text-slate-400 mb-1">Menos 8.5 Córners</label>\n                            <input type="number" id="c_corner_menos85" value="2.00" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-sm font-bold text-amber-300" placeholder="Opcional">\n                        </div>\n                        <div>\n                            <label class="block text-[10px] text-slate-400 mb-1">Más 9.5 Córners</label>\n                            <input type="number" id="c_corner_mas95" value="2.10" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-sm font-bold text-amber-300" placeholder="Opcional">\n                        </div>\n                        <div>\n                            <label class="block text-[10px] text-slate-400 mb-1">Menos 9.5 Córners</label>\n                            <input type="number" id="c_corner_menos95" value="1.65" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-sm font-bold text-amber-300" placeholder="Opcional">\n                        </div>\n                        <div>\n                            <label class="block text-[10px] text-slate-400 mb-1">Más 10.5 Córners</label>\n                            <input type="number" id="c_corner_mas105" value="2.75" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-sm font-bold text-amber-300" placeholder="Opcional">\n                        </div>\n                        <div>\n                            <label class="block text-[10px] text-slate-400 mb-1">Menos 10.5 Córners</label>\n                            <input type="number" id="c_corner_menos105" value="1.40" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-sm font-bold text-amber-300" placeholder="Opcional">\n                        </div>\n                    </div>\n                </div>\n\n                <!-- CUOTAS DE LA CASA DONDE APUESTA EL USUARIO -->\n                <div class="bg-slate-950 p-4 rounded-xl border border-emerald-500/20 space-y-3">\n                    <div>\n                        <p class="text-xs font-bold text-emerald-400 uppercase tracking-wider">Cuotas de la casa donde apuestas — Opcionales</p>\n                        <p class="text-[10px] text-slate-400 mt-1">No cambian el modelo. Solo permiten calcular probabilidad implícita, Edge, EV y valor.</p>\n                    </div>\n                    <div class="grid grid-cols-2 md:grid-cols-3 gap-3">\n                        <input type="number" id="casa_t_mas35" placeholder="Casa Más 3.5 T" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-xs text-emerald-300">\n                        <input type="number" id="casa_t_menos35" placeholder="Casa Menos 3.5 T" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-xs text-emerald-300">\n                        <input type="number" id="casa_t_mas45" placeholder="Casa Más 4.5 T" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-xs text-emerald-300">\n                        <input type="number" id="casa_t_menos45" placeholder="Casa Menos 4.5 T" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-xs text-emerald-300">\n                        <input type="number" id="casa_t_mas55" placeholder="Casa Más 5.5 T" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-xs text-emerald-300">\n                        <input type="number" id="casa_t_menos55" placeholder="Casa Menos 5.5 T" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-xs text-emerald-300">\n                        <input type="number" id="casa_c_mas75" placeholder="Casa Más 7.5 C" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-xs text-emerald-300">\n                        <input type="number" id="casa_c_menos75" placeholder="Casa Menos 7.5 C" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-xs text-emerald-300">\n                        <input type="number" id="casa_c_mas85" placeholder="Casa Más 8.5 C" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-xs text-emerald-300">\n                        <input type="number" id="casa_c_menos85" placeholder="Casa Menos 8.5 C" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-xs text-emerald-300">\n                        <input type="number" id="casa_c_mas95" placeholder="Casa Más 9.5 C" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-xs text-emerald-300">\n                        <input type="number" id="casa_c_menos95" placeholder="Casa Menos 9.5 C" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-xs text-emerald-300">\n                        <input type="number" id="casa_c_mas105" placeholder="Casa Más 10.5 C" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-xs text-emerald-300">\n                        <input type="number" id="casa_c_menos105" placeholder="Casa Menos 10.5 C" step="0.01" class="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-center text-xs text-emerald-300">\n                    </div>\n                </div>\n\n                <!-- CONTENEDOR BLOQUEADO: activación manual por Nequi -->\n                <div class="space-y-4 pt-2">\n                    <div id="jackbusca-lock-container" class="bg-slate-950 border border-amber-500/40 p-4 rounded-xl text-center space-y-3">\n                        <div class="flex items-center justify-center gap-2 text-amber-400 font-bold text-sm">\n                            <span>🔒</span> JackBusca requiere un plan activo\n                        </div>\n                        <p class="text-xs text-slate-400 max-w-lg mx-auto">\n                            En esta versión el pago se gestiona directamente por Nequi y la activación la realiza el administrador.\n                        </p>\n                        <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px]">\n                            <div class="bg-slate-900 border border-slate-800 rounded-lg p-2"><b class="text-white">1 mes</b><br>$12.000 COP</div>\n                            <div class="bg-slate-900 border border-slate-800 rounded-lg p-2"><b class="text-white">3 meses</b><br>$35.000 COP</div>\n                            <div class="bg-slate-900 border border-slate-800 rounded-lg p-2"><b class="text-white">1 año</b><br>$100.000 COP</div>\n                        </div>\n                        <p class="text-[10px] text-slate-500">Después de confirmar el pago, el administrador activa el plan desde el panel.\n                        </p>\n                        <span id="error-msg" class="text-[10px] text-rose-400 block hidden">No se pudo comprobar el estado del plan.</span>\n                    </div>\n\n                    <!-- Botón de Ejecución -->\n                    <button id="btn-ejecutar-jack" onclick="consultarJackBusca()" disabled class="w-full bg-slate-800 text-slate-500 font-extrabold py-3 rounded-xl transition cursor-not-allowed shadow-none">\n                        🔒 Ejecutar Análisis JackBusca (Requiere Activación VIP)\n                    </button>\n                </div>\n\n                <!-- Resultados JackBusca -->\n                <div id="resultado-jack" class="hidden grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-slate-800"></div>\n            </div>\n        </main>\n    </div>\n\n    <script>\n        const baseUrl = \'https://api-futbol-pro.onrender.com\';\n        let tokenJwt = localStorage.getItem(\'token_jwt\') || \'\';\n\n        // Comprobar estado de sesión al cargar la página\n        window.addEventListener(\'DOMContentLoaded\', () => {\n            if (tokenJwt) {\n                verificarTokenGuardado();\n            }\n        });\n\n        function switchAuthTab(tab) {\n            const loginBox = document.getElementById(\'form-login-box\');\n            const registerBox = document.getElementById(\'form-register-box\');\n            const btnLogin = document.getElementById(\'tab-login\');\n            const btnRegister = document.getElementById(\'tab-register\');\n\n            if (tab === \'login\') {\n                loginBox.classList.remove(\'hidden\');\n                registerBox.classList.add(\'hidden\');\n                btnLogin.className = "flex-1 py-1.5 rounded-lg font-bold bg-slate-800 text-emerald-400 transition cursor-pointer";\n                btnRegister.className = "flex-1 py-1.5 rounded-lg font-bold text-slate-400 transition cursor-pointer";\n            } else {\n                loginBox.classList.add(\'hidden\');\n                registerBox.classList.remove(\'hidden\');\n                btnRegister.className = "flex-1 py-1.5 rounded-lg font-bold bg-slate-800 text-blue-400 transition cursor-pointer";\n                btnLogin.className = "flex-1 py-1.5 rounded-lg font-bold text-slate-400 transition cursor-pointer";\n            }\n        }\n\n\n\n\n\n\n\n        async function ejecutarRegistro() {\n            const u = document.getElementById(\'reg_username\').value.trim();\n            const email = document.getElementById(\'reg_email\').value.trim();\n            const p = document.getElementById(\'reg_password\').value.trim();\n            const msg = document.getElementById(\'auth-msg\');\n\n            if (!u || !email || !p) {\n                msg.innerText = "Completa todos los campos (incluyendo el correo).";\n                msg.classList.remove(\'hidden\');\n                return;\n            }\n\n            try {\n                let resp = await fetch(baseUrl + \'/auth/register\', {\n                    method: \'POST\',\n                    headers: { \'Content-Type\': \'application/json\' },\n                   body: JSON.stringify({ usuario: u, correo: email, password: p })\n                });\n                let data = await resp.json();\n                if (resp.ok) {\n                    msg.classList.add(\'hidden\');\n                    alert(data.mensaje || \'Cuenta creada correctamente. Ya puedes iniciar sesión.\');\n                    switchAuthTab(\'login\');\n                } else {\n                    msg.innerText = data.detail || "Error al registrarse.";\n                    msg.classList.remove(\'hidden\');\n                }\n            } catch (err) {\n                msg.innerText = "Error de conexión con el servidor.";\n                msg.classList.remove(\'hidden\');\n            }\n        }\n\n        async function ejecutarLogin() {\n    const u = document.getElementById(\'login_username\').value.trim();\n    const p = document.getElementById(\'login_password\').value.trim();\n    const msg = document.getElementById(\'auth-msg\');\n\n    if (!u || !p) {\n        msg.innerText = "Ingresa usuario y contraseña.";\n        msg.classList.remove(\'hidden\');\n        return;\n    }\n\n    try {\n        let resp = await fetch(baseUrl + \'/auth/login\', {\n            method: \'POST\',\n            headers: { \'Content-Type\': \'application/json\' },\n            body: JSON.stringify({ usuario: u, password: p })\n        });\n        \n        let data = await resp.json();\n        \n        if (resp.ok) {\n            tokenJwt = data.token;\n            localStorage.setItem(\'token_jwt\', tokenJwt);\n            localStorage.setItem(\'username\', data.usuario);\n            msg.classList.add(\'hidden\');\n            actualizarInterfazLogueado(data.usuario, data.correo, data.plan, data.rol);\n            cargarHistorial();\n        } else {\n            msg.innerText = data.detail || "Credenciales incorrectas.";\n            msg.classList.remove(\'hidden\');\n        }\n    } catch (err) {\n        msg.innerText = "Error al conectar con el backend.";\n        msg.classList.remove(\'hidden\');\n    }\n}\n        async function verificarTokenGuardado() {\n            const savedToken = localStorage.getItem(\'token_jwt\');\n            if (!savedToken) return;\n            tokenJwt = savedToken;\n            try {\n                const resp = await fetch(baseUrl + \'/auth/me\', { headers: { \'Authorization\': \'Bearer \' + tokenJwt } });\n                if (!resp.ok) throw new Error(\'Sesión inválida\');\n                const data = await resp.json();\n                localStorage.setItem(\'username\', data.usuario);\n                actualizarInterfazLogueado(data.usuario, data.correo, data.plan, data.rol);\n                cargarHistorial();\n            } catch (e) {\n                tokenJwt = \'\';\n                localStorage.removeItem(\'token_jwt\');\n                localStorage.removeItem(\'username\');\n            }\n        }\n\n        function actualizarInterfazLogueado(username, correo=\'\', plan=\'gratis\', rol=\'usuario\') {\n            document.getElementById(\'auth-forms-container\').classList.add(\'hidden\');\n            document.getElementById(\'user-logged-box\').classList.remove(\'hidden\');\n            document.getElementById(\'lbl-username\').innerText = username;\n            document.getElementById(\'lbl-email\').innerText = correo || \'Correo\';\n            document.getElementById(\'lbl-plan\').innerText = plan === \'gratis\' ? \'GRATIS\' : String(plan).toUpperCase();\n            const adminBtn=document.getElementById(\'btn-admin-panel\');\n            if(adminBtn) adminBtn.classList.toggle(\'hidden\', rol !== \'admin\');\n            verificarAccesoJackBusca();\n            if(rol === \'admin\') cargarAdminResumen();\n            const badge = document.getElementById(\'user-status-badge\');\n            badge.className = "bg-emerald-500/10 text-emerald-400 text-[10px] font-bold px-2 py-0.5 rounded-full border border-emerald-500/20";\n            badge.innerText = "Sesión Activa ✅";\n        }\n\n        function cerrarSesion() {\n            tokenJwt = \'\';\n            localStorage.removeItem(\'token_jwt\');\n            localStorage.removeItem(\'username\');\n            document.getElementById(\'auth-forms-container\').classList.remove(\'hidden\');\n            document.getElementById(\'user-logged-box\').classList.add(\'hidden\');\n            document.getElementById(\'admin-panel\')?.classList.add(\'hidden\');\n            document.getElementById(\'btn-admin-panel\')?.classList.add(\'hidden\');\n            const badge = document.getElementById(\'user-status-badge\');\n            badge.className = "bg-slate-800 text-slate-400 text-[10px] font-bold px-2 py-0.5 rounded-full";\n            badge.innerText = "Modo Invitado";\n            document.getElementById(\'historial-container\').innerHTML = \'<p class="text-slate-500 text-center py-4 text-[11px]">Inicia sesión para ver tu historial guardado.</p>\';\n        }\n\n        let historialActual = [];\n        async function cargarHistorial() {\n            if (!tokenJwt) return;\n            const container = document.getElementById(\'historial-container\');\n            container.innerHTML = \'<p class="text-emerald-400 text-center py-2 animate-pulse">Cargando historial...</p>\';\n            try {\n                const usuarioActual = localStorage.getItem(\'username\');\n                const resp = await fetch(baseUrl + \'/historial/\' + encodeURIComponent(usuarioActual), {headers:{\'Authorization\':\'Bearer \' + tokenJwt}});\n                if (resp.status === 401) { cerrarSesion(); return; }\n                const data = await resp.json();\n                if (!resp.ok) throw new Error(data.detail || \'No se pudo cargar el historial.\');\n                historialActual = data.historial || [];\n                document.getElementById(\'lbl-history-count\').innerText = `${data.usados}/${data.limite}`;\n                document.getElementById(\'lbl-plan\').innerText = data.plan === \'gratis\' ? \'GRATIS\' : data.plan.toUpperCase();\n                renderHistorialFiltrado();\n            } catch (err) {\n                container.innerHTML = \'<p class="text-rose-400 text-center py-2 text-[11px]">Error al cargar historial.</p>\';\n            }\n        }\n\n        function renderHistorialFiltrado() {\n            const container=document.getElementById(\'historial-container\');\n            if (!tokenJwt) return;\n            const filtro=document.getElementById(\'historial-filtro\')?.value || \'todos\';\n            const busq=(document.getElementById(\'historial-busqueda\')?.value || \'\').trim().toLowerCase();\n            const lista=historialActual.filter(item=>{\n                const texto=(item.partido || \'\').toLowerCase();\n                const tipo=JSON.stringify(item.datos || {}).toLowerCase();\n                const esJack=texto.includes(\'jackbusca\') || tipo.includes(\'jackbusca\') || (item.datos && item.datos.origen && String(item.datos.origen).toLowerCase().includes(\'jackbusca\'));\n                return (filtro===\'todos\' || (filtro===\'jackbusca\' ? esJack : !esJack)) && (!busq || texto.includes(busq));\n            });\n            if (!lista.length) { container.innerHTML=\'<p class="text-slate-500 text-center py-4 text-[11px]">No hay análisis que coincidan con el filtro.</p>\'; return; }\n            container.innerHTML=lista.map(item=>{\n                const d=item.datos||{};\n                const tipo=(item.partido||\'\').toLowerCase().includes(\'jackbusca\') ? \'JACKBUSCA\' : \'MOTOR PRINCIPAL\';\n                const estado=d.estado_recomendacion || d.explicacion || \'Análisis guardado\';\n                return `<div class="bg-slate-950 p-3 rounded-xl border border-slate-800 hover:border-emerald-500/40 transition space-y-2">\n                    <div class="flex justify-between gap-2"><span class="text-[9px] font-bold ${tipo===\'JACKBUSCA\'?\'text-amber-300\':\'text-emerald-300\'}">${tipo}</span><span class="text-[9px] text-slate-500">${item.fecha||\'\'}</span></div>\n                    <p class="text-xs text-slate-200 font-semibold truncate">${escapeHtml(item.partido||\'Consulta\')}</p>\n                    <p class="text-[10px] text-slate-500 truncate">${escapeHtml(String(estado))}</p>\n                    <div class="flex gap-2"><button onclick="verAnalisisGuardado(${item.id})" class="flex-1 bg-slate-800 hover:bg-violet-900/40 text-violet-300 py-1.5 rounded-lg text-[10px] font-bold">Ver análisis</button><button onclick="eliminarAnalisis(${item.id})" class="bg-slate-800 hover:bg-rose-900/40 text-rose-300 px-3 py-1.5 rounded-lg text-[10px]">Eliminar</button></div>\n                </div>`;\n            }).join(\'\');\n        }\n        function escapeHtml(value){ const div=document.createElement(\'div\'); div.textContent=value ?? \'\'; return div.innerHTML; }\n        function verAnalisisGuardado(id){\n            const item=historialActual.find(x=>x.id===id); if(!item) return;\n            const d=item.datos||{}; const box=document.getElementById(\'historial-detalle\'); box.classList.remove(\'hidden\');\n            const top=d.top_3_detallado || d.top_3_recomendaciones || [];\n            let html=`<div class="flex justify-between items-center mb-2"><b class="text-violet-300">Análisis guardado</b><button onclick="document.getElementById(\'historial-detalle\').classList.add(\'hidden\')" class="text-slate-500">✕</button></div><p class="text-slate-300"><b>Partido:</b> ${escapeHtml(item.partido)}</p><p class="text-slate-500 mt-1"><b>Fecha:</b> ${escapeHtml(item.fecha)}</p>`;\n            if(d.estado_recomendacion) html+=`<p class="mt-2 text-amber-300"><b>Estado:</b> ${escapeHtml(d.estado_recomendacion)}</p>`;\n            if(d.explicacion_recomendacion || d.explicacion) html+=`<p class="mt-2 text-slate-400">${escapeHtml(d.explicacion_recomendacion || d.explicacion)}</p>`;\n            if(top.length){ html+=\'<div class="mt-3 border-t border-slate-800 pt-2"><b class="text-emerald-300">Top / recomendaciones</b>\'; top.slice(0,3).forEach((m,i)=>{html+=`<p class="mt-1 text-slate-300">#${i+1} ${escapeHtml(m.nombre||\'Mercado\')} — ${m.probabilidad??\'N/D\'}%${m.ev!==undefined&&m.ev!==null?\' | EV \'+m.ev+\'%\':\'\'}${m.nivel?\' | \'+escapeHtml(m.nivel):\'\'}</p>`}); html+=\'</div>\';}\n            box.innerHTML=html; box.scrollIntoView({behavior:\'smooth\',block:\'nearest\'});\n        }\n        async function eliminarAnalisis(id){\n            if(!confirm(\'¿Eliminar este análisis de tu historial?\')) return;\n            try{\n                const resp=await fetch(baseUrl+\'/historial/item/\'+id,{method:\'DELETE\',headers:{\'Authorization\':\'Bearer \'+tokenJwt}});\n                const data=await resp.json(); if(!resp.ok) throw new Error(data.detail||\'No se pudo eliminar.\');\n                historialActual=historialActual.filter(x=>x.id!==id); document.getElementById(\'historial-detalle\').classList.add(\'hidden\');\n                cargarHistorial();\n            }catch(e){ alert(e.message); }\n        }\n\n        async function verificarAccesoJackBusca() {\n            const lock = document.getElementById(\'jackbusca-lock-container\');\n            const btn = document.getElementById(\'btn-ejecutar-jack\');\n            const badge = document.getElementById(\'vip-status-badge\');\n            if (!tokenJwt) {\n                badge.innerText = \'Inicia sesión 🔒\';\n                return;\n            }\n            try {\n                const resp = await fetch(baseUrl + \'/auth/me\', {headers:{\'Authorization\':\'Bearer \'+tokenJwt}});\n                const data = await resp.json();\n                if (!resp.ok) return;\n                if (data.rol === \'admin\' || (data.plan && data.plan !== \'gratis\')) {\n                    lock.classList.add(\'hidden\');\n                    btn.disabled=false;\n                    btn.className="w-full bg-amber-500 hover:bg-amber-600 text-slate-950 font-extrabold py-3 rounded-xl transition shadow-lg cursor-pointer";\n                    btn.innerText="Ejecutar Análisis JackBusca";\n                    badge.className="bg-emerald-500/10 text-emerald-400 text-[10px] font-bold px-2.5 py-1 rounded-full border border-emerald-500/20";\n                    badge.innerText=data.rol===\'admin\'?\'Acceso Administrador ✅\':\'Plan activo ✅\';\n                } else {\n                    lock.classList.remove(\'hidden\');\n                    btn.disabled=true;\n                    badge.innerText=\'Plan premium requerido 🔒\';\n                }\n            } catch(e) {}\n        }\n\n        async function cargarAdminResumen(){\n            if(!tokenJwt) return;\n            try{\n                const r=await fetch(baseUrl+\'/admin/resumen\',{headers:{\'Authorization\':\'Bearer \'+tokenJwt}});\n                const d=await r.json(); if(!r.ok) throw new Error(d.detail||\'Sin acceso\');\n                document.getElementById(\'admin-stats\').innerHTML=`<div class="bg-slate-950 rounded-lg p-2">👥 Usuarios <b class="text-white">${d.usuarios}</b></div><div class="bg-slate-950 rounded-lg p-2">🟢 Activos <b class="text-white">${d.activos}</b></div><div class="bg-slate-950 rounded-lg p-2">⭐ Premium <b class="text-white">${d.premium}</b></div><div class="bg-slate-950 rounded-lg p-2">💳 Pendientes <b class="text-white">${d.pagos_pendientes}</b></div>`;\n            }catch(e){document.getElementById(\'admin-stats\').innerHTML=\'<span class="text-rose-400 text-[10px]">\'+escapeHtml(e.message)+\'</span>\';}\n        }\n        function toggleAdminPanel(){ const p=document.getElementById(\'admin-panel\'); p.classList.toggle(\'hidden\'); if(!p.classList.contains(\'hidden\')){ cargarAdminResumen(); cargarAdminUsuarios(); cargarAdminPagos(); } }\n        async function cargarAdminUsuarios(){\n            const box=document.getElementById(\'admin-users-list\'); if(!box) return; box.innerHTML=\'<p class="text-slate-500 text-xs">Cargando...</p>\';\n            try{const q=document.getElementById(\'admin-user-search\').value.trim(); const r=await fetch(baseUrl+\'/admin/usuarios?q=\'+encodeURIComponent(q),{headers:{\'Authorization\':\'Bearer \'+tokenJwt}}); const d=await r.json(); if(!r.ok) throw new Error(d.detail||\'Sin acceso\');\n                box.innerHTML=(d.usuarios||[]).map(u=>`<div class="bg-slate-950 border border-slate-800 rounded-xl p-3 space-y-1"><div class="flex justify-between"><b class="text-emerald-300">${escapeHtml(u.usuario)}</b><span class="text-[9px] text-violet-300">${escapeHtml(u.rol||\'usuario\')}</span></div><div class="text-[10px] text-slate-400">${escapeHtml(u.correo)}</div><div class="text-[10px] text-slate-500">Plan: ${escapeHtml(u.plan)} · ${u.activo?\'Activo\':\'Suspendido\'} · ${u.email_verificado?\'Verificado\':\'No verificado\'}</div><button onclick="verAdminUsuario(${u.id})" class="mt-1 bg-slate-800 hover:bg-violet-900/30 text-violet-300 px-3 py-1.5 rounded-lg text-[10px] font-bold">Ver detalle</button></div>`).join(\'\') || \'<p class="text-slate-500 text-xs">No hay usuarios.</p>\';\n            }catch(e){box.innerHTML=\'<p class="text-rose-400 text-xs">\'+escapeHtml(e.message)+\'</p>\';}\n        }\n        async function verAdminUsuario(id){\n            const box=document.getElementById(\'admin-user-detail\'); box.classList.remove(\'hidden\'); box.innerHTML=\'Cargando detalle...\';\n            try{const r=await fetch(baseUrl+\'/admin/usuarios/\'+id,{headers:{\'Authorization\':\'Bearer \'+tokenJwt}}); const d=await r.json(); if(!r.ok) throw new Error(d.detail); const u=d.usuario;\n                const pagos=(d.pagos||[]).map(p=>`<p class="text-[10px] text-slate-400">${escapeHtml(p.estado)} · ${escapeHtml(p.plan)} · $${Number(p.monto).toLocaleString(\'es-CO\')} · ${escapeHtml(p.referencia)}</p>`).join(\'\') || \'<p class="text-[10px] text-slate-500">Sin pagos.</p>\';\n                box.innerHTML=`<div><b class="text-violet-300">${escapeHtml(u.usuario)}</b><div class="text-slate-400">${escapeHtml(u.correo)}</div><div class="mt-2 text-slate-400">Rol: <b>${escapeHtml(u.rol||\'usuario\')}</b> · Plan: <b>${escapeHtml(u.plan)}</b> · Estado: <b>${u.activo?\'ACTIVO\':\'SUSPENDIDO\'}</b></div><div class="mt-3 flex flex-wrap gap-2"><button onclick="cambiarEstadoAdmin(${u.id},\'ACTIVO\')" class="bg-emerald-700 px-2 py-1 rounded text-[10px]">Activar</button><button onclick="cambiarEstadoAdmin(${u.id},\'SUSPENDIDO\')" class="bg-rose-800 px-2 py-1 rounded text-[10px]">Suspender</button><button onclick="cambiarRolAdmin(${u.id},\'admin\')" class="bg-violet-700 px-2 py-1 rounded text-[10px]">Dar admin</button></div><div class="mt-3 border-t border-slate-800 pt-3"><b class="text-amber-300">Activar plan por Nequi</b><div class="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2"><select id="admin-plan-${u.id}" class="bg-slate-900 border border-slate-700 rounded-lg p-2 text-[10px]"><option value="1_mes">1 mes</option><option value="3_meses">3 meses</option><option value="12_meses">1 año</option></select><input id="admin-ref-${u.id}" placeholder="Referencia Nequi" class="bg-slate-900 border border-slate-700 rounded-lg p-2 text-[10px]"></div><button onclick="activarPlanAdmin(${u.id})" class="w-full mt-2 bg-amber-500 text-slate-950 font-extrabold px-3 py-2 rounded-lg text-[10px]">Confirmar pago y activar</button></div><div class="mt-3 border-t border-slate-800 pt-2"><b class="text-slate-300">Pagos</b>${pagos}</div></div>`;\n            }catch(e){box.innerHTML=\'<span class="text-rose-400">\'+escapeHtml(e.message)+\'</span>\';}\n        }\n        async function cambiarEstadoAdmin(id,estado){const r=await fetch(baseUrl+\'/admin/usuarios/\'+id+\'/estado?estado=\'+encodeURIComponent(estado),{method:\'POST\',headers:{\'Authorization\':\'Bearer \'+tokenJwt}});const d=await r.json();if(!r.ok)return alert(d.detail||\'Error\');cargarAdminUsuarios();cargarAdminResumen();}\n        async function cambiarRolAdmin(id,rol){const r=await fetch(baseUrl+\'/admin/usuarios/\'+id+\'/rol?rol=\'+encodeURIComponent(rol),{method:\'POST\',headers:{\'Authorization\':\'Bearer \'+tokenJwt}});const d=await r.json();if(!r.ok)return alert(d.detail||\'Error\');cargarAdminUsuarios();}\n        async function activarPlanAdmin(id){const plan=document.getElementById(\'admin-plan-\'+id).value;const referencia=document.getElementById(\'admin-ref-\'+id).value.trim();if(!confirm(\'Confirma que recibiste el pago por Nequi.\'))return;const r=await fetch(baseUrl+\'/admin/usuarios/\'+id+\'/activar-plan\',{method:\'POST\',headers:{\'Authorization\':\'Bearer \'+tokenJwt,\'Content-Type\':\'application/json\'},body:JSON.stringify({tipo_plan:plan,referencia_pago:referencia})});const d=await r.json();if(!r.ok)return alert(d.detail||\'Error\');alert(\'Plan activado hasta \'+new Date(d.fecha_expiracion).toLocaleString());cargarAdminUsuarios();cargarAdminResumen();cargarAdminPagos();}\n        async function cargarAdminPagos(){const box=document.getElementById(\'admin-pagos\');if(!box||!tokenJwt)return;try{const r=await fetch(baseUrl+\'/admin/pagos\',{headers:{\'Authorization\':\'Bearer \'+tokenJwt}});const d=await r.json();if(!r.ok)throw new Error(d.detail||\'Sin acceso\');box.innerHTML=(d.pagos||[]).map(p=>`<div class="bg-slate-950 border border-slate-800 rounded-xl p-3 space-y-1"><div class="flex justify-between"><b class="text-xs">${escapeHtml(p.usuario)}</b><span class="text-[9px]">${escapeHtml(p.estado)}</span></div><div class="text-[10px] text-slate-400">${escapeHtml(p.plan)} · $${Number(p.monto).toLocaleString(\'es-CO\')}</div><div class="text-[9px] text-slate-500">${escapeHtml(p.referencia)}</div>${p.estado===\'PENDING\'?`<div class="flex gap-2 pt-2"><button onclick="resolverPago(${p.id},true)" class="flex-1 bg-emerald-500 text-slate-950 font-bold py-1.5 rounded-lg text-[10px]">Aprobar</button><button onclick="resolverPago(${p.id},false)" class="bg-rose-950/40 text-rose-300 border border-rose-900 px-3 rounded-lg text-[10px]">Rechazar</button></div>`:\'\'}</div>`).join(\'\')||\'<p class="text-[10px] text-slate-500">No hay solicitudes.</p>\';}catch(e){box.innerHTML=\'<p class="text-[10px] text-rose-400">\'+escapeHtml(e.message)+\'</p>\';}}\n        async function resolverPago(id,aprobar){const nota=prompt(aprobar?\'Nota opcional de aprobación:\':\'Motivo del rechazo:\',\'\')??\'\';const r=await fetch(baseUrl+\'/admin/pagos/\'+id+\'/\'+(aprobar?\'aprobar\':\'rechazar\'),{method:\'POST\',headers:{\'Content-Type\':\'application/json\',\'Authorization\':\'Bearer \'+tokenJwt},body:JSON.stringify({nota})});const d=await r.json();if(!r.ok)return alert(d.detail||\'Error\');alert(d.mensaje||\'Listo\');cargarAdminResumen();cargarAdminPagos();cargarAdminUsuarios();}\n        async function cargarPlanes(){const box=document.getElementById(\'planes-lista\');if(!box)return;try{const r=await fetch(baseUrl+\'/planes\');const d=await r.json();box.innerHTML=Object.entries(d.planes||{}).map(([id,p])=>`<button onclick="solicitarPago(\'${id}\')" class="w-full text-left bg-slate-900 border border-slate-800 hover:border-amber-500/50 rounded-lg p-2"><div class="flex justify-between"><b class="text-amber-300">${escapeHtml(p.nombre)}</b><b class="text-emerald-300">$${Number(p.precio_total).toLocaleString(\'es-CO\')}</b></div></button>`).join(\'\');}catch(e){box.innerHTML=\'<p class="text-rose-400 text-[10px]">No se pudieron cargar los planes.</p>\';}}\n        async function solicitarPago(planId){if(!tokenJwt)return;const msg=document.getElementById(\'pago-msg\');try{const r=await fetch(baseUrl+\'/pagos/solicitar\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\',\'Authorization\':\'Bearer \'+tokenJwt},body:JSON.stringify({tipo_plan:planId})});const d=await r.json();if(!r.ok)throw new Error(d.detail||\'No se pudo registrar\');msg.classList.remove(\'hidden\');msg.className=\'text-[10px] text-amber-300 bg-amber-500/5 border border-amber-500/20 rounded-xl p-2\';msg.innerHTML=\'<b>Solicitud registrada</b><br>Paga al <b>3007033243</b><br>Referencia: \'+escapeHtml(d.referencia)+\'<br>Total: $\'+Number(d.monto).toLocaleString(\'es-CO\')+\' COP\';cargarMisPagos();}catch(e){msg.classList.remove(\'hidden\');msg.className=\'text-[10px] text-rose-300 bg-rose-500/5 border border-rose-500/20 rounded-xl p-2\';msg.textContent=e.message;}}\n        async function cargarMisPagos(){const box=document.getElementById(\'mis-pagos\');if(!box||!tokenJwt)return;try{const r=await fetch(baseUrl+\'/pagos/mis-pagos\',{headers:{\'Authorization\':\'Bearer \'+tokenJwt}});const d=await r.json();if(!r.ok)return;const lista=d.pagos||[];box.innerHTML=\'<b class="text-slate-300">Mis solicitudes</b>\'+(lista.length?\'<br>\'+lista.slice(0,5).map(p=>escapeHtml(p.estado)+\' · \'+escapeHtml(p.plan)+\' · $\'+Number(p.monto).toLocaleString(\'es-CO\')).join(\'<br>\'):\'<br>Sin solicitudes.\');}catch(e){}}\n\nasync function consultarGoles() {\n            const l = document.getElementById(\'c_local\').value;\n            const e = document.getElementById(\'c_empate\').value;\n            const v = document.getElementById(\'c_visitante\').value;\n            const m25 = document.getElementById(\'c_mas25\').value;\n            const u25 = document.getElementById(\'c_menos25\').value;\n            const m35 = document.getElementById(\'c_mas35\').value;\n            const u35 = document.getElementById(\'c_menos35\').value;\n            \n            const bttsSi = document.getElementById(\'c_btts_si\').value;\n            const bttsNo = document.getElementById(\'c_btts_no\').value;\n\n            const casaLocal = document.getElementById(\'c_casa_local\').value;\n            const casaEmpate = document.getElementById(\'c_casa_empate\').value;\n            const casaVisitante = document.getElementById(\'c_casa_visitante\').value;\n            const casaM25 = document.getElementById(\'c_casa_mas25\').value;\n            const casaU25 = document.getElementById(\'c_casa_menos25\').value;\n            const casaM35 = document.getElementById(\'c_casa_mas35\').value;\n            const casaU35 = document.getElementById(\'c_casa_menos35\').value;\n            const casaBttsSi = document.getElementById(\'c_casa_btts_si\').value;\n            const casaBttsNo = document.getElementById(\'c_casa_btts_no\').value;\n\n            let url = baseUrl + \'/analisis/partido?cuota_local=\' + l + \'&cuota_empate=\' + e + \'&cuota_visitante=\' + v + \'&cuota_mas_25_goles=\' + m25 + \'&cuota_menos_25_goles=\' + u25 + \'&cuota_mas_35_goles=\' + m35 + \'&cuota_menos_35_goles=\' + u35;\n            \n            if (bttsSi) url += \'&cuota_btts_si=\' + bttsSi;\n            if (bttsNo) url += \'&cuota_btts_no=\' + bttsNo;\n\n            if (casaLocal) url += \'&casa_local=\' + casaLocal;\n            if (casaEmpate) url += \'&casa_empate=\' + casaEmpate;\n            if (casaVisitante) url += \'&casa_visitante=\' + casaVisitante;\n            if (casaM25) url += \'&casa_mas_25=\' + casaM25;\n            if (casaU25) url += \'&casa_menos_25=\' + casaU25;\n            if (casaM35) url += \'&casa_mas_35=\' + casaM35;\n            if (casaU35) url += \'&casa_menos_35=\' + casaU35;\n            if (casaBttsSi) url += \'&casa_btts_si=\' + casaBttsSi;\n            if (casaBttsNo) url += \'&casa_btts_no=\' + casaBttsNo;\n\n            const contenedor = document.getElementById(\'resultado-goles\');\n            contenedor.innerHTML = \'<p class="col-span-3 text-center text-emerald-400 animate-pulse py-2 font-bold">Calculando 1X2, Goles y BTTS...</p>\';\n            contenedor.classList.remove(\'hidden\');\n\n            try {\n                let options = {};\n                if (tokenJwt) {\n                    options.headers = { \'Authorization\': \'Bearer \' + tokenJwt };\n                }\n                let resp = await fetch(url, options);\n                let datos = await resp.json();\n\n                let html = \'\';\n                html += \'<div class="bg-slate-800 p-4 rounded-xl border border-slate-700">\';\n                html += \'<h3 class="font-bold text-emerald-400 mb-2">Probabilidades 1X2</h3>\';\n                html += \'<p>Local (1): <b>\' + datos.probabilidades_1x2_simuladas.local + \'</b></p>\';\n                html += \'<p>Empate (X): <b>\' + datos.probabilidades_1x2_simuladas.empate + \'</b></p>\';\n                html += \'<p>Visitante (2): <b>\' + datos.probabilidades_1x2_simuladas.visitante + \'</b></p>\';\n                html += \'</div>\';\n\n                html += \'<div class="bg-slate-800 p-4 rounded-xl border border-slate-700">\';\n                const estadoRec = datos.estado_recomendacion || \'SIN EVALUAR\';\n                const colorEstado = estadoRec === \'HAY VALOR DETECTADO\' ? \'text-emerald-400\' : \'text-amber-300\';\n                html += \'<h3 class="font-bold \' + colorEstado + \' mb-2">Top Matemático: \' + estadoRec + \'</h3>\';\n                html += \'<p class="text-[10px] text-slate-400 mb-3">El ranking usa probabilidad analítica Poisson + Edge + Valor Esperado (EV) + confianza. Una probabilidad alta por sí sola NO convierte un mercado en recomendación.</p>\';\n                html += \'<div class="bg-slate-950/60 rounded-lg p-3 mb-3 border border-slate-700">\';\n                html += \'<p class="text-xs text-slate-300"><b class="text-violet-300">¿Por qué?</b> \' + (datos.explicacion_recomendacion || \'\') + \'</p>\';\n                html += \'</div>\';\n                html += \'<ul class="list-disc list-inside text-sm space-y-2 text-emerald-300 font-semibold">\';\n                if(datos.top_3_detallado && datos.top_3_detallado.length) {\n                    datos.top_3_detallado.forEach(function(m, i) {\n                        html += \'<li><b>\' + (i + 1) + \'. \' + m.nombre + \'</b> — Modelo \' + m.probabilidad + \'% | Pinnacle \' + Number(m.cuota_pinnacle).toFixed(2) + \' | Casa \' + Number(m.cuota_casa).toFixed(2) + \' | Edge \' + (m.edge >= 0 ? \'+\' : \'\') + m.edge + \'% | EV \' + (m.ev >= 0 ? \'+\' : \'\') + m.ev + \'% | \' + m.nivel + \'<br><span class="text-[10px] text-slate-400 font-normal">\' + m.explicacion + \'</span></li>\';\n                    });\n                } else {\n                    html += \'<li class="text-amber-300">NO RECOMENDACIÓN: ningún mercado superó los mínimos establecidos.</li>\';\n                }\n                html += \'</ul>\';\n                if(datos.top_3_candidatos && datos.top_3_candidatos.length) {\n                    html += \'<div class="mt-3 pt-3 border-t border-slate-700">\';\n                    html += \'<p class="text-[10px] font-bold text-slate-400 mb-1">Candidatos descartados o pendientes de valor:</p>\';\n                    datos.top_3_candidatos.forEach(function(m) {\n                        if (m.accion === \'NO RECOMENDADO\') {\n                            html += \'<p class="text-[10px] text-slate-400">• \' + m.nombre + \': EV \' + (m.ev !== null && m.ev !== undefined ? ((m.ev >= 0 ? \'+\' : \'\') + m.ev + \'%\') : \'pendiente de cuota\') + \' — <span class="text-amber-300">NO RECOMENDADO</span>. \' + m.explicacion + \'</p>\';\n                        }\n                    });\n                    html += \'</div>\';\n                }\n                html += \'<div class="mt-3 pt-3 border-t border-slate-700 text-[10px] text-slate-400">\';\n                html += \'<b>Regla:</b> EV = (Probabilidad del modelo × cuota) − 1. El sistema no fuerza tres apuestas cuando no existe valor suficiente.\';\n                html += \'</div>\';\n                html += \'</div>\';\n\n                html += \'<div class="bg-slate-800 p-4 rounded-xl border border-slate-700">\';\n                html += \'<h3 class="font-bold text-blue-400 mb-2">Comparación Pinnacle vs Casa</h3>\';\n                html += \'<p class="text-[10px] text-slate-400 mb-2">Pinnacle = referencia para calibrar. Casa = precio real usado para calcular EV.</p>\';\n                if (datos.top_3_detallado && datos.top_3_detallado.length) {\n                    datos.top_3_detallado.forEach(function(m) {\n                        html += \'<div class="border-t border-slate-700 pt-2 mt-2 text-xs"><b>\' + m.nombre + \'</b>: Modelo \' + m.probabilidad + \'% | Pinnacle \' + Number(m.cuota_pinnacle).toFixed(2) + \' | Casa \' + Number(m.cuota_casa).toFixed(2) + \' | Edge \' + (m.edge >= 0 ? \'+\' : \'\') + m.edge + \'% | EV \' + (m.ev >= 0 ? \'+\' : \'\') + m.ev + \'%</div>\';\n                    });\n                } else {\n                    html += \'<p class="text-xs text-amber-300">Completa las cuotas de la casa donde apuestas para calcular el valor.</p>\';\n                }\n                html += \'</div>\';\n\n                html += \'<div class="bg-slate-800 p-4 rounded-xl border border-slate-700">\';\n                html += \'<h3 class="font-bold text-blue-400 mb-2">Mercados de Goles & BTTS</h3>\';\n                html += \'<p>Más 2.5: <b>\' + datos.mercados_clave_goles["mas_de_2.5_goles"] + \'</b></p>\';\n                html += \'<p>Menos 2.5: <b>\' + datos.mercados_clave_goles["menos_de_2.5_goles"] + \'</b></p>\';\n                html += \'<p>Más 3.5: <b>\' + datos.mercados_clave_goles["mas_de_3.5_goles"] + \'</b></p>\';\n                html += \'<p>Menos 3.5: <b>\' + datos.mercados_clave_goles["menos_de_3.5_goles"] + \'</b></p>\';\n                if(datos.mercados_clave_goles["btts_si"] || datos.mercados_clave_goles["ambos_anotan_si"]) {\n                    let bttssiVal = datos.mercados_clave_goles["btts_si"] || datos.mercados_clave_goles["ambos_anotan_si"];\n                    let bttsnoVal = datos.mercados_clave_goles["btts_no"] || datos.mercados_clave_goles["ambos_anotan_no"];\n                    html += \'<p class="pt-2 border-t border-slate-700 mt-2">Ambos Anotan (Sí): <b>\' + bttssiVal + \'</b></p>\';\n                    html += \'<p>Ambos Anotan (No): <b>\' + bttsnoVal + \'</b></p>\';\n                }\n                html += \'</div>\';\n\n                if (datos.modelo) {\n                    html += \'<div class="bg-slate-800 p-4 rounded-xl border border-slate-700">\';\n                    html += \'<h3 class="font-bold text-violet-400 mb-2">Calibración del Motor</h3>\';\n                    html += \'<p>Goles esperados local: <b>\' + datos.modelo.goles_esperados_local + \'</b></p>\';\n                    html += \'<p>Goles esperados visitante: <b>\' + datos.modelo.goles_esperados_visitante + \'</b></p>\';\n                    html += \'<p class="text-[10px] text-slate-400 mt-2">\' + datos.modelo.metodo + \'</p>\';\n                    if (datos.modelo.confianza_modelo !== undefined) {\n                        html += \'<p class="text-[10px] text-slate-400 mt-1">Confianza estructural del ajuste: <b class="text-violet-300">\' + datos.modelo.confianza_modelo + \'%</b></p>\';\n                    }\n                    if (datos.btts_referencia_pinnacle && datos.btts_referencia_pinnacle.si) {\n                        html += \'<p class="pt-2 mt-2 border-t border-slate-700">BTTS vs mercado: <b>Sí \' + datos.btts_referencia_pinnacle.edge_si + \'%</b> | <b>No \' + datos.btts_referencia_pinnacle.edge_no + \'%</b></p>\';\n                    }\n                    html += \'</div>\';\n                }\n\n                contenedor.innerHTML = html;\n                if (datos.historial_info) {\n                    const h = datos.historial_info;\n                    let aviso = \'\';\n                    if (h.guardado) aviso = \'📚 Historial: \' + h.usados + \'/\' + h.limite + \' análisis guardados. Restantes: \' + h.restantes + \'.\';\n                    else if (h.motivo === \'limite_historial\') aviso = \'📚 Has alcanzado el límite de \' + h.limite + \' análisis guardados de tu plan.\';\n                    else if (h.motivo === \'invitado\') aviso = \'👤 Inicia sesión para guardar este análisis en tu historial.\';\n                    if (aviso) contenedor.innerHTML += \'<div class="mt-2 text-[10px] text-slate-400">\' + aviso + \'</div>\';\n                }\n\n                if (tokenJwt) cargarHistorial();\n\n            } catch (err) {\n                contenedor.innerHTML = \'<p class="col-span-3 text-center text-red-400 py-2">Error: \' + err + \'</p>\';\n            }\n        }\n\n        async function consultarJackBusca() {\n            const l = document.getElementById(\'c_local\').value;\n            const e = document.getElementById(\'c_empate\').value;\n            const v = document.getElementById(\'c_visitante\').value;\n            const m25 = document.getElementById(\'c_mas25\').value;\n            const u25 = document.getElementById(\'c_menos25\').value;\n            const m35 = document.getElementById(\'c_mas35\').value;\n            const u35 = document.getElementById(\'c_menos35\').value;\n            \n            const corners = document.getElementById(\'prom_corners\').value;\n            const tarjetas = document.getElementById(\'prom_tarjetas\').value;\n\n            let paramsTarjeta = {};\n            const t35s = document.getElementById(\'c_t_mas35\').value; if(t35s) paramsTarjeta[\'cuota_tarjetas_mas_35\'] = t35s;\n            const t35n = document.getElementById(\'c_t_menos35\').value; if(t35n) paramsTarjeta[\'cuota_tarjetas_menos_35\'] = t35n;\n            const t45s = document.getElementById(\'c_t_mas45\').value; if(t45s) paramsTarjeta[\'cuota_tarjetas_mas_45\'] = t45s;\n            const t45n = document.getElementById(\'c_t_menos45\').value; if(t45n) paramsTarjeta[\'cuota_tarjetas_menos_45\'] = t45n;\n            const t55s = document.getElementById(\'c_t_mas55\').value; if(t55s) paramsTarjeta[\'cuota_tarjetas_mas_55\'] = t55s;\n            const t55n = document.getElementById(\'c_t_menos55\').value; if(t55n) paramsTarjeta[\'cuota_tarjetas_menos_55\'] = t55n;\n\n            let paramsCorners = {};\n            const c75s = document.getElementById(\'c_corner_mas75\').value; if(c75s) paramsCorners[\'cuota_corners_mas_75\'] = c75s;\n            const c75n = document.getElementById(\'c_corner_menos75\').value; if(c75n) paramsCorners[\'cuota_corners_menos_75\'] = c75n;\n            const c85s = document.getElementById(\'c_corner_mas85\').value; if(c85s) paramsCorners[\'cuota_corners_mas_85\'] = c85s;\n            const c85n = document.getElementById(\'c_corner_menos85\').value; if(c85n) paramsCorners[\'cuota_corners_menos_85\'] = c85n;\n            const c95s = document.getElementById(\'c_corner_mas95\').value; if(c95s) paramsCorners[\'cuota_corners_mas_95\'] = c95s;\n            const c95n = document.getElementById(\'c_corner_menos95\').value; if(c95n) paramsCorners[\'cuota_corners_menos_95\'] = c95n;\n            const c105s = document.getElementById(\'c_corner_mas105\').value; if(c105s) paramsCorners[\'cuota_corners_mas_105\'] = c105s;\n            const c105n = document.getElementById(\'c_corner_menos105\').value; if(c105n) paramsCorners[\'cuota_corners_menos_105\'] = c105n;\n\n            let urlObj = new URL(baseUrl + \'/jackbusca/partido\');\n            urlObj.searchParams.append(\'cuota_local\', l);\n            urlObj.searchParams.append(\'cuota_empate\', e);\n            urlObj.searchParams.append(\'cuota_visitante\', v);\n            urlObj.searchParams.append(\'cuota_mas_25_goles\', m25);\n            urlObj.searchParams.append(\'cuota_menos_25_goles\', u25);\n            urlObj.searchParams.append(\'cuota_mas_35_goles\', m35);\n            urlObj.searchParams.append(\'cuota_menos_35_goles\', u35);\n            if (tarjetas) urlObj.searchParams.append(\'promedio_tarjetas_arbitro\', tarjetas);\n            if (corners) urlObj.searchParams.append(\'promedio_esperado_corners\', corners);\n\n            for (const [key, value] of Object.entries(paramsTarjeta)) {\n                urlObj.searchParams.append(key, value);\n            }\n            for (const [key, value] of Object.entries(paramsCorners)) {\n                urlObj.searchParams.append(key, value);\n            }\n\n            const casaJack = {\n                casa_tarjetas_mas_35: document.getElementById(\'casa_t_mas35\').value, casa_tarjetas_menos_35: document.getElementById(\'casa_t_menos35\').value,\n                casa_tarjetas_mas_45: document.getElementById(\'casa_t_mas45\').value, casa_tarjetas_menos_45: document.getElementById(\'casa_t_menos45\').value,\n                casa_tarjetas_mas_55: document.getElementById(\'casa_t_mas55\').value, casa_tarjetas_menos_55: document.getElementById(\'casa_t_menos55\').value,\n                casa_corners_mas_75: document.getElementById(\'casa_c_mas75\').value, casa_corners_menos_75: document.getElementById(\'casa_c_menos75\').value,\n                casa_corners_mas_85: document.getElementById(\'casa_c_mas85\').value, casa_corners_menos_85: document.getElementById(\'casa_c_menos85\').value,\n                casa_corners_mas_95: document.getElementById(\'casa_c_mas95\').value, casa_corners_menos_95: document.getElementById(\'casa_c_menos95\').value,\n                casa_corners_mas_105: document.getElementById(\'casa_c_mas105\').value, casa_corners_menos_105: document.getElementById(\'casa_c_menos105\').value\n            };\n            for (const [key, value] of Object.entries(casaJack)) {\n                if (value) urlObj.searchParams.append(key, value);\n            }\n            \n            const contenedor = document.getElementById(\'resultado-jack\');\n            contenedor.innerHTML = \'<p class="col-span-2 text-center text-amber-400 animate-pulse py-2 font-bold">Calculando JackBusca completo...</p>\';\n            contenedor.classList.remove(\'hidden\');\n\n            try {\n                let options = {};\n                if (tokenJwt) {\n                    options.headers = { \'Authorization\': \'Bearer \' + tokenJwt };\n                }\n                let resp = await fetch(urlObj.toString(), options);\n                let datos = await resp.json();\n\n                let html = \'\';\n                \n                html += \'<div class="bg-slate-800 p-4 rounded-xl border border-slate-700 space-y-2">\';\n                html += \'<h3 class="font-bold text-amber-400 border-b border-slate-700 pb-1">Tarjetas (Árbitro: \' + (datos.arbitraje?.promedio_tarjetas_referencia || tarjetas) + \')</h3>\';\n                if (datos.mercados_tarjetas_explicados) {\n                    for (let linea in datos.mercados_tarjetas_explicados) {\n                        html += \'<p class="text-sm capitalize">\' + linea.replace(/_/g, \' \') + \': <b class="text-emerald-400">\' + datos.mercados_tarjetas_explicados[linea] + \'</b></p>\';\n                    }\n                } else {\n                    html += \'<p class="text-xs text-slate-400">Sin datos de tarjetas devueltos.</p>\';\n                }\n                html += \'</div>\';\n\n                html += \'<div class="bg-slate-800 p-4 rounded-xl border border-slate-700 space-y-3">\';\n                html += \'<h3 class="font-bold text-amber-400 border-b border-slate-700 pb-1">Córners por Línea (Base: \' + corners + \')</h3>\';\n                \n                if (datos.mercados_tiros_de_esquina) {\n                    let masCorners = datos.mercados_tiros_de_esquina.mas_de || {};\n                    let menosCorners = datos.mercados_tiros_de_esquina.menos_de || {};\n\n                    html += \'<div class="grid grid-cols-2 gap-4 text-xs">\';\n                    html += \'<div><span class="text-amber-300 font-bold block mb-1">Más de (...)</span>\';\n                    for (let linea in masCorners) {\n                        html += \'<p class="py-0.5">Más \' + linea + \': <span class="text-emerald-400 font-bold">\' + masCorners[linea] + \'</span></p>\';\n                    }\n                    html += \'</div>\';\n\n                    html += \'<div><span class="text-amber-300 font-bold block mb-1">Menos de (...)</span>\';\n                    for (let linea in menosCorners) {\n                        html += \'<p class="py-0.5">Menos \' + linea + \': <span class="text-rose-400 font-bold">\' + menosCorners[linea] + \'</span></p>\';\n                    }\n                    html += \'</div>\';\n                    html += \'</div>\';\n                }\n                html += \'</div>\';\n\n                if (datos.estado_recomendacion) {\n                    html += \'<div class="md:col-span-2 bg-slate-950 border border-amber-500/30 p-4 rounded-xl">\';\n                    html += \'<h3 class="font-bold text-amber-300">\' + datos.estado_recomendacion + \'</h3>\';\n                    html += \'<p class="text-xs text-slate-300 mt-1">\' + (datos.explicacion || \'\') + \'</p>\';\n                    if (datos.top_3_recomendaciones && datos.top_3_recomendaciones.length) {\n                        html += \'<div class="mt-3 space-y-2"><b class="text-emerald-400 text-xs">Top JackBusca</b>\';\n                        datos.top_3_recomendaciones.forEach((m,i)=> { html += \'<p class="text-xs">#\'+(i+1)+\' \'+m.nombre+\' — \'+m.probabilidad+\'% | EV \'+(m.ev ?? \'N/D\')+\'% | \'+m.nivel+\'</p>\'; });\n                        html += \'</div>\';\n                    }\n                    html += \'</div>\';\n                }\n                contenedor.innerHTML = html;\n                if (tokenJwt) cargarHistorial();\n            } catch (err) {\n                contenedor.innerHTML = \'<p class="col-span-2 text-center text-red-400 py-2">Error de conexión: \' + err + \'</p>\';\n            }\n        }\n    </script>\n</body>\n</html>')

# --- RUTA 1: FASE SUPERIOR ---
@app.get("/analisis/partido")
def analizar_partido(
    request: Request,
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

        usuario_actual = _optional_user(request)
        historial_info = _save_analysis_if_allowed(usuario_actual, "Motor Principal | Análisis de partido", sim)

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
            "estado": "Simulación completada con éxito (50k escenarios + Poisson calibrado)",
            "historial_info": historial_info
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
    request: Request,
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
        _require_premium(request)
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

        usuario_actual = _optional_user(request)
        historial_info = _save_analysis_if_allowed(
            usuario_actual,
            "JackBusca | Tarjetas y Córners",
            {"arbitraje": {"lambda_tarjetas": lam_t, "fuente": fuente_t}, "corners": {"lambda_total": lam_c, "fuente": fuente_c}, "top_3_recomendaciones": recomendables[:3], "estado_recomendacion": 'HAY VALOR DETECTADO' if recomendables else 'NO RECOMENDACIÓN'}
        )

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
            'escenarios': 50000,
            'historial_info': historial_info
        }
    except Exception as e:
        return {'error': f'Error en JackBusca: {str(e)}'}

