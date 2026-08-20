import copy
import requests
from config import cambios_habilitados
from meraki_api import (
    actualizar_politica_grupo,
    crear_politica_grupo,
    obtener_networks,
    obtener_organizaciones,
    obtener_politicas_grupo,
)
from modules.alta_evento import (
    seleccionar_network,
    seleccionar_organizacion,
)
from navegacion import input_menu


def seleccionar_varios_elementos(
    elementos: list[dict],
    entrada: str,
    permitir_ninguna: bool = False,
) -> list[dict]:
    """
    Convierte la seleccion en una lista
    """

    entrada = entrada.strip().lower()

    if entrada == "todas":
        return elementos.copy()

    if permitir_ninguna and entrada == "ninguna":
        return []

    seleccionados = []

    for valor in entrada.split(","):
        valor = valor.strip()

        if not valor:
            continue

        if not valor.isdigit():
            raise ValueError(f"'{valor}' no es una opción válida.")

        indice = int(valor) - 1

        if indice < 0 or indice >= len(elementos):
            raise ValueError(f"La opción {valor} no existe.")

        elemento = elementos[indice]

        if elemento not in seleccionados:
            seleccionados.append(elemento)

    if not seleccionados:
        raise ValueError("No seleccionaste ninguna opción válida.")

    return seleccionados


def seleccionar_politicas(
    politicas: list[dict],
) -> list[dict]:
    """
    Permite seleccionar una o varias Group Policies.
    """

    if not politicas:
        return []

    politicas_ordenadas = sorted(
        politicas,
        key=lambda politica: politica.get(
            "name",
            "",
        ).lower(),
    )

    print("\nGroup Policies disponibles:\n")

    for indice, politica in enumerate(
        politicas_ordenadas,
        start=1,
    ):
        nombre = politica.get(
            "name",
            "Sin nombre",
        )

        policy_id = politica.get(
            "groupPolicyId",
            "Sin ID",
        )

        print(f"{indice}. {nombre} " f"| ID: {policy_id}")

    entrada = input_menu(
        "\nSelecciona una o varias políticas "
        "separadas por comas, o escribe 'todas':\n> "
    )

    if entrada.lower() == "todas":
        return politicas_ordenadas

    opciones = []

    for valor in entrada.split(","):
        valor = valor.strip()

        if not valor:
            continue

        if not valor.isdigit():
            raise ValueError(f"'{valor}' no es una opción válida.")

        indice = int(valor) - 1

        if indice < 0 or indice >= len(politicas_ordenadas):
            raise ValueError(f"La opción {valor} no existe.")

        politica = politicas_ordenadas[indice]

        if politica not in opciones:
            opciones.append(politica)

    if not opciones:
        raise ValueError("No seleccionaste ninguna política.")

    return opciones


def preparar_configuracion_politica(
    politica_modelo: dict,
) -> dict:
    """
    Prepara una copia de la política modelo para poder
    crearla o actualizarla en una Network destino.

    Omite lo que no se necesiatara en campos_omitidos
    """

    configuracion = copy.deepcopy(politica_modelo)

    campos_omitidos = [
        "groupPolicyId",
        "bandwidth",
        "splashAuthSettings",
        "vlanTagging",
        "bonjourForwarding",
    ]

    for campo in campos_omitidos:
        configuracion.pop(
            campo,
            None,
        )

    return configuracion


def mostrar_politicas_seleccionadas(
    politicas: list[dict],
) -> None:
    """
    Muestra las políticas modelo seleccionadas
    y su configuración completa.
    """

    print("\n=== POLÍTICAS MODELO SELECCIONADAS ===\n")

    for politica in politicas:
        print(
            f"- {politica.get('name', 'Sin nombre')} "
            f"| ID: "
            f"{politica.get('groupPolicyId', 'Sin ID')}"
        )


