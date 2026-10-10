# ================================================================
# app/config/db.py
# ORION — MongoDB Atlas
# Métodos de pago, carrito, opiniones, MARKETPLACE,
# MONEDERO y SISTEMA DE BLOQUEO/DESBLOQUEO DE MONEDEROS
# ================================================================

import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, DESCENDING


# ================================================================
# 1. CARGAR VARIABLES DE ENTORNO
# ================================================================

RUTA_ENV = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=RUTA_ENV)

# ================================================================
# 2. CONEXIÓN A MONGODB ATLAS
# ================================================================

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DBNAME = os.getenv("MONGO_DBNAME", "orioon")

if not MONGO_URI:
    raise RuntimeError(
        f"No se encontró MONGO_URI en el archivo: {RUTA_ENV}"
    )

client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=10000,
    connectTimeoutMS=10000,
)

db = client[MONGO_DBNAME]

try:
    client.admin.command("ping")
    print("Conexión con MongoDB Atlas establecida.")
    print(f"Base de datos: {db.name}")

except Exception as e:
    client.close()
    raise RuntimeError(
        f"No se pudo conectar con MongoDB Atlas: {e}"
    ) from e


# ================================================================
# 3. DEFINICIÓN DE COLECCIONES
# ================================================================

usuarios_col = db["usuarios"]
categorias_col = db["categorias"]
atributos_col = db["atributos"]
productos_col = db["productos"]
direcciones_col = db["direcciones"]
marcas_col = db["marcas"]
negra_col = db["lista_negra"]
resenas_col = db["resenas"]
ventas_col = db["ventas"]
pedidos_col = db["pedidos"]
cupones_col = db["cupones"]
cupones_usuarios_col = db["cupones_usuarios"]
promociones_col = db["promociones"]
combos_col = db["combos"]
chats_col = db["chats"]
temporadas_col = db["temporadas"]
monedero_col = db["monedero"]

# Monedero digital
monedero_config_col = db["monedero_config"]
monedero_bloqueos_col = db["monedero_bloqueos"]

# Colecciones adicionales
favoritos_col = db["favoritos"]
mensajes_contacto_col = db["mensajes_contacto"]
configuracion_col = db["configuracion"]
notificaciones_col = db["notificaciones"]
auditoria_chat_col = db["auditoria_chat"]
impi_consultas_col = db["impi_consultas"]
lealtad_puntos_col = db["lealtad_puntos"]
complexion_col = db["complexion"]
preferencias_col = db["preferencias"]

# Métodos de pago, carrito y opiniones
metodos_pago_col = db["metodos_pago"]
carrito_col = db["carrito"]
opiniones_col = db["opiniones"]

# Mesas de regalos
mesas_regalos_col = db["mesas_regalos"]

# Marketplace
vendedores_col = db["vendedores"]
comisiones_marketplace_col = db["comisiones_marketplace"]

# Alias para productos del marketplace
productos_marketplace_col = db["productos"]


# ================================================================
# 4. CREACIÓN Y VERIFICACIÓN DE ÍNDICES
# ================================================================

