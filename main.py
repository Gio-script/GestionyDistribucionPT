import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.staticfiles import StaticFiles
from a2wsgi import ASGIMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from database import SupabaseManager
import csv
from datetime import datetime, timedelta, timezone, date  # <-- AGREGADO date

app = FastAPI(title="Cinépolis - SGI Backend")
db = SupabaseManager()
wsgi_app = ASGIMiddleware(app)

# Obtener de forma estricta el directorio raíz donde está main.py para las vistas
CURRENT_DIR = Path(__file__).resolve().parent

# --- MONTAR ARCHIVOS ESTÁTICOS (IMÁGENES) ---
app.mount("/images", StaticFiles(directory=CURRENT_DIR / "images"), name="images")

# --- MODELOS DE DATOS PYDANTIC ---
class LoginRequest(BaseModel):
    email: str
    password: str

class SucursalCreate(BaseModel):
    nombre_suc: str
    correo_usuario_suc: str
    password: str

class SucursalEstadoUpdate(BaseModel):
    estado: bool

class SucursalPerfilUpdate(BaseModel):
    id_usuario: Optional[str] = None
    nombre_suc: str
    correo_usuario_suc: str
    password: Optional[str] = None

class ColaboradorCreate(BaseModel):
    rut: str
    nombre: str
    apellido: str
    correo: str
    tipo_personal: str
    talla_superior: str
    talla_inferior: str
    talla_calzado: str
    genero: Optional[str] = "no_responde"  # <-- NUEVO CAMPO

class DetalleFacturaItem(BaseModel):
    id_producto: int
    talla: str
    cantidad: int

class FacturaCreateRequest(BaseModel):
    correlativo_factura: int
    rut_proveedor: str
    nombre_proveedor: str
    id_sucursal: int
    id_usuario_registra: str
    items: List[DetalleFacturaItem]

class EntregaCreateRequest(BaseModel):
    id_colaborador: int
    id_producto: int
    talla: str
    cantidad: int
    id_usuario_actual: str
    id_sucursal: int

class SolicitudAnulacionRequest(BaseModel):
    id_sucursal: int
    id_factura: int
    id_usuario_solicita: str
    motivo: str

class ResolucionAnulacionRequest(BaseModel):
    estado: str
    observacion_resolucion: str
    id_usuario_resuelve: str
    tipo_solicitud: str

class StockOutRequest(BaseModel):
    origen: str
    id_colaborador: Optional[int] = None
    tipo_salida: str
    id_producto: int
    talla: str
    cantidad: int

class SolicitudTransferenciaStock(BaseModel):
    id_sucursal_origen: int
    id_sucursal_destino: int
    id_producto: int
    talla: str
    cantidad: int
    motivo: str
    id_usuario_solicita: str

class SolicitudTransferenciaColab(BaseModel):
    id_colaborador: int
    id_sucursal_origen: int
    id_sucursal_destino: int
    motivo: str
    id_usuario_solicita: str

class ResolucionTransferenciaRequest(BaseModel):
    estado: str
    observacion_resolucion: str
    id_usuario_resuelve: str

class EntregaMasivaRequest(BaseModel):
    id_colaborador: int
    items: List[dict]
    id_usuario_actual: str
    id_sucursal: int

class TransferenciaProducto(BaseModel):
    id_producto: int
    cantidad: int
    id_sucursal_destino: int

# --- MODELOS PARA LOTES DE TRANSFERENCIA (DISTRIBUCIÓN SUPERADMIN) ---
class LoteItem(BaseModel):
    id_producto: int
    talla: str
    cantidad: int

class LoteTransferenciaCreate(BaseModel):
    id_sucursal_origen: int
    ids_sucursales_destino: List[int]
    id_usuario_envia: str
    motivo: Optional[str] = None
    items: List[LoteItem]

class ResolucionLoteRequest(BaseModel):
    estado: str  # "RECIBIDO" | "RECHAZADO"
    id_usuario_recibe: str
    observacion_resolucion: Optional[str] = None

# --- MODELOS PARA CSVs ---
class CSVGeneradoRequest(BaseModel):
    id_entregas: List[int]
    id_sucursal: int
    id_usuario: str


# --- SEGURIDAD: auditoría, errores genéricos y freno de fuerza bruta (ISO 27001 - A.12.4 / A.9.4) ---
LOG_SEGURIDAD_PATH = CURRENT_DIR / "logs" / "seguridad.log"

def registrar_evento_seguridad(tipo: str, detalle: str):
    """
    Registra eventos de seguridad (login fallido, acceso denegado, token
    inválido, error interno) en un log aparte de los logs normales de la app,
    para poder auditarlos sin mezclarlos con el ruido operativo.
    """
    try:
        with open(str(LOG_SEGURIDAD_PATH), "a", encoding="utf-8") as f:
            marca = datetime.now(timezone.utc).isoformat()
            f.write(f"{marca} | {tipo} | {detalle}\n")
    except Exception:
        pass  # el logging nunca debe romper el request


def manejar_error(e: Exception, status_code: int = 400):
    """
    ISO 27001 - A.14.2: no exponer detalles internos (nombres de tabla,
    stacktraces, mensajes crudos de la BD) al cliente. Registra el error
    real en el log de seguridad y devuelve un mensaje genérico.
    """
    registrar_evento_seguridad("ERROR_INTERNO", f"{type(e).__name__}: {e}")
    mensaje = "Error interno del servidor." if status_code >= 500 else "No se pudo procesar la solicitud."
    raise HTTPException(status_code=status_code, detail=mensaje)


# Freno de fuerza bruta en /api/login: intentos fallidos por correo, en memoria.
# Se reinicia si el servicio se reinicia — suficiente para un solo proceso (nuestro caso).
_intentos_login_fallidos = defaultdict(list)
MAX_INTENTOS_LOGIN = 5
VENTANA_BLOQUEO_SEGUNDOS = 15 * 60  # 15 minutos

def verificar_bloqueo_login(email: str):
    ahora = time.time()
    intentos = _intentos_login_fallidos[email]
    intentos[:] = [t for t in intentos if ahora - t < VENTANA_BLOQUEO_SEGUNDOS]
    if len(intentos) >= MAX_INTENTOS_LOGIN:
        registrar_evento_seguridad("LOGIN_BLOQUEADO", f"email={email} excedió {MAX_INTENTOS_LOGIN} intentos en {VENTANA_BLOQUEO_SEGUNDOS // 60} min")
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos fallidos. Intenta nuevamente en {VENTANA_BLOQUEO_SEGUNDOS // 60} minutos."
        )

def registrar_intento_fallido(email: str):
    _intentos_login_fallidos[email].append(time.time())

def limpiar_intentos_fallidos(email: str):
    _intentos_login_fallidos.pop(email, None)


# --- AUTENTICACIÓN Y AUTORIZACIÓN (ISO 27001 - A.9 Control de acceso) ---
def obtener_usuario_actual(authorization: Optional[str] = Header(None)) -> dict:
    """
    Valida el token Bearer enviado por el frontend contra Supabase Auth y
    retorna el perfil real (rol, sucursal) del usuario autenticado.
    Se usa como Depends() en cada endpoint protegido.
    """
    if not authorization or not authorization.startswith("Bearer "):
        registrar_evento_seguridad("ACCESO_SIN_TOKEN", "Solicitud a la API sin header Authorization")
        raise HTTPException(status_code=401, detail="No autenticado. Falta el token de acceso.")

    token = authorization.removeprefix("Bearer ").strip()
    perfil = db.verificar_token(token)

    if not perfil:
        registrar_evento_seguridad("TOKEN_INVALIDO", "Token inválido o expirado presentado a la API")
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada. Inicia sesión nuevamente.")

    if not perfil.get("estado", True):
        registrar_evento_seguridad("ACCESO_CUENTA_DESHABILITADA", f"id_suc={perfil.get('id_suc')}")
        raise HTTPException(status_code=403, detail="El acceso para esta sucursal se encuentra deshabilitado.")

    return perfil


def verificar_acceso_sucursal(usuario: dict, id_sucursal: int):
    """Un usuario de sucursal solo puede operar sobre su propia sede. El admin puede sobre todas."""
    if usuario["rol"] != "admin" and usuario["id_suc"] != id_sucursal:
        registrar_evento_seguridad(
            "ACCESO_DENEGADO",
            f"usuario id_suc={usuario.get('id_suc')} intentó operar sobre id_sucursal={id_sucursal}"
        )
        raise HTTPException(status_code=403, detail="No tienes permiso para operar sobre esta sucursal.")


