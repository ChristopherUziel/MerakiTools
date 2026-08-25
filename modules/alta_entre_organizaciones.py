import requests
import time
from config import cambios_habilitados
from meraki_api import (
    actualizar_dispositivo,
    actualizar_nombre_dispositivo,
    agregar_dispositivos_network,
    esperar_dispositivo_en_network,
    liberar_dispositivos_organizacion,
    obtener_dispositivos_inventario,
    obtener_networks,
    obtener_organizaciones,
    reclamar_dispositivos_organizacion,
    retirar_dispositivo_network,
)
from modules.alta_evento import (
    convertir_seriales,
    obtener_siguiente_numero_nombre,
    seleccionar_network,
    seleccionar_organizacion,
)
from navegacion import input_menu
from auditoria import registrar_auditoria


def identificar_tipo_equipo(modelo: str) -> str:
    """
    Identifica el tipo de dispositivo según su modelo.
    """

    modelo_mayusculas = (modelo or "").strip().upper()

    if modelo_mayusculas.startswith("MR"):
        return "MR"

    if modelo_mayusculas.startswith("MS"):
        return "MS"

    if modelo_mayusculas.startswith("MX"):
        return "MX"

    return "OTRO"


def crear_mapa_networks(
    organization_id: str,
) -> dict[str, str]:
    """
    Obtiene las Networks de una organización y crea
    un diccionario:

    network_id -> nombre de la Network
    """

    networks = obtener_networks(organization_id)

    return {
        network["id"]: network.get(
            "name",
            "Network sin nombre",
        )
        for network in networks
    }


def buscar_equipos_en_organizaciones(
    seriales: list[str],
    organizaciones: list[dict],
) -> tuple[dict, list[str], list[dict]]:
    """
    Busca los seriales en todas las organizaciones

    Devuelve:
    - equipos encontrados por serial.
    - seriales no encontrados.
    - organizaciones que no pudieron consultarse.
    """

    equipos_encontrados = {}
    organizaciones_con_error = []

    for organizacion in organizaciones:
        seriales_pendientes = [
            serial for serial in seriales if serial not in equipos_encontrados
        ]

        if not seriales_pendientes:
            break

        print(f"Consultando organización: " f"{organizacion['name']}...")

        try:
            dispositivos = obtener_dispositivos_inventario(
                organization_id=organizacion["id"],
                seriales=seriales_pendientes,
            )

        except requests.RequestException as error:
            organizaciones_con_error.append(
                {
                    "organizacion": organizacion["name"],
                    "error": str(error),
                }
            )
            continue

        if not dispositivos:
            continue

        try:
            networks_por_id = crear_mapa_networks(organizacion["id"])

        except requests.RequestException as error:
            organizaciones_con_error.append(
                {
                    "organizacion": organizacion["name"],
                    "error": str(error),
                }
            )
            networks_por_id = {}

        for dispositivo in dispositivos:
            serial = dispositivo.get("serial")

            if not serial:
                continue

            network_actual_id = dispositivo.get("networkId")

            if network_actual_id:
                nombre_network = networks_por_id.get(
                    network_actual_id,
                    "Network no identificada",
                )
            else:
                nombre_network = "Disponible en inventario"

            modelo = dispositivo.get(
                "model",
                "Desconocido",
            )

            equipos_encontrados[serial] = {
                "serial": serial,
                "modelo": modelo,
                "tipo": identificar_tipo_equipo(modelo),
                "nombre_actual": dispositivo.get("name"),
                "tags_actuales": dispositivo.get(
                    "tags",
                    [],
                ),
                "organization_actual_id": (organizacion["id"]),
                "organizacion_actual_nombre": (organizacion["name"]),
                "network_actual_id": (network_actual_id),
                "network_actual_nombre": (nombre_network),
            }

    seriales_no_encontrados = [
        serial for serial in seriales if serial not in equipos_encontrados
    ]

    return (
        equipos_encontrados,
        seriales_no_encontrados,
        organizaciones_con_error,
    )


