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
    Obtiene las organizaciones disponibles
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


def liberar_dispositivos_organizacion(
    organization_id: str,
    seriales: list[str],
) -> dict:
    """
    Libera equipos del inventario de una organizacion.

    Antes de llamarla, primero se tienen que retirar de su network actual
    """

    respuesta = requests.post(
        (f"{BASE_URL}/organizations/" f"{organization_id}/inventory/release"),
        headers=crear_headers(),
        json={
            "serials": seriales,
        },
        timeout=60,
    )

    respuesta.raise_for_status()

    return respuesta.json()


def reclamar_dispositivos_organizacion(
    organization_id: str,
    seriales: list[str],
) -> dict:
    """
    Reclama dispositivos dentre del inventario de la organizacion destino
    """

    respuesta = requests.post(
        (f"{BASE_URL}/organizations/" f"{organization_id}/inventory/claim"),
        headers=crear_headers(),
        json={
            "serials": seriales,
        },
        timeout=60,
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


def actualizar_nombre_dispositivo(
    serial: str,
    nombre: str,
) -> dict:
    """
    Funcion para modulo desmontaje y ya se usa para alta equipos y alta masiva.
    Actualiza únicamente el nombre de un dispositivo,
    sin modificar sus tags ni otras propiedades.
    """

    respuesta = requests.put(
        f"{BASE_URL}/devices/{serial}",
        headers=crear_headers(),
        json={
            "name": nombre,
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


def obtener_dispositivos_network(network_id: str) -> list[dict]:
    """
    Obtiene todos los dispositivos asignados actualmente
    a una Network
    """

    dispositivos = []

    url = f"{BASE_URL}/networks/{network_id}/devices"

    parametros = {
        "perPage": 1000,
    }

    while url:
        respuesta = requests.get(
            url,
            headers=crear_headers(),
            params=parametros,
            timeout=30,
        )

        respuesta.raise_for_status()

        dispositivos.extend(respuesta.json())

        siguiente_pagina = respuesta.links.get("next")

        if siguiente_pagina:
            url = siguiente_pagina["url"]
            parametros = None
        else:
            url = None

    return dispositivos


#############
# Inicio de funciones de modulo actualizacion de politicas


def obtener_politicas_grupo(
    network_id: str,
) -> list[dict]:
    """
    Obtiene todas las Group Policies configuradas
    dentro de una Network
    """

    respuesta = requests.get(
        f"{BASE_URL}/networks/{network_id}/groupPolicies",
        headers=crear_headers(),
        timeout=30,
    )

    respuesta.raise_for_status()

    return respuesta.json()


def crear_politica_grupo(
    network_id: str,
    configuracion: dict,
) -> dict:
    """
    Crea una Group Policy dentro de una Network.

    configuracion contiene el nombre y las reglas
    de la política que se desea crear.
    """

    respuesta = requests.post(
        f"{BASE_URL}/networks/{network_id}/groupPolicies",
        headers=crear_headers(),
        json=configuracion,
        timeout=60,
    )

    respuesta.raise_for_status()

    return respuesta.json()


def actualizar_politica_grupo(
    network_id: str,
    group_policy_id: str,
    configuracion: dict,
) -> dict:
    """
    Actualiza una Group Policy existente dentro de una Network.
    """

    respuesta = requests.put(
        (f"{BASE_URL}/networks/{network_id}" f"/groupPolicies/{group_policy_id}"),
        headers=crear_headers(),
        json=configuracion,
        timeout=60,
    )

    respuesta.raise_for_status()

    return respuesta.json()

##########
#Inicio Content Filtering

def obtener_content_filtering(
    network_id: str,
) -> dict:
    """
    Obtiene todo el content filtering
    """

    respuesta = requests.get(
        f"{BASE_URL}/networks/{network_id}/appliance/contentFiltering",
        headers=crear_headers(),
        timeout=30,
    )

    respuesta.raise_for_status()

    return respuesta.json()


def actualizar_content_filtering(
    network_id: str,
    configuracion: dict,
) -> dict:
    """
    Crea la configuracion de Content Filtering en una network
    """

    respuesta = requests.put(
        f"{BASE_URL}/networks/{network_id}/appliance/contentFiltering",
        headers=crear_headers(),
        json=configuracion,
        timeout=60,
    )

    respuesta.raise_for_status()

    return respuesta.json()

#########
#Traffic shaping


def inicializar():
    print("\n=================================")
    print(" Inicializando Cisco Meraki API")
    print("=================================\n")
