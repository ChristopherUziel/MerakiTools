import json
import requests
from config import cambios_habilitados

from meraki_api import (
    obtener_networks,
    obtener_organizaciones,
    obtener_traffic_shaping_rules,
    obtener_vpn_exclusions_organizacion,
    actualizar_traffic_shaping_rules,
    actualizar_vpn_esclusions,
)
from modules.alta_evento import (
    seleccionar_network,
    seleccionar_organizacion,
)
from modules.politicas import (
    seleccionar_varios_elementos,
)

from navegacion import input_menu


def sincronizar_sdwan_traffic_shaping() -> None:
    """
    Selecciona una Network modelo
    Consulta por separado traffic rules y vpn exclussion por si alguna no esta disponible
    """

    organizacion_modelo = seleccionar_organizacion("modelo")

    network_modelo = seleccionar_network(
        organization_id=organizacion_modelo["id"],
        descripcion="modelo",
    )

    print("\nConsultando configuración de " f"{network_modelo['name']}...\n")

    traffic_shaping_rules = None
    vpn_exclusions = None

    ###################
    # TRAFFIC SHAPING RULES

    try:
        traffic_shaping_rules = obtener_traffic_shaping_rules(network_modelo["id"])

        print("✓ Traffic Shaping Rules disponibles.")

    except requests.HTTPError as error:
        detalle = error.response.text if error.response is not None else str(error)

        print("⚠ Traffic Shaping Rules no disponibles.")
        print(f"  Motivo: {detalle}")

    except requests.RequestException as error:
        print("⚠ No fue posible consultar " "Traffic Shaping Rules.")
        print(f"  Error: {error}")

    #################
    # VPN EXCLUSIONS

    try:
        respuesta_vpn = obtener_vpn_exclusions_organizacion(organizacion_modelo["id"])

        for item in respuesta_vpn.get("items", []):
            if item.get("networkId") == network_modelo["id"]:
                vpn_exclusions = item
                break

        if vpn_exclusions is None:
            print("⚠ La Network modelo no tiene " "VPN Exclusions disponibles.")
        else:
            print("✓ VPN Exclusions disponibles.")

    except requests.HTTPError as error:
        detalle = error.response.text if error.response is not None else str(error)

        print("⚠ VPN Exclusions no disponibles.")
        print(f"  Motivo: {detalle}")

    except requests.RequestException as error:
        print("⚠ No fue posible consultar " "VPN Exclusions.")
        print(f"  Error: {error}")

    ############
    # Respuesta

    if traffic_shaping_rules is None and vpn_exclusions is None:
        print(
            "\nLa Network modelo no tiene ninguna "
            "configuración compatible para clonar.\n"
        )
        return

    networks_destino = seleccionar_networks_destino_sdwan(
        network_modelo_id=network_modelo["id"],
    )

    resultados = analizar_sdwan_destino(
        traffic_shaping_modelo=traffic_shaping_rules,
        vpn_exclusions_modelo=vpn_exclusions,
        networks_destino=networks_destino,
    )

    mostrar_analisis_sdwan(resultados)

    ejecutar_sincronizacion_sdwan(resultados)


def preparar_vpn_exclusion(
    vpn_exclusion: dict,
) -> dict:
    """
    prepara las exclusiones de vpn de la network modelo
    """

    return {
        "custom": vpn_exclusion.get(  ###limpia el diccionario recibido con las claves buscadas
            "custom",
            [],
        ),
        "majorApplications": vpn_exclusion.get(
            "majorApplications",
            [],
        ),
    }


def preparar_traffic_shaping_rules(
    traffic_shaping_rules: dict,
) -> dict:
    """
    Prepara las traffic shaping rules de la network modelo
    """

    return {
        "defaultRulesEnabled": traffic_shaping_rules.get(
            "defaultRulesEnabled",
            False,
        ),
        "rules": traffic_shaping_rules.get(
            "rules",
            [],
        ),
    }