def determinar_accion_equipo(
    equipo: dict,
    organizacion_destino_id: str,
    network_destino_id: str,
) -> str:
    """
    Determina qué proceso necesitaría cada equipo
    para llegar a la Network destino.
    """

    tipo = equipo["tipo"]

    if tipo == "MX":
        return "BLOQUEADO: requiere proceso especial " "o migración manual"

    if tipo not in ("MR", "MS"):
        return "BLOQUEADO: tipo de equipo " "no permitido en este módulo"

    misma_organizacion = equipo["organization_actual_id"] == organizacion_destino_id

    misma_network = equipo["network_actual_id"] == network_destino_id

    if misma_organizacion and misma_network:
        return "Ya está en la Network destino"

    if misma_organizacion and equipo["network_actual_id"] is None:
        return "Agregar desde inventario " "a la Network destino"

    if misma_organizacion:
        return "Mover desde otra Network " "de la misma organización"

    if equipo["network_actual_id"] is None:
        return "Liberar de organización origen, " "reclamar y agregar a destino"

    return "Retirar de Network origen, liberar, " "reclamar y agregar a destino"


def equipo_puede_procesarse(
    equipo: dict,
) -> bool:
    """
    Solo MR y MS pueden moverse
    """

    return equipo["tipo"] in ("MR", "MS")


def preparar_nombres_y_tags(
    equipos: list[dict],
    nombre_base: str,
    tags_nuevos: list[str],
    numero_inicial: int,
) -> None:
    """
    Asigna nombres consecutivos a todos los MR y MS.

    Los tags nuevos se preparan únicamente para los MR.
    Los MS no recibirán cambios de tags.
    """

    numero_actual = numero_inicial

    for equipo in equipos:
        if not equipo_puede_procesarse(equipo):
            continue

        equipo["nombre_nuevo"] = f"{nombre_base}-{numero_actual:02d}"

        numero_actual += 1

        if equipo["tipo"] == "MR":
            equipo["tags_nuevos"] = tags_nuevos
        else:
            equipo["tags_nuevos"] = None


def mostrar_resumen_entre_organizaciones(
    organizacion_destino: dict,
    network_destino: dict,
    equipos: list[dict],
    seriales_no_encontrados: list[str],
    organizaciones_con_error: list[dict],
) -> None:
    """
    Muestra la validación completa antes de realizar
    cualquier movimiento.
    """

    print("\n=== VALIDACIÓN DE ALTA ENTRE " "ORGANIZACIONES ===\n")

    print(f"Organización destino: " f"{organizacion_destino['name']}")
    print(f"Network destino: " f"{network_destino['name']}\n")

    for equipo in equipos:
        print("-" * 60)
        print(f"Serial: {equipo['serial']}")
        print(f"Modelo: {equipo['modelo']}")
        print(f"Tipo: {equipo['tipo']}")
        print(f"Organización actual: " f"{equipo['organizacion_actual_nombre']}")
        print(f"Network actual: " f"{equipo['network_actual_nombre']}")
        print(f"Nombre actual: " f"{equipo['nombre_actual'] or 'Sin nombre'}")
        print(f"Acción: {equipo['accion']}")

        if equipo_puede_procesarse(equipo):
            print(f"Nombre nuevo: " f"{equipo['nombre_nuevo']}")

            if equipo["tipo"] == "MR":
                tags = equipo["tags_nuevos"]

                print("Tags nuevos: " f"{', '.join(tags) or 'Sin tags'}")
            else:
                print("Tags: no se modificarán " "por tratarse de un MS")

    if seriales_no_encontrados:
        print("\n=== SERIALES NO ENCONTRADOS ===\n")

        for serial in seriales_no_encontrados:
            print(f"- {serial}")

    if organizaciones_con_error:
        print("\n=== ORGANIZACIONES NO CONSULTADAS ===\n")

        for error in organizaciones_con_error:
            print(f"- {error['organizacion']}: " f"{error['error']}")

    equipos_procesables = [
        equipo for equipo in equipos if equipo_puede_procesarse(equipo)
    ]

    equipos_mx = [equipo for equipo in equipos if equipo["tipo"] == "MX"]

    equipos_otro_tipo = [equipo for equipo in equipos if equipo["tipo"] == "OTRO"]

    print("\n=== RESUMEN ===\n")
    print(f"Equipos encontrados: {len(equipos)}")
    print(f"Equipos MR/MS procesables: " f"{len(equipos_procesables)}")
    print(f"Equipos MX bloqueados: " f"{len(equipos_mx)}")
    print(f"Otros tipos bloqueados: " f"{len(equipos_otro_tipo)}")
    print(f"No encontrados: " f"{len(seriales_no_encontrados)}")


