from meraki_api import inicializar
from modules.alta_evento import alta_evento
from modules.desmontaje import desmontaje
from modules.buscar import buscar
from modules.reportes import reportes
from config import configurar_api_key_si_es_necesario


def mostrar_menu():
    print("\n" + "=" * 40)
    print("      MERAKI TOOLS")
    print("=" * 40)
    print("1. Alta de Equipos")
    print("2. Desmontaje")
    print("3. Buscar Equipo")
    print("4. Reportes")
    print("5. Salir")
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

        if opcion == "1":
            alta_evento()

        elif opcion == "2":
            desmontaje()

        elif opcion == "3":
            buscar()

        elif opcion == "4":
            reportes()

        elif opcion == "5":
            print("\n¡Hasta luego!")
            break

        else:
            print("\nOpción inválida.")


if __name__ == "__main__":
    main()
