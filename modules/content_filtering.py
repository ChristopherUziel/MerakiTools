import copy
import requests
from config import cambios_habilitados
from meraki_api import (
    obtener_networks,
    obtener_organizaciones,
    obtener_content_filtering,
)
from modules.alta_evento import (
    seleccionar_network,
    seleccionar_organizacion,
)


def preparar_content_filtering(
    filtering_modelo: dict,
) -> dict:
    """
    Prepara una copia de la configuracion de content filtering para pegarla en otra network

    Omite lo que no se necesiatara en campos_omitidos
    """

    configuracion = copy.deepcopy(filtering_modelo)

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

    entrada = input(
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

        entrada_networks = input(
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