def inicializar_resultados_equipos(
    equipos: list[dict],
) -> None:
    """
    Prepara campos que permitirán registrar hasta qué
    etapa avanzó cada equipo.
    """

    for equipo in equipos:
        equipo["resultado"] = "Pendiente"
        equipo["ultima_etapa"] = "Validación"
        equipo["error"] = None


def registrar_error_equipo(
    equipo: dict,
    etapa: str,
    error,
) -> None:
    """
    Registra dónde falló un equipo y el mensaje recibido.
    """

    equipo["resultado"] = "Error"
    equipo["ultima_etapa"] = etapa
    equipo["error"] = str(error)


def liberar_equipos_de_organizaciones(
    equipos: list[dict],
    organizacion_destino_id: str,
) -> list[dict]:
    """
    Libera, por grupos, los equipos que pertenecen
    a organizaciones distintas a la organización destino.

    Devuelve los equipos que Meraki confirmó como liberados.
    """

    grupos = agrupar_equipos_por_organizacion(
        equipos=equipos,
        organizacion_destino_id=organizacion_destino_id,
    )

    equipos_liberados = []

    if not grupos:
        return equipos_liberados

    print("\n=== LIBERANDO DE ORGANIZACIONES " "DE ORIGEN ===\n")

    for organization_id, grupo in grupos.items():
        seriales = [equipo["serial"] for equipo in grupo]

        nombre_organizacion = grupo[0]["organizacion_actual_nombre"]

        try:
            respuesta = liberar_dispositivos_organizacion(
                organization_id=organization_id,
                seriales=seriales,
            )

            seriales_liberados = respuesta.get(
                "serials",
                [],
            )

            for equipo in grupo:
                if equipo["serial"] in seriales_liberados:
                    equipo["ultima_etapa"] = "Liberado de organización origen"

                    equipos_liberados.append(equipo)

                    print(
                        f"✓ {equipo['serial']} | " f"Liberado de {nombre_organizacion}"
                    )
                else:
                    registrar_error_equipo(
                        equipo=equipo,
                        etapa=("Liberar de organización origen"),
                        error=("Meraki no confirmó el serial " "como liberado."),
                    )

        except requests.RequestException as error:
            for equipo in grupo:
                registrar_error_equipo(
                    equipo=equipo,
                    etapa="Liberar de organización origen",
                    error=error,
                )

                print(f"✗ {equipo['serial']} | " f"No se pudo liberar: {error}")

    return equipos_liberados


