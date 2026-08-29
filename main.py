rom fastapi import FastAPI, HTTPException, Depends
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
    version="9.0.0"
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
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://api-futbol-web.vercel.app")
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

def _get_user_from_token(token: str):
    if not token:
        return None
    conn = _db()
    row = conn.execute("SELECT u.id,u.usuario,u.correo,u.plan,u.fecha_expiracion,u.email_verificado,s.expires_at FROM sesiones s JOIN usuarios u ON u.id=s.usuario_id WHERE s.token=?", (token,)).fetchone()
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
    return {"id": row["id"], "usuario": row["usuario"], "correo": row["correo"], "plan": plan, "fecha_expiracion": row["fecha_expiracion"], "email_verificado": bool(row["email_verificado"])}

def _optional_user(request: Request):
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    return _get_user_from_token(token) if token else None

def _history_count(usuario: str) -> int:
    conn = _db()
    row = conn.execute("SELECT COUNT(*) AS c FROM historial WHERE usuario=?", (usuario,)).fetchone()
    conn.close()
    return int(row["c"] or 0)

def _is_admin(user) -> bool:
    return bool(user and ADMIN_EMAIL and user.get("correo", "").lower() == ADMIN_EMAIL.lower())


def _save_analysis_if_allowed(user, partido_resumen: str, datos: dict):
    if not user:
        return {"guardado": False, "motivo": "invitado"}
    limite = PREMIUM_HISTORY_LIMIT if user["plan"] in PLANS or _is_admin(user) else FREE_HISTORY_LIMIT
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
    if user["plan"] not in PLANS and not _is_admin(user):
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
        wompi_id TEXT, comprobante TEXT, notas_admin TEXT, creado_en TEXT NOT NULL, actualizado_en TEXT NOT NULL
    )""")
    pago_cols = [r[1] for r in cursor.execute("PRAGMA table_info(pagos)").fetchall()]
    if "comprobante" not in pago_cols:
        cursor.execute("ALTER TABLE pagos ADD COLUMN comprobante TEXT")
    if "notas_admin" not in pago_cols:
        cursor.execute("ALTER TABLE pagos ADD COLUMN notas_admin TEXT")
    conn.commit()
    conn.close()

inicializar_db()


def inicializar_admin():
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return
    email = ADMIN_EMAIL.strip().lower()
    conn = _db()
    row = conn.execute("SELECT id FROM usuarios WHERE correo=?", (email,)).fetchone()
    if row:
        conn.execute("UPDATE usuarios SET plan='admin', email_verificado=1, activo=1 WHERE id=?", (row["id"],))
        conn.commit(); conn.close(); return
    conflict = conn.execute("SELECT id FROM usuarios WHERE usuario=?", (ADMIN_USERNAME,)).fetchone()
    if conflict:
        conn.close(); raise RuntimeError("API_MASTER_ADMIN_USER ya está ocupado por otra cuenta.")
    conn.execute("INSERT INTO usuarios (usuario, correo, password, plan, fecha_expiracion, activo, email_verificado) VALUES (?, ?, ?, ?, NULL, 1, 1)",
                 (ADMIN_USERNAME, email, _password_hash(ADMIN_PASSWORD), "admin"))
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
        <a href="{FRONTEND_URL}">Ir a API Master Pro</a>
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
        <a href="{FRONTEND_URL}">Iniciar sesión</a>
    </div>
</body>
</html>
""")

@app.post("/auth/login")
def login_usuario(data: LoginSchema):
    conn = _db()
    row = conn.execute("SELECT id, usuario, correo, password, plan, fecha_expiracion, email_verificado FROM usuarios WHERE usuario = ?", (data.usuario.strip(),)).fetchone()
    if not row or not _password_verify(data.password, row["password"]):
        conn.close(); raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")
    if not row["email_verificado"]:
        conn.close(); raise HTTPException(status_code=403, detail="Debes verificar tu correo antes de iniciar sesión.")
    if not row["password"].startswith("pbkdf2$"):
        conn.execute("UPDATE usuarios SET password=? WHERE id=?", (_password_hash(data.password), row["id"]))
    token = _new_session(); now=datetime.now(); exp=now+timedelta(days=SESSION_DAYS)
    conn.execute("INSERT INTO sesiones(token,usuario_id,creado_en,expires_at) VALUES(?,?,?,?)", (token,row["id"],now.isoformat(),exp.isoformat()))
    conn.commit(); conn.close()
    return {"mensaje":"Login exitoso","token":token,"usuario":row["usuario"],"correo":row["correo"],"plan":row["plan"],"fecha_expiracion":row["fecha_expiracion"],"email_verificado":True,"es_admin":bool(ADMIN_EMAIL and row["correo"].lower() == ADMIN_EMAIL.lower())}

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
    return {"planes":salida,"moneda":"COP"}

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

