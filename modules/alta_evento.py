from config import cambios_habilitados
import requests
import re
import time
from meraki_api import (
    actualizar_dispositivo,
    actualizar_nombre_dispositivo,
    agregar_dispositivos_network,
    esperar_dispositivo_en_network,
    obtener_dispositivos_inventario,
    obtener_dispositivos_network,
    obtener_networks,
    obtener_organizaciones,
    retirar_dispositivo_network,
)
from navegacion import input_menu


def normalizar_serial(serial: str) -> str:
    """
    Normaliza el numero de serie al formato estandar
    """

    serial_limpio = serial.strip().upper().replace("-", "").replace("'","")

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


def identificar_tipo_equipo(modelo: str) -> str:
    """
    Identifica el tipo de dispositivo por su modelo
    """

    modelo_mayusculas = (modelo or "").strip().upper()

    if modelo_mayusculas.startswith("MR"):
        return "MR"
    if modelo_mayusculas.startswith("MS"):
        return "MS"
    if modelo_mayusculas.startswith("MX"):
        return "MX"
    return "OTRO"


def combinar_tags(
    tags_actuales: list[str],
    tags_nuevos: list[str],
) -> list[str]:
    """
    conserva los tags actuales y agrega los nuevos.
    """

    tags_combinados = []

    for tag in tags_actuales + tags_nuevos:
        tag_limpio = tag.strip()

        if not tag_limpio:
            continue

        ya_existe = any(
            tag_existente.lower() == tag_limpio.lower()
            for tag_existente in tags_combinados
        )

        if not ya_existe:
            tags_combinados.append(tag_limpio)

    return tags_combinados


def obtener_siguiente_numero_nombre(
    network_id: str,
    nombre_base: str,
) -> int:
    """
    Consulta los nombres actuales de la Network y obtiene
    el siguiente número disponible para el nombre base, su consecutivo.
    """

    dispositivos = obtener_dispositivos_network(network_id)

    numero_mayor = 0

    patron = re.compile(
        rf"^{re.escape(nombre_base)}-(\d+)$",
        re.IGNORECASE,
    )

    for dispositivo in dispositivos:
        nombre_actual = dispositivo.get("name")

        if not nombre_actual:
            continue

        coincidencia = patron.match(nombre_actual.strip())

        if coincidencia:
            numero = int(coincidencia.group(1))
            numero_mayor = max(numero_mayor, numero)

    return numero_mayor + 1


def crear_lista_equipos(
    seriales: list[str],
    nombre_base: str,
    tags: list[str],
    numero_inicial: int = 1,
) -> list[dict]:
    """
    Construye la información que posteriormente se enviará a Meraki.
    """

    equipos = []

    for numero, serial in enumerate(
        seriales,
        start=numero_inicial,
    ):
        equipo = {
            "serial": serial,
            "nombre": f"{nombre_base}-{numero:02d}",
            "tags": tags,
        }

        equipos.append(equipo)

    return equipos


def seleccionar_organizacion(
    descripcion: str = "de destino",
) -> dict:

    organizaciones = obtener_organizaciones()

    if not organizaciones:
        raise ValueError("No se encontraron organizaciones disponibles.")

    print("\nOrganizaciones disponibles:\n")

    for indice, organizacion in enumerate(organizaciones, start=1):
        print(f"{indice}. {organizacion['name']}")

    opcion = input_menu(f"\nSelecciona una organización {descripcion}:\n> ")

    if not opcion.isdigit():
        raise ValueError("Debes ingresar un número.")

    indice = int(opcion) - 1

    if indice < 0 or indice >= len(organizaciones):
        raise ValueError("La organización seleccionada no existe.")

    return organizaciones[indice]


def seleccionar_network(
    organization_id: str,
    descripcion: str = "de destino",
) -> dict:
    networks = obtener_networks(organization_id)

    if not networks:
        raise ValueError("No se encontraron redes disponibles.")

    networks.sort(key=lambda network: network["name"].lower())

    print("\nNetworks disponibles:\n")

    for indice, network in enumerate(networks, start=1):
        print(f"{indice}. {network['name']}")

    opcion = input_menu(f"\nSelecciona la Network {descripcion}:\n> ")

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

    Devuelve
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

        equipo["tipo"] = identificar_tipo_equipo(equipo["modelo"])

        equipo["network_actual_id"] = network_actual_id

        equipo["nombre_actual"] = dispositivo.get("name")

        equipo["tags_actuales"] = dispositivo.get("tags", [])

        if equipo["tipo"] == "MR":
            equipo["procesable"] = True

            equipo["tags_finales"] = combinar_tags(
                tags_actuales=equipo["tags_actuales"],
                tags_nuevos=equipo["tags"],
            )

        elif equipo["tipo"] == "MS":
            equipo["procesable"] = True

            # Los tags del MS se conservan
            equipo["tags_finales"] = None

        elif equipo["tipo"] == "MX":
            equipo["procesable"] = False
            equipo["tags_finales"] = None

            equipo["motivo_bloqueo"] = (
                "Equipo MX: requiere proceso especial " "o migración manual."
            )

        else:
            equipo["procesable"] = False
            equipo["tags_finales"] = None

            equipo["motivo_bloqueo"] = "Tipo de equipo no permitido " "en este módulo."

        if network_actual_id is None:
            equipo["estado"] = "Disponible en inventario"
        elif network_actual_id == network_destino_id:
            equipo["estado"] = "Ya se encuentra en la Network destino"
        else:
            equipo["estado"] = "Asignado a otra Network"

        equipos_validos.append(equipo)

    return equipos_validos, seriales_no_encontrados


