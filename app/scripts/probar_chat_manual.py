# scripts/probar_chat_manual.py
# ================================================================
# SCRIPT DE PRUEBA MANUAL PARA EL CICLO DE VIDA DEL CHAT
# - Previsualizar retención, anonimización y archivado
# - Ejecutar archivado, anonimización y eliminación
# - Ver estadísticas generales
# - Menú interactivo + modo automático
# ================================================================
# USO:
#   python scripts/probar_chat_manual.py
#   python scripts/probar_chat_manual.py --auto
#   python scripts/probar_chat_manual.py --auto --dias-archivar 7 --dias-anonimizar 15 --dias-retencion 30
# ================================================================

import sys
import os
import argparse
from datetime import datetime, timezone, timedelta

# Añadir el directorio raíz al path para importar `app`
RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from app import create_app
from app.models.chat_model import Chat


# ================================================================
# COLORES PARA LA CONSOLA
# ================================================================

class C:
    OK = '\033[92m'
    WARN = '\033[93m'
    ERROR = '\033[91m'
    INFO = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def titulo(texto):
    print()
    print(f"{C.BOLD}{C.INFO}{'=' * 65}{C.END}")
    print(f"{C.BOLD}{C.INFO}  {texto}{C.END}")
    print(f"{C.BOLD}{C.INFO}{'=' * 65}{C.END}")


def seccion(texto):
    print()
    print(f"{C.BOLD}▶ {texto}{C.END}")
    print("-" * 65)


def ok(texto):
    print(f"{C.OK}  ✅ {texto}{C.END}")


def warn(texto):
    print(f"{C.WARN}  ⚠️  {texto}{C.END}")


def error(texto):
    print(f"{C.ERROR}  ❌ {texto}{C.END}")


def info(texto):
    print(f"{C.INFO}  ℹ️  {texto}{C.END}")


# ================================================================
# ESTADÍSTICAS
# ================================================================

def mostrar_estadisticas():
    seccion("ESTADÍSTICAS GENERALES")
    stats = Chat.estadisticas()
    print(f"  Total de conversaciones:      {C.BOLD}{stats['total']}{C.END}")
    print(f"  Activas:                      {C.OK}{stats['activas']}{C.END}")
    print(f"  Archivadas:                   {C.WARN}{stats['archivadas']}{C.END}")
    print(f"  Anonimizadas:                 {C.INFO}{stats.get('anonimizadas', 0)}{C.END}")
    print()
    print(f"  Configuración actual:")
    print(f"    • Días para archivar:       {stats.get('dias_para_archivar', 'N/A')}")
    print(f"    • Días para anonimizar:     {stats.get('dias_anonimizacion', 'N/A')}")
    print(f"    • Días de retención:        {stats.get('dias_retencion', 'N/A')}")


# ================================================================
# PREVISUALIZACIONES
# ================================================================

def previsualizar_archivado(dias):
    seccion(f"PREVISUALIZAR ARCHIVADO ({dias} días de inactividad)")
    limite = datetime.now(timezone.utc) - timedelta(days=dias)
    from app.config.database_config import db
    total = db.chats.count_documents({
        "estado": "activo",
        "updated_at": {"$lt": limite}
    })
    print(f"  Conversaciones activas a archivar: {C.WARN}{total}{C.END}")
    print(f"  Fecha límite: {limite.isoformat()}")
    return total


def previsualizar_anonimizacion(dias):
    seccion(f"PREVISUALIZAR ANONIMIZACIÓN ({dias} días)")
    preview = Chat.previsualizar_anonimizacion(dias=dias)
    print(f"  Conversaciones a anonimizar: {C.INFO}{preview['total_a_anonimizar']}{C.END}")
    print(f"  Fecha límite:                {preview['limite_fecha']}")
    return preview['total_a_anonimizar']


def previsualizar_retencion(dias):
    seccion(f"PREVISUALIZAR RETENCIÓN ({dias} días)")
    preview = Chat.previsualizar_retencion(dias=dias)
    print(f"  Conversaciones a eliminar: {C.ERROR}{preview['total_a_eliminar']}{C.END}")
    print(f"  Fecha límite:              {preview['limite_fecha']}")
    return preview['total_a_eliminar']


# ================================================================
# EJECUCIÓN DE TAREAS
# ================================================================

def ejecutar_archivado(dias, confirmar=True):
    seccion(f"EJECUTAR ARCHIVADO ({dias} días de inactividad)")
    total = previsualizar_archivado(dias)
    if total == 0:
        info("No hay conversaciones para archivar.")
        return 0
    if confirmar:
        respuesta = input(f"\n  ¿Archivar {total} conversaciones? [s/N]: ").strip().lower()
        if respuesta != 's':
            warn("Operación cancelada.")
            return 0
    archivadas = Chat.archivar_sesiones_inactivas(dias=dias)
    ok(f"{archivadas} conversaciones archivadas.")
    return archivadas


def ejecutar_anonimizacion(dias, confirmar=True):
    seccion(f"EJECUTAR ANONIMIZACIÓN ({dias} días)")
    total = previsualizar_anonimizacion(dias)
    if total == 0:
        info("No hay conversaciones para anonimizar.")
        return 0
    if confirmar:
        respuesta = input(f"\n  ¿Anonimizar {total} conversaciones? [s/N]: ").strip().lower()
        if respuesta != 's':
            warn("Operación cancelada.")
            return 0
    anonimizadas = Chat.anonimizar_sesiones_inactivas(dias=dias)
    ok(f"{anonimizadas} conversaciones anonimizadas.")
    return anonimizadas


