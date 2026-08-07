# Gestión y Distribución de Uniformes — Cinépolis

SaaS interno para la gestión de stock, entregas, transferencias y dotación de uniformes entre sucursales Cinépolis. Backend en Python (FastAPI) + Supabase (PostgreSQL + Auth), frontend servido como HTML estático/dinámico desde el propio backend.

## 1. Arquitectura

```
Navegador
   │
   ▼
IIS (puerto 80, http://10.1.43.206/)
   │  proxy inverso (ARR + URL Rewrite)
   ▼
uvicorn (127.0.0.1:8000) — servicio de Windows "GestionDistribucionUvicorn"
   │
   ▼
main.py (FastAPI) ──► database.py (SupabaseManager) ──► Supabase (Postgres + Auth)
```

- **Backend**: FastAPI (`main.py`), expone vistas HTML (`/`, `/login`, `/dashboard`, `/superadmin`) y una API REST bajo `/api/...`.
- **Base de datos**: Supabase (Postgres gestionado) — no hay base de datos local. Toda persistencia y autenticación vive en Supabase.
- **Autenticación**: Supabase Auth (`auth.users`), con datos de rol/sucursal en la tabla propia `sucursal_usuaria`.
- **Frontend**: 3 páginas HTML servidas directamente por FastAPI vía `FileResponse` (no usa motor de templates Jinja2):
  - `templates/login.html`
  - `templates/dashboard_local.html` (vista de sucursal)
  - `templates/superadmin.html` (vista administrador global)
- **Estáticos**: `/images` montado como `StaticFiles`.

## 2. Librerías usadas (`requirements.txt`)

| Librería | Uso |
|---|---|
| `fastapi` | Framework web / API REST |
| `uvicorn` | Servidor ASGI que ejecuta la app en producción |
| `a2wsgi` | Adaptador ASGI→WSGI (quedó en el código de una integración anterior con IIS/FastCGI, ya no se usa en el despliegue actual) |
| `pydantic` | Validación de modelos de entrada/salida de la API |
| `python-dotenv` | Carga de variables desde `.env` |
| `supabase` (+ `postgrest`, `supabase-auth`, `supabase-functions`, `storage3`, `realtime`) | Cliente oficial de Supabase (DB, Auth, Storage) |
| `httpx` | Cliente HTTP (usado internamente por el SDK de Supabase) |
| `pyjwt`, `cryptography` | Verificación de tokens JWT de Supabase Auth |

Instalación: entorno virtual `.venv` dentro del proyecto (`python -m venv .venv`), dependencias instaladas con `pip install -r requirements.txt`. Python 3.14.

## 3. Variables de entorno (`.env`)

Archivo `.env` en la raíz del proyecto (no versionar / no compartir):

| Variable | Descripción |
|---|---|
| `SUPABASE_URL` | URL del proyecto Supabase |
| `SUPABASE_KEY` | Clave anon (pública) de Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | Clave **service_role** — usada por `database.py` para operaciones con privilegios elevados. Nunca exponerla al frontend. |

`database.py` valida al iniciar que `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` existan; si faltan, la app no arranca.

## 4. Estructura de carpetas relevantes

```
main.py                # App FastAPI + todos los endpoints
database.py             # Cliente Supabase (SupabaseManager: login, roles)
schema.sql               # Referencia del esquema de Supabase (no ejecutable tal cual)
templates/                # Vistas HTML (login, dashboard sucursal, superadmin)
images/                    # Estáticos servidos en /images
logs/                        # Logs de la app en producción (uvicorn.log, uvicorn.err.log)
csv_generados/                 # CSVs de entregas generados y registrados en Supabase (tabla csv_generados)
.venv/                          # Entorno virtual Python (no versionar)
tools/nssm.exe                   # Wrapper usado para correr uvicorn como servicio de Windows
web.config                        # Configuración del proxy inverso IIS → uvicorn
```

## 5. Endpoints principales (`/api/...`)

Agrupados por dominio funcional:

