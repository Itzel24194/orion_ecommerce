# ================================================================
# app/config/db.py
# COMPLETO — con metodos_pago, carrito, opiniones, MARKETPLACE,
# MONEDERO y SISTEMA DE BLOQUEO/DESBLOQUEO DE MONEDEROS
# ================================================================

from pymongo import MongoClient, ASCENDING, DESCENDING

# 1. Conexión
client = MongoClient("mongodb://localhost:27017/")
db = client["orioon"]

# 2. Definición de colecciones
usuarios_col = db["usuarios"]
categorias_col = db["categorias"]
atributos_col = db['atributos']
productos_col = db['productos']
direcciones_col = db['direcciones']
marcas_col = db['marcas']
negra_col = db['lista_negra']
resenas_col = db['resenas']
ventas_col = db['ventas']
pedidos_col = db["pedidos"]
cupones_col = db["cupones"]
cupones_usuarios_col = db["cupones_usuarios"]
promociones_col = db["promociones"]
combos_col = db["combos"]
chats_col = db["chats"]
temporadas_col = db["temporadas"]
monedero_col = db["monedero"]

# ⭐ NUEVA — configuración del monedero (límites, comisiones, cashback)
monedero_config_col = db["monedero_config"]

# ⭐⭐⭐ NUEVA — historial/auditoría de bloqueos y desbloqueos de monederos
monedero_bloqueos_col = db["monedero_bloqueos"]

# ⭐ NUEVAS COLECCIONES
favoritos_col = db["favoritos"]
mensajes_contacto_col = db["mensajes_contacto"]
configuracion_col = db["configuracion"]
notificaciones_col = db["notificaciones"]
auditoria_chat_col = db["auditoria_chat"]
impi_consultas_col = db["impi_consultas"]
lealtad_puntos_col = db["lealtad_puntos"]
complexion_col = db["complexion"]
preferencias_col = db["preferencias"]

# ⭐⭐⭐ CRÍTICAS
metodos_pago_col = db["metodos_pago"]
carrito_col = db["carrito"]
opiniones_col = db["opiniones"]

# ⭐⭐⭐ MESAS DE REGALOS
mesas_regalos_col = db["mesas_regalos"]

# ⭐⭐⭐ MARKETPLACE
vendedores_col = db["vendedores"]
comisiones_marketplace_col = db["comisiones_marketplace"]

# ⭐ Alias de productos_col para claridad
productos_marketplace_col = db["productos"]


