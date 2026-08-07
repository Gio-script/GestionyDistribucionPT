import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client
from types import SimpleNamespace
import httpx

# Construir la ruta absoluta hacia el archivo .env basado en la ubicación de este script
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

class SupabaseManager:
    def __init__(self):
        """Inicializa la conexión con Supabase utilizando las variables de entorno."""
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # debe ser la service_role, no la anon

        if not url or not key:
            raise ValueError(
                "❌ Error crítico: SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY no están configuradas en el archivo .env.\n"
                "Por favor, revisa que el archivo exista y tenga las credenciales correctas."
            )

        self._url = url
        self._key = key

        # Crear e inicializar el cliente de Supabase (uso exclusivo: operaciones con service_role)
        self.client: Client = create_client(url, key)

    def login_user(self, email: str, password: str):
        """
        Autentica al usuario mediante una llamada HTTP aislada (NO usa
        self.client.auth, para evitar que la sesión del usuario reemplace
        la sesión de service_role del cliente compartido que usan las
        operaciones de administrador en main.py).
        Retorna un objeto con .user y .session (compatible con el uso previo),
        o None si falla.
        """
        try:
            resp = httpx.post(
                f"{self._url}/auth/v1/token?grant_type=password",
                headers={"apikey": self._key, "Content-Type": "application/json"},
                json={"email": email, "password": password},
                timeout=10
            )
        except Exception as e:
            print(f"❌ Error en Supabase Auth: {e}")
            return None

        if resp.status_code != 200:
            return None

        body = resp.json()
        user_data = body.get("user") or {}
        if not user_data.get("id"):
            return None

        user = SimpleNamespace(id=user_data.get("id"), email=user_data.get("email"))
        session = SimpleNamespace(
            access_token=body.get("access_token"),
            refresh_token=body.get("refresh_token")
        )
        return SimpleNamespace(user=user, session=session)

    def verificar_token(self, access_token: str):
        """
        Valida un access_token de Supabase Auth mediante una llamada HTTP aislada
        (NO usa self.client.auth, para evitar contaminar la sesión del cliente
        compartido que main.py usa con la service_role key para operaciones de
        administrador). Retorna el perfil (rol, sucursal) o None si es inválido.
        """
        try:
            resp = httpx.get(
                f"{self._url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "apikey": self._key
                },
                timeout=10
            )
        except Exception:
            return None

        if resp.status_code != 200:
            return None

        user_id = resp.json().get("id")
        if not user_id:
            return None

        res_perfil = self.client.table("sucursal_usuaria")\
            .select("*")\
            .eq("id_usuario", user_id)\
            .execute()

        if not res_perfil.data:
            return None

        return res_perfil.data[0]

    def get_user_role(self, user_id: str):
        """
        Busca el rol y la sucursal del usuario en la tabla pública 'sucursal_usuaria'
        filtrando por su UUID de autenticación (id_usuario).
        """
        try:
            response = self.client.table("sucursal_usuaria")\
                .select("rol, nombre_suc")\
                .eq("id_usuario", user_id)\
                .execute()

            # Si la consulta devuelve datos, retornamos el primer registro encontrado
            if response.data and len(response.data) > 0:
                return response.data[0]  # Ejemplo: {'rol': 'admin', 'nombre_suc': 'Central'}
            return None
        except Exception as e:
            print(f"❌ Error al consultar rol en BD: {e}")
            return None