def ejecutar_retencion(dias, confirmar=True):
    seccion(f"EJECUTAR RETENCIÓN ({dias} días)")
    total = previsualizar_retencion(dias)
    if total == 0:
        info("No hay conversaciones para eliminar.")
        return 0
    if confirmar:
        print()
        warn(f"⚠️  ESTA ACCIÓN ELIMINARÁ PERMANENTEMENTE {total} CONVERSACIONES.")
        respuesta = input(f"  Escribe 'ELIMINAR' para confirmar: ").strip()
        if respuesta != 'ELIMINAR':
            warn("Operación cancelada.")
            return 0
    eliminadas = Chat.eliminar_sesiones_archivadas(dias=dias)
    ok(f"{eliminadas} conversaciones eliminadas permanentemente.")
    return eliminadas


# ================================================================
# MENÚ INTERACTIVO
# ================================================================

def menu_interactivo(dias_archivar, dias_anonimizar, dias_retencion):
    while True:
        titulo("PANEL DE PRUEBA — CICLO DE VIDA DEL CHAT")
        print()
        print("  1. Mostrar estadísticas generales")
        print("  2. Previsualizar archivado")
        print("  3. Previsualizar anonimización")
        print("  4. Previsualizar retención")
        print()
        print("  5. Ejecutar archivado")
        print("  6. Ejecutar anonimización")
        print("  7. Ejecutar retención")
        print()
        print("  8. Ejecutar TODO el ciclo")
        print("  9. Cambiar días de configuración")
        print("  0. Salir")
        print()

        opcion = input("  Opción: ").strip()

        try:
            if opcion == '1':
                mostrar_estadisticas()
            elif opcion == '2':
                previsualizar_archivado(dias_archivar)
            elif opcion == '3':
                previsualizar_anonimizacion(dias_anonimizar)
            elif opcion == '4':
                previsualizar_retencion(dias_retencion)
            elif opcion == '5':
                ejecutar_archivado(dias_archivar)
            elif opcion == '6':
                ejecutar_anonimizacion(dias_anonimizar)
            elif opcion == '7':
                ejecutar_retencion(dias_retencion)
            elif opcion == '8':
                titulo("EJECUTAR CICLO COMPLETO")
                ejecutar_archivado(dias_archivar)
                ejecutar_anonimizacion(dias_anonimizar)
                ejecutar_retencion(dias_retencion)
                mostrar_estadisticas()
            elif opcion == '9':
                print()
                try:
                    dias_archivar = int(input(f"  Días para archivar [{dias_archivar}]: ") or dias_archivar)
                    dias_anonimizar = int(input(f"  Días para anonimizar [{dias_anonimizar}]: ") or dias_anonimizar)
                    dias_retencion = int(input(f"  Días de retención [{dias_retencion}]: ") or dias_retencion)
                    ok(f"Configuración: archivar={dias_archivar}, anonimizar={dias_anonimizar}, retención={dias_retencion}")
                except ValueError:
                    error("Valores inválidos.")
            elif opcion == '0':
                print()
                info("¡Hasta luego!")
                break
            else:
                warn("Opción no válida.")
        except KeyboardInterrupt:
            print()
            warn("Operación cancelada.")
        except Exception as e:
            error(f"Error: {e}")

        input(f"\n  {C.INFO}Presiona ENTER para continuar...{C.END}")


# ================================================================
# MODO AUTOMÁTICO
# ================================================================

def modo_automatico(dias_archivar, dias_anonimizar, dias_retencion):
    titulo("MODO AUTOMÁTICO — CICLO COMPLETO")
    mostrar_estadisticas()

    print()
    archivadas = Chat.archivar_sesiones_inactivas(dias=dias_archivar)
    ok(f"Archivadas {archivadas} conversaciones (>{dias_archivar} días inactivas).")

    print()
    anonimizadas = Chat.anonimizar_sesiones_inactivas(dias=dias_anonimizar)
    ok(f"Anonimizadas {anonimizadas} conversaciones (>{dias_anonimizar} días archivadas).")

    print()
    eliminadas = Chat.eliminar_sesiones_archivadas(dias=dias_retencion)
    ok(f"Eliminadas {eliminadas} conversaciones (>{dias_retencion} días archivadas).")

    mostrar_estadisticas()
    titulo("✅ CICLO COMPLETO FINALIZADO")


# ================================================================
# MAIN
# ================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Script de prueba manual para el ciclo de vida del chat."
    )
    parser.add_argument('--auto', action='store_true',
                        help="Ejecutar el ciclo completo sin interacción.")
    parser.add_argument('--dias-archivar', type=int, default=None,
                        help="Días para archivar inactivas.")
    parser.add_argument('--dias-anonimizar', type=int, default=None,
                        help="Días para anonimizar.")
    parser.add_argument('--dias-retencion', type=int, default=None,
                        help="Días de retención.")
    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        dias_archivar = args.dias_archivar or Chat.DIAS_PARA_ARCHIVAR
        dias_anonimizar = args.dias_anonimizar or Chat.DIAS_PARA_ANONIMIZAR
        dias_retencion = args.dias_retencion or Chat.DIAS_RETENCION_ARCHIVADAS

        titulo("CICLO DE VIDA DEL CHAT — ORION")
        print(f"  Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Configuración:")
        print(f"    • Archivar inactivas:  {dias_archivar} días")
        print(f"    • Anonimizar:          {dias_anonimizar} días")
        print(f"    • Retención:           {dias_retencion} días")

        if args.auto:
            modo_automatico(dias_archivar, dias_anonimizar, dias_retencion)
        else:
            menu_interactivo(dias_archivar, dias_anonimizar, dias_retencion)


if __name__ == '__main__':
    main()