def requerir_admin(usuario: dict):
    """Para endpoints exclusivos de /api/superadmin/*."""
    if usuario["rol"] != "admin":
        registrar_evento_seguridad(
            "ACCESO_DENEGADO_ADMIN",
            f"usuario id_suc={usuario.get('id_suc')} intentó una acción exclusiva de administrador"
        )
        raise HTTPException(status_code=403, detail="Esta acción requiere rol de administrador.")


def validar_password_segura(password: str):
    """
    ISO 27001 - A.9.4 Política de contraseñas.
    Exige mínimo 8 caracteres, al menos una letra, un número y un carácter especial.
    Solo se aplica a contraseñas nuevas o que se estén cambiando (no retroactivo).
    """
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres.")
    if not re.search(r"[A-Za-z]", password):
        raise HTTPException(status_code=400, detail="La contraseña debe incluir al menos una letra.")
    if not re.search(r"[0-9]", password):
        raise HTTPException(status_code=400, detail="La contraseña debe incluir al menos un número.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise HTTPException(status_code=400, detail="La contraseña debe incluir al menos un carácter especial (ej. !@#$%&*).")


# --- RUTAS DE NAVEGACIÓN (VISTAS HTML DENTRO DE TEMPLATES) ---
@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
def vista_login():
    html_path = CURRENT_DIR / "templates" / "login.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail=f"No se encontró login.html en: {html_path}")
    return FileResponse(str(html_path))

@app.get("/dashboard", response_class=HTMLResponse)
def vista_dashboard():
    html_path = CURRENT_DIR / "templates" / "dashboard_local.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail=f"No se encontró dashboard_local.html en: {html_path}")
    return FileResponse(str(html_path))

@app.get("/superadmin", response_class=HTMLResponse)
def vista_superadmin():
    html_path = CURRENT_DIR / "templates" / "superadmin.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail=f"No se encontró superadmin.html en: {html_path}")
    return FileResponse(str(html_path))


# --- ENDPOINTS DE AUTENTICACIÓN ---
@app.post("/api/login")
def login(data: LoginRequest):
    verificar_bloqueo_login(data.email)
    try:
        auth_res = db.login_user(data.email, data.password)

        if not auth_res or not auth_res.user:
            registrar_intento_fallido(data.email)
            registrar_evento_seguridad("LOGIN_FALLIDO", f"email={data.email}")
            raise HTTPException(status_code=401, detail="Credenciales incorrectas de Supabase Auth.")

        user_uid = auth_res.user.id
        res_perfil = db.client.table("sucursal_usuaria").select("*").eq("id_usuario", user_uid).execute()

        if not res_perfil.data or len(res_perfil.data) == 0:
            registrar_evento_seguridad("LOGIN_SIN_PERFIL", f"email={data.email} uid={user_uid}")
            raise HTTPException(status_code=403, detail="El usuario no tiene una sucursal o rol asignado en la base de datos.")

        perfil = res_perfil.data[0]

        if not perfil.get("estado", True):
            registrar_evento_seguridad("LOGIN_CUENTA_DESHABILITADA", f"email={data.email}")
            raise HTTPException(status_code=403, detail="El acceso para esta sucursal se encuentra deshabilitado.")

        limpiar_intentos_fallidos(data.email)

        return {
            "status": "success",
            "rol": perfil.get("rol"),
            "id_suc": perfil.get("id_suc"),
            "id_usuario": perfil.get("id_usuario"),
            "nombre_suc": perfil.get("nombre_suc"),
            "access_token": auth_res.session.access_token,
            "refresh_token": auth_res.session.refresh_token
        }
    except HTTPException:
        raise
    except Exception as e:
        manejar_error(e, 401)


# --- ENDPOINTS DEL MODULO: COLABORADORES ---
@app.get("/api/sucursal/colaboradores/{id_sucursal}")
def listar_colaboradores(id_sucursal: int, usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, id_sucursal)
    try:
        res = db.client.table("colaborador").select("*").eq("id_sucursal", id_sucursal).execute()
        return res.data
    except Exception as e:
        manejar_error(e, 500)

@app.post("/api/sucursal/colaboradores/{id_sucursal}")
def crear_colaborador(id_sucursal: int, data: ColaboradorCreate, usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, id_sucursal)
    try:
        res = db.client.table("colaborador").insert({
            "rut": data.rut,
            "nombre": data.nombre,
            "apellido": data.apellido,
            "correo": data.correo,
            "tipo_personal": data.tipo_personal,
            "talla_superior": data.talla_superior,
            "talla_inferior": data.talla_inferior,
            "talla_calzado": data.talla_calzado,
            "genero": data.genero or "no_responde",  # <-- NUEVO
            "id_sucursal": id_sucursal,
            "fecha_ingreso": "now()"
        }).execute()
        return {"status": "success", "data": res.data}
    except Exception as e:
        manejar_error(e, 400)

@app.post("/api/sucursal/colaboradores-masivo/{id_sucursal}")
def crear_colaborador_masivo(id_sucursal: int, data: List[ColaboradorCreate], usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, id_sucursal)
    try:
        for col in data:
            correo = col.correo if col.correo and col.correo.strip() else f"sin_correo_{col.rut.replace('.', '').replace('-', '')}@cinepolis.com"
            
            db.client.table("colaborador").insert({
                "rut": col.rut,
                "nombre": col.nombre,
                "apellido": col.apellido,
                "correo": correo,
                "tipo_personal": col.tipo_personal,
                "talla_superior": col.talla_superior,
                "talla_inferior": col.talla_inferior,
                "talla_calzado": col.talla_calzado,
                "genero": col.genero or "no_responde",  # <-- NUEVO
                "id_sucursal": id_sucursal,
                "fecha_ingreso": date.today().isoformat()
            }).execute()
        return {"status": "success", "message": f"{len(data)} colaboradores registrados correctamente."}
    except Exception as e:
        manejar_error(e, 400)

@app.put("/api/sucursal/colaboradores/{id_colaborador}")
def editar_colaborador(id_colaborador: int, data: ColaboradorCreate, usuario_actual: dict = Depends(obtener_usuario_actual)):
    try:
        res_check = db.client.table("colaborador").select("id_sucursal").eq("id_colaborador", id_colaborador).execute()
        if not res_check.data:
            raise HTTPException(status_code=404, detail="Colaborador no encontrado.")
        verificar_acceso_sucursal(usuario_actual, res_check.data[0]["id_sucursal"])

        res = db.client.table("colaborador").update({
            "rut": data.rut,
            "nombre": data.nombre,
            "apellido": data.apellido,
            "correo": data.correo,
            "tipo_personal": data.tipo_personal,
            "talla_superior": data.talla_superior,
            "talla_inferior": data.talla_inferior,
            "talla_calzado": data.talla_calzado,
            "genero": data.genero or "no_responde"  # <-- NUEVO
        }).eq("id_colaborador", id_colaborador).execute()
        return {"status": "success", "data": res.data}
    except HTTPException:
        raise
    except Exception as e:
        manejar_error(e, 400)

@app.delete("/api/sucursal/colaboradores/{id_colaborador}")
def eliminar_colaborador(id_colaborador: int, accion_dotacion: Optional[str] = None, usuario_actual: dict = Depends(obtener_usuario_actual)):
    try:
        res_colab = db.client.table("colaborador").select("id_sucursal").eq("id_colaborador", id_colaborador).execute()
        if not res_colab.data:
            raise HTTPException(status_code=404, detail="Colaborador no encontrado.")
        id_suc = res_colab.data[0]["id_sucursal"]
        verificar_acceso_sucursal(usuario_actual, id_suc)

        res_dot = db.client.table("colaborador_stock_dotacion")\
            .select("*").eq("id_colaborador", id_colaborador).gt("cantidad_en_uso", 0).execute()
        
        if res_dot.data:
            if not accion_dotacion:
                return {"status": "warning", "message": "El colaborador tiene dotación activa. Requiere decisión."}
            
            if accion_dotacion not in ["merma", "stock"]:
                raise HTTPException(status_code=400, detail="Acción de dotación inválida.")

            for item in res_dot.data:
                id_prod = item["id_producto"]
                talla = item["talla"]
                cant = item["cantidad_en_uso"]

                res_inv = db.client.table("inventario_stock")\
                    .select("*").eq("id_sucursal", id_suc).eq("id_producto", id_prod).eq("talla", talla).execute()
                
                if accion_dotacion == "merma":
                    db.client.table("salida_stock").insert({
                        "id_sucursal_origen": id_suc,
                        "tipo_salida": "Renuncia sin devolucion",
                        "id_producto": id_prod,
                        "talla": talla,
                        "cantidad": cant
                    }).execute()

                    if res_inv.data:
                        fila_inv = res_inv.data[0]
                        db.client.table("inventario_stock").update({
                            "cantidad_merma": fila_inv["cantidad_merma"] + cant
                        }).eq("id_stock", fila_inv["id_stock"]).execute()
                    else:
                        db.client.table("inventario_stock").insert({
                            "id_sucursal": id_suc, "id_producto": id_prod, "talla": talla,
                            "cantidad_disponible": 0, "cantidad_merma": cant
                        }).execute()
                
                elif accion_dotacion == "stock":
                    if res_inv.data:
                        fila_inv = res_inv.data[0]
                        db.client.table("inventario_stock").update({
                            "cantidad_disponible": fila_inv["cantidad_disponible"] + cant
                        }).eq("id_stock", fila_inv["id_stock"]).execute()
                    else:
                        db.client.table("inventario_stock").insert({
                            "id_sucursal": id_suc, "id_producto": id_prod, "talla": talla,
                            "cantidad_disponible": cant, "cantidad_merma": 0
                        }).execute()

        db.client.table("colaborador_stock_dotacion").delete().eq("id_colaborador", id_colaborador).execute()
        db.client.table("colaborador").delete().eq("id_colaborador", id_colaborador).execute()

        return {"status": "success", "message": "Colaborador eliminado y dotación procesada."}
    except HTTPException:
        raise
    except Exception as e:
        manejar_error(e, 400)
    

# --- ENDPOINTS DEL MODULO: PRODUCTOS Y CATÁLOGO ---
@app.get("/api/sucursal/productos-catalogo")
def obtener_productos_catalogo(usuario_actual: dict = Depends(obtener_usuario_actual)):
    try:
        res = db.client.table("producto_catalogo").select("*").execute()
        return res.data
    except Exception as e:
        manejar_error(e, 500)


# --- ENDPOINTS DEL MODULO: INVENTARIO / STOCK ---
@app.get("/api/sucursal/inventario-completo/{id_sucursal}")
def obtener_inventario_completo(id_sucursal: int, usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, id_sucursal)
    try:
        res = db.client.table("inventario_stock")\
            .select("*, producto_catalogo(*)")\
            .eq("id_sucursal", id_sucursal)\
            .execute()
        return res.data
    except Exception as e:
        manejar_error(e, 500)

@app.get("/api/sucursal/inventario-disponible/{id_sucursal}")
def obtener_inventario_disponible(id_sucursal: int, usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, id_sucursal)
    try:
        res = db.client.table("inventario_stock")\
            .select("*, producto_catalogo(*)")\
            .eq("id_sucursal", id_sucursal)\
            .gt("cantidad_disponible", 0)\
            .execute()
        return res.data
    except Exception as e:
        manejar_error(e, 500)
    

@app.get("/api/sucursal/dotacion-consolidada/{id_sucursal}")
def obtener_dotacion_consolidada(id_sucursal: int, usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, id_sucursal)
    try:
        res = db.client.table("colaborador_stock_dotacion")\
            .select("*, colaborador!inner(*), producto_catalogo(*)")\
            .eq("colaborador.id_sucursal", id_sucursal)\
            .gt("cantidad_en_uso", 0)\
            .execute()
        return res.data
    except Exception as e:
        manejar_error(e, 500)

@app.get("/api/superadmin/dotacion-consolidada-global")
def obtener_dotacion_consolidada_global(usuario_actual: dict = Depends(obtener_usuario_actual)):
    requerir_admin(usuario_actual)
    try:
        # ✅ CORREGIDO: sucursal_usuaria anidado dentro de colaborador
        res = db.client.table("colaborador_stock_dotacion")\
            .select("*, producto_catalogo(*), colaborador(*, sucursal_usuaria(nombre_suc))")\
            .gt("cantidad_en_uso", 0)\
            .execute()
        return res.data
    except Exception as e:
        # ✅ AQUÍ ESTÁ EL EXCEPT QUE FALTABA
        manejar_error(e, 500)
    
@app.get("/api/sucursal/dotacion-colaborador/{id_colaborador}")
def obtener_dotacion_colaborador(id_colaborador: int, usuario_actual: dict = Depends(obtener_usuario_actual)):
    try:
        res_colab = db.client.table("colaborador").select("id_sucursal").eq("id_colaborador", id_colaborador).execute()
        if not res_colab.data:
            raise HTTPException(status_code=404, detail="Colaborador no encontrado.")
        verificar_acceso_sucursal(usuario_actual, res_colab.data[0]["id_sucursal"])

        res = db.client.table("colaborador_stock_dotacion")\
            .select("*, producto_catalogo(*)")\
            .eq("id_colaborador", id_colaborador)\
            .gt("cantidad_en_uso", 0)\
            .execute()
        return res.data
    except HTTPException:
        raise
    except Exception as e:
        manejar_error(e, 500)


# --- ENDPOINTS DEL MODULO: FACTURAS ---
@app.get("/api/sucursal/facturas-historial/{id_sucursal}")
def obtener_historial_facturas(id_sucursal: int, usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, id_sucursal)
    try:
        res = db.client.table("factura_ingreso")\
            .select("*, detalle_factura(*, producto_catalogo(*))")\
            .eq("id_sucursal", id_sucursal)\
            .order("fecha_ingreso", desc=True)\
            .execute()
        return res.data
    except Exception as e:
        manejar_error(e, 500)

@app.post("/api/sucursal/facturas")
def ingresar_factura(data: FacturaCreateRequest, usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, data.id_sucursal)
    try:
        check = db.client.table("factura_ingreso")\
            .select("id_factura")\
            .eq("correlativo_factura", data.correlativo_factura)\
            .execute()
            
        if check.data:
            raise HTTPException(status_code=400, detail="El correlativo de factura ya existe.")

        res_factura = db.client.table("factura_ingreso").insert({
            "correlativo_factura": data.correlativo_factura,
            "rut_proveedor": data.rut_proveedor,
            "nombre_proveedor": data.nombre_proveedor,
            "id_sucursal": data.id_sucursal,
            "id_usuario_registra": data.id_usuario_registra
        }).execute()

        id_factura_generada = res_factura.data[0]["id_factura"]

        for item in data.items:
            db.client.table("detalle_factura").insert({
                "id_factura": id_factura_generada,
                "id_producto": item.id_producto,
                "talla": item.talla,
                "cantidad": item.cantidad
            }).execute()

            res_stock = db.client.table("inventario_stock")\
                .select("*")\
                .eq("id_sucursal", data.id_sucursal)\
                .eq("id_producto", item.id_producto)\
                .eq("talla", item.talla)\
                .execute()

            if res_stock.data:
                fila = res_stock.data[0]
                nueva_cant = fila["cantidad_disponible"] + item.cantidad
                db.client.table("inventario_stock").update({
                    "cantidad_disponible": nueva_cant
                }).eq("id_stock", fila["id_stock"]).execute() 
            else:
                db.client.table("inventario_stock").insert({
                    "id_sucursal": data.id_sucursal,
                    "id_producto": item.id_producto,
                    "talla": item.talla,
                    "cantidad_disponible": item.cantidad
                }).execute()

        return {"status": "success", "message": "Factura e inventario procesados correctamente."}
    except HTTPException:
        raise
    except Exception as e:
        manejar_error(e, 400)


# --- ENDPOINTS DEL MODULO: ENTREGAS MASIVAS ---
@app.post("/api/sucursal/entregas-masivas")
def registrar_entrega_masiva(data: EntregaMasivaRequest, usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, data.id_sucursal)
    try:
        res_entrega = db.client.table("entrega_insumo").insert({
            "id_colaborador": data.id_colaborador,
            "id_sucursal": data.id_sucursal,
            "id_usuario_despacha": data.id_usuario_actual,
            "firma_digital_url": "N/A"
        }).execute()
        
        id_entrega = res_entrega.data[0]["id_entrega"]

        for item in data.items:
            id_prod = item["id_producto"]
            talla = item["talla"]
            cantidad = item["cantidad"]

            res_stock = db.client.table("inventario_stock")\
                .select("*").eq("id_sucursal", data.id_sucursal)\
                .eq("id_producto", id_prod).eq("talla", talla).execute()
            
            if not res_stock.data or res_stock.data[0]["cantidad_disponible"] < cantidad:
                raise HTTPException(status_code=400, detail=f"Stock insuficiente para producto ID {id_prod} talla {talla}")

            fila_stock = res_stock.data[0]
            db.client.table("inventario_stock").update({
                "cantidad_disponible": fila_stock["cantidad_disponible"] - cantidad
            }).eq("id_stock", fila_stock["id_stock"]).execute() 
            
            db.client.table("detalle_entrega").insert({
                "id_entrega": id_entrega,
                "id_producto": id_prod,
                "talla": talla,
                "cantidad": cantidad
            }).execute()
            
            res_dot = db.client.table("colaborador_stock_dotacion")\
                .select("*").eq("id_colaborador", data.id_colaborador)\
                .eq("id_producto", id_prod).eq("talla", talla).execute()
                
            if res_dot.data:
                fila_dot = res_dot.data[0]
                db.client.table("colaborador_stock_dotacion").update({
                    "cantidad_en_uso": fila_dot["cantidad_en_uso"] + cantidad
                }).eq("id_colaborador_stock", fila_dot["id_colaborador_stock"]).execute()
            else:
                db.client.table("colaborador_stock_dotacion").insert({
                    "id_colaborador": data.id_colaborador,
                    "id_producto": id_prod,
                    "talla": talla,
                    "cantidad_en_uso": cantidad
                }).execute()
            
        return {"status": "success", "message": "Entrega masiva procesada exitosamente."}

    except HTTPException:
        raise
    except Exception as e:
        manejar_error(e, 400)


# --- ENDPOINTS DEL MODULO: SOLICITUDES DE ANULACIÓN ---
@app.post("/api/sucursal/solicitar-anulacion")
def solicitar_anulacion_factura(data: SolicitudAnulacionRequest, usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, data.id_sucursal)
    try:
        res_factura = db.client.table("factura_ingreso").select("*").eq("id_factura", data.id_factura).execute()
        if not res_factura.data:
            raise HTTPException(status_code=404, detail="La factura especificada no existe.")
            
        factura_data = res_factura.data[0]
        rut_p = factura_data.get("rut_proveedor", "N/A")
        nombre_p = factura_data.get("nombre_proveedor", "N/A")
        
        db.client.table("anulacion_factura_solicitud").insert({
            "id_sucursal": data.id_sucursal,
            "id_factura": data.id_factura,
            "folio_factura": factura_data.get("correlativo_factura"), 
            "rut_proveedor": rut_p,          
            "nombre_proveedor": nombre_p,    
            "id_usuario_solicita": data.id_usuario_solicita,
            "motivo": data.motivo,
            "estado": "PENDIENTE",
            "fecha_solicitud": "now()"
        }).execute()
        
        return {"status": "success", "message": "Solicitud enviada a la cola."}
    except HTTPException:
        raise
    except Exception as e:
        manejar_error(e, 400)

@app.get("/api/sucursal/{id_sucursal}/solicitudes-anulacion")
def obtener_historial_solicitudes_sucursal(id_sucursal: int, usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, id_sucursal)
    try:
        res = db.client.table("anulacion_factura_solicitud")\
            .select("*, factura_ingreso(correlativo_factura)")\
            .eq("id_sucursal", id_sucursal)\
            .order("fecha_solicitud", desc=True)\
            .execute()
        return res.data
    except Exception as e:
        manejar_error(e, 500)


# --- ENDPOINTS DEL MODULO: STOCK OUT (ENTREGAS / MERMAS) ---
@app.post("/api/sucursal/stock-out/{id_sucursal}")
def procesar_stock_out(id_sucursal: int, data: StockOutRequest, usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, id_sucursal)
    try:
        if data.origen == "inventario":
            res_stock = db.client.table("inventario_stock")\
                .select("*").eq("id_sucursal", id_sucursal)\
                .eq("id_producto", data.id_producto).eq("talla", data.talla).execute()

            if not res_stock.data or res_stock.data[0]["cantidad_disponible"] < data.cantidad:
                raise HTTPException(status_code=400, detail="Stock insuficiente en inventario físico.")

            fila_stock = res_stock.data[0]
            nuevo_stock = fila_stock["cantidad_disponible"] - data.cantidad
            nueva_merma = fila_stock["cantidad_merma"] + data.cantidad

            db.client.table("inventario_stock").update({
                "cantidad_disponible": nuevo_stock,
                "cantidad_merma": nueva_merma
            }).eq("id_stock", fila_stock["id_stock"]).execute()
            
            db.client.table("salida_stock").insert({
                "id_sucursal_origen": id_sucursal,
                "tipo_salida": data.tipo_salida,
                "id_producto": data.id_producto,
                "talla": data.talla,
                "cantidad": data.cantidad
            }).execute()

        elif data.origen == "dotacion" and data.id_colaborador:
            res_dot = db.client.table("colaborador_stock_dotacion")\
                .select("*").eq("id_colaborador", data.id_colaborador)\
                .eq("id_producto", data.id_producto).eq("talla", data.talla).execute()

            if not res_dot.data or res_dot.data[0]["cantidad_en_uso"] < data.cantidad:
                raise HTTPException(status_code=400, detail="El colaborador no tiene esa cantidad en uso.")

            fila_dot = res_dot.data[0]
            db.client.table("colaborador_stock_dotacion").update({
                "cantidad_en_uso": fila_dot["cantidad_en_uso"] - data.cantidad,
                "fecha_actualizacion": "now()"
            }).eq("id_colaborador_stock", fila_dot["id_colaborador_stock"]).execute()

            res_inv = db.client.table("inventario_stock")\
                .select("*").eq("id_sucursal", id_sucursal)\
                .eq("id_producto", data.id_producto).eq("talla", data.talla).execute()
            
            if data.tipo_salida == "Devolucion conforme a Stock":
                if res_inv.data:
                    fila_inv = res_inv.data[0]
                    db.client.table("inventario_stock").update({
                        "cantidad_disponible": fila_inv["cantidad_disponible"] + data.cantidad
                    }).eq("id_stock", fila_inv["id_stock"]).execute()
                else:
                    db.client.table("inventario_stock").insert({
                        "id_sucursal": id_sucursal,
                        "id_producto": data.id_producto,
                        "talla": data.talla,
                        "cantidad_disponible": data.cantidad,
                        "cantidad_merma": 0
                    }).execute()

            elif data.tipo_salida == "Renuncia sin devolucion":
                if res_inv.data:
                    fila_inv = res_inv.data[0]
                    db.client.table("inventario_stock").update({
                        "cantidad_merma": fila_inv["cantidad_merma"] + data.cantidad
                    }).eq("id_stock", fila_inv["id_stock"]).execute()
                else:
                    db.client.table("inventario_stock").insert({
                        "id_sucursal": id_sucursal,
                        "id_producto": data.id_producto,
                        "talla": data.talla,
                        "cantidad_disponible": 0,
                        "cantidad_merma": data.cantidad
                    }).execute()
                
                db.client.table("salida_stock").insert({
                    "id_sucursal_origen": id_sucursal,
                    "tipo_salida": data.tipo_salida,
                    "id_producto": data.id_producto,
                    "talla": data.talla,
                    "cantidad": data.cantidad
                }).execute()

        return {"status": "success", "message": "Transacción Stock Out registrada."}
    except HTTPException:
        raise
    except Exception as e:
        manejar_error(e, 400)

@app.get("/api/sucursal/entregas-historial/{id_sucursal}")
def obtener_historial_entregas_sucursal(id_sucursal: int, usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, id_sucursal)
    try:
        res = db.client.table("entrega_insumo")\
            .select("*, colaborador(*), detalle_entrega(*, producto_catalogo(*))")\
            .eq("id_sucursal", id_sucursal)\
            .order("fecha_entrega", desc=True)\
            .execute()
        return res.data
    except Exception as e:
        manejar_error(e, 500)


# --- ENDPOINTS EXCLUSIVOS DEL MODULO: SUPERADMIN ---
@app.get("/api/superadmin/sucursales")
def superadmin_listar_sucursales(usuario_actual: dict = Depends(obtener_usuario_actual)):
    requerir_admin(usuario_actual)
    try:
        res = db.client.table("sucursal_usuaria").select("*").execute()
        return res.data
    except Exception as e:
        manejar_error(e, 500)

@app.post("/api/superadmin/sucursales")
def superadmin_crear_sucursal(data: SucursalCreate, usuario_actual: dict = Depends(obtener_usuario_actual)):
    requerir_admin(usuario_actual)
    validar_password_segura(data.password)
    try:
        user_auth = db.client.auth.admin.create_user({
            "email": data.correo_usuario_suc,
            "password": data.password,
            "email_confirm": True
        })

        if not user_auth.user:
            raise HTTPException(status_code=400, detail="No se pudo registrar en Auth Server.")

        res = db.client.table("sucursal_usuaria").insert({
            "nombre_suc": data.nombre_suc,
            "correo_usuario_suc": data.correo_usuario_suc,
            "id_usuario": user_auth.user.id,
            "rol": "usuario",
            "estado": True
        }).execute()

        return {"status": "success", "data": res.data}
    except Exception as e:
        manejar_error(e, 400)

@app.put("/api/superadmin/sucursales/{id_suc}/estado")
def superadmin_actualizar_estado_sucursal(id_suc: int, data: SucursalEstadoUpdate, usuario_actual: dict = Depends(obtener_usuario_actual)):
    requerir_admin(usuario_actual)
    try:
        res = db.client.table("sucursal_usuaria")\
            .update({"estado": data.estado})\
            .eq("id_suc", id_suc)\
            .execute()
        return {"status": "success", "data": res.data}
    except Exception as e:
        manejar_error(e, 400)

@app.put("/api/superadmin/sucursales/{id_suc}/perfil")
def superadmin_actualizar_perfil_sucursal(id_suc: int, data: SucursalPerfilUpdate, usuario_actual: dict = Depends(obtener_usuario_actual)):
    requerir_admin(usuario_actual)
    if data.password:
        validar_password_segura(data.password)
    try:
        id_usuario_final = data.id_usuario
        cuenta_recien_creada = False

        if data.id_usuario:
            # Ya tiene cuenta de Auth: actualizar email/clave SOLO si realmente cambiaron
            fila_actual = db.client.table("sucursal_usuaria").select("correo_usuario_suc").eq("id_suc", id_suc).execute()
            correo_actual = fila_actual.data[0]["correo_usuario_suc"] if fila_actual.data else None

            auth_update = {}
            if data.correo_usuario_suc and data.correo_usuario_suc != correo_actual:
                auth_update["email"] = data.correo_usuario_suc
            if data.password:
                auth_update["password"] = data.password

            if auth_update:
                db.client.auth.admin.update_user_by_id(data.id_usuario, auth_update)
        else:
            # Esta sede nunca tuvo cuenta de Auth creada (ej. carga masiva antigua)
            if not data.password:
                raise HTTPException(
                    status_code=400,
                    detail="Esta sede no tiene cuenta de acceso creada todavía. Escribe una contraseña para crearla."
                )
            user_auth = db.client.auth.admin.create_user({
                "email": data.correo_usuario_suc,
                "password": data.password,
                "email_confirm": True
            })
            if not user_auth.user:
                raise HTTPException(status_code=400, detail="No se pudo crear la cuenta en Auth.")
            id_usuario_final = user_auth.user.id
            cuenta_recien_creada = True

        update_payload = {
            "nombre_suc": data.nombre_suc,
            "correo_usuario_suc": data.correo_usuario_suc,
            "id_usuario": id_usuario_final
        }
        if cuenta_recien_creada:
            update_payload["estado"] = True

        res = db.client.table("sucursal_usuaria")\
            .update(update_payload)\
            .eq("id_suc", id_suc)\
            .execute()
        return {"status": "success", "data": res.data}
    except HTTPException:
        raise
    except Exception as e:
        manejar_error(e, 400)

@app.delete("/api/superadmin/sucursales/{id_suc}")
def superadmin_eliminar_sucursal(id_suc: int, id_usuario: Optional[str] = None, usuario_actual: dict = Depends(obtener_usuario_actual)):
    requerir_admin(usuario_actual)

    # Orden deliberado: primero la cuenta de Auth. Si falla, no se toca la fila
    # (la sede queda intacta, se puede reintentar sin haber perdido nada).
    if id_usuario:
        try:
            db.client.auth.admin.delete_user(id_usuario)
        except Exception as e:
            manejar_error(e, 400)

    try:
        db.client.table("sucursal_usuaria").delete().eq("id_suc", id_suc).execute()
    except Exception as e:
        # La cuenta de Auth ya se borró pero la fila no: no lo escondemos,
        # se registra y se avisa explícitamente en vez de dejarlo inconsistente en silencio.
        registrar_evento_seguridad(
            "INCONSISTENCIA_DATOS",
            f"Se eliminó la cuenta Auth {id_usuario} pero falló borrar sucursal_usuaria id_suc={id_suc}: {type(e).__name__}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail="Se eliminó la cuenta de acceso pero no se pudo eliminar el registro de la sede. Contacta a soporte técnico."
        )

    return {"status": "success"}

@app.get("/api/superadmin/anulaciones-solicitudes")
def superadmin_listar_solicitudes(usuario_actual: dict = Depends(obtener_usuario_actual)):
    requerir_admin(usuario_actual)
    try:
        res = db.client.table("anulacion_factura_solicitud")\
            .select("*, sucursal_usuaria!id_sucursal(nombre_suc)")\
            .order("fecha_solicitud", desc=True)\
            .execute()
        return res.data
    except Exception as e:
        manejar_error(e, 500)

@app.put("/api/superadmin/anulaciones-solicitudes/{id_solicitud}/resolver")
def superadmin_resolver_solicitud(id_solicitud: int, data: ResolucionAnulacionRequest, usuario_actual: dict = Depends(obtener_usuario_actual)):
    requerir_admin(usuario_actual)
    try:
        db.client.table("anulacion_factura_solicitud").update({
            "estado": data.estado,
            "observacion_resolucion": data.observacion_resolucion,
            "id_usuario_resuelve": data.id_usuario_resuelve,
            "fecha_resolucion": "now()"
        }).eq("id_solicitud", id_solicitud).execute()

        warnings = []

        if data.estado == "APROBADA":
            solicitud_res = db.client.table("anulacion_factura_solicitud")\
                .select("id_factura, id_sucursal")\
                .eq("id_solicitud", id_solicitud)\
                .execute()

            if solicitud_res.data:
                id_factura = solicitud_res.data[0]["id_factura"]
                id_sucursal = solicitud_res.data[0]["id_sucursal"]

                items_res = db.client.table("detalle_factura")\
                    .select("id_producto, talla, cantidad, producto_catalogo(nombre_item)")\
                    .eq("id_factura", id_factura)\
                    .execute()

                for item in items_res.data:
                    res_stock = db.client.table("inventario_stock")\
                        .select("*")\
                        .eq("id_sucursal", id_sucursal)\
                        .eq("id_producto", item["id_producto"])\
                        .eq("talla", item["talla"])\
                        .execute()

                    disponible = res_stock.data[0]["cantidad_disponible"] if res_stock.data else 0
                    nombre_prod = (item.get("producto_catalogo") or {}).get("nombre_item") or f"Producto #{item['id_producto']}"

                    if disponible < item["cantidad"]:
                        warnings.append(
                            f"Stock insuficiente para anular {item['cantidad']} de '{nombre_prod}' talla {item['talla']} "
                            f"(solo hay {disponible} disponible(s)). Ese ítem no se descontó."
                        )
                        continue

                    fila = res_stock.data[0]
                    db.client.table("inventario_stock").update({
                        "cantidad_disponible": fila["cantidad_disponible"] - item["cantidad"]
                    }).eq("id_stock", fila["id_stock"]).execute()

        return {"status": "success", "message": f"Solicitud procesada como {data.estado}.", "warnings": warnings}
    except Exception as e:
        manejar_error(e, 400)
    
@app.get("/api/superadmin/stock-consolidado-global")
def obtener_stock_consolidado_global(usuario_actual: dict = Depends(obtener_usuario_actual)):
    requerir_admin(usuario_actual)
    try:
        res = db.client.table("inventario_stock")\
            .select("*, sucursal_usuaria(nombre_suc), producto_catalogo(*)")\
            .execute()
        return res.data
    except Exception as e:
        manejar_error(e, 500)
    
@app.get("/api/superadmin/reporte-entregas-global")
async def get_reporte_entregas_global(usuario_actual: dict = Depends(obtener_usuario_actual)):
    requerir_admin(usuario_actual)
    try:
        res = db.client.table("entrega_insumo")\
            .select(
                "id_entrega, fecha_entrega, id_sucursal, "
                "sucursal_usuaria!entrega_insumo_id_sucursal_fkey(nombre_suc), "
                "colaborador(nombre, apellido, rut), "
                "detalle_entrega(cantidad, talla, producto_catalogo(nombre_item, precio_unitario))"
            )\
            .order("fecha_entrega", desc=True)\
            .execute()

        filas = []
        for entrega in res.data:
            suc = entrega.get("sucursal_usuaria") or {}
            colab = entrega.get("colaborador") or {}
            detalles = entrega.get("detalle_entrega") or []

            if not detalles:
                filas.append({
                    "id_entrega": entrega.get("id_entrega"),
                    "fecha_entrega": entrega.get("fecha_entrega"),
                    "id_sucursal": entrega.get("id_sucursal"),
                    "nombre_suc": suc.get("nombre_suc") or f"Sede #{entrega.get('id_sucursal')}",
                    "nombre_colaborador": f"{colab.get('nombre','')} {colab.get('apellido','')}".strip() or "—",
                    "rut_colaborador": colab.get("rut") or "—",
                    "nombre_item": "— sin detalle —",
                    "talla": "-",
                    "cantidad": 0,
                    "precio_unitario": 0,
                    "valor_total": 0
                })
                continue

            for item in detalles:
                prod = item.get("producto_catalogo") or {}
                cantidad = item.get("cantidad") or 0
                precio_unitario = float(prod.get("precio_unitario") or 0)
                filas.append({
                    "id_entrega": entrega.get("id_entrega"),
                    "fecha_entrega": entrega.get("fecha_entrega"),
                    "id_sucursal": entrega.get("id_sucursal"),
                    "nombre_suc": suc.get("nombre_suc") or f"Sede #{entrega.get('id_sucursal')}",
                    "nombre_colaborador": f"{colab.get('nombre','')} {colab.get('apellido','')}".strip() or "—",
                    "rut_colaborador": colab.get("rut") or "—",
                    "nombre_item": prod.get("nombre_item") or "—",
                    "talla": item.get("talla") or "-",
                    "cantidad": cantidad,
                    "precio_unitario": precio_unitario,
                    "valor_total": round(precio_unitario * cantidad, 2)
                })

        return filas
    except Exception as e:
        manejar_error(e, 500)


# --- ENDPOINTS DE TRANSFERENCIAS (LOCAL Y SUPERADMIN) ---

@app.post("/api/sucursal/solicitar-transferencia-stock")
def solicitar_transferencia_stock(data: SolicitudTransferenciaStock, usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, data.id_sucursal_origen)
    try:
        res_stock = db.client.table("inventario_stock").select("cantidad_disponible")\
            .eq("id_sucursal", data.id_sucursal_origen).eq("id_producto", data.id_producto).eq("talla", data.talla).execute()
        
        if not res_stock.data or res_stock.data[0]["cantidad_disponible"] < data.cantidad:
            raise HTTPException(status_code=400, detail="Stock insuficiente en origen para transferir.")

        res = db.client.table("transferencia_stock_solicitud").insert({
            "id_sucursal_origen": data.id_sucursal_origen,
            "id_sucursal_destino": data.id_sucursal_destino,
            "id_producto": data.id_producto,
            "talla": data.talla,
            "cantidad": data.cantidad,
            "motivo": data.motivo,
            "id_usuario_solicita": data.id_usuario_solicita,
            "estado": "PENDIENTE"
        }).execute()
        return {"status": "success", "message": "Solicitud de stock enviada a Jefatura."}
    except Exception as e:
        manejar_error(e, 400)

@app.post("/api/sucursal/solicitar-transferencia-colaborador")
def solicitar_transferencia_colaborador(data: SolicitudTransferenciaColab, usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, data.id_sucursal_origen)
    try:
        res = db.client.table("transferencia_colaborador_solicitud").insert({
            "id_colaborador": data.id_colaborador,
            "id_sucursal_origen": data.id_sucursal_origen,
            "id_sucursal_destino": data.id_sucursal_destino,
            "motivo": data.motivo,
            "id_usuario_solicita": data.id_usuario_solicita,
            "estado": "PENDIENTE"
        }).execute()
        return {"status": "success", "message": "Solicitud de colaborador enviada a Jefatura."}
    except Exception as e:
        manejar_error(e, 400)

@app.get("/api/transferencias/historial/{id_sucursal}")
def obtener_historial_transferencias(id_sucursal: int, usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, id_sucursal)
    try:
        req_stock = db.client.table("transferencia_stock_solicitud")\
            .select("*, producto_catalogo(*), sucursal_usuaria!id_sucursal_destino(nombre_suc)")\
            .eq("id_sucursal_origen", id_sucursal).order("fecha_solicitud", desc=True).execute()
        
        req_colab = db.client.table("transferencia_colaborador_solicitud")\
            .select("*, colaborador(*), sucursal_usuaria!id_sucursal_destino(nombre_suc)")\
            .eq("id_sucursal_origen", id_sucursal).order("fecha_solicitud", desc=True).execute()
            
        return {"stock": req_stock.data, "colaboradores": req_colab.data}
    except Exception as e:
        manejar_error(e, 500)

@app.get("/api/superadmin/transferencias-solicitudes")
def superadmin_listar_transferencias(usuario_actual: dict = Depends(obtener_usuario_actual)):
    requerir_admin(usuario_actual)
    try:
        req_stock = db.client.table("transferencia_stock_solicitud")\
            .select("*, producto_catalogo(*), origen:sucursal_usuaria!id_sucursal_origen(nombre_suc), destino:sucursal_usuaria!id_sucursal_destino(nombre_suc)").order("fecha_solicitud", desc=True).execute()
        
        req_colab = db.client.table("transferencia_colaborador_solicitud")\
            .select("*, colaborador(*), origen:sucursal_usuaria!id_sucursal_origen(nombre_suc), destino:sucursal_usuaria!id_sucursal_destino(nombre_suc)").order("fecha_solicitud", desc=True).execute()
        
        return {"stock": req_stock.data, "colaboradores": req_colab.data}
    except Exception as e:
        manejar_error(e, 500)

@app.put("/api/superadmin/transferencia/{tipo}/{id_solicitud}/resolver")
def superadmin_resolver_transferencia(tipo: str, id_solicitud: int, data: ResolucionTransferenciaRequest, usuario_actual: dict = Depends(obtener_usuario_actual)):
    requerir_admin(usuario_actual)
    try:
        tabla = "transferencia_stock_solicitud" if tipo == "stock" else "transferencia_colaborador_solicitud"
        
        db.client.table(tabla).update({
            "estado": data.estado,
            "observacion_resolucion": data.observacion_resolucion,
            "id_usuario_resuelve": data.id_usuario_resuelve,
            "fecha_resolucion": "now()"
        }).eq("id_solicitud", id_solicitud).execute()

        if data.estado == "APROBADA":
            solicitud = db.client.table(tabla).select("*").eq("id_solicitud", id_solicitud).execute().data[0]
            
            if tipo == "stock":
                stock_orig = db.client.table("inventario_stock").select("*").eq("id_sucursal", solicitud["id_sucursal_origen"]).eq("id_producto", solicitud["id_producto"]).eq("talla", solicitud["talla"]).execute().data[0]
                db.client.table("inventario_stock").update({"cantidad_disponible": stock_orig["cantidad_disponible"] - solicitud["cantidad"]}).eq("id_stock", stock_orig["id_stock"]).execute()
                
                stock_dest = db.client.table("inventario_stock").select("*").eq("id_sucursal", solicitud["id_sucursal_destino"]).eq("id_producto", solicitud["id_producto"]).eq("talla", solicitud["talla"]).execute()
                if stock_dest.data:
                    db.client.table("inventario_stock").update({"cantidad_disponible": stock_dest.data[0]["cantidad_disponible"] + solicitud["cantidad"]}).eq("id_stock", stock_dest.data[0]["id_stock"]).execute()
                else:
                    db.client.table("inventario_stock").insert({"id_sucursal": solicitud["id_sucursal_destino"], "id_producto": solicitud["id_producto"], "talla": solicitud["talla"], "cantidad_disponible": solicitud["cantidad"]}).execute()
                
                db.client.table("transferencia_producto").insert({"id_producto": solicitud["id_producto"], "id_sucursal_origen": solicitud["id_sucursal_origen"], "id_sucursal_destino": solicitud["id_sucursal_destino"], "cantidad": solicitud["cantidad"]}).execute()

            elif tipo == "colaborador":
                db.client.table("colaborador").update({"id_sucursal": solicitud["id_sucursal_destino"]}).eq("id_colaborador", solicitud["id_colaborador"]).execute()
                
                db.client.table("colaborador_movimiento").insert({"id_colaborador": solicitud["id_colaborador"], "id_sucursal_origen": solicitud["id_sucursal_origen"], "id_sucursal_destino": solicitud["id_sucursal_destino"], "motivo": solicitud["motivo"]}).execute()

        return {"status": "success"}
    except Exception as e:
        manejar_error(e, 400)


# --- ENDPOINTS DE LOTES DE TRANSFERENCIA (DISTRIBUCIÓN SUPERADMIN A VARIOS CINES) ---

def _ajustar_stock(id_sucursal: int, id_producto: int, talla: str, delta: int):
    """Suma (o resta, si delta es negativo) cantidad_disponible en inventario_stock."""
    res = db.client.table("inventario_stock").select("*")\
        .eq("id_sucursal", id_sucursal).eq("id_producto", id_producto).eq("talla", talla).execute()

    if res.data:
        fila = res.data[0]
        nueva_cant = fila["cantidad_disponible"] + delta
        if nueva_cant < 0:
            raise HTTPException(status_code=400, detail=f"Stock insuficiente para el producto ID {id_producto} talla {talla}.")
        db.client.table("inventario_stock").update({"cantidad_disponible": nueva_cant}).eq("id_stock", fila["id_stock"]).execute()
    else:
        if delta < 0:
            raise HTTPException(status_code=400, detail=f"Stock insuficiente para el producto ID {id_producto} talla {talla}.")
        db.client.table("inventario_stock").insert({
            "id_sucursal": id_sucursal, "id_producto": id_producto, "talla": talla,
            "cantidad_disponible": delta
        }).execute()

@app.post("/api/superadmin/lote-transferencia")
def crear_lote_transferencia(data: LoteTransferenciaCreate, usuario_actual: dict = Depends(obtener_usuario_actual)):
    requerir_admin(usuario_actual)
    try:
        if not data.items:
            raise HTTPException(status_code=400, detail="El lote debe tener al menos un ítem.")
        if not data.ids_sucursales_destino:
            raise HTTPException(status_code=400, detail="Debes seleccionar al menos un cine destino.")

        n_destinos = len(data.ids_sucursales_destino)

        # Validar stock suficiente en origen para TODOS los destinos antes de tocar nada
        for item in data.items:
            res_stock = db.client.table("inventario_stock").select("cantidad_disponible")\
                .eq("id_sucursal", data.id_sucursal_origen).eq("id_producto", item.id_producto)\
                .eq("talla", item.talla).execute()
            disponible = res_stock.data[0]["cantidad_disponible"] if res_stock.data else 0
            requerido = item.cantidad * n_destinos
            if disponible < requerido:
                raise HTTPException(
                    status_code=400,
                    detail=f"Stock insuficiente para producto ID {item.id_producto} talla {item.talla}: "
                           f"se requieren {requerido} ({item.cantidad} x {n_destinos} cines) y hay {disponible}."
                )

        lotes_creados = []
        for id_destino in data.ids_sucursales_destino:
            res_lote = db.client.table("transferencia_lote").insert({
                "id_sucursal_origen": data.id_sucursal_origen,
                "id_sucursal_destino": id_destino,
                "id_usuario_envia": data.id_usuario_envia,
                "motivo": data.motivo,
                "estado": "EN_TRANSITO"
            }).execute()
            id_lote = res_lote.data[0]["id_lote"]
            lotes_creados.append(id_lote)

            for item in data.items:
                db.client.table("transferencia_lote_detalle").insert({
                    "id_lote": id_lote,
                    "id_producto": item.id_producto,
                    "talla": item.talla,
                    "cantidad": item.cantidad
                }).execute()
                _ajustar_stock(data.id_sucursal_origen, item.id_producto, item.talla, -item.cantidad)

        return {"status": "success", "lotes_creados": len(lotes_creados), "ids_lote": lotes_creados}
    except HTTPException:
        raise
    except Exception as e:
        manejar_error(e, 400)

@app.get("/api/superadmin/lotes-transferencia")
def superadmin_listar_lotes(usuario_actual: dict = Depends(obtener_usuario_actual)):
    requerir_admin(usuario_actual)
    try:
        res = db.client.table("transferencia_lote")\
            .select("*, transferencia_lote_detalle(*, producto_catalogo(*)), "
                    "origen:sucursal_usuaria!id_sucursal_origen(nombre_suc), "
                    "destino:sucursal_usuaria!id_sucursal_destino(nombre_suc)")\
            .order("fecha_envio", desc=True).execute()
        return res.data
    except Exception as e:
        manejar_error(e, 500)

@app.get("/api/sucursal/lotes-transferencia/{id_sucursal}")
def sucursal_listar_lotes(id_sucursal: int, usuario_actual: dict = Depends(obtener_usuario_actual)):
    verificar_acceso_sucursal(usuario_actual, id_sucursal)
    try:
        res = db.client.table("transferencia_lote")\
            .select("*, transferencia_lote_detalle(*, producto_catalogo(*)), "
                    "origen:sucursal_usuaria!id_sucursal_origen(nombre_suc)")\
            .eq("id_sucursal_destino", id_sucursal)\
            .order("fecha_envio", desc=True).execute()
        return res.data
    except Exception as e:
        manejar_error(e, 500)

@app.put("/api/sucursal/lote-transferencia/{id_lote}/resolver")
def resolver_lote_transferencia(id_lote: int, data: ResolucionLoteRequest, usuario_actual: dict = Depends(obtener_usuario_actual)):
    try:
        if data.estado not in ("RECIBIDO", "RECHAZADO"):
            raise HTTPException(status_code=400, detail="Estado inválido.")
        if data.estado == "RECHAZADO" and not (data.observacion_resolucion and data.observacion_resolucion.strip()):
            raise HTTPException(status_code=400, detail="Debes indicar una observación para rechazar el lote.")

        res_lote = db.client.table("transferencia_lote").select("*").eq("id_lote", id_lote).execute()
        if not res_lote.data:
            raise HTTPException(status_code=404, detail="El lote especificado no existe.")
        lote = res_lote.data[0]
        verificar_acceso_sucursal(usuario_actual, lote["id_sucursal_destino"])

        if lote["estado"] != "EN_TRANSITO":
            raise HTTPException(status_code=400, detail="Este lote ya fue resuelto anteriormente.")

        detalle = db.client.table("transferencia_lote_detalle").select("*").eq("id_lote", id_lote).execute().data

        if data.estado == "RECIBIDO":
            for item in detalle:
                _ajustar_stock(lote["id_sucursal_destino"], item["id_producto"], item["talla"], item["cantidad"])
        else:
            for item in detalle:
                _ajustar_stock(lote["id_sucursal_origen"], item["id_producto"], item["talla"], item["cantidad"])

        db.client.table("transferencia_lote").update({
            "estado": data.estado,
            "fecha_resolucion": "now()",
            "id_usuario_recibe": data.id_usuario_recibe,
            "observacion_resolucion": data.observacion_resolucion
        }).eq("id_lote", id_lote).execute()

        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        manejar_error(e, 400)


# --- ENDPOINT LISTAR SUCURSALES (CORREGIDO) ---
@app.get("/api/sucursales-listado")
def listar_sucursales(usuario_actual: dict = Depends(obtener_usuario_actual)):
    # Excluir "Administrador Principal" de la lista de sedes para transferencias
    res = db.client.table("sucursal_usuaria")\
        .select("id_suc, nombre_suc")\
        .neq("nombre_suc", "Administrador Principal")\
        .execute()
    return res.data


# =============================================
# NUEVOS ENDPOINTS PARA GESTIÓN DE CSVs
# =============================================

# --- FUNCIÓN AUXILIAR PARA LIMPIAR CSVs EXPIRADOS (CORREGIDA) ---
def limpiar_csvs_expirados():
    """Elimina archivos CSV expirados y actualiza su estado en la base de datos."""
    try:
        # Usar datetime con timezone UTC para comparar correctamente
        fecha_actual = datetime.now(timezone.utc).isoformat()
        
        # Obtener CSVs expirados
        res = db.client.table("csv_generados")\
            .select("*")\
            .eq("estado", "ACTIVO")\
            .lt("fecha_expiracion", fecha_actual)\
            .execute()
        
        for csv_exp in res.data:
            # Eliminar archivo físico
            archivo_path = Path(csv_exp["ruta_archivo"])
            if archivo_path.exists():
                archivo_path.unlink()
            
            # Actualizar estado en BD
            db.client.table("csv_generados")\
                .update({"estado": "EXPIRADO"})\
                .eq("id_csv", csv_exp["id_csv"])\
                .execute()
        
        # Eliminar registros expirados antiguos (más de 90 días)
        fecha_limite = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        db.client.table("csv_generados")\
            .delete()\
            .eq("estado", "EXPIRADO")\
            .lt("fecha_expiracion", fecha_limite)\
            .execute()
            
    except Exception as e:
        print(f"⚠️ Error al limpiar CSVs expirados: {str(e)}")


# --- ENDPOINTS PARA CSVs (CORREGIDOS) ---

@app.post("/api/sucursal/csv-entregas/generar")
def generar_csv_entregas(data: CSVGeneradoRequest, usuario_actual: dict = Depends(obtener_usuario_actual)):
    """
    Genera un archivo CSV con los datos de las entregas seleccionadas.
    """
    verificar_acceso_sucursal(usuario_actual, data.id_sucursal)
    try:
        # 1. Generar folio único
        fecha_actual = datetime.now()
        fecha_actual_str = fecha_actual.strftime("%Y%m%d")
        hora_actual = fecha_actual.strftime("%H%M%S")
        folio = f"CSV-{fecha_actual_str}-{hora_actual}"
        
        # 2. Obtener datos de las entregas seleccionadas
        entregas_data = []
        
        for id_entrega in data.id_entregas:
            # Consultar datos de la entrega con todos los detalles necesarios
            res_entrega = db.client.table("entrega_insumo")\
                .select(
                    "id_entrega, fecha_entrega, "
                    "colaborador(rut, nombre, apellido), "
                    "detalle_entrega(cantidad, talla, producto_catalogo(nombre_item))"
                )\
                .eq("id_entrega", id_entrega)\
                .execute()
            
            if res_entrega.data:
                entrega = res_entrega.data[0]
                colab = entrega.get("colaborador", {})
                detalles = entrega.get("detalle_entrega", [])
                
                # Si la entrega no tiene detalles, la saltamos
                if not detalles:
                    continue
                
                for detalle in detalles:
                    prod = detalle.get("producto_catalogo", {})
                    # Formatear fecha correctamente
                    fecha_entrega = entrega.get("fecha_entrega", "")
                    if fecha_entrega:
                        try:
                            # Si es string ISO, convertir a datetime y formatear
                            if isinstance(fecha_entrega, str):
                                dt = datetime.fromisoformat(fecha_entrega.replace('Z', '+00:00'))
                                fecha_entrega = dt.strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            pass
                    
                    entregas_data.append({
                        "folio": folio,
                        "fecha_entrega": fecha_entrega,
                        "rut_trabajador": colab.get("rut", ""),
                        "nombre_trabajador": f"{colab.get('nombre', '')} {colab.get('apellido', '')}".strip(),
                        "sucursal": data.id_sucursal,
                        "producto": prod.get("nombre_item", ""),
                        "talla": detalle.get("talla", ""),
                        "cantidad": detalle.get("cantidad", 0)
                    })
        
        if not entregas_data:
            raise HTTPException(
                status_code=400, 
                detail="No se encontraron entregas válidas con detalles de productos"
            )
        
        # 3. Crear directorio para CSVs si no existe
        csv_dir = CURRENT_DIR / "csv_generados"
        csv_dir.mkdir(exist_ok=True)
        
        # 4. Generar archivo CSV con encoding UTF-8 con BOM para Excel
        archivo_nombre = f"{folio}.csv"
        archivo_path = csv_dir / archivo_nombre
        
        # Escribir el archivo CSV con la estructura requerida
        with open(archivo_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=[
                "folio", "fecha_entrega", "rut_trabajador", "nombre_trabajador",
                "sucursal", "producto", "talla", "cantidad"
            ])
            writer.writeheader()
            writer.writerows(entregas_data)
        
        # 5. Calcular fecha de expiración (30 días) con timezone UTC
        fecha_generacion = datetime.now(timezone.utc)
        fecha_expiracion = fecha_generacion + timedelta(days=30)
        
        # 6. Registrar en base de datos
        res_registro = db.client.table("csv_generados").insert({
            "folio": folio,
            "id_sucursal": data.id_sucursal,
            "id_usuario_genera": data.id_usuario,
            "fecha_generacion": fecha_generacion.isoformat(),
            "fecha_expiracion": fecha_expiracion.isoformat(),
            "cantidad_registros": len(entregas_data),
            "ruta_archivo": str(archivo_path),
            "estado": "ACTIVO"
        }).execute()
        
        # 7. Limpiar CSVs expirados
        limpiar_csvs_expirados()
        
        return {
            "status": "success",
            "folio": folio,
            "fecha_generacion": fecha_generacion.strftime("%Y-%m-%d %H:%M:%S"),
            "cantidad_registros": len(entregas_data),
            "mensaje": f"CSV generado exitosamente con folio {folio}",
            "url_descarga": f"/api/sucursal/csv-entregas/descargar/{folio}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar CSV: {str(e)}")


@app.get("/api/sucursal/csv-entregas/historial/{id_sucursal}")
def listar_csv_generados(id_sucursal: int, usuario_actual: dict = Depends(obtener_usuario_actual)):
    """
    Lista todos los CSVs activos (no expirados) generados por una sucursal.
    """
    verificar_acceso_sucursal(usuario_actual, id_sucursal)
    try:
        # Obtener CSVs activos y no expirados
        fecha_actual = datetime.now(timezone.utc).isoformat()
        res = db.client.table("csv_generados")\
            .select("*")\
            .eq("id_sucursal", id_sucursal)\
            .eq("estado", "ACTIVO")\
            .gte("fecha_expiracion", fecha_actual)\
            .order("fecha_generacion", desc=True)\
            .execute()
        
        # Formatear fechas para el frontend
        for item in res.data:
            if item.get("fecha_generacion"):
                try:
                    dt = datetime.fromisoformat(item["fecha_generacion"])
                    item["fecha_generacion"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass
            if item.get("fecha_expiracion"):
                try:
                    dt = datetime.fromisoformat(item["fecha_expiracion"])
                    item["fecha_expiracion"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass
        
        return res.data
    except Exception as e:
        manejar_error(e, 500)


@app.get("/api/sucursal/csv-entregas/descargar/{folio}")
def descargar_csv(folio: str, usuario_actual: dict = Depends(obtener_usuario_actual)):
    """
    Descarga un archivo CSV por su folio.
    """
    try:
        # Buscar el registro en BD
        res = db.client.table("csv_generados")\
            .select("*")\
            .eq("folio", folio)\
            .eq("estado", "ACTIVO")\
            .execute()

        if not res.data:
            raise HTTPException(status_code=404, detail="CSV no encontrado o expirado")

        csv_data = res.data[0]
        verificar_acceso_sucursal(usuario_actual, csv_data["id_sucursal"])

        # Verificar fecha de expiración
        fecha_expiracion = datetime.fromisoformat(csv_data["fecha_expiracion"])
        if datetime.now(timezone.utc) > fecha_expiracion:
            # Marcar como expirado
            db.client.table("csv_generados")\
                .update({"estado": "EXPIRADO"})\
                .eq("folio", folio)\
                .execute()
            raise HTTPException(status_code=410, detail="CSV expirado")
        
        # Verificar que el archivo existe
        archivo_path = Path(csv_data["ruta_archivo"])
        if not archivo_path.exists():
            raise HTTPException(status_code=404, detail="Archivo físico no encontrado")
        
        return FileResponse(
            path=str(archivo_path),
            media_type="text/csv",
            filename=f"{folio}.csv"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        manejar_error(e, 500)


@app.delete("/api/sucursal/csv-entregas/eliminar/{folio}")
def eliminar_csv(folio: str, usuario_actual: dict = Depends(obtener_usuario_actual)):
    """
    Elimina manualmente un archivo CSV y su registro en la base de datos.
    """
    try:
        res = db.client.table("csv_generados")\
            .select("*")\
            .eq("folio", folio)\
            .execute()

        if not res.data:
            raise HTTPException(status_code=404, detail="CSV no encontrado")

        csv_data = res.data[0]
        verificar_acceso_sucursal(usuario_actual, csv_data["id_sucursal"])

        # Eliminar archivo físico
        archivo_path = Path(csv_data["ruta_archivo"])
        if archivo_path.exists():
            archivo_path.unlink()
        
        # Eliminar registro de BD
        db.client.table("csv_generados")\
            .delete()\
            .eq("folio", folio)\
            .execute()
        
        return {"status": "success", "message": "CSV eliminado correctamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        manejar_error(e, 500)