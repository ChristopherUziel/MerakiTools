from config import cambios_habilitados

import requests

from meraki_api import (
    actualizar_dispositivo,
    agregar_dispositivos_network,
    esperar_dispositivo_en_network,
    obtener_dispositivos_inventario,
    obtener_networks,
    obtener_organizaciones,
    retirar_dispositivo_network,
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

        equipo["nombre_actual"] = dispositivo.get("name")
        equipo["tags_actuales"] = dispositivo.get("tags", [])

        if network_actual_id is None:
            equipo["estado"] = "Disponible en inventario"
        elif network_actual_id == network_destino_id:
            equipo["estado"] = "Ya se encuentra en la Network destino"
        else:
            equipo["estado"] = "Asignado a otra Network"

        equipos_validos.append(equipo)

    return equipos_validos, seriales_no_encontrados


def procesar_alta_equipos(
    equipos: list[dict],
    network_destino: dict,
) -> None:
    """
    Mueve o agrega los equipos a la Network destino y después
    actualiza sus nombres y tags.
    """

    if not cambios_habilitados():
        print(
            "\nOperaciones de escritura bloqueadas. "
            "No se realizaron cambios en Meraki.\n"
        )
        return

    equipos_ya_en_destino = []
    equipos_para_agregar = []
    equipos_retirados = []

    for equipo in equipos:
        if equipo["estado"] == "Ya se encuentra en la Network destino":
            equipos_ya_en_destino.append(equipo)

        else:
            equipos_para_agregar.append(equipo)

    print("\n=== PROCESANDO ALTA ===\n")

    # Retirar los equipos que actualmente están en otra Network.
    for equipo in equipos_para_agregar:
        network_anterior_id = equipo.get("network_actual_id")

        if network_anterior_id is None:
            continue

        print(f"Retirando {equipo['serial']} " "de su Network anterior...")

        try:
            retirar_dispositivo_network(
                network_id=network_anterior_id,
                serial=equipo["serial"],
            )

            equipos_retirados.append(equipo)

        except requests.RequestException as error:
            equipo["resultado"] = "Error al retirar"
            equipo["error"] = str(error)

            print(f"✗ No se pudo retirar {equipo['serial']}: " f"{error}")

    equipos_listos_para_claim = [
        equipo
        for equipo in equipos_para_agregar
        if equipo.get("resultado") != "Error al retirar"
    ]

    # Agregar todos los equipos disponibles a la Network destino.
    if equipos_listos_para_claim:
        seriales = [equipo["serial"] for equipo in equipos_listos_para_claim]

        print(
            f"\nAgregando {len(seriales)} equipo(s) a " f"{network_destino['name']}..."
        )

        try:
            respuesta_claim = agregar_dispositivos_network(
                network_id=network_destino["id"],
                seriales=seriales,
            )

            errores_claim = {
                error["serial"]: error.get("errors", [])
                for error in respuesta_claim.get("errors", [])
            }

            for equipo in equipos_listos_para_claim:
                errores = errores_claim.get(equipo["serial"])

                if errores:
                    equipo["resultado"] = "Error al agregar"
                    equipo["error"] = "; ".join(errores)

        except requests.RequestException as error:
            print(
                "\n✗ Falló el alta de los dispositivos "
                f"en la Network destino: {error}"
            )

            for equipo in equipos_listos_para_claim:
                equipo["resultado"] = "Error al agregar"
                equipo["error"] = str(error)

    equipos_para_configurar = equipos_ya_en_destino + [
        equipo
        for equipo in equipos_listos_para_claim
        if equipo.get("resultado") != "Error al agregar"
    ]

    # Esperar y después actualizar nombre y tags.
    for equipo in equipos_para_configurar:
        serial = equipo["serial"]

        print(f"\nVerificando {serial}...")

        disponible = esperar_dispositivo_en_network(
            serial=serial,
            network_id=network_destino["id"],
        )

        if not disponible:
            equipo["resultado"] = "No disponible después del alta"
            equipo["error"] = (
                "El dispositivo no apareció en la Network "
                "destino dentro del tiempo esperado."
            )

            print(f"✗ {serial} no apareció a tiempo " "en la Network destino.")
            continue

        try:
            actualizar_dispositivo(
                serial=serial,
                nombre=equipo["nombre"],
                tags=equipo["tags"],
            )

            equipo["resultado"] = "Correcto"

            print(
                f"✓ {serial} | "
                f"{equipo['nombre']} | "
                f"Tags: {', '.join(equipo['tags']) or 'Sin tags'}"
            )

        except requests.RequestException as error:
            equipo["resultado"] = "Error de configuración"
            equipo["error"] = str(error)

            print(f"✗ No se pudo configurar {serial}: {error}")

    print("\n=== RESULTADO FINAL ===\n")

    for equipo in equipos:
        resultado = equipo.get("resultado", "Sin procesar")

        print(f"{equipo['serial']} | " f"{equipo['modelo']} | " f"{resultado}")

        if equipo.get("error"):
            print(f"  Error: {equipo['error']}")

    correctos = sum(equipo.get("resultado") == "Correcto" for equipo in equipos)

    print(f"\nCompletados correctamente: " f"{correctos}/{len(equipos)}\n")


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


    if not equipos_validos:
        print("\nNo hay equipos válidos para procesar.\n")
        return

    print(
        "\nADVERTENCIA: esta operación puede mover equipos "
        "desde otras Networks y cambiar sus nombres y tags."
    )

    confirmacion = input(
        "\n¿Deseas continuar con el alta? (S/N):\n> "
    ).strip().upper()

    if confirmacion != "S":
        print("\nOperación cancelada. No se realizaron cambios.\n")
        return

    procesar_alta_equipos(
        equipos=equipos_validos,
        network_destino=network,
    )