- **Auth**: `POST /api/login`
- **Colaboradores**: alta/baja/edición individual y masiva, dotación consolidada por colaborador y por sucursal
- **Catálogo e inventario**: catálogo de productos, inventario completo/disponible por sucursal, stock consolidado global (superadmin)
- **Facturas de ingreso**: alta de factura con detalle, historial por sucursal, solicitud y resolución de anulaciones
- **Entregas**: entregas masivas a colaboradores, historial de entregas, reporte global (superadmin)
- **Salidas de stock**: merma, extravío, renuncia sin devolución, transferencia, devolución a proveedor
- **Transferencias**: de stock y de colaboradores entre sucursales (con flujo de solicitud/resolución), transferencias por lote
- **Sucursales**: listado, alta (superadmin)
- **Notificaciones** y **CSV de entregas** (generación, historial, descarga, eliminación con expiración)

Roles: `admin` (superadmin, visión global) y `usuario` (acotado a su sucursal), definidos en `sucursal_usuaria.rol`.

## 6. Esquema de base de datos (Supabase / Postgres)

Ver `schema.sql` para el detalle completo (columnas, checks, FKs). Tablas principales:

- `sucursal_usuaria` — sucursales + usuario/rol asociado (vínculo con `auth.users`)
- `colaborador` — dotación de personal por sucursal
- `producto_catalogo` — catálogo de prendas/insumos (talla, categoría, tipo, precio)
- `inventario_stock` — stock disponible/merma por sucursal, producto y talla
- `factura_ingreso` + `detalle_factura` — ingresos de mercadería por proveedor
- `entrega_insumo` + `detalle_entrega` — entregas de uniformes a colaboradores (con firma digital)
- `colaborador_stock_dotacion` — qué tiene en uso cada colaborador
- `salida_stock` — mermas, extravíos, devoluciones a proveedor
- `transferencia_producto` / `transferencia_stock_solicitud` / `transferencia_lote(_detalle)` — movimiento de stock entre sucursales
- `transferencia_colaborador(_solicitud)` / `colaborador_movimiento` — traslado de colaboradores entre sucursales
- `anulacion_factura_solicitud` + `anulacion_factura_detalle_revision` — flujo de anulación de facturas
- `notificacion` — notificaciones internas por sucursal
- `csv_generados` — control de CSVs exportados (con expiración)

## 7. Despliegue en IIS (Windows Server — `PROYECTOSCHILE`)

### Decisión de arquitectura

Se intentó primero el enfoque clásico **wfastcgi** (FastCGI puro sobre IIS), pero el proceso Python moría de forma intermitente antes de ejecutar cualquier línea de código, con errores de bajo nivel (`ERROR_DIRECTORY`, `ERROR_FILE_NOT_FOUND`) que persistían incluso corriendo el App Pool como `LocalSystem`. Se descartó por ser un proyecto sin mantenimiento activo, frágil en combinaciones recientes de Windows/Python. Se optó por el patrón moderno **reverse proxy**: la app corre nativamente con `uvicorn` y IIS solo enruta el tráfico.

### Componentes instalados en el servidor

- **Windows Feature `Web-CGI`**: habilitado (quedó de la prueba con wfastcgi, no se usa actualmente pero no estorba).
- **URL Rewrite Module** (Microsoft, oficial): instalado.
- **Application Request Routing — ARR** (Microsoft, oficial): instalado, con `system.webServer/proxy enabled="true"` a nivel de servidor.
- **NSSM** (`tools/nssm.exe` dentro del proyecto): envoltorio usado para registrar `uvicorn` como servicio de Windows.

### Sitio IIS

- Nombre: **`Gestion y Distribucion`**
- Ruta física: `c:\inetpub\wwwroot\Gestion y Distribucion`
- Application Pool: `GestionDistribucionAppPool` (sin código administrado, ya que solo hace de proxy)
- Binding: `http://10.1.43.206:80` (IP fija del servidor; no se usó hostname porque el servidor está en `WORKGROUP`, sin DNS interno)
- `web.config`: una única regla de `URL Rewrite` que reenvía todo el tráfico a `http://127.0.0.1:8000/{R:1}`