# 3. Configuración de índices
def crear_indices():
    """Crear índices de manera segura, eliminando índices duplicados si existen"""
    try:
        # --- Usuarios ---
        try:
            usuarios_col.create_index([("email", ASCENDING)], unique=True)
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    usuarios_col.drop_index("email_1")
                    usuarios_col.create_index([("email", ASCENDING)], unique=True)
                except:
                    pass
            else:
                print(f"  ⚠️ Usuarios: {e}")

        # --- Categorías ---
        try:
            categorias_col.create_index([("nombre", ASCENDING)], unique=True)
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    categorias_col.drop_index("nombre_1")
                    categorias_col.create_index([("nombre", ASCENDING)], unique=True)
                except:
                    pass
            else:
                print(f"  ⚠️ Categorías: {e}")

        # ⭐ Jerarquía de categorías
        try:
            categorias_col.create_index([("padre_id", ASCENDING)])
        except:
            pass
        try:
            categorias_col.create_index([("nivel", ASCENDING)])
        except:
            pass
        try:
            categorias_col.create_index([("activo", ASCENDING)])
        except:
            pass

        # --- Productos ---
        try:
            productos_col.create_index([("nombre", ASCENDING)])
        except:
            pass
        try:
            productos_col.create_index([("categoria_id", ASCENDING)])
        except:
            pass
        try:
            productos_col.create_index([("precio", ASCENDING)])
        except:
            pass
        try:
            productos_col.create_index([("marca_id", ASCENDING)])
        except:
            pass
        try:
            productos_col.create_index([("activo", ASCENDING)])
        except:
            pass
        try:
            productos_col.create_index([("created_at", DESCENDING)])
        except:
            pass
        try:
            productos_col.create_index([("temporada_id", ASCENDING)], sparse=True)
        except:
            pass
        try:
            productos_col.create_index([("estado", ASCENDING)])
        except:
            pass

        # ⭐⭐⭐ MARKETPLACE: índices para productos del vendedor ⭐⭐⭐
        try:
            productos_col.create_index([("vendedor_id", ASCENDING)])
        except:
            pass

        try:
            productos_col.create_index([
                ("vendedor_id", ASCENDING),
                ("activo", ASCENDING)
            ])
        except:
            pass

        try:
            productos_col.create_index([
                ("vendedor_id", ASCENDING),
                ("estado", ASCENDING)
            ])
        except:
            pass

        try:
            productos_col.create_index([
                ("vendedor_id", ASCENDING),
                ("created_at", DESCENDING)
            ])
        except:
            pass

        # ⭐ NUEVOS: filtros del panel del vendedor por categoría/marca
        try:
            productos_col.create_index([
                ("vendedor_id", ASCENDING),
                ("categoria_id", ASCENDING)
            ])
        except:
            pass

        try:
            productos_col.create_index([
                ("vendedor_id", ASCENDING),
                ("marca_id", ASCENDING)
            ])
        except:
            pass

        # ⭐ NUEVO: vendedor + activo + created_at (listado principal del catálogo del vendedor)
        try:
            productos_col.create_index([
                ("vendedor_id", ASCENDING),
                ("activo", ASCENDING),
                ("created_at", DESCENDING)
            ])
        except:
            pass

        # --- Pedidos ---
        try:
            pedidos_col.create_index([("numero_pedido", ASCENDING)], unique=True)
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    pedidos_col.drop_index("numero_pedido_1")
                    pedidos_col.create_index([("numero_pedido", ASCENDING)], unique=True)
                except:
                    pass
            else:
                print(f"  ⚠️ Pedidos (numero_pedido): {e}")

        try:
            pedidos_col.create_index([("usuario_id", ASCENDING)])
        except:
            pass
        try:
            pedidos_col.create_index([("estado", ASCENDING)])
        except:
            pass
        try:
            pedidos_col.create_index([("created_at", DESCENDING)])
        except:
            pass

        # ⭐⭐⭐ MARKETPLACE: índices para pedidos del vendedor ⭐⭐⭐
        try:
            pedidos_col.create_index([("items.vendedor_id", ASCENDING)])
        except:
            pass

        try:
            pedidos_col.create_index([("items_list.vendedor_id", ASCENDING)])
        except:
            pass

        try:
            pedidos_col.create_index([
                ("items.vendedor_id", ASCENDING),
                ("estado", ASCENDING)
            ])
        except:
            pass

        # --- Cupones ---
        try:
            cupones_col.create_index([("codigo", ASCENDING)], unique=True)
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    cupones_col.drop_index("codigo_1")
                    cupones_col.create_index([("codigo", ASCENDING)], unique=True)
                except:
                    pass
            else:
                print(f"  ⚠️ Cupones (codigo): {e}")

        try:
            cupones_col.create_index([("activo", ASCENDING)])
        except:
            pass
        try:
            cupones_col.create_index([("fecha_inicio", ASCENDING)])
        except:
            pass
        try:
            cupones_col.create_index([("fecha_fin", ASCENDING)])
        except:
            pass

        # --- Cupones Usuarios ---
        try:
            cupones_usuarios_col.create_index([("usuario_id", ASCENDING)])
        except:
            pass
        try:
            cupones_usuarios_col.create_index([("cupon_codigo", ASCENDING)])
        except:
            pass
        try:
            cupones_usuarios_col.create_index([("fecha_uso", ASCENDING)])
        except:
            pass

        # --- Marca ---
        try:
            marcas_col.create_index([("nombre", ASCENDING)], unique=True)
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    marcas_col.drop_index("nombre_1")
                    marcas_col.create_index([("nombre", ASCENDING)], unique=True)
                except:
                    pass
            else:
                print(f"  ⚠️ Marcas (nombre): {e}")

        try:
            marcas_col.create_index([("estado", ASCENDING)])
        except:
            pass

        try:
            marcas_col.create_index([("nombre_comercial", ASCENDING)])
        except:
            pass

        # --- Ventas ---
        try:
            ventas_col.create_index([("fecha", ASCENDING)])
        except:
            pass
        try:
            ventas_col.create_index([("usuario_id", ASCENDING)])
        except:
            pass

        try:
            ventas_col.create_index([("productos.id", ASCENDING)])
        except:
            pass

        # --- PROMOCIONES ---
        try:
            promociones_col.create_index([("codigo", ASCENDING)], unique=True, sparse=True)
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    promociones_col.drop_index("codigo_1")
                    promociones_col.create_index([("codigo", ASCENDING)], unique=True, sparse=True)
                except:
                    pass
            else:
                print(f"  ⚠️ Promociones (codigo): {e}")
        try:
            promociones_col.create_index([("activo", ASCENDING)])
        except:
            pass
        try:
            promociones_col.create_index([("fecha_inicio", ASCENDING)])
        except:
            pass
        try:
            promociones_col.create_index([("fecha_fin", ASCENDING)])
        except:
            pass
        try:
            promociones_col.create_index([("tipo", ASCENDING)])
        except:
            pass
        try:
            promociones_col.create_index([("prioridad", ASCENDING)])
        except:
            pass

        # --- COMBOS ---
        try:
            combos_col.create_index([("nombre", ASCENDING)], unique=True)
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    combos_col.drop_index("nombre_1")
                    combos_col.create_index([("nombre", ASCENDING)], unique=True)
                except:
                    pass
            else:
                print(f"  ⚠️ Combos (nombre): {e}")
        try:
            combos_col.create_index([("activo", ASCENDING)])
        except:
            pass
        try:
            combos_col.create_index([("precio", ASCENDING)])
        except:
            pass
        try:
            combos_col.create_index([("descuento", ASCENDING)])
        except:
            pass
        try:
            combos_col.create_index([("productos", ASCENDING)])
        except:
            pass

        # --- TEMPORADAS ---
        try:
            temporadas_col.create_index([("nombre", ASCENDING)], unique=True)
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    temporadas_col.drop_index("nombre_1")
                    temporadas_col.create_index([("nombre", ASCENDING)], unique=True)
                except:
                    pass
            else:
                print(f"  ⚠️ Temporadas (nombre): {e}")

        try:
            temporadas_col.create_index([("fecha_inicio", ASCENDING)])
        except:
            pass
        try:
            temporadas_col.create_index([("fecha_fin", ASCENDING)])
        except:
            pass
        try:
            temporadas_col.create_index([("activa", ASCENDING)])
        except:
            pass
        try:
            temporadas_col.create_index([("fecha_inicio", ASCENDING), ("fecha_fin", ASCENDING)])
        except:
            pass

        # ============================================================
        # --- MONEDERO DIGITAL ---
        # ============================================================
        try:
            monedero_col.create_index([("usuario_id", ASCENDING)], unique=True)
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    monedero_col.drop_index("usuario_id_1")
                    monedero_col.create_index([("usuario_id", ASCENDING)], unique=True)
                except:
                    pass
            else:
                print(f"  ⚠️ Monedero (usuario_id): {e}")
        try:
            monedero_col.create_index([("numero_tarjeta", ASCENDING)])
        except:
            pass
        try:
            monedero_col.create_index([("created_at", ASCENDING)])
        except:
            pass
        try:
            monedero_col.create_index([("updated_at", ASCENDING)])
        except:
            pass

        # ⭐ NUEVOS índices para el panel admin del monedero
        try:
            monedero_col.create_index([("bloqueado", ASCENDING)])
        except:
            pass
        try:
            monedero_col.create_index([("saldo", DESCENDING)])
        except:
            pass
        try:
            monedero_col.create_index([("movimientos.fecha", DESCENDING)])
        except:
            pass

        # ⭐⭐⭐ NUEVOS índices para el SISTEMA DE BLOQUEO ⭐⭐⭐
        # Filtro combinado: activos vs bloqueados
        try:
            monedero_col.create_index([
                ("bloqueado", ASCENDING),
                ("saldo", DESCENDING)
            ])
        except:
            pass

        # Ordenar por fecha de bloqueo (para ver los más recientes)
        try:
            monedero_col.create_index([("bloqueado_en", DESCENDING)])
        except:
            pass

        # Saber qué admin bloqueó (auditoría rápida)
        try:
            monedero_col.create_index([("bloqueado_por", ASCENDING)])
        except:
            pass

        # Historial de desbloqueos
        try:
            monedero_col.create_index([("desbloqueado_en", DESCENDING)])
        except:
            pass

        # Motivo de bloqueo (búsquedas por texto parcial)
        try:
            monedero_col.create_index([("motivo_bloqueo", ASCENDING)])
        except:
            pass

        # Usuario + estado de bloqueo (para validar si un usuario puede operar)
        try:
            monedero_col.create_index([
                ("usuario_id", ASCENDING),
                ("bloqueado", ASCENDING)
            ])
        except:
            pass

        # ============================================================
        # ⭐ CONFIGURACIÓN DEL MONEDERO (admin)
        # ============================================================
        # El documento de config usa _id = "global" (singleton)
        # No necesita índices extra más allá del _id por defecto.
        try:
            monedero_config_col.create_index([("updated_at", DESCENDING)])
        except:
            pass

        # ============================================================
        # ⭐⭐⭐ HISTORIAL DE BLOQUEOS DE MONEDERO (AUDITORÍA) ⭐⭐⭐
        # ============================================================
        # Cada documento representa un evento: bloqueo o desbloqueo.
        # Ejemplo de documento:
        # {
        #   monedero_id: ObjectId,
        #   usuario_id: ObjectId,
        #   accion: "bloqueo" | "desbloqueo",
        #   motivo: "...",
        #   admin_id: ObjectId,
        #   admin_nombre: "...",
        #   saldo_al_momento: 123.45,
        #   created_at: datetime
        # }

        # Buscar eventos por monedero
        try:
            monedero_bloqueos_col.create_index([("monedero_id", ASCENDING)])
        except:
            pass

        # Buscar eventos por usuario
        try:
            monedero_bloqueos_col.create_index([("usuario_id", ASCENDING)])
        except:
            pass

        # Filtrar por tipo de acción (bloqueo / desbloqueo)
        try:
            monedero_bloqueos_col.create_index([("accion", ASCENDING)])
        except:
            pass

        # Ver qué admin hizo la acción
        try:
            monedero_bloqueos_col.create_index([("admin_id", ASCENDING)])
        except:
            pass

        # Ordenar por fecha (los más recientes primero)
        try:
            monedero_bloqueos_col.create_index([("created_at", DESCENDING)])
        except:
            pass

        # Combinado: usuario + fecha (historial completo de un usuario)
        try:
            monedero_bloqueos_col.create_index([
                ("usuario_id", ASCENDING),
                ("created_at", DESCENDING)
            ])
        except:
            pass

        # Combinado: acción + fecha (todos los bloqueos ordenados)
        try:
            monedero_bloqueos_col.create_index([
                ("accion", ASCENDING),
                ("created_at", DESCENDING)
            ])
        except:
            pass

        # Combinado: admin + fecha (actividad de un admin)
        try:
            monedero_bloqueos_col.create_index([
                ("admin_id", ASCENDING),
                ("created_at", DESCENDING)
            ])
        except:
            pass

        # ============================================================
        # ⭐ DIRECCIONES
        # ============================================================
        try:
            direcciones_col.create_index([("usuario_id", ASCENDING)])
        except:
            pass

        # ============================================================
        # ⭐ RESEÑAS
        # ============================================================
        try:
            resenas_col.create_index([("producto_id", ASCENDING)])
        except:
            pass
        try:
            resenas_col.create_index([("usuario_id", ASCENDING)])
        except:
            pass
        try:
            resenas_col.create_index([("created_at", DESCENDING)])
        except:
            pass

        # ============================================================
        # ⭐ FAVORITOS
        # ============================================================
        try:
            favoritos_col.create_index(
                [("usuario_id", ASCENDING), ("producto_id", ASCENDING)],
                unique=True
            )
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    favoritos_col.drop_index("usuario_id_1_producto_id_1")
                    favoritos_col.create_index(
                        [("usuario_id", ASCENDING), ("producto_id", ASCENDING)],
                        unique=True
                    )
                except:
                    pass
            else:
                print(f"  ⚠️ Favoritos (usuario_id+producto_id): {e}")
        try:
            favoritos_col.create_index([("usuario_id", ASCENDING)])
        except:
            pass
        try:
            favoritos_col.create_index([("producto_id", ASCENDING)])
        except:
            pass
        try:
            favoritos_col.create_index([("created_at", DESCENDING)])
        except:
            pass

        # ============================================================
        # ⭐ MENSAJES DE CONTACTO
        # ============================================================
        try:
            mensajes_contacto_col.create_index([("created_at", DESCENDING)])
        except:
            pass
        try:
            mensajes_contacto_col.create_index([("email", ASCENDING)])
        except:
            pass

        # ============================================================
        # ⭐ NOTIFICACIONES
        # ============================================================
        try:
            notificaciones_col.create_index([("usuario_id", ASCENDING)])
        except:
            pass
        try:
            notificaciones_col.create_index([("leida", ASCENDING)])
        except:
            pass
        try:
            notificaciones_col.create_index([("created_at", DESCENDING)])
        except:
            pass

        # ============================================================
        # ⭐ AUDITORÍA CHAT
        # ============================================================
        try:
            auditoria_chat_col.create_index([("sesion_id", ASCENDING)])
        except:
            pass
        try:
            auditoria_chat_col.create_index([("created_at", DESCENDING)])
        except:
            pass
        try:
            auditoria_chat_col.create_index([("admin_id", ASCENDING)])
        except:
            pass

        # ============================================================
        # ⭐ IMPI CONSULTAS
        # ============================================================
        try:
            impi_consultas_col.create_index([("rfc", ASCENDING)])
        except:
            pass
        try:
            impi_consultas_col.create_index([("marca_id", ASCENDING)])
        except:
            pass
        try:
            impi_consultas_col.create_index([("created_at", DESCENDING)])
        except:
            pass

        # ============================================================
        # ⭐ LEALTAD PUNTOS
        # ============================================================
        try:
            lealtad_puntos_col.create_index([("usuario_id", ASCENDING)])
        except:
            pass
        try:
            lealtad_puntos_col.create_index([("created_at", DESCENDING)])
        except:
            pass

        # ============================================================
        # ⭐ COMPLEXION
        # ============================================================
        try:
            complexion_col.create_index([("usuario_id", ASCENDING)], unique=True)
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    complexion_col.drop_index("usuario_id_1")
                    complexion_col.create_index([("usuario_id", ASCENDING)], unique=True)
                except:
                    pass
            else:
                print(f"  ⚠️ Complexion (usuario_id): {e}")

        # ============================================================
        # ⭐ PREFERENCIAS
        # ============================================================
        try:
            preferencias_col.create_index([("usuario_id", ASCENDING)], unique=True)
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    preferencias_col.drop_index("usuario_id_1")
                    preferencias_col.create_index([("usuario_id", ASCENDING)], unique=True)
                except:
                    pass
            else:
                print(f"  ⚠️ Preferencias (usuario_id): {e}")

        # ============================================================
        # ⭐⭐⭐ METODOS_PAGO ⭐⭐⭐
        # ============================================================
        try:
            metodos_pago_col.create_index([("id", ASCENDING)], unique=True, sparse=True)
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    metodos_pago_col.drop_index("id_1")
                    metodos_pago_col.create_index([("id", ASCENDING)], unique=True, sparse=True)
                except:
                    pass
            else:
                print(f"  ⚠️ metodos_pago (id): {e}")

        try:
            metodos_pago_col.create_index([("usuario_id", ASCENDING)])
        except:
            pass

        try:
            metodos_pago_col.create_index([("usuario_id", ASCENDING), ("predeterminado", ASCENDING)])
        except:
            pass

        try:
            metodos_pago_col.create_index([("conekta_customer_id", ASCENDING)], sparse=True)
        except:
            pass

        # ============================================================
        # ⭐ CARRITO
        # ============================================================
        try:
            carrito_col.create_index([("usuario_id", ASCENDING)])
        except:
            pass

        # ============================================================
        # ⭐ OPINIONES
        # ============================================================
        try:
            opiniones_col.create_index([("producto_id", ASCENDING)])
        except:
            pass
        try:
            opiniones_col.create_index([("usuario_id", ASCENDING)])
        except:
            pass
        try:
            opiniones_col.create_index([("created_at", DESCENDING)])
        except:
            pass

        # ============================================================
        # ⭐⭐⭐ MESAS DE REGALOS ⭐⭐⭐
        # ============================================================
        try:
            mesas_regalos_col.create_index([("slug", ASCENDING)], unique=True)
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    mesas_regalos_col.drop_index("slug_1")
                    mesas_regalos_col.create_index([("slug", ASCENDING)], unique=True)
                except:
                    pass
            else:
                print(f"  ⚠️ Mesas de Regalos (slug): {e}")

        try:
            mesas_regalos_col.create_index([("owner_id", ASCENDING)])
        except:
            pass
        try:
            mesas_regalos_col.create_index([("owner_email", ASCENDING)])
        except:
            pass
        try:
            mesas_regalos_col.create_index([("activa", ASCENDING)])
        except:
            pass
        try:
            mesas_regalos_col.create_index([("created_at", DESCENDING)])
        except:
            pass
        try:
            mesas_regalos_col.create_index([("event_type", ASCENDING)])
        except:
            pass
        try:
            mesas_regalos_col.create_index([("event_date", ASCENDING)])
        except:
            pass
        try:
            mesas_regalos_col.create_index([("owner_id", ASCENDING), ("activa", ASCENDING)])
        except:
            pass

        # ============================================================
        # ⭐⭐⭐ MARKETPLACE — VENDEDORES ⭐⭐⭐
        # ============================================================
        try:
            vendedores_col.create_index([("slug", ASCENDING)], unique=True)
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    vendedores_col.drop_index("slug_1")
                    vendedores_col.create_index([("slug", ASCENDING)], unique=True)
                except:
                    pass
            else:
                print(f"  ⚠️ Vendedores (slug): {e}")

        try:
            vendedores_col.create_index([("user_id", ASCENDING)], unique=True, sparse=True)
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    vendedores_col.drop_index("user_id_1")
                    vendedores_col.create_index([("user_id", ASCENDING)], unique=True, sparse=True)
                except:
                    pass
            else:
                print(f"  ⚠️ Vendedores (user_id): {e}")

        try:
            vendedores_col.create_index([("estado", ASCENDING)])
        except:
            pass

        try:
            vendedores_col.create_index([("activo", ASCENDING)])
        except:
            pass

        try:
            vendedores_col.create_index([("destacado", ASCENDING)])
        except:
            pass

        try:
            vendedores_col.create_index([("categorias", ASCENDING)])
        except:
            pass

        try:
            vendedores_col.create_index([("created_at", DESCENDING)])
        except:
            pass

        try:
            vendedores_col.create_index([("estado", ASCENDING), ("activo", ASCENDING)])
        except:
            pass

        try:
            vendedores_col.create_index([
                ("estado", ASCENDING),
                ("activo", ASCENDING),
                ("destacado", ASCENDING)
            ])
        except:
            pass

        try:
            vendedores_col.create_index([
                ("estado", ASCENDING),
                ("destacado", ASCENDING)
            ])
        except:
            pass

        try:
            vendedores_col.create_index([
                ("estado", ASCENDING),
                ("activo", ASCENDING),
                ("created_at", DESCENDING)
            ])
        except:
            pass

        # ============================================================
        # ⭐⭐⭐ MARKETPLACE — COMISIONES (AUDITORÍA) ⭐⭐⭐
        # ============================================================
        try:
            comisiones_marketplace_col.create_index([("vendedor_id", ASCENDING)])
        except:
            pass

        try:
            comisiones_marketplace_col.create_index([("pedido_id", ASCENDING)], sparse=True)
        except:
            pass

        try:
            comisiones_marketplace_col.create_index([("numero_pedido", ASCENDING)], sparse=True)
        except:
            pass

        try:
            comisiones_marketplace_col.create_index([("estado", ASCENDING)])
        except:
            pass

        try:
            comisiones_marketplace_col.create_index([("created_at", DESCENDING)])
        except:
            pass

        try:
            comisiones_marketplace_col.create_index([
                ("vendedor_id", ASCENDING),
                ("estado", ASCENDING)
            ])
        except:
            pass

        try:
            comisiones_marketplace_col.create_index([
                ("vendedor_id", ASCENDING),
                ("created_at", DESCENDING)
            ])
        except:
            pass

        print("✅ Índices creados correctamente")

    except Exception as e:
        print(f"⚠️ Nota sobre índices: {e}")


