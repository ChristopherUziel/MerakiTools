import atexit
import base64
import csv
import ctypes
import hashlib
import json
import os
import secrets
from datetime import datetime
from getpass import getpass

import uuid

import keyring
from azure.storage.blob import BlobClient  ###Import azure
from cryptography.fernet import Fernet

from config import CARPETA_BASE

### archivo de auditoria respaldo local
CARPETA_AUDITORIA = CARPETA_BASE / "auditoria"
ARCHIVO_AUDITORIA = CARPETA_AUDITORIA / "auditoria.dat"

##### Archivo de pendientes de sincronizar en azure
ARCHIVO_PENDIENTES = CARPETA_AUDITORIA / "pendientes.dat"

SERVICIO_AUDITORIA = "MerakiTools_Auditoria"
USUARIO_CLAVE_CIFRADO = "clave_cifrado"

######## USUARIO SAS AZURE
USUARIO_SAS_AZURE = "azure_sas"

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


def asegurar_configuracion_sas_azure() -> bool:
    """
    Comprueba si el SAS de Azure ya está guardado

    Si no existe, valida el ingresado y lo guarda en credenciales
    """
    try:
        sas_guardado = keyring.get_password(
            SERVICIO_AUDITORIA,
            USUARIO_SAS_AZURE,
        )
    except Exception:
        print("\nNo fue posible consultar la " "configuración de Azure.")
        print("MerakiTools continuará con " "auditoría local.\n")
        return False

    if sas_guardado:
        return True

    print("\nEl acceso a la auditoría central " "de Azure no está configurado.")

    sas_url = getpass("Pega el SAS URL proporcionado: ").strip()

    if not sas_url:
        print("\nNo se ingresó un SAS.")
        print("MerakiTools continuará con " "auditoría local.\n")
        return False

    try:
        cliente = BlobClient.from_blob_url(sas_url)

        propiedades = cliente.get_blob_properties()

        if str(propiedades.blob_type).lower() not in (
            "appendblob",
            "blobtype.appendblob",
        ):
            print("\nEl SAS no apunta a un " "Append Blob.")
            print("El SAS no fue guardado.\n")
            return False

        keyring.set_password(
            SERVICIO_AUDITORIA,
            USUARIO_SAS_AZURE,
            sas_url,
        )

        sas_verificacion = keyring.get_password(
            SERVICIO_AUDITORIA,
            USUARIO_SAS_AZURE,
        )

        if sas_verificacion != sas_url:
            raise RuntimeError("El SAS no pudo guardarse " "correctamente.")

    except Exception as error:
        print("\nNo fue posible validar el acceso " "a la auditoría central de Azure.")
        print(f"Detalle: " f"{type(error).__name__}: {error}")
        print("El SAS no fue guardado.")
        print("MerakiTools continuará con " "auditoría local.\n")
        return False

    print("\nAcceso a la auditoría central " "configurado correctamente.\n")

    return True


def obtener_cliente_auditoria_azure() -> BlobClient:
    """
    Obtiene el cliente para el Append Blob central de auditoría.
    """

    sas_url = keyring.get_password(
        SERVICIO_AUDITORIA,
        USUARIO_SAS_AZURE,
    )

    if not sas_url:
        raise RuntimeError("El acceso de auditoría a Azure no está configurado.")

    return BlobClient.from_blob_url(sas_url)


def enviar_auditoria_azure(
    registro_cifrado: bytes,
) -> bool:
    """
    Intenta enviar un registro cifrado al Append Blob central.

    Devuelve True si Azure confirmó el append.
    Devuelve False si no fue posible enviarlo.
    """

    try:
        cliente = obtener_cliente_auditoria_azure()

        cliente.append_block(registro_cifrado + b"\n")

        return True

    except Exception:
        return False


def guardar_auditoria_pendiente(
    registro_cifrado: bytes,
) -> None:
    """
    Guarda un registro cifrado en pendientes.dat que no pudo
    confirmarse en central azure
    """
    CARPETA_AUDITORIA.mkdir(
        parents=True,
        exist_ok=True,
    )

    with ARCHIVO_PENDIENTES.open("ab") as archivo:
        archivo.write(registro_cifrado + b"\n")


