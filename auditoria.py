import atexit
import base64
import csv
import ctypes
import hashlib
import json
import os
import secrets
from datetime import datetime

import uuid

import keyring
from cryptography.fernet import Fernet

from config import CARPETA_BASE

### archivo de auditoria respaldo local
CARPETA_AUDITORIA = CARPETA_BASE / "auditoria"
ARCHIVO_AUDITORIA = CARPETA_AUDITORIA / "auditoria.dat"

##### Archivo de pendientes de sincronizar en azure
ARCHIVO_PENDIENTES = CARPETA_AUDITORIA / "pendientes.dat"

SERVICIO_AUDITORIA = "MerakiTools_Auditoria"
USUARIO_CLAVE_CIFRADO = "clave_cifrado"

##### clave para ezportacion
USUARIO_PASSWORD_EXPORTACION = "password_exportacion"

ITERACIONES_PASSWORD = 310_000

# Credenciales iniciales compartidas de MerakiTools.
# Se utilizan únicamente cuando el equipo todavía no tiene configuradas las credenciales de auditoría.

CLAVE_CIFRADO_INICIAL = "fycsSvifTNLKZrq_eKoSDOGvNvnwsPyEhMsY78c5nVI="

VERIFICADOR_PASSWORD_EXPORTACION_INICIAL = (
    '{"salt": "JmRuup4uTfe7RslZ6k8Uhw==", '
    '"hash": "xEUBkoWNtj/5+TyOkqrW9VDWa+6/AV3ziym2JKdsxRc="}'
)

CARPETA_EXPORTACIONES = CARPETA_AUDITORIA / "exportaciones"
######

USUARIO_ACTUAL = "Usuario desconocido"
SESION_CERRADA = False


def asegurar_configuracion_auditoria() -> None:
    """
    Verifica que el equipo tenga instaladas las
    credenciales necesarias para la auditoría.

    Si todavía no existen, instala las credenciales
    iniciales definidas
    """

    try:
        clave_guardada = keyring.get_password(
            SERVICIO_AUDITORIA,
            USUARIO_CLAVE_CIFRADO,
        )

        if not clave_guardada:

            try:
                Fernet(CLAVE_CIFRADO_INICIAL.encode("utf-8"))

            except Exception as error:
                raise RuntimeError(
                    "La clave Fernet inicial configurada "
                    "en MerakiTools no es válida."
                ) from error

            keyring.set_password(
                SERVICIO_AUDITORIA,
                USUARIO_CLAVE_CIFRADO,
                CLAVE_CIFRADO_INICIAL,
            )

            clave_verificacion = keyring.get_password(
                SERVICIO_AUDITORIA,
                USUARIO_CLAVE_CIFRADO,
            )

            if clave_verificacion != CLAVE_CIFRADO_INICIAL:
                raise RuntimeError(
                    "La clave de cifrado no pudo guardarse correctamente."
                )

        password_guardado = keyring.get_password(
            SERVICIO_AUDITORIA,
            USUARIO_PASSWORD_EXPORTACION,
        )

        if not password_guardado:

            try:
                datos_password = json.loads(VERIFICADOR_PASSWORD_EXPORTACION_INICIAL)

                base64.b64decode(
                    datos_password["salt"],
                    validate=True,
                )

                base64.b64decode(
                    datos_password["hash"],
                    validate=True,
                )

            except (
                json.JSONDecodeError,
                KeyError,
                ValueError,
            ) as error:
                raise RuntimeError(
                    "El verificador inicial de la "
                    "contraseña de auditoría no es válido."
                ) from error

            keyring.set_password(
                SERVICIO_AUDITORIA,
                USUARIO_PASSWORD_EXPORTACION,
                VERIFICADOR_PASSWORD_EXPORTACION_INICIAL,
            )

            password_verificacion = keyring.get_password(
                SERVICIO_AUDITORIA,
                USUARIO_PASSWORD_EXPORTACION,
            )

            if password_verificacion != VERIFICADOR_PASSWORD_EXPORTACION_INICIAL:
                raise RuntimeError(
                    "El verificador de la contraseña "
                    "de auditoría no pudo guardarse correctamente."
                )

    except RuntimeError:
        raise

    except Exception as error:
        raise RuntimeError(
            "No fue posible configurar las credenciales "
            "de auditoría en el gestor de credenciales "
            "del sistema."
        ) from error


def obtener_clave_cifrado() -> bytes:
    """
    Obtiene la clave de cifrada guardara en credenciales del sistema
    """

    try:
        clave_guardada = keyring.get_password(
            SERVICIO_AUDITORIA,
            USUARIO_CLAVE_CIFRADO,
        )

    except Exception as error:
        raise RuntimeError(
            "No fue posible acceder a la clave de "
            "cifrado almacenada en el gestor de "
            "credenciales del sistema."
        ) from error

    if not clave_guardada:
        raise RuntimeError(
            "La clave de cifrado de auditoría "
            "no se encuentra configurada en este equipo."
        )

    try:
        Fernet(clave_guardada.encode("utf-8"))

    except Exception as error:
        raise RuntimeError(
            "La clave de cifrado almacenada " "no tiene un formato Fernet válido."
        ) from error

    return clave_guardada.encode("utf-8")


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
        "id_registro": str(uuid.uuid4()),
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
        "id_registro",
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
