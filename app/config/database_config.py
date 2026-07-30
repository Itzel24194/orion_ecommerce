from pymongo import MongoClient, ASCENDING

# 1. Conexión
client = MongoClient("mongodb://localhost:27017/")
db = client["orioon"]

# 2. Definición de colecciones
usuarios_col = db["usuarios"]
categorias_col = db["categorias"]
atributos_col = db['atributos']
productos_col = db['productos']
direcciones_col = db['direcciones']
empresas_col = db['empresas']
negra_col = db['lista_negra']
resenas_col = db['resenas']
ventas_col = db['ventas']
pedidos_col = db["pedidos"]
cupones_col = db["cupones"]
cupones_usuarios_col = db["cupones_usuarios"]
promociones_col = db["promociones"]
combos_col = db["combos"]  # <--- NUEVA COLECCIÓN

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
            pedidos_col.create_index([("created_at", ASCENDING)])
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
        
        # --- Empresas ---
        try:
            empresas_col.create_index([("nombre", ASCENDING)], unique=True)
        except Exception as e:
            if "duplicate key error" in str(e) or "Index already exists" in str(e):
                try:
                    empresas_col.drop_index("nombre_1")
                    empresas_col.create_index([("nombre", ASCENDING)], unique=True)
                except:
                    pass
            else:
                print(f"  ⚠️ Empresas (nombre): {e}")
        
        try:
            empresas_col.create_index([("estado", ASCENDING)])
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

        # --- COMBOS (NUEVO) ---
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

        print("✅ Índices creados correctamente")
        
    except Exception as e:
        print(f"⚠️ Nota sobre índices: {e}")

# 4. Ejecutar la creación de índices
crear_indices()