def sincronizar_auditoria_pendiente() -> tuple[int, int]:
    """
    Intenta enviar a Azure los registros de pendientes.dat

    Devuelve:
        enviados y pendientes que no pudieron enviarse.
    """
    if not ARCHIVO_PENDIENTES.exists():
        return 0, 0

    registros_pendientes = []

    with ARCHIVO_PENDIENTES.open("rb") as archivo:
        for linea in archivo:
            registro_cifrado = linea.strip()

            if registro_cifrado:
                registros_pendientes.append(
                    registro_cifrado,
                )

    if not registros_pendientes:
        return 0, 0

    registros_no_enviados = []
    enviados = 0

    for registro_cifrado in registros_pendientes:
        enviado = enviar_auditoria_azure(
            registro_cifrado,
        )

        if enviado:
            enviados += 1
        else:
            registros_no_enviados.append(
                registro_cifrado,
            )

    archivo_temporal = ARCHIVO_PENDIENTES.with_suffix(
        ".tmp",
    )

    with archivo_temporal.open("wb") as archivo:
        for registro_cifrado in registros_no_enviados:
            archivo.write(
                registro_cifrado + b"\n",
            )

    archivo_temporal.replace(
        ARCHIVO_PENDIENTES,
    )

    return enviados, len(registros_no_enviados)


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

    # Enviado a azure
    enviado_azure = enviar_auditoria_azure(
        registro_cifrado,
    )

    # Si falla manda a pendientes
    if not enviado_azure:
        guardar_auditoria_pendiente(
            registro_cifrado,
        )


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


def leer_auditoria_central() -> tuple[list[dict], int]:
    """
    Descarga la auditoría central en memoria y
    descifra sus registros

    Las líneas que no puedan descifrarse se incluyen
    como registros de error para no cancelar toda
    la exportación
    """
    cliente = obtener_cliente_auditoria_azure()

    contenido_blob = cliente.download_blob().readall()

    if not contenido_blob:
        return [], 0

    clave = obtener_clave_cifrado()
    cifrador = Fernet(clave)

    registros = []
    registros_con_error = 0

    for numero_linea, linea in enumerate(
        contenido_blob.splitlines(),
        start=1,
    ):
        linea = linea.strip()

        if not linea:
            continue

        try:
            contenido = cifrador.decrypt(linea)
            registro = json.loads(contenido.decode("utf-8"))

            if not isinstance(registro, dict):
                raise ValueError("El registro descifrado no es un objeto.")

            registros.append(registro)

        except Exception:
            registros_con_error += 1

            registros.append(
                {
                    "id_registro": "",
                    "fecha_hora": "",
                    "usuario": "",
                    "modulo": "Auditoría central",
                    "accion": "Lectura de registro",
                    "organizacion": "",
                    "network": "",
                    "objetivo": f"Línea {numero_linea}",
                    "resultado": "ERROR DE LECTURA",
                    "detalle": (
                        "No fue posible descifrar el "
                        "registro central número "
                        f"{numero_linea}."
                    ),
                }
            )

    return registros, registros_con_error


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


def exportar_auditoria_central_csv() -> tuple[str, int]:
    """
    Descarga la auditoría central en memoria,
    la descifra y genera un archivo CSV local.

    Devuelve:
        ruta del archivo CSV.
        cantidad de registros con error.
    """
    registros, registros_con_error = leer_auditoria_central()

    if not registros:
        raise ValueError("No existen registros de auditoría " "central para exportar.")

    CARPETA_EXPORTACIONES.mkdir(
        parents=True,
        exist_ok=True,
    )

    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")

    archivo_salida = CARPETA_EXPORTACIONES / f"auditoria_central_{fecha}.csv"

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
            extrasaction="ignore",
        )

        escritor.writeheader()
        escritor.writerows(registros)

    return str(archivo_salida), registros_con_error


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