@app.post("/pagos/solicitar")
def solicitar_pago(data: SolicitarPagoSchema, user=Depends(_current_user)):
    if data.tipo_plan not in PLANS:
        raise HTTPException(status_code=400, detail="Plan no válido.")
    amount, base, tax = _plan_amount(data.tipo_plan)
    reference = f"AMP-NEQUI-{user['id']}-{secrets.token_hex(5).upper()}"
    now = datetime.now().isoformat()
    conn = _db()
    conn.execute("INSERT INTO pagos(referencia,usuario,plan,monto,moneda,estado,comprobante,wompi_id,creado_en,actualizado_en) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (reference,user['usuario'],data.tipo_plan,amount,'COP','PENDING',None,None,now,now))
    conn.commit(); conn.close()
    return {"ok":True,"referencia":reference,"plan":data.tipo_plan,"precio_base":base,"iva":tax,"monto":amount,"moneda":"COP","estado":"PENDING","contacto_nequi":NEQUI_NUMBER,
            "mensaje":"Realiza el pago por Nequi al 3007033243 y envía el comprobante al administrador. El plan se activa después de verificar el pago."}


@app.get("/pagos/mis-pagos")
def mis_pagos(user=Depends(_current_user)):
    conn=_db()
    rows=conn.execute("SELECT referencia,plan,monto,moneda,estado,comprobante,creado_en,actualizado_en FROM pagos WHERE usuario=? ORDER BY id DESC",(user['usuario'],)).fetchall()
    conn.close()
    return {"pagos":[dict(r) for r in rows]}


def _sync_expired_plans():
    """Marca como gratis los planes cuyo vencimiento ya pasó."""
    conn = _db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        UPDATE usuarios
        SET plan='gratis', fecha_expiracion=fecha_expiracion
        WHERE plan NOT IN ('gratis','admin')
          AND fecha_expiracion IS NOT NULL
          AND datetime(fecha_expiracion) <= datetime(?)
    """, (now,))
    conn.commit()
    conn.close()


@app.get("/admin/resumen")
def admin_resumen(user=Depends(_current_user)):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Acceso de administrador requerido.")
    _sync_expired_plans()
    conn=_db()
    usuarios=conn.execute("SELECT COUNT(*) c FROM usuarios").fetchone()['c']
    premium=conn.execute("SELECT COUNT(*) c FROM usuarios WHERE plan != 'gratis' AND plan != 'admin'").fetchone()['c']
    pagos=conn.execute("SELECT COUNT(*) c FROM pagos WHERE estado='APPROVED'").fetchone()['c']
    pendientes=conn.execute("SELECT COUNT(*) c FROM pagos WHERE estado='PENDING'").fetchone()['c']
    conn.close()
    return {"usuarios":usuarios,"premium":premium,"pagos_aprobados":pagos,"pagos_pendientes":pendientes}


@app.get("/admin/usuarios")
def admin_usuarios(buscar: str = "", user=Depends(_current_user)):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Acceso de administrador requerido.")
    _sync_expired_plans()
    q = f"%{buscar.strip()}%"
    conn = _db()
    rows = conn.execute("""
        SELECT u.id, u.usuario, u.correo, u.plan, u.fecha_expiracion,
               u.activo, u.email_verificado,
               CASE
                 WHEN u.plan='admin' THEN 'ADMIN'
                 WHEN u.plan='gratis' AND u.fecha_expiracion IS NOT NULL AND datetime(u.fecha_expiracion) <= datetime('now') THEN 'EXPIRED'
                 WHEN u.plan='gratis' THEN 'FREE'
                 ELSE 'ACTIVE'
               END AS estado_plan,
               (SELECT COUNT(*) FROM historial h WHERE h.usuario=u.usuario) AS historial_count,
               (SELECT COUNT(*) FROM pagos p WHERE p.usuario=u.usuario AND p.estado='PENDING') AS pagos_pendientes
        FROM usuarios u
        WHERE u.usuario LIKE ? OR u.correo LIKE ?
        ORDER BY u.id DESC
        LIMIT 100
    """, (q, q)).fetchall()
    conn.close()
    return {"usuarios": [dict(r) for r in rows]}

@app.get("/admin/usuarios/{usuario}")
def admin_detalle_usuario(usuario: str, user=Depends(_current_user)):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Acceso de administrador requerido.")
    conn = _db()
    row = conn.execute("""
        SELECT id, usuario, correo, plan, fecha_expiracion, activo, email_verificado
        FROM usuarios WHERE usuario=?
    """, (usuario,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    pagos = conn.execute("""
        SELECT referencia, plan, monto, moneda, estado, notas_admin, creado_en, actualizado_en
        FROM pagos WHERE usuario=? ORDER BY id DESC LIMIT 25
    """, (usuario,)).fetchall()
    historial = conn.execute("""
        SELECT id, fecha, partido_resumen FROM historial
        WHERE usuario=? ORDER BY id DESC LIMIT 20
    """, (usuario,)).fetchall()
    conn.close()
    return {
        "usuario": dict(row),
        "pagos": [dict(r) for r in pagos],
        "historial": [dict(r) for r in historial]
    }

@app.post("/admin/usuarios/{usuario}/desactivar")
def admin_desactivar_plan(usuario: str, user=Depends(_current_user)):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Acceso de administrador requerido.")
    conn = _db()
    row = conn.execute("SELECT id, plan, fecha_expiracion FROM usuarios WHERE usuario=?", (usuario,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if row["plan"] == "admin":
        conn.close()
        raise HTTPException(status_code=400, detail="La cuenta administradora no se puede desactivar desde aquí.")
    conn.execute("UPDATE usuarios SET plan='gratis', fecha_expiracion=NULL WHERE id=?", (row["id"],))
    conn.execute("DELETE FROM sesiones WHERE usuario_id=?", (row["id"],))
    conn.commit(); conn.close()
    return {"ok": True, "mensaje": "Plan desactivado. El usuario conserva su cuenta e historial.", "usuario": usuario, "plan": "gratis", "fecha_expiracion": row["fecha_expiracion"]}

class AdminActivarPlanSchema(BaseModel):
    tipo_plan: str
    nota: str = ""

@app.post("/admin/usuarios/{usuario}/activar")
def admin_activar_plan(usuario: str, data: AdminActivarPlanSchema, user=Depends(_current_user)):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Acceso de administrador requerido.")
    if data.tipo_plan not in PLANS:
        raise HTTPException(status_code=400, detail="Plan no válido.")
    expiration = _activate_plan_by_username(usuario, data.tipo_plan)
    return {
        "ok": True,
        "mensaje": "Plan activado manualmente.",
        "usuario": usuario,
        "plan": data.tipo_plan,
        "fecha_expiracion": expiration.strftime('%Y-%m-%d %H:%M:%S'),
        "nota": data.nota.strip()
    }

@app.get("/admin/pagos")
def admin_pagos(user=Depends(_current_user)):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Acceso de administrador requerido.")
    conn=_db()
    rows=conn.execute("SELECT id,referencia,usuario,plan,monto,moneda,estado,comprobante,notas_admin,creado_en,actualizado_en FROM pagos ORDER BY id DESC").fetchall()
    conn.close()
    return {"pagos":[dict(r) for r in rows]}

class AdminPagoSchema(BaseModel):
    nota: str = ""

@app.post("/admin/pagos/{pago_id}/aprobar")
def admin_aprobar_pago(pago_id:int, data:AdminPagoSchema=None, user=Depends(_current_user)):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Acceso de administrador requerido.")
    conn=_db(); row=conn.execute("SELECT id,usuario,plan,estado FROM pagos WHERE id=?",(pago_id,)).fetchone()
    if not row:
        conn.close(); raise HTTPException(status_code=404, detail="Pago no encontrado.")
    if row['estado']=='APPROVED':
        conn.close(); return {"ok":True,"mensaje":"El pago ya estaba aprobado."}
    nota=(data.nota if data else "").strip()
    now=datetime.now().isoformat()
    conn.execute("UPDATE pagos SET estado='APPROVED',notas_admin=?,actualizado_en=? WHERE id=?",(nota,now,pago_id))
    conn.commit(); conn.close()
    expiration=_activate_plan_by_username(row['usuario'],row['plan'])
    return {"ok":True,"mensaje":"Pago aprobado y plan activado.","usuario":row['usuario'],"plan":row['plan'],"fecha_expiracion":expiration.strftime('%Y-%m-%d %H:%M:%S')}

@app.post("/admin/pagos/{pago_id}/rechazar")
def admin_rechazar_pago(pago_id:int, data:AdminPagoSchema=None, user=Depends(_current_user)):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Acceso de administrador requerido.")
    nota=(data.nota if data else "").strip()
    conn=_db(); row=conn.execute("SELECT id FROM pagos WHERE id=?",(pago_id,)).fetchone()
    if not row:
        conn.close(); raise HTTPException(status_code=404, detail="Pago no encontrado.")
    conn.execute("UPDATE pagos SET estado='REJECTED',notas_admin=?,actualizado_en=? WHERE id=?",(nota,datetime.now().isoformat(),pago_id))
    conn.commit(); conn.close()
    return {"ok":True,"mensaje":"Pago rechazado."}



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
    return {"mensaje": "API Master Pro - Motor Estocástico con Base de Datos e Historial Activo"}

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
    except HTTPException:
        raise
    except Exception as e:
        return {"error": f"Error en el servidor: {str(e)}"}

# ==========================================
# JACKBUSCA V3 + MOTOR UNIFICADO v9.0
# ==========================================
# OBJETIVO:
#   JackBusca genera una señal PREDICTIVA específica de córners/tarjetas.
#   EV/Edge NO decide la señal predictiva.
#   El Unificado compara el vector del Principal con el de JackBusca.
#
# COMPATIBILIDAD:
#   Se mantienen los nombres de la ruta /jackbusca/partido y sus parámetros.
#   Las claves antiguas de respuesta también se conservan.
#
# REGLA:
#   Si no hay datos suficientes, no se inventa una señal.
#   La cuota de la casa solo entra en una capa separada de valor.
# ==========================================

# Referencia estadística obtenida del dataset LaLiga de 4.180 partidos
# usado durante la calibración offline. Son PRIORS, no resultados futuros.
JACKBUSCA_LALIGA_PRIOR = {
    "corners_mean": 9.5038277512,
    "cards_mean": 4.8866028708,
}

JACK_MIN_CONFIDENCE = 65.0
JACK_HIGH_CONFIDENCE = 80.0


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
    k = int(math.floor(linea))
    return 1.0 - _poisson_cdf_leq(max(float(lam), 0.01), k)


def _ajustar_lambda_a_linea(lam_inicial, objetivos):
    """Ajusta lambda a las probabilidades O/U disponibles."""
    if not objetivos:
        return None, None
    mejor_lam, mejor_err = None, float('inf')
    for i in range(20, 251):
        lam = i / 20.0
        err = sum((_poisson_over(lam, linea) - p_over) ** 2
                  for linea, p_over in objetivos)
        if err < mejor_err:
            mejor_lam, mejor_err = lam, err
    return mejor_lam, mejor_err


def _lambda_corners_desde_mercado(lineas):
    objetivos = []
    for linea, over, under in lineas:
        po, _ = _prob_2way_opcional(over, under)
        if po is not None:
            objetivos.append((float(linea), po))
    if not objetivos:
        return None, None, 0
    lam, err = _ajustar_lambda_a_linea(JACKBUSCA_LALIGA_PRIOR["corners_mean"], objetivos)
    return lam, err, len(objetivos)


def _lambda_tarjetas_v3(promedio_arbitro, lineas):
    objetivos = []
    for linea, over, under in lineas:
        po, _ = _prob_2way_opcional(over, under)
        if po is not None:
            objetivos.append((float(linea), po))

    lam_mercado, err_mercado = _ajustar_lambda_a_linea(
        JACKBUSCA_LALIGA_PRIOR["cards_mean"], objetivos
    ) if objetivos else (None, None)

    # Si hay árbitro, se mantiene como señal fuerte.
    if promedio_arbitro is not None and promedio_arbitro > 0:
        if lam_mercado is not None:
            lam = 0.70 * float(promedio_arbitro) + 0.30 * lam_mercado
            confianza = 85.0 if len(objetivos) >= 2 else 78.0
            fuente = "PROMEDIO ÁRBITRO + MERCADO O/U"
        else:
            lam = float(promedio_arbitro)
            confianza = 70.0
            fuente = "PROMEDIO ÁRBITRO"
        return lam, confianza, fuente, err_mercado, len(objetivos)

    if lam_mercado is not None:
        # Con 3 líneas completas hay evidencia suficiente de mercado.
        confianza = 68.0 if len(objetivos) >= 3 else 58.0
        return lam_mercado, confianza, "MERCADO O/U", err_mercado, len(objetivos)

    # Fallback estadístico: solo prior de LaLiga, marcado como referencia.
    return JACKBUSCA_LALIGA_PRIOR["cards_mean"], 50.0, "PRIOR HISTÓRICO LALIGA (REFERENCIA)", None, 0


def _confianza_corners_v3(n_lineas, tiene_promedio):
    if n_lineas >= 4:
        return 75.0
    if n_lineas >= 3:
        return 68.0
    if n_lineas >= 2:
        return 65.0
    if n_lineas == 1 or tiene_promedio:
        return 58.0
    return 0.0


def _nivel_confianza_jack(conf):
    conf = float(conf)
    if conf >= 80:
        return "MUY ALTA"
    if conf >= 75:
        return "ALTA"
    if conf >= 70:
        return "MEDIA"
    if conf >= 65:
        return "BAJA"
    return "NO RECOMENDADA"


def _vector_jackbusca(mercados, confianza_corners, confianza_tarjetas):
    """Vector puro de señal; no usa EV/Edge para decidir dirección."""
    validos = [m for m in mercados if m and m.get("confianza", 0) >= JACK_MIN_CONFIDENCE]

    def best_for(prefix):
        candidatos = [m for m in validos if m["nombre"].startswith(prefix)]
        if not candidatos:
            return None
        return max(candidatos, key=lambda m: (
            m.get("confianza", 0),
            abs(float(m.get("probabilidad", 50)) - 50)
        ))

    bc = best_for("Más ")  # se reemplaza abajo por selección por mercado
    corners = [m for m in validos if "Córners" in m["nombre"]]
    cards = [m for m in validos if "Tarjetas" in m["nombre"]]

    def best(items):
        return max(items, key=lambda m: (
            m.get("confianza", 0),
            abs(float(m.get("probabilidad", 50)) - 50)
        )) if items else None

    bc = best(corners)
    bt = best(cards)

    def signal(m):
        if not m:
            return "SIN_DATOS"
        return "OVER" if m["nombre"].startswith("Más ") else "UNDER"

    actividad = []
    if bc:
        actividad.append("ALTA" if signal(bc) == "OVER" else "BAJA")
    if bt:
        actividad.append("ALTA" if signal(bt) == "OVER" else "BAJA")

    if len(actividad) == 2 and actividad[0] == actividad[1]:
        escenario = "ACTIVIDAD ALTA" if actividad[0] == "ALTA" else "ACTIVIDAD BAJA"
    elif actividad:
        escenario = "ACTIVIDAD MIXTA"
    else:
        escenario = "SIN DATOS"

    return {
        "corners": {
            "direccion": signal(bc),
            "seleccion": bc["nombre"] if bc else None,
            "linea": bc.get("linea") if bc else None,
            "confianza": bc.get("confianza") if bc else 0.0,
        },
        "tarjetas": {
            "direccion": signal(bt),
            "seleccion": bt["nombre"] if bt else None,
            "linea": bt.get("linea") if bt else None,
            "confianza": bt.get("confianza") if bt else 0.0,
        },
        "escenario_actividad": escenario,
        "confianza_global": round(
            max([x for x in [confianza_corners, confianza_tarjetas] if x is not None] or [0.0]), 1
        ),
    }


def _vector_principal(sim):
    """Vector del motor principal, independiente del EV/Edge."""
    p1, px, p2 = sim.get("p_1", 0), sim.get("p_x", 0), sim.get("p_2", 0)
    if max(p1, px, p2) < 55:
        resultado = "NEUTRO"
    elif p1 == max(p1, px, p2):
        resultado = "LOCAL"
    elif p2 == max(p1, px, p2):
        resultado = "VISITANTE"
    else:
        resultado = "EMPATE"

    goles_over = sim.get("over_25", 0)
    goles_under = sim.get("under_25", 0)
    if max(goles_over, goles_under) < 55:
        goles = "NEUTRO"
    else:
        goles = "OVER 2.5" if goles_over >= goles_under else "UNDER 2.5"

    btts = "BTTS SI" if sim.get("btts_si", 0) >= sim.get("btts_no", 0) else "BTTS NO"
    return {
        "resultado": resultado,
        "goles": goles,
        "btts": btts,
        "confianza_resultado": round(max(p1, px, p2), 1),
        "confianza_goles": round(max(goles_over, goles_under), 1),
        "confianza_btts": round(max(sim.get("btts_si", 0), sim.get("btts_no", 0)), 1),
    }


def _unificar_vectores(vector_principal, vector_jack):
    """
    Clasificación deliberadamente conservadora:
      - COMPLEMENTARIEDAD: dominios distintos, ambos con señal >=65.
      - CONFLUENCIA: además de complementariedad, el contexto apunta en la misma dirección.
      - CONTRADICCIÓN: solo si existe una dirección comparable opuesta.
      - NEUTRO: señales insuficientes.
    """
    jc = vector_jack["corners"]
    jt = vector_jack["tarjetas"]
    principal_fuerte = max(
        vector_principal.get("confianza_resultado", 0),
        vector_principal.get("confianza_goles", 0),
        vector_principal.get("confianza_btts", 0)
    ) >= JACK_MIN_CONFIDENCE
    jack_fuerte = vector_jack.get("confianza_global", 0) >= JACK_MIN_CONFIDENCE

    if not principal_fuerte and not jack_fuerte:
        return {
            "clasificacion": "NEUTRO",
            "confianza": 0.0,
            "motivo": "Ninguno de los dos vectores alcanza la confianza mínima."
        }

    # Los mercados de JackBusca son córners/tarjetas y no son directamente
    # comparables con 1X2/goles/BTTS; por eso, por defecto, su relación es complementaria.
    if principal_fuerte and jack_fuerte:
        # Actividad alta + goles Over o BTTS Sí => confluencia contextual.
        actividad = vector_jack.get("escenario_actividad")
        goles = vector_principal.get("goles")
        btts = vector_principal.get("btts")
        if actividad == "ACTIVIDAD ALTA" and (goles == "OVER 2.5" or btts == "BTTS SI"):
            return {
                "clasificacion": "CONFLUENCIA",
                "confianza": round(min(
                    vector_jack["confianza_global"],
                    max(vector_principal["confianza_goles"], vector_principal["confianza_btts"])
                ), 1),
                "motivo": "Principal proyecta mayor actividad ofensiva y JackBusca detecta actividad alta."
            }
        if actividad == "ACTIVIDAD BAJA" and (goles == "UNDER 2.5" and btts == "BTTS NO"):
            return {
                "clasificacion": "CONFLUENCIA",
                "confianza": round(min(
                    vector_jack["confianza_global"],
                    max(vector_principal["confianza_goles"], vector_principal["confianza_btts"])
                ), 1),
                "motivo": "Principal proyecta baja actividad ofensiva y JackBusca detecta actividad baja."
            }
        return {
            "clasificacion": "COMPLEMENTARIEDAD",
            "confianza": round(min(vector_jack["confianza_global"], max(
                vector_principal["confianza_resultado"],
                vector_principal["confianza_goles"],
                vector_principal["confianza_btts"]
            )), 1),
            "motivo": "Ambos motores aportan señales útiles en mercados diferentes sin contradicción directa."
        }

    return {
        "clasificacion": "NEUTRO",
        "confianza": round(max(
            vector_jack.get("confianza_global", 0),
            vector_principal.get("confianza_resultado", 0),
            vector_principal.get("confianza_goles", 0),
            vector_principal.get("confianza_btts", 0)
        ), 1),
        "motivo": "Solo uno de los motores alcanza la confianza mínima; no se fuerza una relación."
    }


def _evaluar_mercado_jack_v3(nombre, prob_modelo, cuota_ref=None, cuota_casa=None,
                             confianza=0.0, nota=''):
    if prob_modelo is None:
        return None
    conf = float(confianza)
    resultado = {
        "nombre": nombre,
        "probabilidad": round(float(prob_modelo), 1),
        "cuota_pinnacle": cuota_ref,
        "cuota_casa": cuota_casa,
        "confianza": round(conf, 1),
        "nivel_confianza": _nivel_confianza_jack(conf),
        "edge": None,
        "ev": None,
        "nivel": "SEÑAL PREDICTIVA",
        "accion": "RECOMENDADO" if conf >= JACK_MIN_CONFIDENCE else "NO RECOMENDADA",
        "explicacion": nota or "Señal predictiva independiente de EV/Edge."
    }
    # EV/Edge queda disponible solo como información secundaria, nunca modifica accion.
    if _cuota_valida(cuota_casa):
        p = max(0.0, min(1.0, float(prob_modelo) / 100.0))
        p_casa = 1.0 / cuota_casa
        resultado["probabilidad_implicita_casa"] = round(p_casa * 100.0, 1)
        resultado["edge"] = round((p - p_casa) * 100.0, 1)
        resultado["ev"] = round((p * cuota_casa - 1.0) * 100.0, 2)
        resultado["nivel_valor"] = "VALOR INFORMATIVO"
    return resultado


@app.get('/jackbusca/partido')
def jackbusca_partido(
    request: Request,
    promedio_tarjetas_arbitro: float = None,
    promedio_esperado_corners: float = None,
    cuota_tarjetas_mas_35: float = None,
    cuota_tarjetas_menos_35: float = None,
    cuota_tarjetas_mas_45: float = None,
    cuota_tarjetas_menos_45: float = None,
    cuota_tarjetas_mas_55: float = None,
    cuota_tarjetas_menos_55: float = None,
    cuota_corners_mas_75: float = None,
    cuota_corners_menos_75: float = None,
    cuota_corners_mas_85: float = None,
    cuota_corners_menos_85: float = None,
    cuota_corners_mas_95: float = None,
    cuota_corners_menos_95: float = None,
    cuota_corners_mas_105: float = None,
    cuota_corners_menos_105: float = None,
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

        lam_t, conf_t, fuente_t, err_t, n_t = _lambda_tarjetas_v3(
            promedio_tarjetas_arbitro, lineas_t
        )
        lam_c, err_c, n_c = _lambda_corners_desde_mercado(lineas_c)

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

        conf_c = _confianza_corners_v3(
            n_c, promedio_esperado_corners is not None and promedio_esperado_corners > 0
        )

        lineas_tarjetas = [3.5, 4.5, 5.5]
        tarjetas_mas, tarjetas_menos = ({}, {})
        if lam_t is not None:
            tarjetas_mas, tarjetas_menos = _probabilidades_con_lambda_total(lam_t, lineas_tarjetas)

        lineas_corners = [7.5, 8.5, 9.5, 10.5]
        corners_mas, corners_menos = ({}, {})
        if lam_c is not None:
            corners_mas, corners_menos = _probabilidades_con_lambda_total(lam_c, lineas_corners)

        mercados = []

        if lam_t is not None:
            for linea, over, under, casa_o, casa_u in [
                (3.5, cuota_tarjetas_mas_35, cuota_tarjetas_menos_35, casa_tarjetas_mas_35, casa_tarjetas_menos_35),
                (4.5, cuota_tarjetas_mas_45, cuota_tarjetas_menos_45, casa_tarjetas_mas_45, casa_tarjetas_menos_45),
                (5.5, cuota_tarjetas_mas_55, cuota_tarjetas_menos_55, casa_tarjetas_mas_55, casa_tarjetas_menos_55),
            ]:
                mercados.append(_evaluar_mercado_jack_v3(
                    f'Más {linea} Tarjetas', tarjetas_mas[linea], over, casa_o, conf_t,
                    f'Fuente: {fuente_t}. EV/Edge no modifica esta señal.'
                ))
                mercados.append(_evaluar_mercado_jack_v3(
                    f'Menos {linea} Tarjetas', tarjetas_menos[linea], under, casa_u, conf_t,
                    f'Fuente: {fuente_t}. EV/Edge no modifica esta señal.'
                ))

        if lam_c is not None:
            for linea, over, under, casa_o, casa_u in [
                (7.5, cuota_corners_mas_75, cuota_corners_menos_75, casa_corners_mas_75, casa_corners_menos_75),
                (8.5, cuota_corners_mas_85, cuota_corners_menos_85, casa_corners_mas_85, casa_corners_menos_85),
                (9.5, cuota_corners_mas_95, cuota_corners_menos_95, casa_corners_mas_95, casa_corners_menos_95),
                (10.5, cuota_corners_mas_105, cuota_corners_menos_105, casa_corners_mas_105, casa_corners_menos_105),
            ]:
                mercados.append(_evaluar_mercado_jack_v3(
                    f'Más {linea} Córners', corners_mas[linea], over, casa_o, conf_c,
                    f'Fuente: {fuente_c}. EV/Edge no modifica esta señal.'
                ))
                mercados.append(_evaluar_mercado_jack_v3(
                    f'Menos {linea} Córners', corners_menos[linea], under, casa_u, conf_c,
                    f'Fuente: {fuente_c}. EV/Edge no modifica esta señal.'
                ))

        mercados = [m for m in mercados if m]

        # Top 3 PREDICTIVO: confianza primero; luego separación del 50%.
        predictivos = [m for m in mercados if m["confianza"] >= JACK_MIN_CONFIDENCE]
        predictivos.sort(key=lambda x: (
            x["confianza"], abs(x["probabilidad"] - 50)
        ), reverse=True)
        top3 = predictivos[:3]

        vector_jack = _vector_jackbusca(mercados, conf_c, conf_t)

        bloques = []
        if lam_t is None:
            bloques.append("Tarjetas: DATOS INSUFICIENTES.")
        if lam_c is None:
            bloques.append("Córners: DATOS INSUFICIENTES.")
        if not bloques:
            bloques.append("Datos suficientes para generar señal en ambos bloques.")

        usuario_actual = _optional_user(request)
        historial_info = _save_analysis_if_allowed(
            usuario_actual,
            "JackBusca V3 | Tarjetas y Córners",
            {
                "vector_jackbusca": vector_jack,
                "top_3_selecciones": top3,
                "estado_recomendacion": "HAY SEÑAL" if top3 else "NO RECOMENDADA"
            }
        )

        return {
            "origen": "JackBusca V3 - Motor predictivo de Tarjetas y Córners",
            "version_motor": "V3.0",
            "regla_datos": "La señal predictiva NO depende de EV/Edge. No se inventan cuotas.",
            "calibracion": {
                "dataset_referencia": "LaLiga | 4.180 partidos",
                "prior_corners": JACKBUSCA_LALIGA_PRIOR["corners_mean"],
                "prior_tarjetas": JACKBUSCA_LALIGA_PRIOR["cards_mean"],
                "nota": "Los priors son referencia histórica offline; las cuotas O/U actuales y el árbitro, si existen, aportan la señal del partido."
            },
            "arbitraje": {
                "promedio_tarjetas_referencia": promedio_tarjetas_arbitro,
                "lambda_tarjetas": round(lam_t, 3) if lam_t is not None else None,
                "fuente": fuente_t,
                "confianza": round(conf_t, 1) if lam_t is not None else 0.0
            },
            "corners": {
                "promedio_aportado": promedio_esperado_corners,
                "lambda_total": round(lam_c, 3) if lam_c is not None else None,
                "lineas_pinnacle_disponibles": n_c,
                "fuente": fuente_c,
                "error_calibracion": round(err_c, 5) if err_c is not None else None,
                "confianza": round(conf_c, 1)
            },
            "mercados_tarjetas_explicados": ({
                f'mas_de_{x}': f'{tarjetas_mas[x]}%' for x in lineas_tarjetas
            } | {
                f'menos_de_{x}': f'{tarjetas_menos[x]}%' for x in lineas_tarjetas
            }) if lam_t is not None else {},
            "mercados_tiros_de_esquina": {
                "mas_de": {str(x): f'{corners_mas[x]}%' for x in lineas_corners} if lam_c is not None else {},
                "menos_de": {str(x): f'{corners_menos[x]}%' for x in lineas_corners} if lam_c is not None else {}
            },
            "mercados_valor": mercados,
            "top_3_recomendaciones": top3,
            "top_3_selecciones": top3,
            "estado_recomendacion": "HAY SEÑAL" if top3 else "NO RECOMENDADA",
            "explicacion": " ".join(bloques) + " Si la confianza es menor de 65%, la selección aparece como NO RECOMENDADA.",
            "vector_jackbusca": vector_jack,
            "escenarios": 50000,
            "historial_info": historial_info
        }

    except HTTPException:
        raise
    except Exception as e:
        return {'error': f'Error en JackBusca V3: {str(e)}'}


# ==========================================
# MOTOR UNIFICADO
# ==========================================
@app.get('/unificado/partido')
def unificado_partido(
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
    promedio_tarjetas_arbitro: float = None,
    promedio_esperado_corners: float = None,
    cuota_tarjetas_mas_35: float = None,
    cuota_tarjetas_menos_35: float = None,
    cuota_tarjetas_mas_45: float = None,
    cuota_tarjetas_menos_45: float = None,
    cuota_tarjetas_mas_55: float = None,
    cuota_tarjetas_menos_55: float = None,
    cuota_corners_mas_75: float = None,
    cuota_corners_menos_75: float = None,
    cuota_corners_mas_85: float = None,
    cuota_corners_menos_85: float = None,
    cuota_corners_mas_95: float = None,
    cuota_corners_menos_95: float = None,
    cuota_corners_mas_105: float = None,
    cuota_corners_menos_105: float = None,
):
    try:
        _require_premium(request)

        sim = simular_escenarios_con_pinnacle(
            cuota_local, cuota_empate, cuota_visitante,
            cuota_mas_25_goles, cuota_menos_25_goles,
            cuota_mas_35_goles, cuota_menos_35_goles,
            cuota_btts_si=cuota_btts_si,
            cuota_btts_no=cuota_btts_no
        )

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

        lam_t, conf_t, fuente_t, _, n_t = _lambda_tarjetas_v3(
            promedio_tarjetas_arbitro, lineas_t
        )
        lam_c, _, n_c = _lambda_corners_desde_mercado(lineas_c)

        if lam_c is None and promedio_esperado_corners is not None and promedio_esperado_corners > 0:
            lam_c = float(promedio_esperado_corners)

        if lam_c is not None and promedio_esperado_corners is not None and promedio_esperado_corners > 0 and n_c:
            lam_c = .75 * lam_c + .25 * float(promedio_esperado_corners)

        conf_c = _confianza_corners_v3(
            n_c, promedio_esperado_corners is not None and promedio_esperado_corners > 0
        )

        corners_mas, corners_menos = ({}, {})
        if lam_c is not None:
            corners_mas, corners_menos = _probabilidades_con_lambda_total(lam_c, [7.5,8.5,9.5,10.5])

        tarjetas_mas, tarjetas_menos = ({}, {})
        if lam_t is not None:
            tarjetas_mas, tarjetas_menos = _probabilidades_con_lambda_total(lam_t, [3.5,4.5,5.5])

        mercados_jack = []
        if lam_t is not None:
            for linea in [3.5,4.5,5.5]:
                mercados_jack += [
                    _evaluar_mercado_jack_v3(f"Más {linea} Tarjetas", tarjetas_mas[linea], confianza=conf_t),
                    _evaluar_mercado_jack_v3(f"Menos {linea} Tarjetas", tarjetas_menos[linea], confianza=conf_t),
                ]
        if lam_c is not None:
            for linea in [7.5,8.5,9.5,10.5]:
                mercados_jack += [
                    _evaluar_mercado_jack_v3(f"Más {linea} Córners", corners_mas[linea], confianza=conf_c),
                    _evaluar_mercado_jack_v3(f"Menos {linea} Córners", corners_menos[linea], confianza=conf_c),
                ]

        vector_p = _vector_principal(sim)
        vector_j = _vector_jackbusca(mercados_jack, conf_c, conf_t)
        unificado = _unificar_vectores(vector_p, vector_j)

        candidatos = [m for m in mercados_jack if m and m["confianza"] >= JACK_MIN_CONFIDENCE]
        candidatos.sort(key=lambda x: (x["confianza"], abs(x["probabilidad"] - 50)), reverse=True)

        return {
            "origen": "API Master Pro - Motor Unificado v9.0",
            "motor_principal": {
                "vector": vector_p,
                "probabilidades": {
                    "local": sim["p_1"],
                    "empate": sim["p_x"],
                    "visitante": sim["p_2"],
                    "over_25": sim["over_25"],
                    "under_25": sim["under_25"],
                    "btts_si": sim["btts_si"],
                    "btts_no": sim["btts_no"]
                },
                "escenarios": sim.get("escenarios", 50000)
            },
            "jackbusca": {
                "vector": vector_j,
                "top_3_selecciones": candidatos[:3]
            },
            "lectura_unificada": unificado,
            "top_3_selecciones": candidatos[:3],
            "regla_recomendacion": "Solo mostrar selección como RECOMENDADA cuando la confianza sea >=65%. EV/Edge no cambia la predicción.",
            "estado": "OK"
        }

    except HTTPException:
        raise
    except Exception as e:
        return {"error": f"Error en Motor Unificado: {str(e)}"}