def actualizar_equipo_con_reintentos(
    equipo: dict,
    intentos: int = 10,
    espera_segundos: int = 10,
) -> bool:
    """
    Actualiza el nombre y, cuando sea MR, también los tags.

    Si Meraki responde temporalmente con 404 después de mover
    el dispositivo, espera y vuelve a intentarlo.

    Devuelve:
    True  -> actualización correcta.
    False -> no fue posible actualizar.
    """

    serial = equipo["serial"]
    ultimo_error = None

    for intento in range(1, intentos + 1):
        try:
            if equipo["tipo"] == "MR":
                actualizar_dispositivo(
                    serial=serial,
                    nombre=equipo["nombre"],
                    tags=equipo["tags_finales"],
                )

            elif equipo["tipo"] == "MS":
                actualizar_nombre_dispositivo(
                    serial=serial,
                    nombre=equipo["nombre"],
                )

            equipo["resultado"] = "Correcto"
            equipo["ultima_etapa"] = "Nombre y configuración actualizados"
            equipo["error"] = None

            print(f"✓ {serial} | " f"Actualizado como {equipo['nombre']}")

            return True

        except requests.HTTPError as error:
            ultimo_error = error

            codigo_estado = (
                error.response.status_code if error.response is not None else None
            )

            if codigo_estado == 404 and intento < intentos:
                print(f"{serial} todavía no está disponible " "para actualizarse.")
                print(
                    f"Reintentando en {espera_segundos} segundos "
                    f"({intento}/{intentos})...\n"
                )

                time.sleep(espera_segundos)
                continue

            break

        except requests.RequestException as error:
            ultimo_error = error

            if intento < intentos:
                print(
                    f"No fue posible actualizar {serial}. "
                    f"Reintentando en {espera_segundos} segundos "
                    f"({intento}/{intentos})...\n"
                )

                time.sleep(espera_segundos)
                continue

            break

    equipo["resultado"] = "Movimiento correcto, actualización pendiente"
    equipo["ultima_etapa"] = "Equipo en destino; nombre o tags pendientes"
    equipo["error"] = str(ultimo_error or "Error desconocido")

    print(
        f"⚠ {serial} | El equipo llegó a destino, "
        "pero no fue posible actualizar su nombre o tags."
    )

    return False


def error_es_incompatibilidad_nbar(
    error: requests.HTTPError,
) -> bool:
    """
    Revisa si Meraki rechazó el equipo porque la Network
    utiliza NBAR y el modelo no es compatible.
    """

    if error.response is None:
        return False

    detalle = error.response.text.upper()

    return "NBAR" in detalle


