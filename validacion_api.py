import requests

BASE_URL = "https://api.meraki.com/api/v1"


def validar_api_key(api_key: str) -> dict:
    """
    Valida temporalmente la API KEY, consulta el nombre de usuario.

    La API Key todavía no se guarda en Windows.
    """

    respuesta = requests.get(
        f"{BASE_URL}/administered/identities/me",
        headers={
            "X-Cisco-Meraki-API-Key": api_key,
            "Accept": "application/json",
        },
        timeout=20,
    )

    respuesta.raise_for_status()

    return respuesta.json()
