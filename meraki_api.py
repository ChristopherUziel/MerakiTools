import requests

from config import obtener_api_key

BASE_URL = "https://api.meraki.com/api/v1"


def crear_headers() -> dict:
    """
    Construye los encabezados necesarios para autenticar
    las solicitudes a Meraki.
    """

    return {
        "X-Cisco-Meraki-API-Key": obtener_api_key(),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def obtener_organizaciones() -> list[dict]:
    """
    Obtiene las organizaciones disponibles para el usuario.
    """

    respuesta = requests.get(
        f"{BASE_URL}/organizations",
        headers=crear_headers(),
        timeout=20,
    )

    respuesta.raise_for_status()

    return respuesta.json()


def obtener_networks(organization_id: str) -> list[dict]:
    """
    Obtiene las redes a las que el usuario tiene acceso
    dentro de una organización.
    """

    respuesta = requests.get(
        f"{BASE_URL}/organizations/{organization_id}/networks",
        headers=crear_headers(),
        timeout=20,
    )

    respuesta.raise_for_status()

    return respuesta.json()


def obtener_dispositivos_inventario(
    organization_id: str,
    seriales: list[str],
) -> list[dict]:
    """
    Busca dispositivos concretos dentro del inventario
    de la organización mediante sus seriales.
    """

    respuesta = requests.get(
        f"{BASE_URL}/organizations/{organization_id}/inventory/devices",
        headers=crear_headers(),
        params={
            "serials[]": seriales,
            "perPage": 1000,
        },
        timeout=30,
    )

    respuesta.raise_for_status()

    return respuesta.json()


def inicializar():
    print("\n=================================")
    print(" Inicializando Cisco Meraki API")
    print("=================================\n")
