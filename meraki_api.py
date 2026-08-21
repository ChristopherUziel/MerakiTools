"""
MerakiTools
Herramienta de automatización para Cisco Meraki.

Desarrollado por: Christopher Uziel Martinez Alvarez
Año: 2026
"""

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


def hacer_peticion_meraki(
    metodo: str,
    url: str,
    intentos: int = 10,
    **kwargs,
) -> requests.Response:
    """
    Realiza peticion a la API Meraki

    Si Meraki responde con HTTP 429 (de limite de peticiones por segundo)
    """

    ultima_respuesta = None

    for intento in range(1, intentos + 1):
        respuesta = requests.request(
            method=metodo,
            url=url,
            **kwargs,
        )

        ultima_respuesta = respuesta

        if respuesta.status_code != 429:
            return respuesta

        retry_after = respuesta.headers.get("Retry-After")

        if retry_after is not None:
            try:
                espera = float(retry_after)
            except ValueError:
                espera = min(
                    2 ** (intento - 1),
                    10,
                )
        else:
            espera = min(
                2 ** (intento - 1),
                10,
            )

        if intento < intentos:
            print("\n⚠ Límite de peticiones de Meraki alcanzado.")
            print(
                f"Esperando {espera:g} segundo(s) "
                f"antes de reintentar "
                f"({intento}/{intentos})..."
            )

            time.sleep(espera)

    if ultima_respuesta is None:
        raise RuntimeError("No se obtuvo respuesta de la API de Meraki.")

    return ultima_respuesta