def reclamar_equipos_en_destino(
    equipos_liberados: list[dict],
    organizacion_destino_id: str,
) -> list[dict]:
    """
    Reclama dentro de la organización destino los equipos
    previamente liberados de otras organizaciones.
    """

    if not equipos_liberados:
        return []

    print("\n=== RECLAMANDO EN ORGANIZACIÓN DESTINO ===\n")

    seriales = [equipo["serial"] for equipo in equipos_liberados]

    try:
        respuesta = reclamar_dispositivos_organizacion(
            organization_id=organizacion_destino_id,
            seriales=seriales,
        )

        seriales_reclamados = respuesta.get(
            "serials",
            [],
        )

    except requests.RequestException as error:
        for equipo in equipos_liberados:
            registrar_error_equipo(
                equipo=equipo,
                etapa="Reclamar en organización destino",
                error=error,
            )

            print(
                f"✗ {equipo['serial']} | "
                "Fue liberado, pero no pudo reclamarse "
                f"en destino: {error}"
            )

        return []

    equipos_reclamados = []

    for equipo in equipos_liberados:
        if equipo["serial"] in seriales_reclamados:
            equipo["ultima_etapa"] = "Reclamado en organización destino"

            equipos_reclamados.append(equipo)

            print(f"✓ {equipo['serial']} | " "Reclamado en organización destino")
        else:
            registrar_error_equipo(
                equipo=equipo,
                etapa="Reclamar en organización destino",
                error=("Meraki no confirmó el serial " "como reclamado."),
            )

            print(
                f"✗ {equipo['serial']} | " "Quedó liberado y requiere revisión manual"
            )

    return equipos_reclamados


def agrupar_equipos_por_organizacion(
    equipos: list[dict],
    organizacion_destino_id: str,
) -> dict[str, list[dict]]:
    """
    Agrupa únicamente los equipos que deben salir
    de otra organización.

    Devuelve:

    organization_id -> lista de equipos
    """

    grupos = {}

    for equipo in equipos:
        if not equipo_puede_procesarse(equipo):
            continue

        if equipo["resultado"] == "Error":
            continue

        organizacion_actual_id = equipo["organization_actual_id"]

        if organizacion_actual_id == organizacion_destino_id:
            continue

        if organizacion_actual_id not in grupos:
            grupos[organizacion_actual_id] = []

        grupos[organizacion_actual_id].append(equipo)

    return grupos


def retirar_equipos_de_network_origen(
    equipos: list[dict],
    network_destino_id: str,
) -> None:
    """
    Retira cada equipo de su Network actual cuando:

    - tiene una Network asignada o esa Network no es la Network destino.

    Los equipos que ya están en destino no se retiran.
    """

    print("\n=== RETIRANDO DE NETWORKS DE ORIGEN ===\n")

    for equipo in equipos:
        if not equipo_puede_procesarse(equipo):
            continue

        if equipo["resultado"] == "Error":
            continue

        network_actual_id = equipo["network_actual_id"]

        if network_actual_id is None:
            equipo["ultima_etapa"] = "Disponible en inventario de origen"
            continue

        if network_actual_id == network_destino_id:
            equipo["ultima_etapa"] = "Ya estaba en la Network destino"
            continue

        try:
            retirar_dispositivo_network(
                network_id=network_actual_id,
                serial=equipo["serial"],
            )

            equipo["ultima_etapa"] = "Retirado de la Network origen"

            print(
                f"✓ {equipo['serial']} | "
                f"Retirado de "
                f"{equipo['network_actual_nombre']}"
            )

        except requests.RequestException as error:
            registrar_error_equipo(
                equipo=equipo,
                etapa="Retirar de Network origen",
                error=error,
            )

            print(f"✗ {equipo['serial']} | " f"No se pudo retirar: {error}")


def obtener_equipos_para_network_destino(
    equipos: list[dict],
    organizacion_destino_id: str,
    network_destino_id: str,
    equipos_reclamados: list[dict],
) -> list[dict]:
    """
    Devuelve los equipos que todavía deben agregarse
    a la Network destino.

    Incluye:
    - equipos recién reclamados;
    - equipos que ya pertenecían a la organización destino;
    - equipos disponibles en el inventario destino.
    """

    seriales_reclamados = {equipo["serial"] for equipo in equipos_reclamados}

    equipos_para_agregar = []

    for equipo in equipos:
        if not equipo_puede_procesarse(equipo):
            continue

        if equipo["resultado"] == "Error":
            continue

        ya_esta_en_destino = (
            equipo["organization_actual_id"] == organizacion_destino_id
            and equipo["network_actual_id"] == network_destino_id
        )

        if ya_esta_en_destino:
            continue

        pertenece_al_destino = (
            equipo["organization_actual_id"] == organizacion_destino_id
        )

        fue_reclamado = equipo["serial"] in seriales_reclamados

        if pertenece_al_destino or fue_reclamado:
            equipos_para_agregar.append(equipo)

    return equipos_para_agregar