def seleccionar_networks_destino(
    network_modelo_id: str,
) -> list[dict]:
    """
    Permite seleccionar una o varias organizaciones
    y después una o varias Networks de cada una.

    La Network modelo se excluye automáticamente
    """

    organizaciones = obtener_organizaciones()

    if not organizaciones:
        raise ValueError("No se encontraron organizaciones disponibles.")

    organizaciones_ordenadas = sorted(
        organizaciones,
        key=lambda organizacion: organizacion.get(
            "name",
            "",
        ).lower(),
    )

    print("\n=== ORGANIZACIONES DESTINO ===\n")

    for indice, organizacion in enumerate(
        organizaciones_ordenadas,
        start=1,
    ):
        print(f"{indice}. " f"{organizacion.get('name', 'Sin nombre')}")

    entrada = input_menu(
        "\nSelecciona una o varias organizaciones "
        "separadas por comas, o escribe 'todas':\n> "
    )

    organizaciones_seleccionadas = seleccionar_varios_elementos(
        elementos=organizaciones_ordenadas,
        entrada=entrada,
    )

    networks_destino = []

    for organizacion in organizaciones_seleccionadas:
        organization_id = organizacion["id"]
        organization_name = organizacion.get(
            "name",
            "Sin nombre",
        )

        networks = obtener_networks(organization_id)

        # Evitamos mostrar la Network modelo como destino y no compatibles
        networks_disponibles = [
            network
            for network in networks
            if network.get("id") != network_modelo_id
            and (
                "wireless" in network.get("productTypes", [])
                or "appliance" in network.get("productTypes", [])
            )
        ]

        networks_ordenadas = sorted(
            networks_disponibles,
            key=lambda network: network.get(
                "name",
                "",
            ).lower(),
        )

        print("\n" + "=" * 60)
        print(f" ORGANIZACIÓN: {organization_name}")
        print("=" * 60)

        if not networks_ordenadas:
            print("\nNo tiene Networks disponibles " "para usarse como destino.")
            continue

        for indice, network in enumerate(
            networks_ordenadas,
            start=1,
        ):
            print(f"{indice}. " f"{network.get('name', 'Sin nombre')}")

        entrada_networks = input_menu(
            "\nSelecciona una o varias Networks, " "'todas' o 'ninguna':\n> "
        )

        networks_seleccionadas = seleccionar_varios_elementos(
            elementos=networks_ordenadas,
            entrada=entrada_networks,
            permitir_ninguna=True,
        )

        for network in networks_seleccionadas:
            networks_destino.append(
                {
                    "organization_id": organization_id,
                    "organization_name": organization_name,
                    "network_id": network["id"],
                    "network_name": network.get(
                        "name",
                        "Sin nombre",
                    ),
                }
            )

    if not networks_destino:
        raise ValueError("No seleccionaste ninguna Network destino.")

    return networks_destino


def mostrar_networks_destino(
    networks_destino: list[dict],
) -> None:
    """
    Muestra las Networks que recibiran las políticas
    """

    print("\n=== NETWORKS DESTINO SELECCIONADAS ===\n")

    for destino in networks_destino:
        print(f"- {destino['organization_name']} " f"| {destino['network_name']}")

    print(f"\nTotal de Networks destino: " f"{len(networks_destino)}")


def analizar_politicas_destino(
    politicas_modelo: list[dict],
    networks_destino: list[dict],
) -> list[dict]:
    """
    Consulta cada Network destino y clasifica cada política
    Esta función solamente lee y clasifica
    """

    resultados = []

    for destino in networks_destino:
        print(
            "\nConsultando políticas de "
            f"{destino['organization_name']} | "
            f"{destino['network_name']}..."
        )

        try:
            politicas_destino = obtener_politicas_grupo(destino["network_id"])

        except requests.HTTPError as error:
            detalle = error.response.text if error.response is not None else str(error)

            print(
                f"⚠ Se omitió "
                f"{destino['organization_name']} | "
                f"{destino['network_name']}."
            )
            print(f"  Motivo: {detalle}")

            continue

        except requests.RequestException as error:
            print(
                f"⚠ No fue posible consultar "
                f"{destino['organization_name']} | "
                f"{destino['network_name']}."
            )
            print(f"  Error: {error}")

            continue

        politicas_por_nombre = {
            politica.get("name", "").strip().lower(): politica
            for politica in politicas_destino
        }

        for politica_modelo in politicas_modelo:
            nombre_modelo = politica_modelo.get(
                "name",
                "",
            ).strip()

            politica_existente = politicas_por_nombre.get(nombre_modelo.lower())

            configuracion_modelo = preparar_configuracion_politica(politica_modelo)

            if politica_existente is None:
                accion = "Crear"
                group_policy_id_destino = None

            else:
                configuracion_destino = preparar_configuracion_politica(
                    politica_existente
                )

                if configuracion_modelo == configuracion_destino:
                    accion = "Sin cambios"
                else:
                    accion = "Actualizar"

                group_policy_id_destino = politica_existente.get("groupPolicyId")

            resultados.append(
                {
                    "organization_id": destino["organization_id"],
                    "organization_name": destino["organization_name"],
                    "network_id": destino["network_id"],
                    "network_name": destino["network_name"],
                    "policy_name": nombre_modelo,
                    "group_policy_id_destino": (group_policy_id_destino),
                    "accion": accion,
                    "configuracion": configuracion_modelo,
                }
            )

    return resultados


