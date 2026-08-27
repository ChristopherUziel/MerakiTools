from getpass import getpass

from auditoria import (
    exportar_auditoria_csv,
    password_exportacion_configurado,
    validar_password_exportacion,
    vaciar_auditoria,
)
from navegacion import input_menu


def solicitar_password_auditoria() -> bool:
    """
    Solicita y valida la contraseña de auditoria
    """

    if not password_exportacion_configurado():
        print("\nLa contraseña de auditoría " "todavía no ha sido configurada.")
        print("Debe configurarse desde MerakiTools_Dev.\n")
        return False

    password = getpass("\nContraseña de exportación:\n> ")

    if not validar_password_exportacion(password):
        print("\nContraseña incorrecta.\n")
        return False

    return True


def menu_auditoria() -> None:
    """
    Menu para auditoria
    """

    print("\n" + "=" * 50)
    print(" ADMINISTRACIÓN DE AUDITORÍA")
    print("=" * 50)

    print("\n1. Exportar auditoría a CSV")
    print("2. Exportar y vaciar auditoría")
    print("0. Volver al menú principal")

    opcion = input_menu("\nSelecciona una opción:\n> ")

    if opcion not in ("1", "2"):
        print("\nOpción no válida.\n")
        return

    if not solicitar_password_auditoria():
        return

    try:
        archivo = exportar_auditoria_csv()

    except ValueError as error:
        print(f"\nNo fue posible exportar " f"la auditoría: {error}\n")
        return

    print("\n✓ Auditoría exportada correctamente.")

    print(f"Archivo:\n{archivo}\n")

    if opcion == "1":
        return

    print("⚠ El CSV ya fue generado correctamente.")

    confirmacion = input_menu(
        "\nEscribe CONFIRMAR para vaciar " "el historial interno:\n> "
    )

    if confirmacion.upper() != "CONFIRMAR":
        print("\nEl historial NO fue eliminado.\n")
        return

    vaciar_auditoria()

    print("\n✓ Historial interno de auditoría " "vaciado correctamente.\n")
