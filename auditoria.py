import csv
from datetime import datetime
from pathlib import Path
import atexit
import ctypes
import os

from config import CARPETA_BASE

CARPETA_AUDITORIA = CARPETA_BASE / "auditoria"
ARCHIVO_AUDITORIA = CARPETA_AUDITORIA / "auditoria.csv"

USUARIO_ACTUAL = "Usuario desconocido"
SESION_CERRADA = False


def establecer_usuario_auditoria(
    usuario: str,
) -> None:
    """
    Guarda la identidad de usuario durante toda la sesion
    """

    global USUARIO_ACTUAL

    USUARIO_ACTUAL = usuario.strip() if usuario else "Usuario desconocido"


def registrar_cierre_sesion(
    motivo: str,
) -> None:
    """
    Registra una sola vez el cierre de MerakiTools.
    """

    global SESION_CERRADA

    if SESION_CERRADA:
        return

    SESION_CERRADA = True

    registrar_auditoria(
        modulo="Sistema",
        accion="Cierre de sesión",
        resultado="Correcto",
        detalle=motivo,
    )


MANEJADOR_CONSOLA = None


def preparar_control_cierre() -> None:
    """
    Prepara el registro del cierre de MerakiTools.
    """

    atexit.register(
        registrar_cierre_sesion,
        "Cierre del proceso",
    )

    if os.name != "nt":
        return

    controlador_tipo = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_uint,
    )

    @controlador_tipo
    def controlador(evento):

        if evento in (2, 5, 6):
            registrar_cierre_sesion("Cierre directo de la consola")

        return False

    global MANEJADOR_CONSOLA
    MANEJADOR_CONSOLA = controlador

    ctypes.windll.kernel32.SetConsoleCtrlHandler(
        MANEJADOR_CONSOLA,
        True,
    )


def registrar_auditoria(
    modulo: str,
    accion: str,
    resultado: str,
    organizacion: str = "",
    network: str = "",
    objetivo: str = "",
    detalle: str = "",
) -> None:
    """
    Registra acciones realizadas dentro de MerakiTolls
    """

    CARPETA_AUDITORIA.mkdir(
        parents=True,
        exist_ok=True,
    )

    archivo_nuevo = not ARCHIVO_AUDITORIA.exists()

    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with ARCHIVO_AUDITORIA.open(
        "a",
        newline="",
        encoding="utf-8-sig",
    ) as archivo:

        escritor = csv.writer(archivo)

        if archivo_nuevo:
            escritor.writerow(
                [
                    "fecha_hora",
                    "usuario",
                    "modulo",
                    "accion",
                    "organizacion",
                    "network",
                    "objetivo",
                    "resultado",
                    "detalle",
                ]
            )

        escritor.writerow(
            [
                fecha_hora,
                USUARIO_ACTUAL,
                modulo,
                accion,
                organizacion,
                network,
                objetivo,
                resultado,
                detalle,
            ]
        )
