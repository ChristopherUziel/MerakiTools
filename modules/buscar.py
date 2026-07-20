import requests

from meraki_api import (
    obtener_dispositivo,
    obtener_dispositivos_inventario,
    obtener_networks,
    obtener_organizaciones,
)


def normalizar_serial_busqueda(serial: str) -> str:
    """
    Normaliza la serie del equipo
    """

    serial_limpio = serial.strip().upper().replace("-", "")

    if len(serial_limpio) != 12:
        raise ValueError("El serial debe contener 12 caracteres.")

    return f"{serial_limpio[:4]}-" f"{serial_limpio[4:8]}-" f"{serial_limpio[8:12]}"


def seleccionar_organizacion_busqueda() -> dict:
    """
    Muestra las organizaciones disponibles y devuelve
    la organización seleccionada.
    """

    organizaciones = obtener_organizaciones()

    if not organizaciones:
        raise ValueError("No se encontraron organizaciones disponibles.")

    print("\nOrganizaciones disponibles:\n")

    for indice, organizacion in enumerate(
        organizaciones,
        start=1,
    ):
        print(f"{indice}. {organizacion['name']}")

    opcion = input("\nSelecciona una organización:\n> ").strip()

    if not opcion.isdigit():
        raise ValueError("Debes ingresar un número.")

    indice = int(opcion) - 1

    if indice < 0 or indice >= len(organizaciones):
        raise ValueError("La organización seleccionada no existe.")

    return organizaciones[indice]


def buscar_equipo_en_inventario(
    organization_id: str,
    serial: str,
) -> dict | None:
    """
    Busca un equipo dentro del inventario de la organización.

    Devuelve el dispositivo encontrado o null.
    """

    dispositivos = obtener_dispositivos_inventario(
        organization_id=organization_id,
        seriales=[serial],
    )

    if not dispositivos:
        return None

    return dispositivos[0]


def resolver_nombre_network(
    organization_id: str,
    network_id: str | None,
) -> str:
    """
    Devuelve el nombre de la Network asociada al dispositivo.
    """

    if network_id is None:
        return "Ninguna - disponible en inventario"

    networks = obtener_networks(organization_id)

    for network in networks:
        if network.get("id") == network_id:
            return network.get("name", "Sin nombre")

    return "Network no identificada"


def identificar_tipo_equipo(modelo: str) -> str:
    """
    Identifica el tipo general del equipo según su modelo.
    """

    modelo_mayusculas = modelo.upper()

    if modelo_mayusculas.startswith("MR"):
        return "Access Point"

    if modelo_mayusculas.startswith("MS"):
        return "Switch"

    if modelo_mayusculas.startswith("MX"):
        return "Security Appliance"

    if modelo_mayusculas.startswith("MG"):
        return "Gateway celular"

    if modelo_mayusculas.startswith("MV"):
        return "Cámara"

    if modelo_mayusculas.startswith("MT"):
        return "Sensor"

    return "Tipo desconocido"


def mostrar_informacion_equipo(
    dispositivo_inventario: dict,
    dispositivo_detallado: dict | None,
    nombre_network: str,
) -> None:
    """
    Muestra la información principal del equipo.
    """

    detalle = dispositivo_detallado or {}

    serial = dispositivo_inventario.get(
        "serial",
        "No disponible",
    )

    modelo = dispositivo_inventario.get(
        "model",
        detalle.get("model", "No disponible"),
    )

    nombre = detalle.get(
        "name",
        dispositivo_inventario.get("name"),
    )

    mac = detalle.get(
        "mac",
        dispositivo_inventario.get("mac"),
    )

    tags = detalle.get(
        "tags",
        dispositivo_inventario.get("tags", []),
    )

    network_id = dispositivo_inventario.get("networkId")

    if network_id:
        estado = "Asignado a una Network"
    else:
        estado = "Disponible en inventario"

    tipo = identificar_tipo_equipo(modelo)

    nombre_mostrado = nombre or "Sin nombre"
    mac_mostrada = mac or "No disponible"
    tags_mostrados = ", ".join(tags) if tags else "Sin tags"
    network_id_mostrado = network_id or "Ninguno"

    print("\n" + "=" * 48)
    print("           INFORMACIÓN DEL EQUIPO")
    print("=" * 48)
    print(f"Serial:          {serial}")
    print(f"Modelo:          {modelo}")
    print(f"Tipo:            {tipo}")
    print(f"Nombre:          {nombre_mostrado}")
    print(f"MAC:             {mac_mostrada}")
    print(f"Tags:            {tags_mostrados}")
    print(f"Estado:          {estado}")
    print(f"Network actual:  {nombre_network}")
    print(f"Network ID:      {network_id_mostrado}")
    print("=" * 48)


def ejecutar_busqueda(
    organizacion: dict,
    serial: str,
) -> None:
    """
    Ejecuta la consulta completa de un equipo.
    """

    dispositivo_inventario = buscar_equipo_en_inventario(
        organization_id=organizacion["id"],
        serial=serial,
    )

    if dispositivo_inventario is None:
        print("\nNo se encontró el equipo en el inventario " "de la organización.\n")
        print("Posibles causas:")
        print("- El serial está mal escrito.")
        print("- El equipo todavía no ha sido reclamado.")
        print("- El equipo pertenece a otra organización.")
        return

    network_id = dispositivo_inventario.get("networkId")

    nombre_network = resolver_nombre_network(
        organization_id=organizacion["id"],
        network_id=network_id,
    )

    dispositivo_detallado = None

    if network_id is not None:
        try:
            dispositivo_detallado = obtener_dispositivo(serial)

        except requests.RequestException:
            dispositivo_detallado = None

    mostrar_informacion_equipo(
        dispositivo_inventario=dispositivo_inventario,
        dispositivo_detallado=dispositivo_detallado,
        nombre_network=nombre_network,
    )


def buscar():
    print("\n=== BUSCAR EQUIPO ===\n")

    try:
        organizacion = seleccionar_organizacion_busqueda()

    except requests.RequestException as error:
        print(f"\nNo fue posible consultar Meraki: {error}\n")
        return

    except ValueError as error:
        print(f"\nError: {error}\n")
        return

    while True:
        entrada_serial = input("\nIngresa el serial completo del equipo:\n> ")

        try:
            serial = normalizar_serial_busqueda(entrada_serial)

            ejecutar_busqueda(
                organizacion=organizacion,
                serial=serial,
            )

        except ValueError as error:
            print(f"\nError: {error}\n")

        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code == 400:
                print(
                    "\nMeraki rechazó el serial ingresado. "
                    "Verifica que sea un serial real y válido.\n"
                )
            else:
                print("\nNo fue posible consultar el equipo: " f"{error}\n")

        except requests.RequestException as error:
            print("\nNo fue posible comunicarse con Meraki: " f"{error}\n")

        continuar = input("\n¿Deseas buscar otro equipo? (S/N):\n> ").strip().upper()

        if continuar != "S":
            print("\nRegresando al menú principal...\n")
            break
