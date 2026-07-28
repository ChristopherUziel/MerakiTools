import json
import sys
from getpass import getpass
from pathlib import Path

import keyring
import requests

from validacion_api import validar_api_key

SERVICIO_CREDENCIAL = "MerakiTools"
USUARIO_CREDENCIAL = "meraki_api_key"


def obtener_carpeta_base() -> Path:
    """
    Devuelve la carpeta principal de MerakiTools.
    """

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


CARPETA_BASE = obtener_carpeta_base()

CONFIG_FILE = CARPETA_BASE / "config" / "settings.json"


def cargar_configuracion() -> dict:
    """
    Lee la configuración guardada en config/settings.json.
    """

    if not CONFIG_FILE.exists():
        raise FileNotFoundError("No se encontró config/settings.json.")

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as archivo:
            configuracion = json.load(archivo)

    except json.JSONDecodeError as error:
        raise ValueError("El archivo settings.json no contiene JSON válido.") from error

    return configuracion


def obtener_api_key() -> str:
    """
    Obtiene la API Key desde el almacén de credenciales
    de Windows.
    """

    api_key = keyring.get_password(
        SERVICIO_CREDENCIAL,
        USUARIO_CREDENCIAL,
    )

    if not api_key:
        raise ValueError("La API Key todavía no ha sido configurada.")

    return api_key.strip()


def guardar_api_key(api_key: str) -> None:
    """
    Guarda la API Key en el almacén seguro de Windows.
    """

    api_key = api_key.strip()

    if not api_key:
        raise ValueError("La API Key no puede estar vacía.")

    keyring.set_password(
        SERVICIO_CREDENCIAL,
        USUARIO_CREDENCIAL,
        api_key,
    )


def configurar_api_key_si_es_necesario() -> None:
    """
    Solicita y valida la API Key cuando todavía no está
    registrada en las credenciales de Windows.

    La clave se guarda únicamente después de que Meraki
    confirma que es válida.
    """

    api_key_actual = keyring.get_password(
        SERVICIO_CREDENCIAL,
        USUARIO_CREDENCIAL,
    )

    if api_key_actual:
        return

    print("\n=== CONFIGURACIÓN INICIAL ===\n")
    print("No se encontró una API Key guardada " "para este usuario de Windows.")

    while True:
        print("\nPara pegarla, usa clic derecho o Editar > Pegar. NO USAR CTRL + V")

        api_key = getpass("\nIngresa tu API Key de Meraki:\n> ").strip()

        if not api_key:
            print("\nNo se ingresó ninguna API Key. " "Inténtalo nuevamente.")
            continue

        print("\nValidando API Key con Meraki...")

        try:
            identidad = validar_api_key(api_key)

        except requests.HTTPError as error:
            codigo_estado = (
                error.response.status_code if error.response is not None else None
            )

            if codigo_estado in (401, 403):
                print(
                    "\nLa API Key no es válida o no está "
                    "autorizada. Verifica la clave e "
                    "inténtalo nuevamente."
                )
            else:
                print(
                    "\nMeraki rechazó la consulta. "
                    f"Código HTTP: {codigo_estado or 'desconocido'}."
                )

            continue

        except requests.ConnectionError:
            print(
                "\nNo fue posible conectarse con Meraki. "
                "Verifica la conexión a Internet e "
                "inténtalo nuevamente."
            )
            continue

        except requests.Timeout:
            print("\nLa consulta a Meraki tardó demasiado. " "Inténtalo nuevamente.")
            continue

        except requests.RequestException as error:
            print("\nOcurrió un error al validar la API Key: " f"{error}")
            continue

        guardar_api_key(api_key)

        nombre_usuario = identidad.get("name") or "usuario"

        print("\nAPI Key validada y guardada correctamente.")
        print(f"\nHola, {nombre_usuario}.\n")

        return


def cambios_habilitados() -> bool:
    """
    Indica si el programa tiene autorización para ejecutar
    operaciones que modifican el Dashboard.
    """

    configuracion = cargar_configuracion()

    return configuracion.get("permitir_cambios", False) is True