def mostrar_analisis_politicas(
    resultados: list[dict],
) -> None:
    """
    Muestra qué ocurriría en cada Network,
    sin realizar cambios.
    """

    print("\n=== ANÁLISIS DE SINCRONIZACIÓN ===\n")

    crear = 0
    actualizar = 0
    sin_cambios = 0

    for resultado in resultados:
        accion = resultado["accion"]

        print(
            f"- {resultado['organization_name']} | "
            f"{resultado['network_name']} | "
            f"{resultado['policy_name']} "
            f"→ {accion}"
        )

        if accion == "Crear":
            crear += 1

        elif accion == "Actualizar":
            actualizar += 1

        elif accion == "Sin cambios":
            sin_cambios += 1

    print("\nResumen:")
    print(f"- Por crear: {crear}")
    print(f"- Por actualizar: {actualizar}")
    print(f"- Sin cambios: {sin_cambios}")


def ejecutar_sincronizacion_politicas(
    resultados: list[dict],
) -> None:
    """
    Ejecuta las acciones obtenidas durante el análisis:

    - Crear
    - Actualizar
    - Sin cambios
    """

    resultados_con_cambios = [
        resultado
        for resultado in resultados
        if resultado["accion"]
        in {
            "Crear",
            "Actualizar",
        }
    ]

    if not resultados_con_cambios:
        print("\nTodas las políticas seleccionadas " "ya están sincronizadas.\n")
        return

    print("\nSe realizarán " f"{len(resultados_con_cambios)} cambio(s).")

    confirmacion = input_menu(
        "\nEscribe CONFIRMAR para continuar (Debe ser en mayusculas):\n> "
    )

    if confirmacion != "CONFIRMAR":
        print("\nOperación cancelada. " "No se realizaron cambios.\n")
        return

    if not cambios_habilitados():
        print(
            "\nLas operaciones de escritura están bloqueadas "
            "en config/settings.json."
        )
        print("No se realizaron cambios en Meraki.\n")
        return

    creadas = 0
    actualizadas = 0
    sin_cambios = 0
    errores = 0

    print("\n=== EJECUTANDO SINCRONIZACIÓN ===\n")

    resumen_networks = {}

    for resultado in resultados:

        network_id = resultado["network_id"]

        if network_id not in resumen_networks:
            resumen_networks[network_id] = {
                "organization_name": resultado["organization_name"],
                "network_name": resultado["network_name"],
                "correctas": [],
                "omitidas": [],
            }

        accion = resultado["accion"]

        organizacion = resultado["organization_name"]
        network = resultado["network_name"]
        politica = resultado["policy_name"]

        if accion == "Sin cambios":
            sin_cambios += 1

            resumen_networks[network_id]["correctas"].append(
                {
                    "politica": politica,
                    "accion": "Sin cambios",
                }
            )

            print(f"○ {organizacion} | {network} | " f"{politica} → Sin cambios")
            continue

        try:
            if accion == "Crear":
                crear_politica_grupo(
                    network_id=resultado["network_id"],
                    configuracion=resultado["configuracion"],
                )

                creadas += 1

                resumen_networks[network_id]["correctas"].append(
                    {
                        "politica": politica,
                        "accion": "Creada",
                    }
                )

                print(f"✓ {organizacion} | {network} | " f"{politica} → Creada")

            elif accion == "Actualizar":
                actualizar_politica_grupo(
                    network_id=resultado["network_id"],
                    group_policy_id=resultado["group_policy_id_destino"],
                    configuracion=resultado["configuracion"],
                )

                actualizadas += 1

                resumen_networks[network_id]["correctas"].append(
                    {
                        "politica": politica,
                        "accion": "Actualizada",
                    }
                )

                print(f"✓ {organizacion} | {network} | " f"{politica} → Actualizada")

        except requests.HTTPError as error:
            errores += 1

            detalle = error.response.text if error.response is not None else str(error)

            resumen_networks[network_id]["omitidas"].append(
                {
                    "politica": politica,
                    "motivo": detalle,
                }
            )

            print(f"✗ {organizacion} | {network} | " f"{politica} → Error")
            print(f"  Detalle: {detalle}")

        except requests.RequestException as error:
            errores += 1

            resumen_networks[network_id]["omitidas"].append(
                {
                    "politica": politica,
                    "motivo": error,
                }
            )

            print(f"✗ {organizacion} | {network} | " f"{politica} → Error de conexión")
            print(f"  Detalle: {error}")

    print("\n=== RESULTADO FINAL ===\n")
    print(f"- Creadas: {creadas}")
    print(f"- Actualizadas: {actualizadas}")
    print(f"- Sin cambios: {sin_cambios}")
    print(f"- Errores: {errores}")

    # Resumen detallado por Network
    print("\n=== RESUMEN POR NETWORK ===\n")

    networks_completas = 0
    networks_parciales = 0

    for datos in resumen_networks.values():
        print(f"{datos['organization_name']} | " f"{datos['network_name']}")

        for politica_correcta in datos["correctas"]:
            print(
                f"  ✓ {politica_correcta['politica']} "
                f"→ {politica_correcta['accion']}"
            )

        if datos["omitidas"]:
            networks_parciales += 1

            print("  Estado: PARCIAL")

            for politica_omitida in datos["omitidas"]:
                print(f"  ✗ {politica_omitida['politica']} " "→ Omitida")

                print(f"    Motivo: " f"{politica_omitida['motivo']}")

        else:
            networks_completas += 1
            print("  Estado: COMPLETA")

        print()

    #Resumen de networks
    print("Resumen de Networks:")
    print(f"- Actualizadas completamente: " f"{networks_completas}")
    print(f"- Con políticas omitidas: " f"{networks_parciales}")