### Servicio de la aplicación

- Nombre del servicio de Windows: **`GestionDistribucionUvicorn`**
- Comando: `.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000`
- Tipo de inicio: **Automático** (arranca solo al prender el servidor, sin necesidad de login)
- Reinicio automático ante caída (configurado vía NSSM)
- Logs: `logs\uvicorn.log` (salida estándar) y `logs\uvicorn.err.log` (errores), con rotación a 5 MB

### Persistencia ante reinicios del servidor

No requiere intervención manual: `W3SVC` (IIS) y `GestionDistribucionUvicorn` están ambos configurados como servicios de **inicio automático**. Si el servidor se apaga y se vuelve a prender, ambos arrancan solos y el sitio vuelve a responder en `http://10.1.43.206/` sin que nadie tenga que ejecutar nada.

### Cómo actualizar el código en producción

1. Reemplazar/editar los archivos en `c:\inetpub\wwwroot\Gestion y Distribucion`.
2. Si cambiaron las dependencias: `.venv\Scripts\python.exe -m pip install -r requirements.txt`.
3. Reiniciar el servicio para que tome los cambios:
   ```powershell
   Restart-Service GestionDistribucionUvicorn
   ```
   (IIS no necesita reiniciarse, solo actúa como proxy).

### Diagnóstico rápido

```powershell
Get-Service GestionDistribucionUvicorn, W3SVC
Get-Content "c:\inetpub\wwwroot\Gestion y Distribucion\logs\uvicorn.err.log" -Tail 50
curl.exe -s -o NUL -w "STATUS: %{http_code}`n" http://10.1.43.206/login
```

## 8. Registro del sitio en IIS — qué se hizo y qué falta revisar

Resumen de todo lo que se configuró a nivel de servidor para dejar este proyecto corriendo en IIS, y los puntos importantes a tener en cuenta (algunos no tienen que ver con la app en sí, sino con el servidor completo).

### 8.1 Qué se registró para este proyecto

| Componente | Detalle |
|---|---|
| Sitio IIS | `Gestion y Distribucion`, físico en `c:\inetpub\wwwroot\Gestion y Distribucion` |
| Application Pool | `GestionDistribucionAppPool` (sin código administrado — solo hace de proxy) |
| Binding | `http://10.1.43.206:80` — **sin HTTPS, sin certificado** |
| Servicio de Windows | `GestionDistribucionUvicorn` (arranque automático, se reinicia solo si falla) |
| Módulos IIS instalados | URL Rewrite + Application Request Routing (ARR), oficiales de Microsoft, habilitados para hacer de proxy inverso hacia `uvicorn` |
| Certificado SSL propio | **No existe.** El tráfico (incluidas las contraseñas que se escriben en el login y en "Editar Perfil Sede") viaja sin cifrar por la red interna. |

### 8.2 ⚠️ Lo más urgente — no es de este proyecto, es del servidor completo

El sistema operativo **Windows Server 2019** de esta máquina (`PROYECTOSCHILE`) está activado con una **licencia de evaluación por tiempo limitado** (`ServerStandardEval`, canal `TIMEBASED_EVAL`), no con una licencia definitiva:

```
Estado de la licencia: con licencia
Expiración de la activación con límite de tiempo: 171 día(s)
```

Esto afecta a **los 4 sitios que corren en este servidor** (el nuestro, `CRM_QA-V2.1`, `InventarioTI` y el Default Web Site), no solo a "Gestión y Distribución". Cuando venza, Windows puede empezar a apagarse solo periódicamente o bloquear funciones hasta reactivarlo. Hay que gestionar con TI corporativo una licencia real (Volume Licensing / Datacenter/Standard con clave propia) bastante antes de que se cumplan los 171 días, o el servidor completo (no solo esta app) queda en riesgo.