def crear_indices():
    """
    Crea y verifica los índices utilizados por ORION.

    Características:
    - No elimina documentos ni colecciones.
    - No elimina índices existentes.
    - Evita crear nuevamente índices con las mismas claves.
    - Comprueba las opciones de índices existentes.
    - Informa de los problemas de unicidad sin modificar datos.
    - Permite que marcas sin nombre_normalizado no entren
      en el índice único parcial.
    """

    indices = [

        # --------------------------------------------------------
        # USUARIOS
        # --------------------------------------------------------
        (
            usuarios_col,
            [("email", ASCENDING)],
            {"unique": True},
        ),

        # --------------------------------------------------------
        # CATEGORÍAS
        # --------------------------------------------------------
        (
            categorias_col,
            [("nombre", ASCENDING)],
            {"unique": True},
        ),
        (categorias_col, [("padre_id", ASCENDING)], {}),
        (categorias_col, [("nivel", ASCENDING)], {}),
        (categorias_col, [("activo", ASCENDING)], {}),

        # --------------------------------------------------------
        # ATRIBUTOS
        # --------------------------------------------------------
        (atributos_col, [("nombre", ASCENDING)], {}),
        (atributos_col, [("categoria_id", ASCENDING)], {}),

        # --------------------------------------------------------
        # PRODUCTOS
        # --------------------------------------------------------
        (productos_col, [("nombre", ASCENDING)], {}),
        (productos_col, [("categoria_id", ASCENDING)], {}),
        (productos_col, [("precio", ASCENDING)], {}),
        (productos_col, [("marca_id", ASCENDING)], {}),
        (productos_col, [("activo", ASCENDING)], {}),
        (productos_col, [("created_at", DESCENDING)], {}),
        (
            productos_col,
            [("temporada_id", ASCENDING)],
            {"sparse": True},
        ),
        (productos_col, [("estado", ASCENDING)], {}),

        # --------------------------------------------------------
        # MARKETPLACE: PRODUCTOS POR VENDEDOR
        # --------------------------------------------------------
        (
            productos_col,
            [("vendedor_id", ASCENDING)],
            {"sparse": True},
        ),
        (
            productos_col,
            [
                ("vendedor_id", ASCENDING),
                ("activo", ASCENDING),
            ],
            {},
        ),
        (
            productos_col,
            [
                ("vendedor_id", ASCENDING),
                ("estado", ASCENDING),
            ],
            {},
        ),
        (
            productos_col,
            [
                ("vendedor_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {},
        ),
        (
            productos_col,
            [
                ("vendedor_id", ASCENDING),
                ("categoria_id", ASCENDING),
            ],
            {},
        ),
        (
            productos_col,
            [
                ("vendedor_id", ASCENDING),
                ("marca_id", ASCENDING),
            ],
            {},
        ),
        (
            productos_col,
            [
                ("vendedor_id", ASCENDING),
                ("activo", ASCENDING),
                ("created_at", DESCENDING),
            ],
            {},
        ),

        # --------------------------------------------------------
        # DIRECCIONES
        # --------------------------------------------------------
        (direcciones_col, [("usuario_id", ASCENDING)], {}),

        # --------------------------------------------------------
        # MARCAS
        #
        # Se utiliza nombre_normalizado porque la aplicación
        # guarda el nombre comercial y su versión normalizada.
        #
        # El índice parcial solo incluye documentos cuyo
        # nombre_normalizado sea de tipo string.
        #
        # IMPORTANTE:
        # Los valores string duplicados todavía deben revisarse.
        # --------------------------------------------------------
        (
            marcas_col,
            [("nombre_normalizado", ASCENDING)],
            {
                "unique": True,
                "partialFilterExpression": {
                    "nombre_normalizado": {"$type": "string"}
                },
            },
        ),
        (marcas_col, [("estado", ASCENDING)], {}),
        (marcas_col, [("nombre_comercial", ASCENDING)], {}),

        # --------------------------------------------------------
        # LISTA NEGRA
        # --------------------------------------------------------
        (negra_col, [("usuario_id", ASCENDING)], {}),
        (negra_col, [("email", ASCENDING)], {}),

        # --------------------------------------------------------
        # RESEÑAS Y OPINIONES
        # --------------------------------------------------------
        (resenas_col, [("producto_id", ASCENDING)], {}),
        (resenas_col, [("usuario_id", ASCENDING)], {}),
        (opiniones_col, [("producto_id", ASCENDING)], {}),
        (opiniones_col, [("usuario_id", ASCENDING)], {}),

        # --------------------------------------------------------
        # VENTAS
        # --------------------------------------------------------
        (ventas_col, [("fecha", ASCENDING)], {}),
        (ventas_col, [("usuario_id", ASCENDING)], {}),
        (ventas_col, [("productos.id", ASCENDING)], {}),

        # --------------------------------------------------------
        # PEDIDOS
        #
        # numero_pedido debe ser único.
        # Si existen pedidos con el mismo número, MongoDB
        # no podrá crear el índice único hasta resolverlos.
        # No se borran ni modifican pedidos automáticamente.
        # --------------------------------------------------------
        (
            pedidos_col,
            [("numero_pedido", ASCENDING)],
            {"unique": True},
        ),
        (pedidos_col, [("usuario_id", ASCENDING)], {}),
        (pedidos_col, [("estado", ASCENDING)], {}),
        (pedidos_col, [("created_at", DESCENDING)], {}),
        (pedidos_col, [("items.vendedor_id", ASCENDING)], {}),
        (pedidos_col, [("items_list.vendedor_id", ASCENDING)], {}),
        (
            pedidos_col,
            [
                ("items.vendedor_id", ASCENDING),
                ("estado", ASCENDING),
            ],
            {},
        ),

        # --------------------------------------------------------
        # CUPONES
        # --------------------------------------------------------
        (
            cupones_col,
            [("codigo", ASCENDING)],
            {"unique": True},
        ),
        (cupones_col, [("activo", ASCENDING)], {}),
        (cupones_col, [("fecha_inicio", ASCENDING)], {}),
        (cupones_col, [("fecha_fin", ASCENDING)], {}),

        # --------------------------------------------------------
        # CUPONES UTILIZADOS POR USUARIOS
        # --------------------------------------------------------
        (cupones_usuarios_col, [("usuario_id", ASCENDING)], {}),
        (cupones_usuarios_col, [("cupon_codigo", ASCENDING)], {}),
        (cupones_usuarios_col, [("fecha_uso", ASCENDING)], {}),

        # --------------------------------------------------------
        # PROMOCIONES
        # --------------------------------------------------------
        (
            promociones_col,
            [("codigo", ASCENDING)],
            {"unique": True, "sparse": True},
        ),
        (promociones_col, [("activo", ASCENDING)], {}),
        (promociones_col, [("fecha_inicio", ASCENDING)], {}),
        (promociones_col, [("fecha_fin", ASCENDING)], {}),

        # --------------------------------------------------------
        # COMBOS
        # --------------------------------------------------------
        (
            combos_col,
            [("nombre", ASCENDING)],
            {"unique": True},
        ),
        (combos_col, [("activo", ASCENDING)], {}),

        # --------------------------------------------------------
        # CHATS Y AUDITORÍA
        # --------------------------------------------------------
        (chats_col, [("usuario_id", ASCENDING)], {}),
        (auditoria_chat_col, [("usuario_id", ASCENDING)], {}),
        (auditoria_chat_col, [("created_at", DESCENDING)], {}),

        # --------------------------------------------------------
        # TEMPORADAS
        # --------------------------------------------------------
        (
            temporadas_col,
            [("nombre", ASCENDING)],
            {"unique": True},
        ),
        (temporadas_col, [("activo", ASCENDING)], {}),

        # --------------------------------------------------------
        # MONEDERO Y AUDITORÍA DE BLOQUEOS
        # --------------------------------------------------------
        (
            monedero_col,
            [("usuario_id", ASCENDING)],
            {"unique": True},
        ),
        (monedero_config_col, [("activo", ASCENDING)], {}),
        (monedero_bloqueos_col, [("usuario_id", ASCENDING)], {}),
        (monedero_bloqueos_col, [("created_at", DESCENDING)], {}),
        (monedero_bloqueos_col, [("fecha", DESCENDING)], {}),

        # --------------------------------------------------------
        # FAVORITOS
        # --------------------------------------------------------
        (favoritos_col, [("usuario_id", ASCENDING)], {}),
        (favoritos_col, [("producto_id", ASCENDING)], {}),

        # --------------------------------------------------------
        # CONTACTO, CONFIGURACIÓN Y NOTIFICACIONES
        # --------------------------------------------------------
        (mensajes_contacto_col, [("created_at", DESCENDING)], {}),
        (configuracion_col, [("nombre", ASCENDING)], {}),
        (notificaciones_col, [("usuario_id", ASCENDING)], {}),
        (notificaciones_col, [("created_at", DESCENDING)], {}),

        # --------------------------------------------------------
        # CONSULTAS IMPI
        # --------------------------------------------------------
        (impi_consultas_col, [("usuario_id", ASCENDING)], {}),
        (impi_consultas_col, [("created_at", DESCENDING)], {}),

        # --------------------------------------------------------
        # LEALTAD, COMPLEXIÓN Y PREFERENCIAS
        # --------------------------------------------------------
        (lealtad_puntos_col, [("usuario_id", ASCENDING)], {}),
        (
            complexion_col,
            [("usuario_id", ASCENDING)],
            {"unique": True},
        ),
        (
            preferencias_col,
            [("usuario_id", ASCENDING)],
            {"unique": True},
        ),

        # --------------------------------------------------------
        # MÉTODOS DE PAGO
        # --------------------------------------------------------
        (metodos_pago_col, [("usuario_id", ASCENDING)], {}),

        # --------------------------------------------------------
        # CARRITO
        # --------------------------------------------------------
        (carrito_col, [("usuario_id", ASCENDING)], {}),

        # --------------------------------------------------------
        # MESAS DE REGALOS
        # --------------------------------------------------------
        (mesas_regalos_col, [("usuario_id", ASCENDING)], {}),
        (mesas_regalos_col, [("created_at", DESCENDING)], {}),

        # --------------------------------------------------------
        # MARKETPLACE: VENDEDORES Y COMISIONES
        # --------------------------------------------------------
        (vendedores_col, [("usuario_id", ASCENDING)], {}),
        (vendedores_col, [("estado", ASCENDING)], {}),
        (
            comisiones_marketplace_col,
            [("vendedor_id", ASCENDING)],
            {},
        ),
        (
            comisiones_marketplace_col,
            [("created_at", DESCENDING)],
            {},
        ),
    ]

    creados = 0
    verificados = 0
    advertencias = 0

    for coleccion, campos, opciones in indices:
        campos_solicitados = list(campos)

        try:
            indices_existentes = coleccion.index_information()
            indice_existente = None

            # Buscar un índice que utilice exactamente las mismas claves.
            for nombre_indice, informacion in indices_existentes.items():
                claves_existentes = [
                    tuple(clave)
                    for clave in informacion.get("key", [])
                ]

                if claves_existentes == campos_solicitados:
                    indice_existente = (
                        nombre_indice,
                        informacion,
                    )
                    break

            # Si existe, verificar sus opciones sin modificarlo.
            if indice_existente:
                nombre_indice, informacion = indice_existente
                conflictos = []

                opciones_a_verificar = (
                    "unique",
                    "sparse",
                    "partialFilterExpression",
                )

                for opcion in opciones_a_verificar:
                    solicitada = opciones.get(opcion)
                    actual = informacion.get(opcion)

                    # MongoDB puede omitir las opciones falsas.
                    if opcion in ("unique", "sparse"):
                        solicitada = bool(solicitada)
                        actual = bool(actual)

                    if solicitada != actual:
                        conflictos.append(
                            f"{opcion}: existente={actual}, "
                            f"solicitado={solicitada}"
                        )

                if conflictos:
                    advertencias += 1
                    print(
                        f"[REVISAR] Índice '{nombre_indice}' "
                        f"en colección '{coleccion.name}'. "
                        + "; ".join(conflictos)
                    )
                else:
                    verificados += 1

                continue

            # Si no existe un índice con esas claves, intentar crearlo.
            coleccion.create_index(
                campos_solicitados,
                **opciones,
            )

            creados += 1

        except Exception as e:
            advertencias += 1
            print(
                f"[ADVERTENCIA] No se pudo crear/verificar el índice "
                f"en '{coleccion.name}', campos {campos_solicitados}: "
                f"{e}"
            )

    # ------------------------------------------------------------
    # RESUMEN
    # ------------------------------------------------------------
    print("\n" + "=" * 60)
    print("RESUMEN DE ÍNDICES DE ORION")
    print("=" * 60)
    print(f"Índices creados: {creados}")
    print(f"Índices existentes verificados: {verificados}")
    print(f"Advertencias que requieren revisión: {advertencias}")

    if advertencias:
        print(
            "\nHay índices o datos que requieren revisión. "
            "Consulta los mensajes [REVISAR] y [ADVERTENCIA]."
        )
    else:
        print(
            "\nTodos los índices solicitados se crearon "
            "o se verificaron correctamente."
        )


# ================================================================
# 5. EJECUTAR CREACIÓN DE ÍNDICES
# ================================================================

crear_indices()


# ================================================================
# 6. EXPORTS PARA OTROS MÓDULOS
# ================================================================

__all__ = [
    "client",
    "db",
    "usuarios_col",
    "categorias_col",
    "atributos_col",
    "productos_col",
    "direcciones_col",
    "marcas_col",
    "negra_col",
    "resenas_col",
    "ventas_col",
    "pedidos_col",
    "cupones_col",
    "cupones_usuarios_col",
    "promociones_col",
    "combos_col",
    "chats_col",
    "temporadas_col",
    "monedero_col",
    "monedero_config_col",
    "monedero_bloqueos_col",
    "favoritos_col",
    "mensajes_contacto_col",
    "configuracion_col",
    "notificaciones_col",
    "auditoria_chat_col",
    "impi_consultas_col",
    "lealtad_puntos_col",
    "complexion_col",
    "preferencias_col",
    "metodos_pago_col",
    "carrito_col",
    "opiniones_col",
    "mesas_regalos_col",
    "vendedores_col",
    "comisiones_marketplace_col",
    "productos_marketplace_col",
    "crear_indices",
]