def seleccionar_networks_destino_sdwan(
    network_modelo_id: str,
) -> list[dict]:
    """
    Permite seleccionar una o varias org y networks destino
    """

    organizaciones = obtener_organizaciones()

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

        # Solo Networks con MX / appliance.
        # También excluimos la Network modelo.
        networks_disponibles = [
            network
            for network in networks
            if (network.get("id") != network_modelo_id)
            and (
                "appliance"
                in network.get(
                    "productTypes",
                    [],
                )
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
            print("\nNo tiene Networks con MX disponibles.")
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


def analizar_sdwan_destino(
    traffic_shaping_modelo: dict | None,
    vpn_exclusions_modelo: dict | None,
    networks_destino: list[dict],
) -> list[dict]:
    """
    Analiza las Networks destino sin realizar cambios
    """

    resultados = []

    vpn_por_organizacion = {}

    for destino in networks_destino:

        print(
            "\nAnalizando "
            f"{destino['organization_name']} | "
            f"{destino['network_name']}..."
        )

        resultado = {
            "organization_id": destino["organization_id"],
            "organization_name": destino["organization_name"],
            "network_id": destino["network_id"],
            "network_name": destino["network_name"],
            "traffic_shaping": {
                "accion": "Omitir",
                "motivo": None,
            },
            "vpn_exclusions": {
                "accion": "Omitir",
                "motivo": None,
            },
        }

        # =====================================
        # TRAFFIC SHAPING RULES
        # =====================================

        if traffic_shaping_modelo is not None:

            try:
                traffic_destino = obtener_traffic_shaping_rules(destino["network_id"])

                modelo_preparado = preparar_traffic_shaping_rules(
                    traffic_shaping_modelo
                )

                destino_preparado = preparar_traffic_shaping_rules(traffic_destino)

                if modelo_preparado == destino_preparado:
                    accion = "Sin cambios"
                else:
                    accion = "Actualizar"

                resultado["traffic_shaping"] = {
                    "accion": accion,
                    "motivo": None,
                    "configuracion": modelo_preparado,
                }

            except requests.HTTPError as error:

                detalle = (
                    error.response.text if error.response is not None else str(error)
                )

                resultado["traffic_shaping"] = {
                    "accion": "Omitir",
                    "motivo": detalle,
                }

            except requests.RequestException as error:

                resultado["traffic_shaping"] = {
                    "accion": "Omitir",
                    "motivo": str(error),
                }

        else:
            resultado["traffic_shaping"]["motivo"] = (
                "La Network modelo no proporcionó " "Traffic Shaping Rules."
            )

        ##############
        # VPN EXCLUSIONS

        if vpn_exclusions_modelo is not None:

            try:
                organization_id = destino["organization_id"]

                # Solo consultamos una vez cada organización.
                if organization_id not in vpn_por_organizacion:
                    vpn_por_organizacion[organization_id] = (
                        obtener_vpn_exclusions_organizacion(organization_id)
                    )

                respuesta_vpn = vpn_por_organizacion[organization_id]

                vpn_destino = None

                for item in respuesta_vpn.get(
                    "items",
                    [],
                ):
                    if item.get("networkId") == destino["network_id"]:
                        vpn_destino = item
                        break

                modelo_preparado = preparar_vpn_exclusion(vpn_exclusions_modelo)

                # Si la Network aparece pero no tiene reglas se convierte en una lista vacia
                if vpn_destino is None:
                    destino_preparado = {
                        "custom": [],
                        "majorApplications": [],
                    }

                else:
                    destino_preparado = preparar_vpn_exclusion(vpn_destino)

                if modelo_preparado == destino_preparado:
                    accion = "Sin cambios"
                else:
                    accion = "Actualizar"

                resultado["vpn_exclusions"] = {
                    "accion": accion,
                    "motivo": None,
                    "configuracion": modelo_preparado,
                }

            except requests.HTTPError as error:

                detalle = (
                    error.response.text if error.response is not None else str(error)
                )

                resultado["vpn_exclusions"] = {
                    "accion": "Omitir",
                    "motivo": detalle,
                }

            except requests.RequestException as error:

                resultado["vpn_exclusions"] = {
                    "accion": "Omitir",
                    "motivo": str(error),
                }

        else:
            resultado["vpn_exclusions"]["motivo"] = (
                "La Network modelo no proporcionó " "VPN Exclusions."
            )

        resultados.append(resultado)

    return resultados


def mostrar_analisis_sdwan(
    resultados: list[dict],
) -> None:
    """
    Muestra qué se haría en cada Network.
    """

    print("\n=== ANÁLISIS SD-WAN / " "TRAFFIC SHAPING ===\n")

    for resultado in resultados:

        print(f"{resultado['organization_name']} | " f"{resultado['network_name']}")

        traffic = resultado["traffic_shaping"]

        print("  Traffic Shaping Rules: " f"{traffic['accion']}")

        if traffic.get("motivo"):
            print(f"    Motivo: {traffic['motivo']}")

        vpn = resultado["vpn_exclusions"]

        print("  VPN Exclusions: " f"{vpn['accion']}")

        if vpn.get("motivo"):
            print(f"    Motivo: {vpn['motivo']}")

        print()


def ejecutar_sincronizacion_sdwan(
    resultados: list[dict],
) -> None:
    """
    Ejecuta la sincronizació de traffic shaping y vpn exlclusions

    Cada apartado se procesa de forma independiente.
    """

    cambios_pendientes = False

    for resultado in resultados:
        if resultado["traffic_shaping"]["accion"] == "Actualizar":
            cambios_pendientes = True

        if resultado["vpn_exclusions"]["accion"] == "Actualizar":
            cambios_pendientes = True

    if not cambios_pendientes:
        print(
            "\nTodas las configuraciones seleccionadas "
            "ya están sincronizadas o fueron omitidas.\n"
        )
        return

    confirmacion = input_menu("\nEscribe CONFIRMAR para aplicar los cambios:\n> ")

    if confirmacion != "CONFIRMAR":
        print("\nOperación cancelada. " "No se realizaron cambios.\n")
        return

    if not cambios_habilitados():
        print("\nLas operaciones de escritura estan bloqueadas")

        print("No se realizaron cambios en Meraki.\n")
        return

    print("\n == EJECUTANDO SINCRONIZACIÓN ==\n")

    resumen_networks = {}

    for resultado in resultados:
        network_id = resultado["network_id"]
        organizacion = resultado["organization_name"]
        network = resultado["network_name"]

        resumen_networks[network_id] = {
            "organization_name": organizacion,
            "network_name": network,
            "traffic_shaping": {
                "estado": None,
                "motivo": None,
            },
            "vpn_exclusions": {
                "estado": None,
                "motivo": None,
            },
        }

        print(f"\n{organizacion} | {network}")

        traffic = resultado["traffic_shaping"]

        if traffic["accion"] == "Actualizar":
            try:
                actualizar_traffic_shaping_rules(
                    network_id=network_id,
                    configuracion=traffic["configuracion"],
                )

                print("✓ Traffic Shaping Rules → Actualizadas")

                resumen_networks[network_id]["traffic_shaping"][
                    "estado"
                ] = "Actualizada"

            except requests.HTTPError as error:
                detalle = (
                    error.response.text if error.response is not None else str(error)
                )

                print("✗ Traffic Shaping Rules → Error")
                print(f"Motivo: {detalle}")

                resumen_networks[network_id]["traffic_shaping"]["estado"] = "Error"
                resumen_networks[network_id]["traffic_shaping"]["motivo"] = detalle

            except requests.RequestException as error:

                print("  ✗ Traffic Shaping Rules → Error")
                print(f"    Motivo: {error}")

        elif traffic["accion"] == "Sin cambios":
            print("  ○  Traffic Shaping Rules → Sin cambios")

            resumen_networks[network_id]["traffic_shaping"]["estado"] = "Sin cambios"

        elif traffic["accion"] == "Omitir":
            print("  ⚠ Traffic Shaping Rules → Omitidas ")

            resumen_networks[network_id]["traffic_shaping"]["estado"] = "Omitida"
            resumen_networks[network_id]["traffic_shaping"]["motivo"] = traffic.get(
                "motivo"
            )

            if traffic.get("motivo"):
                print(f"    Motivo: {traffic['motivo']}")

        #### vpn exclusions
        vpn = resultado["vpn_exclusions"]

        if vpn["accion"] == "Actualizar":
            try:
                actualizar_vpn_esclusions(
                    network_id=network_id,
                    configuracion=vpn["configuracion"],
                )

                print("  ✓ VPN Exclusions → Actualizadas")

                resumen_networks[network_id]["vpn_exclusions"]["estado"] = "Actualizada"

            except requests.HTTPError as error:
                detalle = (
                    error.response.text if error.response is not None else str(error)
                )

                print("  ✗ VPN Exclusions → Error")
                print(f"    Motivo: {detalle}")

                resumen_networks[network_id]["vpn_exclusions"]["estado"] = "Error"
                resumen_networks[network_id]["vpn_exclusions"]["motivo"] = detalle

            except requests.RequestException as error:
                print("  ✗ VPN Exclusions → Error")
                print(f"    Motivo: {error}")

        elif vpn["accion"] == "Sin cambios":
            print("  ○ VPN Exclusions → Sin cambios")

            resumen_networks[network_id]["vpn_exclusions"]["estado"] = "Sin cambios"

        elif vpn["accion"] == "Omitir":
            print("  ⚠ VPN Exclusions → Omitidas")

            resumen_networks[network_id]["vpn_exclusions"]["estado"] = "Omitida"
            resumen_networks[network_id]["vpn_exclusions"]["motivo"] = traffic.get(
                "motivo"
            )

            if vpn.get("motivo"):
                print(f"    Motivo: {vpn['motivo']}")

    completas = 0
    parciales = 0
    sin_cambios = 0

    for datos in resumen_networks.values():
        traffic = datos["traffic_shaping"]
        vpn = datos["vpn_exclusions"]

        estados = {
            traffic["estado"],
            vpn["estado"],
        }

        if estados <= {"Sin cambios"}:
            sin_cambios += 1

        elif "Error" in estados or "Omitida" in estados:
            parciales += 1

        else:
            completas += 1

    print("Resumen:")
    print(f"- Completas: {completas}")
    print(f"- Parciales: {parciales}")
    print(f"- Sin cambios: {sin_cambios}")