def obtener_organizaciones() -> list[dict]:
    """
    Obtiene las organizaciones disponibles
    """

    respuesta = hacer_peticion_meraki(
        "GET",
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

    respuesta = hacer_peticion_meraki(
        "GET",
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

    respuesta = hacer_peticion_meraki(
        "GET",
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

    respuesta = hacer_peticion_meraki(
        "POST",
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

    respuesta = hacer_peticion_meraki(
        "POST",
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

    respuesta = hacer_peticion_meraki(
        "POST",
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

    respuesta = hacer_peticion_meraki(
        "POST",
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

    respuesta = hacer_peticion_meraki(
        "GET",
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

    respuesta = hacer_peticion_meraki(
        "PUT",
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

    respuesta = hacer_peticion_meraki(
        "PUT",
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
        respuesta = hacer_peticion_meraki(
            "GET",
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

    respuesta = hacer_peticion_meraki(
        "GET",
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

    respuesta = hacer_peticion_meraki(
        "POST",
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

    respuesta = hacer_peticion_meraki(
        "PUT",
        (f"{BASE_URL}/networks/{network_id}" f"/groupPolicies/{group_policy_id}"),
        headers=crear_headers(),
        json=configuracion,
        timeout=60,
    )

    respuesta.raise_for_status()

    return respuesta.json()


##########
# Inicio Content Filtering


def obtener_content_filtering(
    network_id: str,
) -> dict:
    """
    Obtiene todo el content filtering
    """

    respuesta = hacer_peticion_meraki(
        "GET",
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

    respuesta = hacer_peticion_meraki(
        "PUT",
        f"{BASE_URL}/networks/{network_id}/appliance/contentFiltering",
        headers=crear_headers(),
        json=configuracion,
        timeout=60,
    )

    respuesta.raise_for_status()

    return respuesta.json()


#########
# Traffic shaping


def obtener_vpn_exclusions_organizacion(
    organization_id: str,
) -> dict:
    """
    Obtiene las reglas de VPN exclusion de las Networks con MX
    de una organización
    """

    respuesta = hacer_peticion_meraki(
        "GET",
        (
            f"{BASE_URL}/organizations/{organization_id}/appliance/trafficShaping/vpnExclusions/byNetwork"
        ),
        headers=crear_headers(),
        timeout=30,
    )

    respuesta.raise_for_status()

    return respuesta.json()


def obtener_traffic_shaping_rules(
    network_id: str,
) -> dict:
    """
    Obtiene las Traffic Shaping Rules
    """

    respuesta = hacer_peticion_meraki(
        "GET",
        (f"{BASE_URL}/networks/{network_id}/appliance/trafficShaping/rules"),
        headers=crear_headers(),
        timeout=30,
    )

    respuesta.raise_for_status()

    return respuesta.json()


def actualizar_traffic_shaping_rules(
    network_id: str,
    configuracion: dict,
) -> dict:
    """
    Actualiza la configuraciond e traffic shaping rules de las networks seleccionadas
    """

    respuesta = hacer_peticion_meraki(
        "PUT",
        f"{BASE_URL}/networks/{network_id}/appliance/trafficShaping/rules",
        headers=crear_headers(),
        json=configuracion,
        timeout=60,
    )

    respuesta.raise_for_status()

    return respuesta.json()


def actualizar_vpn_esclusions(
    network_id: str,
    configuracion: dict,
) -> dict:
    """
    Actualiza la configuracion de vpn exclussion en la network seleccionada
    """

    respuesta = hacer_peticion_meraki(
        "PUT",
        f"{BASE_URL}/networks/{network_id}/appliance/trafficShaping/vpnExclusions",
        headers=crear_headers(),
        json=configuracion,
        timeout=60,
    )

    respuesta.raise_for_status()

    return respuesta.json()


#########
# Busqueda de usaurios por ip y MAC


def obtener_clientes_network(
    network_id: str,
    timespan: int,
    mac: str | None = None,
    ip: str | None = None,
    descripcion: str | None = None,
) -> list[dict]:
    """
    Obtiene clientes vistos en una Network durante
    el período indicado.

    Permite filtrar por MAC, IP o descripción.
    """

    parametros = {
        "timespan": timespan,
        "perPage": 100,
    }

    if mac:
        parametros["mac"] = mac

    if ip:
        parametros["ip"] = ip

    if descripcion:
        parametros["description"] = descripcion

    respuesta = hacer_peticion_meraki(
        "GET",
        f"{BASE_URL}/networks/{network_id}/clients",
        headers=crear_headers(),
        params=parametros,
        timeout=90,
    )

    respuesta.raise_for_status()

    return respuesta.json()


def obtener_detalle_cliente(
    network_id: str,
    client_id: str,
) -> dict:
    """
    Obtiene información detallada de un cliente
    localizado dentro de una Network.
    """

    respuesta = hacer_peticion_meraki(
        "GET",
        (f"{BASE_URL}/networks/{network_id}" f"/clients/{client_id}"),
        headers=crear_headers(),
        timeout=30,
    )

    respuesta.raise_for_status()

    return respuesta.json()


def buscar_clientes_organizacion_por_mac(
    organization_id: str,
    mac: str,
) -> dict | None:
    """
    Busca una MAC en una organización y devuelve
    todos los registros históricos disponibles

    Maneja paginación y organizaciones donde
    la MAC no tenga registros.
    """

    url = f"{BASE_URL}/organizations/{organization_id}/clients/search"

    parametros = {
        "mac": mac,
        "perPage": 5,
    }

    datos_cliente = None
    registros = []

    while url:
        respuesta = hacer_peticion_meraki(
            "GET",
            url,
            headers=crear_headers(),
            params=parametros,
            timeout=60,
        )

        # Si no existe información para esa MAC en esta org
        if respuesta.status_code == 204:
            return None

        respuesta.raise_for_status()

        # Evita intentar convertir una lista vacia
        if not respuesta.text.strip():
            return None

        datos = respuesta.json()

        if datos_cliente is None:
            datos_cliente = {
                "clientId": datos.get("clientId"),
                "mac": datos.get("mac"),
                "manufacturer": datos.get("manufacturer"),
            }

        registros.extend(datos.get("records", []))

        siguiente = respuesta.links.get("next")

        if siguiente:
            url = siguiente["url"]

            # La siguiente URL ya contiene los parámetros
            # de paginación necesarios.
            parametros = None
        else:
            url = None

    if datos_cliente is None or not registros:
        return None

    datos_cliente["records"] = registros

    return datos_cliente


def inicializar():
    print("\n=================================")
    print(" Inicializando Cisco Meraki API")
    print("=================================\n")
