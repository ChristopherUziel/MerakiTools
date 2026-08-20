import copy
import requests
from config import cambios_habilitados
from meraki_api import (
    obtener_networks,
    obtener_organizaciones,
    obtener_content_filtering,
    actualizar_content_filtering,
)
from modules.alta_evento import (
    seleccionar_network,
    seleccionar_organizacion,
)
from navegacion import input_menu


def preparar_content_filtering(
    filtering_modelo: dict,
) -> dict:
    """
    Prepara Content Filtering para compararlo.

    Convierte las categorías al formato del PUT
    """

    configuracion = copy.deepcopy(filtering_modelo)

    categorias = configuracion.get("blockedUrlCategories", [])

    categorias_preparadas = []

    for categoria in categorias:
        if isinstance(categoria, dict):
            categoria_id = categoria.get("id")

            if categoria_id:
                categorias_preparadas.append(categoria_id)

        elif isinstance(categoria, str):
            categorias_preparadas.append(categoria)

    configuracion["blockedUrlCategories"] = categorias_preparadas

    return configuracion


def mostrar_filtering_seleccionado(
    filtering: dict,
) -> None:
    """
    Muestra la onfiguracion de filtering modelo
    """

    print("\n=== Content Filtering Modelo Seleccionado ===\n")

    # Imprimir patrones de URLs permitidas
    print("URLs Permitidas:")
    urls_permitidas = filtering.get("allowedUrlPatterns", [])
    if urls_permitidas:
        for url in urls_permitidas:
            print(f"  - {url}")
    else:
        print("  (Ninguna)")

    print("")  # Espacio en blanco

    # 3. Imprimir patrones de URLs bloqueadas
    print("URLs Bloqueadas:")
    urls_bloqueadas = filtering.get("blockedUrlPatterns", [])
    if urls_bloqueadas:
        for url in urls_bloqueadas:
            print(f"  - {url}")
    else:
        print("  (Ninguna)")

    print("")  # Espacio en blanco

    # 4. Imprimir categorías bloqueadas
    print("Categorías Bloqueadas:")
    categorias = filtering.get("blockedUrlCategories", [])
    if categorias:
        for cat in categorias:
            print(f"  - {cat}")
    else:
        print("  (Ninguna)")


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
            and ("appliance" in network.get("productTypes", []))
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


def analizar_filtering_destino(
    filtering_modelo: dict,
    networks_destino: list[dict],
) -> list[dict]:
    """
    Consulta cada Network destino y clasifica
    """

    resultados = []

    for destino in networks_destino:
        print(
            "\nConsultando Content filtering de "
            f"{destino['organization_name']} | "
            f"{destino['network_name']}..."
        )

        try:
            filtering_destino = obtener_content_filtering(destino["network_id"])

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

        configuracion_modelo = preparar_content_filtering(filtering_modelo)

        configuracion_destino = preparar_content_filtering(filtering_destino)

        if configuracion_modelo == configuracion_destino:
            accion = "Sin cambios"
        else:
            accion = "Actualizar"

        resultados.append(
            {
                "organization_id": destino["organization_id"],
                "organization_name": destino["organization_name"],
                "network_id": destino["network_id"],
                "network_name": destino["network_name"],
                "accion": accion,
                "configuracion": configuracion_modelo,
            }
        )

    return resultados


def mostrar_analisis_filtering(
    resultados: list[dict],
) -> None:
    """
    Muestra qué se hará en cada Network de destino
    """

    print("\n=== ANÁLISIS CONTENT FILTERING ===\n")

    for resultado in resultados:
        print(
            f"{resultado['organization_name']} | "
            f"{resultado['network_name']} "
            f"→ {resultado['accion']}"
        )


def ejecutar_sincronizacion_filtering(
    resultados: list[dict],
) -> None:
    """
    Actualiza Content Filtering en las Networks
    que hayan sido clasificadas como Actualizar.
    """

    cambios_pendientes = any(
        resultado["accion"] == "Actualizar" for resultado in resultados
    )

    if not cambios_pendientes:
        print(
            "\nTodas las Networks seleccionadas " "ya tienen la misma configuración.\n"
        )
        return

    confirmacion = input_menu("\nEscribe CONFIRMAR para aplicar los cambios:\n> ")

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

    actualizadas = 0
    sin_cambios = 0
    errores = 0

    print("\n=== EJECUTANDO SINCRONIZACIÓN ===\n")

    for resultado in resultados:
        organizacion = resultado["organization_name"]
        network = resultado["network_name"]

        if resultado["accion"] == "Sin cambios":
            sin_cambios += 1

            print(f"{organizacion} | {network} " "→ Sin cambios")
            continue

        try:
            actualizar_content_filtering(
                network_id=resultado["network_id"],
                configuracion=resultado["configuracion"],
            )

            actualizadas += 1

            print(f"✓ {organizacion} | {network} " "→ Content Filtering actualizado")

        except requests.HTTPError as error:
            errores += 1

            detalle = error.response.text if error.response is not None else str(error)

            print(f"✗ {organizacion} | {network} " "→ Omitida")
            print(f"  Motivo: {detalle}")

        except requests.RequestException as error:
            errores += 1

            print(f"✗ {organizacion} | {network} " "→ Error")
            print(f"  Motivo: {error}")

    print("\nResumen:")
    print(f"- Actualizadas: {actualizadas}")
    print(f"- Sin cambios: {sin_cambios}")
    print(f"- Omitidas / errores: {errores}")


def sincronizar_content_filtering() -> None:
    """
    Sincroniza Content Filtering
    """

    print("\n" + "=" * 50)
    print(" SINCRONIZACIÓN DE CONTENT FILTERING")
    print("=" * 50)

    try:
        organizacion_modelo = seleccionar_organizacion("modelo")

        network_modelo = seleccionar_network(
            organization_id=organizacion_modelo["id"],
            descripcion="modelo",
        )

        print("\nConsultando Content Filtering de " f"{network_modelo['name']}...")

        filtering_modelo = obtener_content_filtering(network_modelo["id"])

        mostrar_filtering_seleccionado(filtering_modelo)

        networks_destino = seleccionar_networks_destino(
            network_modelo_id=network_modelo["id"],
        )

        resultados = analizar_filtering_destino(
            filtering_modelo=filtering_modelo,
            networks_destino=networks_destino,
        )

        mostrar_analisis_filtering(resultados)

        ejecutar_sincronizacion_filtering(resultados)

    except ValueError as error:
        print(f"\nError de selección: {error}\n")

    except requests.RequestException as error:
        print("\nNo fue posible completar la operación:\n" f"{error}\n")
