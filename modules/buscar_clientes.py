import requests
import re
from datetime import datetime
from meraki_api import (
    buscar_clientes_organizacion_por_mac,
    obtener_detalle_cliente,
    obtener_organizaciones,
)


def buscar_cliente_global_mac(
    mac: str,
) -> list[dict]:
    """
    Busca una MAC en todas las organizaciones
    y conserva todas las Networks donde fue vista
    """

    resultados = []

    organizaciones = obtener_organizaciones()

    for organizacion in organizaciones:
        organization_id = organizacion["id"]
        organization_name = organizacion.get(
            "name",
            "Sin nombre",
        )

        print(f"\nBuscando en organización: " f"{organization_name}")

        try:
            cliente = buscar_clientes_organizacion_por_mac(
                organization_id=organization_id,
                mac=mac,
            )

        except requests.RequestException as error:
            print(f"⚠ No fue posible consultar " f"{organization_name}: {error}")
            continue

        if cliente is None:
            continue

        client_id = cliente.get("clientId")

        for registro in cliente.get("records", []):
            network = registro.get("network", {})
            network_id = network.get("id")

            if not network_id:
                continue

            detalle = registro

            # Si tenemos clientId, intentamos obtener
            # información más detallada de esa Network.
            if client_id:
                try:
                    detalle_api = obtener_detalle_cliente(
                        network_id=network_id,
                        client_id=client_id,
                    )

                    # Conservamos lastSeen/firstSeen del
                    # historial por si el detalle no los trae.
                    detalle_api.setdefault(
                        "lastSeen",
                        registro.get("lastSeen"),
                    )

                    detalle_api.setdefault(
                        "firstSeen",
                        registro.get("firstSeen"),
                    )

                    detalle = detalle_api

                except requests.RequestException:
                    # El registro histórico sigue siendo útil
                    # aunque el detalle adicional falle.
                    detalle = registro

            resultados.append(
                {
                    "organization_name": organization_name,
                    "network_name": network.get(
                        "name",
                        "No disponible",
                    ),
                    "detalle": detalle,
                }
            )

    return resultados


def validar_y_normalizar_mac(mac: str) -> str | None:
    """
    Valida una MAC con formato correcto y normaliza a minusculas
    """

    mac = mac.strip()

    if not re.fullmatch(
        r"[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}",
        mac,
    ):
        return None

    return mac.lower()


def convertir_last_seen(fecha) -> datetime | None:
    """
    Convierte lastSeen de Meraki a datetime y ordenna los resultados con fecha de conexion
    """

    if not fecha:
        return None

    try:
        if isinstance(fecha, (int, float)):
            if fecha > 10_000_000_000:
                fecha = fecha / 1000

            return datetime.fromtimestamp(fecha)

        # Formato ISO de Meraki.
        if isinstance(fecha, str):
            fecha_normalizada = fecha.replace(
                "Z",
                "+00:00",
            )

            return datetime.fromisoformat(fecha_normalizada).astimezone()

    except (ValueError, TypeError, OSError):
        return None

    return None


def mostrar_cliente_encontrado(
    resultado: dict,
) -> None:
    """
    Muestra los datos de cliente
    """

    detalle = resultado["detalle"]

    print("\n" + "=" * 60)

    print(f"Organización: " f"{resultado['organization_name']}")

    print(f"Network: " f"{resultado['network_name']}")

    print(f"Estado: " f"{detalle.get('status', 'Desconocido')}")

    last_seen = convertir_last_seen(
        detalle.get("lastSeen")
    )

    if last_seen:
        print(
            "Ultima vez visto: "
            f"{last_seen.strftime('%d/%m/%y %H:%M:%S')}"
        )
    else:
        print(
            "Ulrima vez visto: No disponible"
        )

    print(f"IP: " f"{detalle.get('ip', 'No disponible')}")

    print(f"MAC: " f"{detalle.get('mac', 'No disponible')}")

    print(f"VLAN: " f"{detalle.get('vlan', 'No disponible')}")

    if detalle.get("namedVlan"):
        print(f"VLAN nombrada: " f"{detalle['namedVlan']}")

    conexion = detalle.get("recentDeviceConnection")

    print(f"Tipo de conexión: " f"{conexion or 'No disponible'}")

    if conexion == "Wireless":
        print(f"SSID: " f"{detalle.get('ssid', 'No disponible')}")

        print(f"AP: " f"{detalle.get('recentDeviceName', 'No disponible')}")

        print(f"Serial AP: " f"{detalle.get('recentDeviceSerial', 'No disponible')}")

    elif conexion == "Wired":
        print(f"Switch: " f"{detalle.get('recentDeviceName', 'No disponible')}")

        print(
            f"Serial switch: " f"{detalle.get('recentDeviceSerial', 'No disponible')}"
        )

        print(f"Puerto: " f"{detalle.get('switchport', 'No disponible')}")

    print(f"Usuario: " f"{detalle.get('user', 'No disponible') or 'No disponible'}")

    print(
        f"Descripción: "
        f"{detalle.get('description', 'No disponible') or 'No disponible'}"
    )


def buscar_clientes() -> None:
    """
    Busca globalmente un cliente por MAC
    """

    print("\n" + "=" * 50)
    print(" BÚSQUEDA GLOBAL DE CLIENTES POR MAC")
    print("=" * 50)

    mac_ingresada = input("\nIngresa la MAC del cliente:\n> ").strip()

    mac = validar_y_normalizar_mac(mac_ingresada)

    if mac is None:
        print("\nMAC inválida o incompleta. Usa el formato aa:bb:cc:dd:ee:ff.\n")
        return

    resultados = buscar_cliente_global_mac(mac)

    if not resultados:
        print("\nNo se encontró el cliente.\n")
        return

    print(f"\nSe encontraron " f"{len(resultados)} coincidencia(s).")

    for resultado in resultados:
        mostrar_cliente_encontrado(resultado)

    print()