def agregar_equipos_network_con_reintentos(
    equipos: list[dict],
    network_destino_id: str,
    intentos: int = 10,
    espera_segundos: int = 10,
) -> list[dict]:
    """
    Agrega los equipos a la Network destino.

    Si Meraki todavía está procesando el retiro de la
    Network anterior, espera y vuelve a intentarlo.
    """

    if not equipos:
        return []

    seriales = [equipo["serial"] for equipo in equipos]

    ultimo_error = None
    detalle_meraki = ""

    for intento in range(1, intentos + 1):
        try:
            agregar_dispositivos_network(
                network_id=network_destino_id,
                seriales=seriales,
            )

            for equipo in equipos:
                equipo["ultima_etapa"] = (
                    "Solicitud de alta enviada " "a la Network destino"
                )

                print(
                    f"✓ {equipo['serial']} | " "Solicitud enviada a la Network destino"
                )

            return equipos

        except requests.HTTPError as error:
            ultimo_error = error

            detalle_meraki = error.response.text if error.response is not None else ""

            if error_es_incompatibilidad_nbar(error):
                print(
                    "\nMeraki no permitió agregar uno o más "
                    "equipos porque la Network tiene NBAR activo "
                    "y el modelo no es compatible.\n"
                )

                for equipo in equipos:
                    equipo["resultado"] = "Error"
                    equipo["ultima_etapa"] = "Agregar a Network destino"
                    equipo["error"] = (
                        "Modelo incompatible con una Network " "que utiliza NBAR."
                    )

                    print(
                        f"✗ {equipo['serial']} | "
                        "Debe utilizarse una Network compatible "
                        "o revisar la configuración NBAR."
                    )

                return []

            if intento < intentos:
                print(
                    "\nMeraki todavía no permitió agregar " "los equipos a la Network."
                )
                print(
                    f"Reintentando en {espera_segundos} segundos "
                    f"({intento}/{intentos})...\n"
                )

                time.sleep(espera_segundos)
                continue

            break

        except requests.RequestException as error:
            ultimo_error = error

            if intento < intentos:
                print("\nNo fue posible completar la solicitud.")
                print(
                    f"Reintentando en {espera_segundos} segundos "
                    f"({intento}/{intentos})...\n"
                )

                time.sleep(espera_segundos)
                continue

            break

    if detalle_meraki:
        print("\nDetalle devuelto por Meraki:\n" f"{detalle_meraki}\n")

    for equipo in equipos:
        equipo["resultado"] = "Error"
        equipo["ultima_etapa"] = "Agregar a Network destino"
        equipo["error"] = str(ultimo_error or "Error desconocido")

        print(f"✗ {equipo['serial']} | " "No se pudo agregar a la Network destino")

    return []


