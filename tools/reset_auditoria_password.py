from getpass import getpass

from auditoria import (
    establecer_password_exportacion,
)


def main() -> None:

    print("\n" + "=" * 50)
    print(" CONFIGURAR CONTRASEÑA DE AUDITORÍA")
    print("=" * 50)

    password = getpass("\nNueva contraseña:\n> ")

    confirmacion = getpass("Confirma la contraseña:\n> ")

    if not password:
        print("\nLa contraseña no puede " "estar vacía.\n")
        return

    if password != confirmacion:
        print("\nLas contraseñas no coinciden.\n")
        return

    establecer_password_exportacion(password)

    print("\n✓ Contraseña de auditoría " "actualizada correctamente.\n")


if __name__ == "__main__":
    main()


############# Desde raiz
####### py -m tools.reset_auditoria_password