Verificar el estado actual en cualquier momento:
```powershell
cscript //nologo C:\Windows\System32\slmgr.vbs /dli
```

### 8.3 Sobre el certificado de 5 años que viste

Ese certificado (`CN=10.1.43.206`, válido 2026–2031) **no es de este proyecto**. Pertenece al sitio `CRM_QA-V2.1`, que corre en el mismo servidor con binding HTTPS en el puerto 443. Es un certificado **autofirmado** (no emitido por una entidad certificadora real), así que aunque exista, cualquier navegador lo va a marcar como "no seguro" / "no confiable" igual — autofirmarlo no resuelve el problema de confianza, solo cifra el tráfico.

### 8.4 HTTPS agregado (autofirmado)

Se agregó un certificado autofirmado propio para este proyecto, sin tocar el binding 443 que ya usa `CRM_QA-V2.1`:

| Detalle | Valor |
|---|---|
| Certificado | `CN=10.1.43.206`, autofirmado, en `Cert:\LocalMachine\My` |
| Thumbprint | `ACB5F2AE1BE7B2F0F5289903E056DFC510E1F8E3` |
| Vigencia | 31-07-2026 → 31-07-2031 (5 años) |
| Binding nuevo | `https://10.1.43.206:8443` |
| Binding original | `http://10.1.43.206` (puerto 80) — sigue funcionando igual que antes |

El sitio ahora responde en **ambos**: `http://10.1.43.206/` (sin cifrar, como hasta ahora) y `https://10.1.43.206:8443/` (cifrado). Al ser autofirmado, el navegador va a mostrar una advertencia de "certificado no confiable" la primera vez — es esperado, hay que aceptar/continuar manualmente. No requirió cambios en `web.config` ni en la app: IIS termina el TLS antes de reenviar a `uvicorn` igual que con HTTP.

Pendiente si se quiere resolver la advertencia del navegador: obtener un certificado real (CA corporativa interna, o pasar el binding a un hostname DNS real + certificado público) en vez del autofirmado.

## 9. Controles ISO 27001 aplicados

### 9.1 Autorización real en la API (A.9 - Control de acceso)

Antes de este cambio, cualquier endpoint de la API confiaba ciegamente en el `id_sucursal` que mandaba el navegador (guardado en `localStorage`), sin verificar nada en el servidor. Cualquiera que supiera la URL podía operar sobre cualquier sede sin haber iniciado sesión.

Se implementó:
- `POST /api/login` ahora devuelve un `access_token` real de Supabase Auth.
- Un mecanismo (`obtener_usuario_actual` en `main.py`) que valida ese token en **cada** llamada a la API y determina el rol/sucursal real del usuario desde el servidor, no desde lo que mande el navegador.
- Cada endpoint exige ese token (401 si falta o es inválido) y verifica que el usuario solo opere sobre su propia sucursal (403 si intenta acceder a otra), salvo el rol `admin` que puede operar sobre todas.
- El frontend (`dashboard_local.html`, `superadmin.html`) manda el token automáticamente en cada request vía un interceptor de `fetch`, sin tener que modificar cada llamada individual.

### 9.2 Política de contraseñas (A.9.4)

Toda contraseña nueva o modificada (creación de sede o cambio de clave) debe tener mínimo 8 caracteres, incluir al menos una letra, un número y un carácter especial. Validado tanto en el navegador (`passwordEsSegura()` en `superadmin.html`) como en el servidor (`validar_password_segura()` en `main.py`) — la validación del navegador es solo para feedback inmediato, la del servidor es la que realmente protege, ya que el navegador se puede saltar.

### 9.3 Bug crítico encontrado durante las pruebas: sesión de administrador contaminada

