import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "config" / "settings.json"


def cargar_configuracion() -> dict:
    """
    Lee la configuración guardada en config/settings.json.
    """

    if not CONFIG_FILE.exists():
        raise FileNotFoundError("No se encontró config/settings.json.")

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as archivo:
            configuracion = json.load(archivo)

    except json.JSONDecodeError as error:
        raise ValueError("El archivo settings.json no contiene JSON válido.") from error

    return configuracion


def obtener_api_key() -> str:
    """
    Obtiene la API Key desde el archivo de configuración.
    """

    configuracion = cargar_configuracion()
    api_key = configuracion.get("api_key", "").strip()

    if not api_key:
        raise ValueError("La API Key todavía no ha sido configurada.")

    return api_key


def cambios_habilitados() -> bool:
    """
    Indica si el programa tiene autorización para ejecutar
    operaciones que modifican el Dashboard.
    """

    configuracion = cargar_configuracion()

    return configuracion.get("permitir_cambios", False) is True