def sincronizar_politicas() -> None:
    """
    Selecciona una Network modelo y permite escoger
    las Group Policies que se actualizaran
    """

    print("\n" + "=" * 50)
    print(" SINCRONIZACIÓN DE GROUP POLICIES")
    print("=" * 50)

    try:
        organizacion_modelo = seleccionar_organizacion("modelo")

        network_modelo = seleccionar_network(
            organization_id=organizacion_modelo["id"],
            descripcion="modelo",
        )

        print("\nConsultando políticas de " f"{network_modelo['name']}...")

        politicas = obtener_politicas_grupo(network_modelo["id"])

        if not politicas:
            print("\nLa Network modelo no tiene " "Group Policies disponibles.\n")
            return

        politicas_seleccionadas = seleccionar_politicas(politicas)

        mostrar_politicas_seleccionadas(politicas_seleccionadas)

        networks_destino = seleccionar_networks_destino(
            network_modelo_id=network_modelo["id"],
        )

        mostrar_networks_destino(networks_destino)

        resultados = analizar_politicas_destino(
            politicas_modelo=politicas_seleccionadas,
            networks_destino=networks_destino,
        )

        mostrar_analisis_politicas(resultados)

        ejecutar_sincronizacion_politicas(resultados)

    except ValueError as error:
        print(f"\nError de selección: {error}\n")

    except requests.RequestException as error:
        print("\nNo fue posible consultar las políticas " f"en Meraki:\n{error}\n")
