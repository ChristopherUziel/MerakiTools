import csv
import os
import re
from datetime import datetime

import requests

from meraki_api import (
    obtener_dispositivos_network,
    obtener_networks,
    obtener_organizaciones,
)

CARPETA_REPORTES = "reportes"


def seleccionar_organizacion_reporte() -> dict:
    """
    Muestra las organizaciones disponibles y devuelve
    la seleccionada.
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


def seleccionar_network_reporte(
    organization_id: str,
) -> dict:
    """
    Muestra las Networks disponibles y devuelve
    la seleccionada.
    """

    networks = obtener_networks(organization_id)

    if not networks:
        raise ValueError("No se encontraron Networks disponibles.")

    networks.sort(key=lambda network: network["name"].lower())

    print("\nNetworks disponibles:\n")

    for indice, network in enumerate(networks, start=1):
        print(f"{indice}. {network['name']}")

    opcion = input("\nSelecciona una Network:\n> ").strip()

    if not opcion.isdigit():
        raise ValueError("Debes ingresar un número.")

    indice = int(opcion) - 1

    if indice < 0 or indice >= len(networks):
        raise ValueError("La Network seleccionada no existe.")

    return networks[indice]


def limpiar_nombre_archivo(texto: str) -> str:
    """
    Convierte el nombre de la Network en un texto seguro
    para utilizarlo dentro del nombre de un archivo.
    """

    texto = texto.strip()

    texto = re.sub(
        r'[<>:"/\\|?*]',
        "",
        texto,
    )

    texto = re.sub(
        r"\s+",
        "_",
        texto,
    )

    return texto or "network"


def obtener_ruta_reporte(
    tipo_reporte: str,
    nombre_network: str,
) -> str:
    """
    Construye una ruta única utilizando fecha y hora.
    """

    os.makedirs(
        CARPETA_REPORTES,
        exist_ok=True,
    )

    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")

    network_limpia = limpiar_nombre_archivo(nombre_network)

    nombre_archivo = f"{tipo_reporte}_" f"{network_limpia}_" f"{fecha}.csv"

    return os.path.join(
        CARPETA_REPORTES,
        nombre_archivo,
    )


def ordenar_dispositivos(
    dispositivos: list[dict],
) -> list[dict]:
    """
    Ordena los equipos por nombre y después por serial.
    """

    return sorted(
        dispositivos,
        key=lambda dispositivo: (
            dispositivo.get("name") or "",
            dispositivo.get("serial") or "",
        ),
    )


def nombre_esta_recuperado(
    nombre: str | None,
) -> bool:
    """
    Indica si el nombre contiene la palabra RECUPERADO.

    También reconoce RECUPERADA en caso de que se requiera.
    """

    if not nombre:
        return False

    palabras = nombre.upper().split()

    return "RECUPERADO" in palabras or "RECUPERADA" in palabras


def generar_reporte_alta(
    network: dict,
    dispositivos: list[dict],
) -> str:
    """
    Genera un CSV con el estado actual de los equipos
    asignados a la Network, es basicamente una imagen del dashboard.
    """

    ruta = obtener_ruta_reporte(
        tipo_reporte="alta",
        nombre_network=network["name"],
    )

    dispositivos_ordenados = ordenar_dispositivos(dispositivos)

    with open(
        ruta,
        mode="w",
        newline="",
        encoding="utf-8-sig",
    ) as archivo:
        escritor = csv.writer(archivo)

        escritor.writerow(
            [
                "Modelo",
                "Serial",
                "Nombre actual",
            ]
        )

        for dispositivo in dispositivos_ordenados:
            escritor.writerow(
                [
                    dispositivo.get(
                        "model",
                        "Desconocido",
                    ),
                    dispositivo.get(
                        "serial",
                        "Sin serial",
                    ),
                    dispositivo.get("name") or "Sin nombre",
                ]
            )

    return ruta


def generar_reporte_desmontaje(
    network: dict,
    dispositivos: list[dict],
) -> tuple[str, dict]:
    """
    Genera un CSV clasificando cada dispositivo como
    RECUPERADO o PENDIENTE.
    """

    ruta = obtener_ruta_reporte(
        tipo_reporte="desmontaje",
        nombre_network=network["name"],
    )

    dispositivos_ordenados = ordenar_dispositivos(dispositivos)

    total = len(dispositivos_ordenados)
    recuperados = 0
    pendientes = 0

    filas = []

    for dispositivo in dispositivos_ordenados:
        nombre_actual = dispositivo.get("name") or "Sin nombre"

        if nombre_esta_recuperado(nombre_actual):
            estado = "Recuperado"
            recuperados += 1
        else:
            estado = "Pendiente"
            pendientes += 1

        filas.append(
            [
                dispositivo.get(
                    "model",
                    "Desconocido",
                ),
                dispositivo.get(
                    "serial",
                    "Sin serial",
                ),
                nombre_actual,
                estado,
            ]
        )

    with open(
        ruta,
        mode="w",
        newline="",
        encoding="utf-8-sig",
    ) as archivo:
        escritor = csv.writer(archivo)

        escritor.writerow(
            [
                "Modelo",
                "Serial",
                "Nombre actual",
                "Estado",
            ]
        )

        escritor.writerows(filas)

        escritor.writerow([])

        escritor.writerow(
            [
                "Resumen",
                "Cantidad",
            ]
        )

        escritor.writerow(
            [
                "Total en la Network",
                total,
            ]
        )

        escritor.writerow(
            [
                "Recuperados",
                recuperados,
            ]
        )

        escritor.writerow(
            [
                "Pendientes",
                pendientes,
            ]
        )

    resumen = {
        "total": total,
        "recuperados": recuperados,
        "pendientes": pendientes,
    }

    return ruta, resumen


def mostrar_resultado_alta(
    network: dict,
    dispositivos: list[dict],
    ruta: str,
) -> None:
    """
    Muestra el resultado del reporte de alta.
    """

    print("\n=== REPORTE DE ALTA GENERADO ===\n")

    print(f"Network: {network['name']}")
    print(f"Total de equipos: {len(dispositivos)}")
    print(f"Archivo: {os.path.abspath(ruta)}\n")


def mostrar_resultado_desmontaje(
    network: dict,
    resumen: dict,
    ruta: str,
) -> None:
    """
    Muestra el resumen del reporte de desmontaje.
    """

    print("\n=== REPORTE DE DESMONTAJE GENERADO ===\n")

    print(f"Network: {network['name']}")
    print(f"Total en la Network: " f"{resumen['total']}")
    print(f"Recuperados: " f"{resumen['recuperados']}")
    print(f"Pendientes: " f"{resumen['pendientes']}")
    print(f"Archivo: {os.path.abspath(ruta)}\n")


def ejecutar_reporte(
    tipo_reporte: str,
) -> None:
    """
    Solicita organización y Network, consulta Meraki
    y genera el reporte.
    """

    try:
        organizacion = seleccionar_organizacion_reporte()

        network = seleccionar_network_reporte(organizacion["id"])

        print("\nConsultando dispositivos " "de la Network...\n")

        dispositivos = obtener_dispositivos_network(network["id"])

    except ValueError as error:
        print(f"\nError: {error}\n")
        return

    except requests.HTTPError as error:
        print("\nMeraki rechazó la consulta: " f"{error}\n")
        return

    except requests.RequestException as error:
        print("\nNo fue posible comunicarse con Meraki: " f"{error}\n")
        return

    if not dispositivos:
        print(
            "\nLa Network seleccionada no tiene "
            "dispositivos asignados actualmente.\n"
        )
        return

    try:
        if tipo_reporte == "alta":
            ruta = generar_reporte_alta(
                network=network,
                dispositivos=dispositivos,
            )

            mostrar_resultado_alta(
                network=network,
                dispositivos=dispositivos,
                ruta=ruta,
            )

        elif tipo_reporte == "desmontaje":
            ruta, resumen = generar_reporte_desmontaje(
                network=network,
                dispositivos=dispositivos,
            )

            mostrar_resultado_desmontaje(
                network=network,
                resumen=resumen,
                ruta=ruta,
            )

    except OSError as error:
        print("\nNo fue posible crear el archivo CSV: " f"{error}\n")


def reportes():
    """
    Menú principal del módulo de reportes.
    """

    while True:
        print("\n=== REPORTES ===\n")

        print("1. Reporte de alta de equipos")
        print("2. Reporte de desmontaje")
        print("3. Regresar al menú principal")

        opcion = input("\nSelecciona una opción:\n> ").strip()

        if opcion == "1":
            ejecutar_reporte("alta")

        elif opcion == "2":
            ejecutar_reporte("desmontaje")

        elif opcion == "3":
            print("\nRegresando al menú principal...\n")
            return

        else:
            print("\nOpción no válida. " "Selecciona 1, 2 o 3.\n")