def agregar_equipos_a_network_destino(
    equipos: list[dict],
    network_destino_id: str,
    intentos: int = 6,
    espera_segundos: int = 15,
) -> list[dict]:
    """
    Intenta agregar los equipos a la Network destino.

    Si Meraki todavía no ha terminado de propagar el claim,
    espera y vuelve a intentarlo.

    Si detecta un error de compatibilidad con NBAR,
    no continúa reintentando.
    """

    if not equipos:
        return []

    print("\n=== AGREGANDO A NETWORK DESTINO ===\n")

    seriales = [equipo["serial"] for equipo in equipos]

    ultimo_error = None
    detalle_meraki = ""

    for intento in range(1, intentos + 1):
        try:
            agregar_dispositivos_network(
                network_id=network_destino_id,
                seriales=seriales,
            )

            equipos_agregados = []

            for equipo in equipos:
                equipo["ultima_etapa"] = "Solicitud de alta enviada a Network destino"

                equipos_agregados.append(equipo)

                print(f"✓ {equipo['serial']} | " "Solicitud enviada")

            return equipos_agregados

        except requests.HTTPError as error:
            ultimo_error = error

            if error.response is not None:
                detalle_meraki = error.response.text
            else:
                detalle_meraki = ""

            detalle_mayusculas = detalle_meraki.upper()

            if "NBAR" in detalle_mayusculas:
                print(
                    "\nNo se pueden agregar uno o más equipos "
                    "a la Network destino porque tiene NBAR activo."
                )
                print(
                    "El modelo detectado no es compatible " "con esa configuración.\n"
                )

                for equipo in equipos:
                    registrar_error_equipo(
                        equipo=equipo,
                        etapa="Agregar a Network destino",
                        error=(
                            "Equipo incompatible con la Network "
                            "mientras NBAR está activo. "
                            "El dispositivo permanece en el "
                            "inventario de la organización destino."
                        ),
                    )

                    print(
                        f"✗ {equipo['serial']} | "
                        "Pendiente de asignación a una "
                        "Network compatible"
                    )

                return []

            if intento < intentos:
                print(
                    f"\nMeraki todavía no permitió agregar "
                    f"los equipos. Intento {intento} de "
                    f"{intentos}."
                )
                print(
                    f"Esperando {espera_segundos} segundos "
                    "antes de volver a intentar...\n"
                )

                time.sleep(espera_segundos)
                continue

        except requests.RequestException as error:
            ultimo_error = error

            if intento < intentos:
                print(
                    f"\nNo fue posible completar la solicitud. "
                    f"Intento {intento} de {intentos}."
                )
                print(f"Esperando {espera_segundos} segundos...\n")

                time.sleep(espera_segundos)
                continue

    print("\nNo fue posible agregar los equipos después de varios intentos.")

    if detalle_meraki:
        print(f"\nDetalle devuelto por Meraki:\n{detalle_meraki}\n")

    for equipo in equipos:
        registrar_error_equipo(
            equipo=equipo,
            etapa="Agregar a Network destino",
            error=ultimo_error or "Error desconocido",
        )

        print(f"✗ {equipo['serial']} | " "No se pudo agregar a la Network destino")

    return []


