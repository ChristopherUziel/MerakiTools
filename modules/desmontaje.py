import requests

from config import cambios_habilitados
from meraki_api import (
    actualizar_nombre_dispositivo,
    obtener_dispositivos_inventario,
    obtener_networks,
    obtener_organizaciones,
)


def normalizar_serial_desmontaje(serial: str) -> str:

    serial_limpio = serial.strip().upper().replace("-", "")

    if len(serial_limpio) != 12:
        raise ValueError(f"El serial '{serial}' no tiene 12 caracteres.")

    return f"{serial_limpio[:4]}-" f"{serial_limpio[4:8]}-" f"{serial_limpio[8:12]}"


def convertir_seriales_desmontaje(
    texto_seriales: str,
) -> tuple[list[str], list[str]]:
    """
    Normaliza los seriales y devuelve:
    - seriales únicos
    - seriales repetidos en la captura
    """

    seriales_unicos = []
    seriales_duplicados = []

    for serial in texto_seriales.split(","):
        if not serial.strip():
            continue

        serial_normalizado = normalizar_serial_desmontaje(serial)

        if serial_normalizado in seriales_unicos:
            if serial_normalizado not in seriales_duplicados:
                seriales_duplicados.append(serial_normalizado)

            continue

        seriales_unicos.append(serial_normalizado)

    return seriales_unicos, seriales_duplicados


def seleccionar_organizacion_desmontaje() -> dict:

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


def seleccionar_network_desmontaje(
    organization_id: str,
) -> dict:
    """
    Muestra la network
    """

    networks = obtener_networks(organization_id)

    if not networks:
        raise ValueError("No se encontraron Networks disponibles.")

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


def nombre_esta_recuperado(nombre: str | None) -> bool:
    """
    Indica si el nombre ya contiene la palabra RECUPERADO.
    """

    if not nombre:
        return False

    palabras = nombre.upper().split()

    return "RECUPERADO" in palabras


def crear_nombre_recuperado(nombre_actual: str | None) -> str:
    """
    Añade RECUPERADO al nombre actual.
    """

    nombre_base = (nombre_actual or "SIN-NOMBRE").strip()

    return f"{nombre_base} RECUPERADO"


def clasificar_equipos_desmontaje(
    organization_id: str,
    network_evento_id: str,
    seriales: list[str],
) -> dict:
    """
    Clasifica los equipos antes de realizar cambios.
    aqui debe de colocar recuperada aunque este en otra network
    """

    dispositivos = obtener_dispositivos_inventario(
        organization_id=organization_id,
        seriales=seriales,
    )

    dispositivos_por_serial = {
        dispositivo["serial"]: dispositivo for dispositivo in dispositivos
    }

    clasificacion = {
        "pendientes": [],
        "ya_recuperados": [],
        "otra_network": [],
        "no_encontrados": [],
    }

    for serial in seriales:
        dispositivo = dispositivos_por_serial.get(serial)

        if dispositivo is None:
            clasificacion["no_encontrados"].append(serial)
            continue

        equipo = {
            "serial": serial,
            "modelo": dispositivo.get(
                "model",
                "Desconocido",
            ),
            "nombre_actual": dispositivo.get("name"),
            "network_actual_id": dispositivo.get("networkId"),
        }

        if nombre_esta_recuperado(equipo["nombre_actual"]):
                    clasificacion["ya_recuperados"].append(equipo)

        elif equipo["network_actual_id"] != network_evento_id:
            equipo["nombre_nuevo"] = crear_nombre_recuperado(equipo["nombre_actual"])
            clasificacion["otra_network"].append(equipo)

        else:
            equipo["nombre_nuevo"] = crear_nombre_recuperado(equipo["nombre_actual"])

            clasificacion["pendientes"].append(equipo)

    return clasificacion


def mostrar_resumen_desmontaje(
    clasificacion: dict,
    seriales_duplicados: list[str],
) -> None:
    """
    Muestra todos los casos encontrados antes de confirmar.
    """

    print("\n=== VALIDACIÓN DE DESMONTAJE ===\n")

    pendientes = clasificacion["pendientes"]
    ya_recuperados = clasificacion["ya_recuperados"]
    otra_network = clasificacion["otra_network"]
    no_encontrados = clasificacion["no_encontrados"]

    if pendientes:
        print("Pendientes por marcar:\n")

        for equipo in pendientes:
            print(
                f"- {equipo['serial']} | "
                f"{equipo['modelo']} | "
                f"{equipo['nombre_actual'] or 'Sin nombre'}"
                f" -> {equipo['nombre_nuevo']}"
            )

    if seriales_duplicados:
        print("\nSeriales repetidos durante esta captura:\n")

        for serial in seriales_duplicados:
            print(f"- {serial} | " "Ya había sido ingresado en esta misma lista.")

    if ya_recuperados:
        print("\nEquipos que ya estaban marcados como RECUPERADO:\n")

        for equipo in ya_recuperados:
            print(
                f"- {equipo['serial']} | "
                f"{equipo['modelo']} | "
                f"{equipo['nombre_actual']}"
            )

    if otra_network:
        print("\nEquipos que no pertenecen a la Network seleccionada:\n")

        for equipo in otra_network:
            print(
                f"- {equipo['serial']} | "
                f"{equipo['modelo']} | "
                f"{equipo['nombre_actual'] or 'Sin nombre'}"
            )

    if no_encontrados:
        print("\nSeriales no encontrados en el inventario:\n")

        for serial in no_encontrados:
            print(f"- {serial}")

    print("\nResumen:")
    print(f"- Pendientes: {len(pendientes)}")
    print(f"- Ya recuperados: {len(ya_recuperados)}")
    print(f"- Duplicados en captura: " f"{len(seriales_duplicados)}")
    print(f"- En otra Network: {len(otra_network)}")
    print(f"- No encontrados: {len(no_encontrados)}")


