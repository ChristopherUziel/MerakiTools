from getpass import getpass

from auditoria import (
    exportar_auditoria_csv,
    exportar_auditoria_central_csv,
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

    print("\n1. Exportar auditoría local a CSV")
    print("2. Exportar y vaciar auditoría local")
    print("3. Exportar auditoria central a CSV")
    print("0. Volver al menú principal")

    opcion = input_menu("\nSelecciona una opción:\n> ")

    if opcion not in ("1", "2", "3"):
        print("\nOpción no válida.\n")
        return

    if not solicitar_password_auditoria():
        return

    if opcion == "3":
        try:
            archivo, registros_con_error = exportar_auditoria_central_csv()

        except ValueError as error:
            print("\nNo fue posible exportar " f"la auditoría central: {error}\n")
            return

        except Exception as error:
            print("\nNo fue posible descargar o " "exportar la auditoría central.")
            print(f"Detalle: " f"{type(error).__name__}: {error}\n")
            return

        print("\n✓ Auditoría central exportada " "correctamente.")
        print(f"Archivo:\n{archivo}\n")

        if registros_con_error > 0:
            print(
                "⚠ La exportación contiene "
                f"{registros_con_error} registro(s) "
                "que no pudieron descifrarse."
            )
            print("Los registros afectados fueron " "marcados dentro del CSV.\n")

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
