from meraki_api import inicializar
from modules.alta_evento import alta_evento
from modules.alta_entre_organizaciones import (
    alta_entre_organizaciones,
)
from modules.desmontaje import desmontaje
from modules.buscar import buscar, buscar_todas_organizaciones
from modules.reportes import reportes
from config import configurar_api_key_si_es_necesario

## imports de modulo politicas
from modules.politicas import sincronizar_politicas

##imports de modulo content filtering
from modules.content_filtering import(
    sincronizar_content_filtering,
)

## imports modulo traffic shaping
from modules.sdwan_traffic_shaping import sincronizar_sdwan_traffic_shaping

## import modulo busqueda de cliente
from modules.buscar_clientes import buscar_clientes

##import para anvegacion a menu
from navegacion import VolverMenuPrincipal

__author__ = "Christopher Uziel Martinez Alvarez"
__project__ = "MerakiTools"
__version__ = "1.0"


def mostrar_menu():

    arte_ascii = """
     ###   ###  #####  ####  ###  
    #   # #     #     #     #   # 
    #   # #     ####   ###  ##### 
    #   # #     #         # #   # 
     ###   ###  ##### ####  #   # 
    """

    print("\n" + "=" * 40)
    print(arte_ascii)
    print("\n" + "=" * 40)
    print("      MERAKI TOOLS")
    print("=" * 40)
    print("1. Alta de Equipos en la misma Organización")
    print("2. Alta masiva entre Organizaciones")
    print("3. Desmontaje")
    print("4. Buscar Equipo en una Organización")
    print("5. Buscar Equipo en todas las Organizaciones")
    print("6. Buscar Cliente en todas las Organizaciones")
    print("7. Sincronizar Group Policies")
    print("8. Sincronizar SD-WAN & Traffic shaping")
    print("9. Sincronizar Content Filtering")
    print("10. Reportes")
    print("11. Salir")
    print("=" * 40)


def main():

    try:
        configurar_api_key_si_es_necesario()

    except ValueError as error:
        print(f"\nError de configuración: {error}\n")
        input("Presiona Enter para cerrar...")
        return

    inicializar()

    while True:
        mostrar_menu()

        opcion = input("Selecciona una opción: ")

        try:
            if opcion == "1":
                alta_evento()

            elif opcion == "2":
                alta_entre_organizaciones()

            elif opcion == "3":
                desmontaje()

            elif opcion == "4":
                buscar()

            elif opcion == "5":
                buscar_todas_organizaciones()

            elif opcion == "6":
                buscar_clientes()

            elif opcion == "7":
                sincronizar_politicas()

            elif opcion == "8":
                sincronizar_sdwan_traffic_shaping()

            elif opcion == "9":
                sincronizar_content_filtering()

            elif opcion == "10":
                reportes()

            elif opcion == "11":
                print("\n¡Hasta luego!")
                break

            else:
                print("\nOpción inválida.")

        except VolverMenuPrincipal:
            print("\nRegresando al menu principal...\n")


if __name__ == "__main__":
    main()