def procesar_desmontaje(
    equipos: list[dict],
) -> None:
    """
    Añade RECUPERADO al nombre de los equipos pendientes.
    """

    if not cambios_habilitados():
        print(
            "\nOperaciones de escritura bloqueadas. "
            "No se realizaron cambios en Meraki.\n"
        )
        return

    print("\n=== MARCANDO EQUIPOS RECUPERADOS ===\n")

    correctos = 0

    for equipo in equipos:
        serial = equipo["serial"]
        nombre_nuevo = equipo["nombre_nuevo"]

        try:
            actualizar_nombre_dispositivo(
                serial=serial,
                nombre=nombre_nuevo,
            )

            equipo["resultado"] = "Correcto"
            correctos += 1

            print(f"✓ {serial} | {nombre_nuevo}")

        except requests.RequestException as error:
            equipo["resultado"] = "Error"
            equipo["error"] = str(error)

            print(f"✗ {serial} | No se pudo actualizar: " f"{error}")

    print("\n=== RESULTADO FINAL ===\n")

    for equipo in equipos:
        print(f"{equipo['serial']} | " f"{equipo.get('resultado', 'Sin procesar')}")

        if equipo.get("error"):
            print(f"  Error: {equipo['error']}")

    print(f"\nEquipos marcados correctamente: " f"{correctos}/{len(equipos)}\n")


def desmontaje():
    print("\n=== DESMONTAJE / RECUPERACIÓN ===\n")

    try:
        organizacion = seleccionar_organizacion_desmontaje()

        network = seleccionar_network_desmontaje(organizacion["id"])

    except requests.RequestException as error:
        print(f"\nNo fue posible consultar Meraki: {error}\n")
        return

    except ValueError as error:
        print(f"\nError: {error}\n")
        return

    print(f"\nOrganización: {organizacion['name']}")
    print(f"Network del evento: {network['name']}\n")

    entrada_seriales = input(
        "Ingresa los seriales recuperados " "separados por comas:\n> "
    )

    try:
        seriales, seriales_duplicados = convertir_seriales_desmontaje(entrada_seriales)

    except ValueError as error:
        print(f"\nError: {error}\n")
        return

    if not seriales:
        print("\nNo se ingresaron seriales válidos.\n")
        return

    try:
        clasificacion = clasificar_equipos_desmontaje(
            organization_id=organizacion["id"],
            network_evento_id=network["id"],
            seriales=seriales,
        )

    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code == 400:
            print(
                "\nMeraki rechazó uno o más seriales. "
                "Verifica que sean reales y estén "
                "escritos correctamente.\n"
            )
        else:
            print("\nNo fue posible consultar los equipos: " f"{error}\n")

        return

    except requests.RequestException as error:
        print("\nNo fue posible comunicarse con Meraki: " f"{error}\n")
        return

    mostrar_resumen_desmontaje(
        clasificacion=clasificacion,
        seriales_duplicados=seriales_duplicados,
    )

    pendientes = clasificacion["pendientes"]
    otra_network = clasificacion["otra_network"]

    if not pendientes and not otra_network:
        print("\nNo existen equipos pendientes por marcar.\n")
        return

    if not pendientes:
        print("\nNo existen equipos pendientes en esta Network por marcar.\n")
    else:
        print("\nSolo se modificarán los equipos mostrados " "como pendientes")

        confirmacion = (
            input("\n¿Deseas marcar los pendientes como RECUPERADO? " "(S/N):\n> ").strip().upper()
        )

        if confirmacion != "S":
            print("\nOperación cancelada. " "No se realizaron cambios en los pendientes.\n")
        else: 
            procesar_desmontaje(pendientes)

    if not otra_network:
        print("\nNo existen equipos pendientes de otra Network por marcar. \n")
    else:
        print("\nDeseas modificar los equipos mostrados " "en otra network?")
    
        confirmacion = (
            input("\n¿Deseas marcarlos como RECUPERADO? " "(S/N):\n> ").strip().upper()
        )
    
        if confirmacion != "S":
            print("\nOperación cancelada. " "No se realizaron cambios.\n")
            return
    
        procesar_desmontaje(otra_network)