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


def convertir_seriales_busqueda(
    texto_seriales: str,
) -> tuple[list[str], list[str]]:
    """
    Convierte varios seriales separados por comas y devuelve los unicos y repetidos
    """

    seriales_unicos = []
    seriales_duplicados = []

    for serial in texto_seriales.split(","):
        if not serial.strip():
            continue

        serial_normalizado = normalizar_serial_busqueda(serial)

        if serial_normalizado in seriales_unicos:
            if serial_normalizado not in seriales_duplicados:
                seriales_duplicados.append(serial_normalizado)

            continue

        seriales_unicos.append(serial_normalizado)

    return seriales_unicos, seriales_duplicados


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


def ejecutar_busqueda_multiple(
    organizacion: dict,
    seriales: list[str],
) -> None:
    """
    Busca varios equipos en una sola consulta
    """

    dispositivos = obtener_dispositivos_inventario(
        organization_id=organizacion["id"],
        seriales=seriales,
    )

    dispositivos_por_serial = {
        dispositivo.get("serial"): dispositivo for dispositivo in dispositivos
    }

    networks = obtener_networks(organizacion["id"])

    networks_por_id = {
        network.get("id"): network.get("name", "Sin nombre") for network in networks
    }

    encontrados = 0
    no_encontrados = []

    for serial in seriales:
        dispositivo_inventario = dispositivos_por_serial.get(serial)

        if dispositivo_inventario is None:
            no_encontrados.append(serial)
            continue

        encontrados += 1

        network_id = dispositivo_inventario.get("networkId")

        if network_id is None:
            nombre_network = "Ninguna - disponible en inventario"
        else:
            nombre_network = networks_por_id.get(
                network_id,
                "Network no identificada",
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

    if no_encontrados:
        print("\n=== EQUIPOS NO ENCONTRADOS ===\n")

        for serial in no_encontrados:
            print(f"- {serial}")

        print(
            "\nEs posible que estén en otra organización, "
            "no hayan sido reclamados o que el serial sea incorrecto."
        )

    print("\n=== RESUMEN DE BÚSQUEDA ===\n")
    print(f"Seriales consultados: {len(seriales)}")
    print(f"Equipos encontrados:  {encontrados}")
    print(f"No encontrados:       {len(no_encontrados)}")


def ejecutar_busqueda_global(
    seriales: list[str],
) -> None:
    """
    Busca uno o varios equipos en todas las
    organizaciones que tenga acceso el usuario.
    """

    organizaciones = obtener_organizaciones()

    if not organizaciones:
        raise ValueError("No se encontraron organizaciones disponibles.")

    resultados = {}
    organizaciones_con_error = []

    print("\nBuscando equipos en todas las " "organizaciones accesibles...\n")

    for organizacion in organizaciones:
        seriales_pendientes = [
            serial for serial in seriales if serial not in resultados
        ]

        if not seriales_pendientes:
            break

        try:
            dispositivos = obtener_dispositivos_inventario(
                organization_id=organizacion["id"],
                seriales=seriales_pendientes,
            )

        except requests.RequestException as error:
            organizaciones_con_error.append(
                {
                    "nombre": organizacion["name"],
                    "error": str(error),
                }
            )
            continue

        if not dispositivos:
            continue

        networks = obtener_networks(organizacion["id"])

        networks_por_id = {
            network.get("id"): network.get(
                "name",
                "Sin nombre",
            )
            for network in networks
        }

        for dispositivo in dispositivos:
            serial = dispositivo.get("serial")

            if not serial:
                continue

            network_id = dispositivo.get("networkId")

            if network_id is None:
                nombre_network = "Ninguna - disponible en inventario"
            else:
                nombre_network = networks_por_id.get(
                    network_id,
                    "Network no identificada",
                )

            resultados[serial] = {
                "organizacion": organizacion,
                "dispositivo": dispositivo,
                "nombre_network": nombre_network,
            }

    for serial in seriales:
        resultado = resultados.get(serial)

        if resultado is None:
            continue

        dispositivo_inventario = resultado["dispositivo"]

        dispositivo_detallado = None

        if dispositivo_inventario.get("networkId"):
            try:
                dispositivo_detallado = obtener_dispositivo(serial)

            except requests.RequestException:
                dispositivo_detallado = None

        print(f"\nOrganización: " f"{resultado['organizacion']['name']}")

        mostrar_informacion_equipo(
            dispositivo_inventario=dispositivo_inventario,
            dispositivo_detallado=dispositivo_detallado,
            nombre_network=resultado["nombre_network"],
        )

    no_encontrados = [serial for serial in seriales if serial not in resultados]

    if no_encontrados:
        print("\n=== EQUIPOS NO ENCONTRADOS ===\n")

        for serial in no_encontrados:
            print(f"- {serial}")

        print("\nNo fueron encontrados en ninguna " "organización accesible.")

    if organizaciones_con_error:
        print("\n=== ORGANIZACIONES NO CONSULTADAS ===\n")

        for organizacion in organizaciones_con_error:
            print(f"- {organizacion['nombre']}: " f"{organizacion['error']}")

    print("\n=== RESUMEN GLOBAL ===\n")
    print(f"Seriales consultados: {len(seriales)}")
    print(f"Equipos encontrados:  {len(resultados)}")
    print(f"No encontrados:       {len(no_encontrados)}")


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
        entrada_seriales = input(
            "\nIngresa uno o varios seriales separados por comas:\n> "
        )

        try:
            seriales, seriales_duplicados = convertir_seriales_busqueda(
                entrada_seriales
            )

            if not seriales:
                print("\nNo se ingresaron seriales válidos.\n")
                continue

            if seriales_duplicados:
                print("\nSeriales repetidos en la captura:\n")

                for serial in seriales_duplicados:
                    print(f"- {serial}")

            ejecutar_busqueda_multiple(
                organizacion=organizacion,
                seriales=seriales,
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


def buscar_todas_organizaciones():
    """
    Permite buscar uno o varios equipos en todas
    las organizaciones que se tengan acceso
    """

    print("\n=== BUSCAR EQUIPO EN TODAS " "LAS ORGANIZACIONES ===\n")

    while True:
        entrada_seriales = input(
            "\nIngresa uno o varios seriales " "separados por comas:\n> "
        )

        try:
            seriales, seriales_duplicados = convertir_seriales_busqueda(
                entrada_seriales
            )

            if not seriales:
                print("\nNo se ingresaron seriales " "válidos.\n")
                continue

            if seriales_duplicados:
                print("\nSeriales repetidos " "en la captura:\n")

                for serial in seriales_duplicados:
                    print(f"- {serial}")

            ejecutar_busqueda_global(seriales)

        except ValueError as error:
            print(f"\nError: {error}\n")

        except requests.HTTPError as error:
            print("\nMeraki rechazó la consulta: " f"{error}\n")

        except requests.RequestException as error:
            print("\nNo fue posible comunicarse " f"con Meraki: {error}\n")

        continuar = (
            input("\n¿Deseas realizar otra búsqueda global? " "(S/N):\n> ")
            .strip()
            .upper()
        )

        if continuar != "S":
            print("\nRegresando al menú principal...\n")
            return
