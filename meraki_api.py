import requests
import time

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


def retirar_dispositivo_network(
    network_id: str,
    serial: str,
) -> None:
    """
    Retira un dispositivo de una Network y lo deja disponible
    en el inventario de la organización.
    """

    respuesta = requests.post(
        f"{BASE_URL}/networks/{network_id}/devices/remove",
        headers=crear_headers(),
        json={
            "serial": serial,
        },
        timeout=30,
    )

    respuesta.raise_for_status()


def agregar_dispositivos_network(
    network_id: str,
    seriales: list[str],
) -> dict:
    """
    Agrega varios dispositivos disponibles a una Network.

    addAtomically=True indica que Meraki debe agregar todos
    los equipos o no agregar ninguno.
    """

    respuesta = requests.post(
        f"{BASE_URL}/networks/{network_id}/devices/claim",
        headers=crear_headers(),
        params={
            "addAtomically": "true",
        },
        json={
            "serials": seriales,
        },
        timeout=60,
    )

    respuesta.raise_for_status()

    return respuesta.json()


def obtener_dispositivo(serial: str) -> dict:
    """
    Consulta un dispositivo individual mediante su serial.
    """

    respuesta = requests.get(
        f"{BASE_URL}/devices/{serial}",
        headers=crear_headers(),
        timeout=30,
    )

    respuesta.raise_for_status()

    return respuesta.json()


def actualizar_dispositivo(
    serial: str,
    nombre: str,
    tags: list[str],
) -> dict:
    """
    Actualiza el nombre y los tags de un dispositivo.
    """

    respuesta = requests.put(
        f"{BASE_URL}/devices/{serial}",
        headers=crear_headers(),
        json={
            "name": nombre,
            "tags": tags,
        },
        timeout=30,
    )

    respuesta.raise_for_status()

    return respuesta.json()


def esperar_dispositivo_en_network(
    serial: str,
    network_id: str,
    intentos: int = 12,
    espera_segundos: int = 10,
) -> bool:
    """
    Espera a que un dispositivo recién agregado aparezca
    dentro de la Network destino.

    Por defecto espera hasta dos minutos.
    """

    for _ in range(intentos):
        try:
            dispositivo = obtener_dispositivo(serial)

            if dispositivo.get("networkId") == network_id:
                return True

        except requests.RequestException:
            pass

        time.sleep(espera_segundos)

    return False


def inicializar():
    print("\n=================================")
    print(" Inicializando Cisco Meraki API")
    print("=================================\n")