def procesar_alta_equipos(
    equipos: list[dict],
    network_destino: dict,
) -> None:
    """
    Mueve o agrega los equipos MR y MS a la Network destino.
    """

    if not cambios_habilitados():
        print(
            "\nOperaciones de escritura bloqueadas. "
            "No se realizaron cambios en Meraki.\n"
        )
        return

    equipos_ya_en_destino = []
    equipos_para_agregar = []

    for equipo in equipos:
        equipo["resultado"] = "Pendiente"
        equipo["ultima_etapa"] = "Validación"
        equipo["error"] = None

        if equipo["network_actual_id"] == network_destino["id"]:
            equipos_ya_en_destino.append(equipo)
        else:
            equipos_para_agregar.append(equipo)

    print("\n=== PROCESANDO ALTA ===\n")

    # Retirar únicamente los equipos que están
    # asignados a otra Network.
    for equipo in equipos_para_agregar:
        network_anterior_id = equipo.get("network_actual_id")

        if network_anterior_id is None:
            equipo["ultima_etapa"] = "Disponible en inventario"
            continue

        print(f"Retirando {equipo['serial']} " "de su Network anterior...")

        try:
            retirar_dispositivo_network(
                network_id=network_anterior_id,
                serial=equipo["serial"],
            )

            equipo["ultima_etapa"] = "Retirado de la Network anterior"

            print(f"✓ {equipo['serial']} | " "Retirado correctamente")

        except requests.RequestException as error:
            equipo["resultado"] = "Error"
            equipo["ultima_etapa"] = "Retirar de Network anterior"
            equipo["error"] = str(error)

            print(f"✗ No se pudo retirar " f"{equipo['serial']}: {error}")

    # Excluir los equipos que no pudieron retirarse.
    equipos_listos_para_agregar = [
        equipo for equipo in equipos_para_agregar if equipo["resultado"] != "Error"
    ]

    if equipos_listos_para_agregar:
        print(
            f"\nAgregando "
            f"{len(equipos_listos_para_agregar)} "
            f"equipo(s) a {network_destino['name']}..."
        )

    equipos_agregados = agregar_equipos_network_con_reintentos(
        equipos=equipos_listos_para_agregar,
        network_destino_id=network_destino["id"],
    )

    # Los equipos que ya estaban en destino no necesitan
    # volver a agregarse, pero sí deben actualizarse.
    equipos_para_configurar = equipos_agregados + equipos_ya_en_destino

    print("\n=== ACTUALIZANDO EQUIPOS ===\n")

    for equipo in equipos_para_configurar:
        if equipo["resultado"] == "Error":
            continue

        serial = equipo["serial"]

        print(f"\nVerificando {serial}...")

        try:
            disponible = esperar_dispositivo_en_network(
                serial=serial,
                network_id=network_destino["id"],
            )

        except requests.RequestException as error:
            equipo["resultado"] = "Error"
            equipo["ultima_etapa"] = "Verificar equipo en destino"
            equipo["error"] = str(error)

            print(f"✗ No fue posible verificar " f"{serial}: {error}")
            continue

        if not disponible:
            equipo["resultado"] = "Error"
            equipo["ultima_etapa"] = "Esperar equipo en Network destino"
            equipo["error"] = (
                "El dispositivo no apareció en la "
                "Network destino dentro del tiempo esperado."
            )

            print(f"✗ {serial} no apareció a tiempo " "en la Network destino.")
            continue

        actualizar_equipo_con_reintentos(equipo)

    print("\n=== RESULTADO FINAL ===\n")

    correctos = 0
    errores = 0
    pendientes_actualizacion = 0

    for equipo in equipos:
        resultado = equipo.get(
            "resultado",
            "Sin procesar",
        )

        print(f"{equipo['serial']} | " f"{equipo['modelo']} | " f"{resultado}")

        if equipo.get("ultima_etapa"):
            print(f"  Última etapa: " f"{equipo['ultima_etapa']}")

        if equipo.get("error"):
            print(f"  Error: {equipo['error']}")

        if resultado == "Correcto":
            correctos += 1

        elif resultado == "Error":
            errores += 1

        elif resultado == ("Movimiento correcto, actualización pendiente"):
            pendientes_actualizacion += 1

    print("\nResumen:")
    print(f"- Correctos: {correctos}")
    print(f"- Errores: {errores}")
    print("- Movidos con actualización pendiente: " f"{pendientes_actualizacion}")


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

    entrada_seriales = input_menu("Ingresa los números de serie separados por comas:\n> ")

    try:
        seriales = convertir_seriales(entrada_seriales)

    except ValueError as error:
        print(f"\nError: {error}\n")
        return

    if not seriales:
        print("\nNo se ingresaron números de serie válidos.\n")
        return

    nombre_base = input_menu("Nombre base de los equipos:\n> ").upper()

    if not nombre_base:
        print("\nEl nombre base es obligatorio.\n")
        return

    entrada_tags = input_menu("Tags separados por comas:\n> ")

    tags = [tag.strip() for tag in entrada_tags.split(",") if tag.strip()]

    try:
        numero_inicial = obtener_siguiente_numero_nombre(
            network_id=network["id"],
            nombre_base=nombre_base,
        )

    except requests.RequestException as error:
        print(
            "\nNo fue posible revisar la numeración actual " f"de la Network: {error}\n"
        )
        return

    equipos = crear_lista_equipos(
        seriales=seriales,
        nombre_base=nombre_base,
        tags=tags,
        numero_inicial=numero_inicial,
    )

    try:
        equipos_validos, seriales_no_encontrados = validar_equipos_inventario(
            organization_id=organizacion["id"],
            equipos=equipos,
            network_destino_id=network["id"],
        )

    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code == 400:
            print(
                "\nMeraki rechazó la consulta del inventario. "
                "Verifica que los seriales sean reales y estén escritos correctamente.\n"
            )
        else:
            print(f"\nNo fue posible consultar el inventario: {error}\n")

        return

    except requests.RequestException as error:
        print(f"\nNo fue posible comunicarse con Meraki: {error}\n")
        return

    print("\n=== VALIDACIÓN DE EQUIPOS ===\n")

    for equipo in equipos_validos:
        print("-" * 60)

        print(
            f"{equipo['serial']} | " f"{equipo['modelo']} | " f"Tipo: {equipo['tipo']}"
        )

        print(f"Estado: {equipo['estado']}")

        if equipo["procesable"]:
            print(f"Nuevo nombre: " f"{equipo['nombre']}")

            if equipo["tipo"] == "MR":
                print(
                    "Tags actuales: "
                    f"{', '.join(equipo['tags_actuales']) or 'Sin tags'} "
                )

                print(
                    "Tags finales: "
                    f"{', '.join(equipo['tags_finales']) or 'Sin tags'} "
                )

            elif equipo["tipo"] == "MS":
                print("Tags: se conservarán sin cambios")

        else:
            print(f"Bloqueado: " f"{equipo['motivo_bloqueo']}")

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

    equipos_procesables = [equipo for equipo in equipos_validos if equipo["procesable"]]

    if not equipos_procesables:
        print("\nNo hay equipos MR o MS disponibles " "para procesar.\n")
        return

    print(
        "\nADVERTENCIA: esta operación puede mover equipos "
        "desde otras Networks y cambiar sus nombres y tags."
    )

    confirmacion = input_menu("\n¿Deseas continuar con el alta? (S/N):\n> ").upper()

    if confirmacion != "S":
        print("\nOperación cancelada. No se realizaron cambios.\n")
        return

    procesar_alta_equipos(
        equipos=equipos_procesables,
        network_destino=network,
    )
