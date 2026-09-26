# app/config/roles_permisos.py
# Configuración de roles y permisos para el marketplace

ROLES_CONFIG = {
    "super_admin": {
        "nombre": "👑 Super Administrador",
        "descripcion": "Dueño de la plataforma con control total",
        "jerarquia": 100,
        "permisos": {
            "usuarios": ["ver", "crear", "editar", "eliminar", "cambiar_rol", "asignar_sucursal"],
            "sucursales": ["ver", "crear", "editar", "eliminar", "asignar_encargado"],
            "vendedores": ["ver", "aprobar", "suspender", "configurar_comision", "verificar"],
            "productos": ["ver", "crear", "editar", "eliminar", "revisar", "destacar"],
            "pedidos": ["ver", "editar", "cancelar", "reembolsar"],
            "reportes": ["ver", "exportar", "generar"],
            "finanzas": ["ver", "configurar_comisiones", "ver_pagos", "generar_reportes"],
            "configuracion": ["ver", "editar", "ver_logs", "hacer_backup"],
            "chat": ["ver", "responder", "cerrar_sesion"]
        }
    },
    "admin": {
        "nombre": "📊 Administrador General",
        "descripcion": "Supervisa todas las sucursales y vendedores",
        "jerarquia": 80,
        "permisos": {
            "usuarios": ["ver", "crear", "editar", "cambiar_rol"],
            "sucursales": ["ver", "editar", "asignar_encargado"],
            "vendedores": ["ver", "aprobar", "suspender"],
            "productos": ["ver", "editar", "revisar"],
            "pedidos": ["ver", "editar", "reembolsar"],
            "reportes": ["ver", "exportar"],
            "chat": ["ver", "responder", "cerrar_sesion"]
        }
    },
    "admin_sucursal": {
        "nombre": "🏪 Administrador de Sucursal",
        "descripcion": "Gerente de una tienda física específica",
        "jerarquia": 60,
        "permisos": {
            "usuarios": ["ver", "crear_empleado", "editar_empleado"],
            "sucursal": ["ver", "editar"],
            "empleados": ["ver", "crear", "editar", "eliminar"],
            "inventario": ["ver", "editar", "ajustar", "transferir"],
            "productos": ["ver", "editar_stock"],
            "pedidos": ["ver", "procesar", "preparar", "enviar"],
            "reportes": ["ver_sucursal", "exportar_sucursal"],
            "chat": ["ver", "responder"]
        }
    },
    "vendedor": {
        "nombre": "🛍️ Vendedor",
        "descripcion": "Dueño de tienda en el marketplace",
        "jerarquia": 50,
        "permisos": {
            "tienda": ["editar", "configurar", "ver_estadisticas"],
            "productos": ["ver", "crear", "editar", "eliminar", "gestionar_stock"],
            "pedidos": ["ver", "procesar", "enviar", "cancelar"],
            "envios": ["gestionar", "actualizar_guia"],
            "promociones": ["crear", "editar", "eliminar"],
            "reseñas": ["ver", "responder"],
            "reportes": ["ver_tienda", "exportar_tienda"],
            "chat": ["ver", "responder"]
        }
    },
    "empleado": {
        "nombre": "👔 Empleado",
        "descripcion": "Personal operativo de sucursal",
        "jerarquia": 30,
        "permisos": {
            "inventario": ["ver", "editar"],
            "pedidos": ["ver", "procesar", "preparar"],
            "clientes": ["ver", "atender"],
            "caja": ["abrir", "cerrar", "registrar_venta"]
        }
    },
    "cliente": {
        "nombre": "👤 Cliente",
        "descripcion": "Comprador final en la plataforma",
        "jerarquia": 10,
        "permisos": {
            "productos": ["ver", "buscar", "filtrar"],
            "compras": ["realizar", "ver_historial", "ver_detalle"],
            "perfil": ["editar", "ver_direcciones", "editar_direcciones"],
            "reseñas": ["crear", "editar", "eliminar_propias"],
            "favoritos": ["agregar", "eliminar", "ver"],
            "chat": ["iniciar", "enviar"]
        }
    }
}

# Mapeo de permisos para verificación rápida
PERMISOS_FLAT = {
    rol: []
    for rol in ROLES_CONFIG
}

for rol, config in ROLES_CONFIG.items():
    for modulo, permisos in config["permisos"].items():
        for permiso in permisos:
            PERMISOS_FLAT[rol].append(f"{modulo}:{permiso}")

# Decorador para verificar permisos
def verificar_permiso(permiso_requerido):
    """Decorador para verificar permisos en rutas"""
    from functools import wraps
    from flask import session, flash, redirect, url_for
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Inicia sesión para acceder', 'warning')
                return redirect(url_for('web.login'))
            
            from app.models.usuarios_model import Usuario
            usuario = Usuario.obtener_por_id(session['user_id'])
            if not usuario:
                flash('Usuario no encontrado', 'danger')
                return redirect(url_for('web.login'))
            
            rol = usuario.get('rol', 'cliente')
            if rol == 'super_admin':
                return f(*args, **kwargs)
            
            permisos_usuario = PERMISOS_FLAT.get(rol, [])
            if permiso_requerido in permisos_usuario:
                return f(*args, **kwargs)
            
            flash('No tienes permiso para realizar esta acción', 'danger')
            return redirect(url_for('web.dashboard'))
        return decorated_function
    return decorator