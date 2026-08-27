import atexit
import base64
import csv
import ctypes
import hashlib
import json
import os
import secrets
from datetime import datetime

import keyring
from cryptography.fernet import Fernet

from config import CARPETA_BASE

CARPETA_AUDITORIA = CARPETA_BASE / "auditoria"
ARCHIVO_AUDITORIA = CARPETA_AUDITORIA / "auditoria.dat"

SERVICIO_AUDITORIA = "MerakiTools_Auditoria"
USUARIO_CLAVE_CIFRADO = "clave_cifrado"

##### clave para ezportacion
USUARIO_PASSWORD_EXPORTACION = "password_exportacion"

ITERACIONES_PASSWORD = 310_000

CARPETA_EXPORTACIONES = CARPETA_AUDITORIA / "exportaciones"
######

USUARIO_ACTUAL = "Usuario desconocido"
SESION_CERRADA = False


def obtener_clave_cifrado() -> bytes:
    """
    Obtiene la clave utilizada para cifrar la auditoría o si no existe, crea una nueva
    """

    clave_guardada = keyring.get_password(
        SERVICIO_AUDITORIA,
        USUARIO_CLAVE_CIFRADO,
    )

    if clave_guardada:
        return clave_guardada.encode("utf-8")

    clave_nueva = Fernet.generate_key()

    keyring.set_password(
        SERVICIO_AUDITORIA,
        USUARIO_CLAVE_CIFRADO,
        clave_nueva.decode("utf-8"),
    )

    return clave_nueva


def establecer_password_exportacion(
    password: str,
) -> None:
    """
    Establece la contraseña que autoriza
    la exportación de la auditoría
    """

    if not password:
        raise ValueError("La contraseña no puede estar vacía.")

    salt = secrets.token_bytes(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        ITERACIONES_PASSWORD,
    )

    datos = {
        "salt": base64.b64encode(salt).decode("utf-8"),
        "hash": base64.b64encode(password_hash).decode("utf-8"),
    }

    keyring.set_password(
        SERVICIO_AUDITORIA,
        USUARIO_PASSWORD_EXPORTACION,
        json.dumps(datos),
    )


def validar_password_exportacion(
    password: str,
) -> bool:
    """
    Valida la contraseña ingresada para
    exportar la auditoría
    """

    datos_guardados = keyring.get_password(
        SERVICIO_AUDITORIA,
        USUARIO_PASSWORD_EXPORTACION,
    )

    if not datos_guardados:
        return False

    try:
        datos = json.loads(datos_guardados)

        salt = base64.b64decode(datos["salt"])

        hash_guardado = base64.b64decode(datos["hash"])

    except (
        json.JSONDecodeError,
        KeyError,
        ValueError,
    ):
        return False

    hash_ingresado = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        ITERACIONES_PASSWORD,
    )

    return secrets.compare_digest(
        hash_ingresado,
        hash_guardado,
    )


def password_exportacion_configurado() -> bool:
    """
    Revisa si ya tiene una contraseña configurada
    """

    return (
        keyring.get_password(
            SERVICIO_AUDITORIA,
            USUARIO_PASSWORD_EXPORTACION,
        )
        is not None
    )


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
    Registra una acción realizada dentro de MerakiTools
    """

    CARPETA_AUDITORIA.mkdir(
        parents=True,
        exist_ok=True,
    )

    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    registro = {
        "fecha_hora": fecha_hora,
        "usuario": USUARIO_ACTUAL,
        "modulo": modulo,
        "accion": accion,
        "organizacion": organizacion,
        "network": network,
        "objetivo": objetivo,
        "resultado": resultado,
        "detalle": detalle,
    }

    # Convierte el registro a json
    registro_json = json.dumps(
        registro,
        ensure_ascii=False,
    ).encode("utf-8")

    # Obtiene la clave interna de win
    clave = obtener_clave_cifrado()

    cifrador = Fernet(clave)

    # Cifra solamente un registro
    registro_cifrado = cifrador.encrypt(registro_json)

    # Agrega el registro como una nueva linea
    with ARCHIVO_AUDITORIA.open("ab") as archivo:
        archivo.write(registro_cifrado + b"\n")


def leer_auditoria() -> list[dict]:
    """
    Lee todos los registros
    almacenados en auditoria
    """

    if not ARCHIVO_AUDITORIA.exists():
        return []

    clave = obtener_clave_cifrado()
    cifrador = Fernet(clave)

    registros = []

    with ARCHIVO_AUDITORIA.open("rb") as archivo:

        for numero_linea, linea in enumerate(
            archivo,
            start=1,
        ):
            linea = linea.strip()

            if not linea:
                continue

            try:
                contenido = cifrador.decrypt(linea)

                registro = json.loads(contenido.decode("utf-8"))

                registros.append(registro)

            except Exception as error:
                raise ValueError(
                    "No fue posible leer el "
                    "registro de auditoría "
                    f"número {numero_linea}."
                ) from error

    return registros


def exportar_auditoria_csv() -> str:
    """
    Descifra auditoria.dat y genera una copia en csv
    """

    registros = leer_auditoria()

    if not registros:
        raise ValueError("No existen registros de auditoría " "para exportar.")

    CARPETA_EXPORTACIONES.mkdir(
        parents=True,
        exist_ok=True,
    )

    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")

    archivo_salida = CARPETA_EXPORTACIONES / f"auditoria_{fecha}.csv"

    columnas = [
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

    with archivo_salida.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as archivo:

        escritor = csv.DictWriter(
            archivo,
            fieldnames=columnas,
        )

        escritor.writeheader()
        escritor.writerows(registros)

    return str(archivo_salida)


def vaciar_auditoria() -> None:
    """
    Vacía el historial interno de auditoría
    """

    CARPETA_AUDITORIA.mkdir(
        parents=True,
        exist_ok=True,
    )

    with ARCHIVO_AUDITORIA.open("wb"):
        pass