# 4. Ejecutar la creación de índices
crear_indices()

# ============================================================
# 5. EXPORTS PARA USAR EN OTROS MÓDULOS
# ============================================================
__all__ = [
    'client', 'db',
    'usuarios_col', 'categorias_col', 'atributos_col', 'productos_col',
    'direcciones_col', 'marcas_col', 'negra_col', 'resenas_col',
    'ventas_col', 'pedidos_col', 'cupones_col', 'cupones_usuarios_col',
    'promociones_col', 'combos_col', 'chats_col', 'temporadas_col',
    'monedero_col',
    # ⭐ NUEVA — configuración del monedero
    'monedero_config_col',
    # ⭐⭐⭐ NUEVA — historial/auditoría de bloqueos
    'monedero_bloqueos_col',
    # ⭐ NUEVAS
    'favoritos_col', 'mensajes_contacto_col', 'configuracion_col',
    'notificaciones_col', 'auditoria_chat_col', 'impi_consultas_col',
    'lealtad_puntos_col', 'complexion_col', 'preferencias_col',
    # ⭐⭐⭐ NUEVAS CRÍTICAS
    'metodos_pago_col', 'carrito_col', 'opiniones_col',
    # ⭐⭐⭐ NUEVA — MESAS DE REGALOS
    'mesas_regalos_col',
    # ⭐⭐⭐ NUEVAS — MARKETPLACE
    'vendedores_col', 'comisiones_marketplace_col',
    'productos_marketplace_col',
    'crear_indices',
]