import requests

from meraki_api import (
    obtener_dispositivos_inventario,
    obtener_networks,
    obtener_organizaciones,
)


def normalizar_serial(serial: str) -> str:
    """
    Convierte un serial Meraki al formato estándar:
    XXXX-XXXX-XXXX
    """

    serial_limpio = serial.strip().upper().replace("-", "")

    if len(serial_limpio) != 12:
        raise ValueError(f"El serial '{serial}' no tiene 12 caracteres.")

    return f"{serial_limpio[:4]}-" f"{serial_limpio[4:8]}-" f"{serial_limpio[8:12]}"


def convertir_seriales(texto_seriales: str) -> list[str]:
    """
    Convierte seriales separados por comas en una lista
    normalizada y sin duplicados.
    """

    seriales = []

    for serial in texto_seriales.split(","):
        if not serial.strip():
            continue

        serial_normalizado = normalizar_serial(serial)

        if serial_normalizado not in seriales:
            seriales.append(serial_normalizado)

    return seriales


def crear_lista_equipos(
    seriales: list[str],
    nombre_base: str,
    tags: list[str],
) -> list[dict]:
    """
    Construye la información que posteriormente se enviará a Meraki.
    """

    equipos = []

    for numero, serial in enumerate(seriales, start=1):
        equipo = {
            "serial": serial,
            "nombre": f"{nombre_base}-{numero:02d}",
            "tags": tags,
        }

        equipos.append(equipo)

    return equipos


def seleccionar_organizacion() -> dict:
    organizaciones = obtener_organizaciones()

    if not organizaciones:
        raise ValueError("No se encontraron organizaciones disponibles.")

    print("\nOrganizaciones disponibles:\n")

    for indice, organizacion in enumerate(organizaciones, start=1):
        print(f"{indice}. {organizacion['name']}")

    opcion = input("\nSelecciona una organización:\n> ").strip()

    if not opcion.isdigit():
        raise ValueError("Debes ingresar un número.")

    indice = int(opcion) - 1

    if indice < 0 or indice >= len(organizaciones):
        raise ValueError("La organización seleccionada no existe.")

    return organizaciones[indice]


def seleccionar_network(organization_id: str) -> dict:
    networks = obtener_networks(organization_id)

    if not networks:
        raise ValueError("No se encontraron redes disponibles.")

    networks.sort(key=lambda network: network["name"].lower())

    print("\nNetworks disponibles:\n")

    for indice, network in enumerate(networks, start=1):
        print(f"{indice}. {network['name']}")

    opcion = input("\nSelecciona la Network del evento:\n> ").strip()

    if not opcion.isdigit():
        raise ValueError("Debes ingresar un número.")

    indice = int(opcion) - 1

    if indice < 0 or indice >= len(networks):
        raise ValueError("La Network seleccionada no existe.")

    return networks[indice]


def validar_equipos_inventario(
    organization_id: str,
    equipos: list[dict],
    network_destino_id: str,
) -> tuple[list[dict], list[str]]:
    """
    Complementa cada equipo con su modelo y ubicación actual.

    Devuelve:
    - equipos válidos encontrados en el inventario
    - seriales que no aparecen en el inventario
    """

    seriales = [equipo["serial"] for equipo in equipos]

    dispositivos = obtener_dispositivos_inventario(
        organization_id,
        seriales,
    )

    inventario_por_serial = {
        dispositivo["serial"]: dispositivo for dispositivo in dispositivos
    }

    equipos_validos = []
    seriales_no_encontrados = []

    for equipo in equipos:
        dispositivo = inventario_por_serial.get(equipo["serial"])

        if dispositivo is None:
            seriales_no_encontrados.append(equipo["serial"])
            continue

        network_actual_id = dispositivo.get("networkId")

        equipo["modelo"] = dispositivo.get("model", "Desconocido")
        equipo["network_actual_id"] = network_actual_id

        if network_actual_id is None:
            equipo["estado"] = "Disponible en inventario"
        elif network_actual_id == network_destino_id:
            equipo["estado"] = "Ya se encuentra en la Network destino"
        else:
            equipo["estado"] = "Asignado a otra Network"

        equipos_validos.append(equipo)

    return equipos_validos, seriales_no_encontrados


def alta_evento():
    print("\n=== ALTA DE EQUIPOS ===\n")

    try:
        organizacion = seleccionar_organizacion()
        network = seleccionar_network(organizacion["id"])

    except requests.RequestException as error:
        print(f"\nNo fue posible consultar Meraki: {error}\n")
        return

    except ValueError as error:
        print(f"\nError: {error}\n")
        return

    print(f"\nOrganización: {organizacion['name']}")
    print(f"Network seleccionada: {network['name']}\n")

    entrada_seriales = input("Ingresa los números de serie separados por comas:\n> ")

    try:
        seriales = convertir_seriales(entrada_seriales)

    except ValueError as error:
        print(f"\nError: {error}\n")
        return

    if not seriales:
        print("\nNo se ingresaron números de serie válidos.\n")
        return

    nombre_base = input("Nombre base de los equipos:\n> ").strip().upper()

    if not nombre_base:
        print("\nEl nombre base es obligatorio.\n")
        return

    entrada_tags = input("Tags separados por comas:\n> ")

    tags = [tag.strip() for tag in entrada_tags.split(",") if tag.strip()]

    equipos = crear_lista_equipos(
        seriales=seriales,
        nombre_base=nombre_base,
        tags=tags,
    )

    try:
        equipos_validos, seriales_no_encontrados = validar_equipos_inventario(
            organization_id=organizacion["id"],
            equipos=equipos,
            network_destino_id=network["id"],
        )

    except requests.RequestException as error:
        print(f"\nNo fue posible consultar el inventario: {error}\n")
        return

    print("\n=== VALIDACIÓN DE EQUIPOS ===\n")

    for equipo in equipos_validos:
        print(
            f"{equipo['serial']} | "
            f"{equipo['modelo']} | "
            f"{equipo['estado']} | "
            f"Nuevo nombre: {equipo['nombre']}"
        )

    if seriales_no_encontrados:
        print("\nNo encontrados en el inventario:\n")

        for serial in seriales_no_encontrados:
            print(f"- {serial}")

        print(
            "\nEstos equipos requieren revisión o claim previo " "en la organización."
        )

    print(f"\nEquipos válidos: {len(equipos_validos)}")
    print(f"No encontrados: {len(seriales_no_encontrados)}")

    print(
        "\nOperaciones de escritura bloqueadas. "
        "Todavía no se realizaron cambios en Meraki.\n"
    )