Al implementar el punto 9.1, empezó a fallar la creación/edición de cuentas de sedes con el error `"User not allowed"` (Supabase devolvía `code: not_admin, status: 403`). Diagnóstico: `database.py` reutilizaba el **mismo cliente de Supabase** (`self.client`, configurado con la clave `service_role` para operaciones de administrador) tanto para las operaciones de admin como para autenticar usuarios en el login normal. Al iniciar sesión un usuario cualquiera, `self.client.auth.sign_in_with_password(...)` reemplazaba la sesión interna del cliente compartido por la de ese usuario regular — así, cualquier operación de administrador posterior (crear/actualizar cuentas) se ejecutaba con privilegios de usuario normal en vez de `service_role`, y Supabase la rechazaba.

**Corrección**: `login_user()` y `verificar_token()` en `database.py` ahora hacen sus propias llamadas HTTP aisladas (vía `httpx`) directo a la API de Supabase Auth, sin tocar `self.client`. El cliente compartido queda dedicado exclusivamente a operaciones con `service_role`, sin que ninguna autenticación de usuario pueda contaminarlo. Verificado con pruebas automatizadas: creación de cuenta, actualización de contraseña, acceso a sede propia (200), acceso a sede ajena (403), sin token (401) — todo funcionando correctamente tras el fix.

### 9.4 Row Level Security (RLS) en Postgres — defensa adicional (A.9)

Script en `migrations/2026_rls_policies.sql`, para pegar en el SQL Editor de Supabase. Cada usuario solo ve datos de su propia sucursal; las tablas de transferencias (stock, colaborador, lote) son visibles tanto para la sede origen como destino; `admin` ve y administra todo. No cambia el comportamiento actual de la app (el backend usa `service_role`, que ignora RLS por diseño) — es una capa de defensa para cualquier conexión futura con una clave de menor privilegio.

### 9.5 Mensajes de error genéricos (A.14.2)

Los 39 endpoints que devolvían `detail=str(e)` (el error crudo de Python/Postgres/Supabase) ahora pasan por `manejar_error()`: al cliente le llega un mensaje genérico ("No se pudo procesar la solicitud." / "Error interno del servidor."), y el detalle técnico real se registra en `logs/seguridad.log` para que quede disponible para diagnóstico sin exponerlo a quien provocó el error.

### 9.6 Protección contra fuerza bruta en `/api/login` (A.9.4)

Máximo 5 intentos fallidos por correo en una ventana de 15 minutos; al superarlo, responde `429` con el tiempo de espera. El contador vive en memoria del proceso (se reinicia si el servicio se reinicia — suficiente dado que corre como un solo proceso) y se limpia automáticamente al iniciar sesión con éxito.

### 9.7 Registro de auditoría de seguridad (A.12.4)

Nuevo archivo `logs/seguridad.log`, separado de los logs normales de la app, con marca de tiempo UTC. Registra: login fallido, bloqueo por fuerza bruta, acceso sin token, token inválido/expirado, cuenta deshabilitada, acceso denegado por sucursal, acceso denegado por rol de administrador, e inconsistencias de datos (ver 9.8). No requiere tabla nueva en Supabase ni cambios de esquema.

### 9.8 `DELETE /api/superadmin/sucursales/{id}` ahora es más seguro ante fallos parciales

Antes borraba primero la fila de la tabla y después la cuenta de Auth — si el segundo paso fallaba (nos pasó de verdad durante las pruebas), la sede desaparecía y quedaba una cuenta huérfana sin ningún aviso. Ahora el orden es al revés (Auth primero): si falla, la sede queda intacta y se puede reintentar sin haber perdido nada. Si el paso de Auth tiene éxito pero falla el borrado de la fila (mucho menos probable), se lo indica explícitamente al admin en vez de fallar en silencio, y queda registrado en `logs/seguridad.log` como `INCONSISTENCIA_DATOS`.

### 9.9 Pendiente (no implementado aún)

- Política de backups documentada para la base de datos.
- Política de retención de datos personales de colaboradores.
- MFA para cuentas de administrador.



# COLABORADOR A CARGO 
# GIOVANNI DONOSO PRACTICANTE EN SISTEMAS 2026 GDNOSO7@GMAIL.COM, +56941770349