def actualizar_equipos_en_destino(
    equipos: list[dict],
    network_destino_id: str,
    intentos: int = 12,
    espera_segundos: int = 10,
) -> None:
    """
    Espera a que cada dispositivo aparezca en destino
    y actualiza sus datos.

    Si marca error 404, espera a meraki responda y termine la propagacion
    """

    if not equipos:
        return

    print("\n=== ACTUALIZANDO NOMBRES Y TAGS ===\n")

    for equipo in equipos:
        if equipo["resultado"] == "Error":
            continue

        serial = equipo["serial"]

        try:
            encontrado = esperar_dispositivo_en_network(
                serial=serial,
                network_id=network_destino_id,
            )

        except requests.RequestException as error:
            registrar_error_equipo(
                equipo=equipo,
                etapa="Esperar equipo en Network destino",
                error=error,
            )

            print(f"✗ {serial} | " "No fue posible verificar la Network destino")
            continue

        if not encontrado:
            registrar_error_equipo(
                equipo=equipo,
                etapa="Esperar equipo en Network destino",
                error=(
                    "El equipo no apareció en destino " "dentro del tiempo esperado."
                ),
            )

            print(f"✗ {serial} | " "No apareció a tiempo en destino")
            continue

        actualizado = False
        ultimo_error = None

        for intento in range(1, intentos + 1):
            try:
                if equipo["tipo"] == "MR":
                    actualizar_dispositivo(
                        serial=serial,
                        nombre=equipo["nombre_nuevo"],
                        tags=equipo["tags_nuevos"],
                    )

                elif equipo["tipo"] == "MS":
                    actualizar_nombre_dispositivo(
                        serial=serial,
                        nombre=equipo["nombre_nuevo"],
                    )

                actualizado = True
                break

            except requests.HTTPError as error:
                ultimo_error = error

                codigo_estado = (
                    error.response.status_code if error.response is not None else None
                )

                if codigo_estado == 404 and intento < intentos:
                    print(
                        f"El equipo {serial} ya está en destino, "
                        "pero Meraki todavía no permite actualizarlo."
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
                    print(
                        f"No fue posible actualizar {serial}. "
                        f"Reintentando en {espera_segundos} segundos "
                        f"({intento}/{intentos})...\n"
                    )

                    time.sleep(espera_segundos)
                    continue

                break

        if actualizado:
            equipo["resultado"] = "Correcto"
            equipo["ultima_etapa"] = "Nombre y configuración actualizados"

            print(f"✓ {serial} | " f"{equipo['nombre_nuevo']}")

        else:
            equipo["resultado"] = "Movimiento correcto, actualización pendiente"
            equipo["ultima_etapa"] = (
                "Equipo agregado a destino; " "nombre o tags pendientes"
            )
            equipo["error"] = str(ultimo_error or "Error desconocido")

            print(
                f"⚠ {serial} | "
                "El equipo fue movido correctamente, "
                "pero no fue posible actualizar todavía "
                "su nombre o tags."
            )


def obtener_equipos_ya_en_destino(
    equipos: list[dict],
    organizacion_destino_id: str,
    network_destino_id: str,
) -> list[dict]:
    """
    Obtiene los equipos que ya estaban asignados
    a la Network destino para actualizarlos
    """

    return [
        equipo
        for equipo in equipos
        if equipo_puede_procesarse(equipo)
        and equipo["resultado"] != "Error"
        and equipo["organization_actual_id"] == organizacion_destino_id
        and equipo["network_actual_id"] == network_destino_id
    ]


def alta_entre_organizaciones():
    """
    Controla el flujo principal del modulo
    """

    print("\n=== ALTA MASIVA ENTRE " "ORGANIZACIONES ===\n")

    try:
        organizacion_destino = seleccionar_organizacion()

        network_destino = seleccionar_network(organizacion_destino["id"])

    except requests.RequestException as error:
        print("\nNo fue posible consultar Meraki: " f"{error}\n")
        return

    except ValueError as error:
        print(f"\nError: {error}\n")
        return

    print(f"\nOrganización destino: " f"{organizacion_destino['name']}")
    print(f"Network destino: " f"{network_destino['name']}\n")

    entrada_seriales = input_menu("Ingresa los seriales separados por comas:\n> ")

    try:
        seriales = convertir_seriales(entrada_seriales)

    except ValueError as error:
        print(f"\nError: {error}\n")
        return

    if not seriales:
        print("\nNo se ingresaron seriales válidos.\n")
        return

    nombre_base = input_menu("Nombre base de los equipos:\n> ").upper()

    if not nombre_base:
        print("\nEl nombre base es obligatorio.\n")
        return

    entrada_tags = input_menu(
        "Nuevos tags para equipos MR, " "separados por comas:\n> "
    )

    tags_nuevos = [tag.strip() for tag in entrada_tags.split(",") if tag.strip()]

    try:
        numero_inicial = obtener_siguiente_numero_nombre(
            network_id=network_destino["id"],
            nombre_base=nombre_base,
        )

        organizaciones = obtener_organizaciones()

        (
            equipos_encontrados,
            seriales_no_encontrados,
            organizaciones_con_error,
        ) = buscar_equipos_en_organizaciones(
            seriales=seriales,
            organizaciones=organizaciones,
        )

    except requests.RequestException as error:
        print("\nNo fue posible completar " f"la búsqueda: {error}\n")
        return

    equipos = []

    for serial in seriales:
        equipo = equipos_encontrados.get(serial)

        if equipo is None:
            continue

        equipo["accion"] = determinar_accion_equipo(
            equipo=equipo,
            organizacion_destino_id=(organizacion_destino["id"]),
            network_destino_id=(network_destino["id"]),
        )

        equipos.append(equipo)

    preparar_nombres_y_tags(
        equipos=equipos,
        nombre_base=nombre_base,
        tags_nuevos=tags_nuevos,
        numero_inicial=numero_inicial,
    )

    mostrar_resumen_entre_organizaciones(
        organizacion_destino=organizacion_destino,
        network_destino=network_destino,
        equipos=equipos,
        seriales_no_encontrados=(seriales_no_encontrados),
        organizaciones_con_error=(organizaciones_con_error),
    )

    equipos_procesables = [
        equipo for equipo in equipos if equipo_puede_procesarse(equipo)
    ]

    if not equipos_procesables:
        print("\nNo hay equipos MR o MS disponibles " "para procesar.\n")
        return

    confirmacion = input_menu(
        "\n¿Confirmas el movimiento de los equipos " "MR y MS mostrados? (S/N):\n> "
    ).upper()

    if confirmacion != "S":
        print("\nOperación cancelada. " "No se realizaron cambios.\n")
        return

    procesar_alta_entre_organizaciones(
        equipos=equipos,
        organizacion_destino=organizacion_destino,
        network_destino=network_destino,
    )


def mostrar_resultado_final_movimiento(
    equipos: list[dict],
) -> None:
    """
    Muestra el resultado y la última etapa alcanzada
    por cada dispositivo
    """

    pendientes_actualizacion = 0

    print("\n=== RESULTADO FINAL DEL MOVIMIENTO ===\n")

    correctos = 0
    errores = 0
    bloqueados = 0

    for equipo in equipos:
        if not equipo_puede_procesarse(equipo):
            bloqueados += 1

            print(f"{equipo['serial']} | " f"{equipo['tipo']} | BLOQUEADO")
            print(f"  Motivo: {equipo['accion']}")
            continue

        resultado = equipo.get(
            "resultado",
            "Sin procesar",
        )

        if resultado == "Correcto":
            correctos += 1
        elif resultado == "Error":
            errores += 1
        elif resultado == "Movimiento correcto, actualización pendiente":
            pendientes_actualizacion += 1

        print(f"{equipo['serial']} | " f"{equipo['tipo']} | {resultado}")

        print(f"  Última etapa: " f"{equipo.get('ultima_etapa', 'Desconocida')}")

        if equipo.get("error"):
            print(f"  Error: {equipo['error']}")

    print("\nResumen:")
    print(f"- Correctos: {correctos}")
    print(f"- Errores: {errores}")
    print(f"- Movidos con actualización pendiente: " f"{pendientes_actualizacion}")
    print(f"- Bloqueados: {bloqueados}")


def procesar_alta_entre_organizaciones(
    equipos: list[dict],
    organizacion_destino: dict,
    network_destino: dict,
) -> None:
    """
    Ejecuta el movimiento completo de los equipos MR y MS.
    """

    if not cambios_habilitados():
        print("\nLas operaciones de escritura están " "bloqueadas en settings.json.\n")
        return

    inicializar_resultados_equipos(equipos)

    retirar_equipos_de_network_origen(
        equipos=equipos,
        network_destino_id=network_destino["id"],
    )

    equipos_liberados = liberar_equipos_de_organizaciones(
        equipos=equipos,
        organizacion_destino_id=(organizacion_destino["id"]),
    )

    equipos_reclamados = reclamar_equipos_en_destino(
        equipos_liberados=equipos_liberados,
        organizacion_destino_id=(organizacion_destino["id"]),
    )

    equipos_para_agregar = obtener_equipos_para_network_destino(
        equipos=equipos,
        organizacion_destino_id=(organizacion_destino["id"]),
        network_destino_id=network_destino["id"],
        equipos_reclamados=equipos_reclamados,
    )

    equipos_agregados = agregar_equipos_a_network_destino(
        equipos=equipos_para_agregar,
        network_destino_id=network_destino["id"],
    )

    equipos_ya_en_destino = obtener_equipos_ya_en_destino(
        equipos=equipos,
        organizacion_destino_id=(organizacion_destino["id"]),
        network_destino_id=network_destino["id"],
    )

    equipos_para_actualizar = equipos_agregados + equipos_ya_en_destino

    actualizar_equipos_en_destino(
        equipos=equipos_para_actualizar,
        network_destino_id=network_destino["id"],
    )

    mostrar_resultado_final_movimiento(equipos)

    ###### Auditoria
    for equipo in equipos:

        if not equipo_puede_procesarse(equipo):
            registrar_auditoria(
                modulo="Alta entre organizaciones",
                accion="Validar equipo para movimiento",
                organizacion=organizacion_destino["name"],
                network=network_destino["name"],
                objetivo=equipo["serial"],
                resultado="Bloqueado",
                detalle=(
                    f"Origen: "
                    f"{equipo.get('organizacion_actual_nombre', 'No disponible')} | "
                    f"{equipo.get('network_actual_nombre', 'No disponible')} | "
                    f"Motivo: {equipo.get('accion', 'Tipo no permitido')}"
                ),
            )

            continue

        serial = equipo["serial"]

        organizacion_origen = equipo.get(
            "organizacion_actual_nombre",
            "No disponible",
        )

        network_origen = equipo.get(
            "network_actual_nombre",
            "No disponible",
        )

        resultado = equipo.get(
            "resultado",
            "Sin procesar",
        )

        ultima_etapa = equipo.get(
            "ultima_etapa",
            "No disponible",
        )

        error = equipo.get("error")

        detalle = (
            f"Origen: {organizacion_origen} | "
            f"{network_origen} | "
            f"Destino: {organizacion_destino['name']} | "
            f"{network_destino['name']} | "
            f"Última etapa: {ultima_etapa}"
        )

        if error:
            detalle += f" | Error: {error}"

        registrar_auditoria(
            modulo="Alta entre organizaciones",
            accion="Mover equipo entre organizaciones",
            organizacion=organizacion_destino["name"],
            network=network_destino["name"],
            objetivo=serial,
            resultado=resultado,
            detalle=detalle,
        )
