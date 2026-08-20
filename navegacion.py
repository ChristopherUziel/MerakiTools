class VolverMenuPrincipal(Exception):
    """
    Se ultiliza para regresar al menu
    """

    pass


def input_menu(mensaje: str) -> str:
    """
    permite escribir menu o 0 para regresar al menu
    """

    valor = input(mensaje).strip()

    if valor.lower() == "menu" or valor == "0":
        raise VolverMenuPrincipal()

    return valor
