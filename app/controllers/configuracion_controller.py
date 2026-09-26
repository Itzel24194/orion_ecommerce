# app/controllers/configuracion_controller.py
# ================================================================
# CONTROLADOR DE CONFIGURACIÓN DEL SISTEMA (ADMIN)
# ================================================================

from flask import render_template, request, redirect, url_for, session, current_app, flash
from bson import ObjectId
from app.models.configuracion_model import Configuracion


# ================================================================
# HELPERS
# ================================================================

def _normalizar_rol(rol):
    if not rol:
        return 'cliente'
    rol = rol.lower().strip()
    if rol in ['administrador', 'admin', 'superadmin', 'root']:
        return 'admin'
    return rol


def _verificar_admin():
    """Devuelve (usuario, redireccion) — redireccion es None si todo ok."""
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return None, redirect(url_for('web.login'))

    db = current_app.db
    try:
        usuario = db.usuarios.find_one({'_id': ObjectId(session['user_id'])})
    except Exception:
        usuario = None

    if not usuario or _normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return None, redirect(url_for('web.raiz_tienda'))

    return usuario, None


def _to_float(valor, default=0.0):
    try:
        if valor is None or valor == '':
            return default
        return float(valor)
    except (ValueError, TypeError):
        return default


def _to_int(valor, default=0):
    try:
        if valor is None or valor == '':
            return default
        return int(valor)
    except (ValueError, TypeError):
        return default


# ================================================================
# CONFIGURACIÓN GENERAL
# ================================================================

def configuracion():
    usuario, redir = _verificar_admin()
    if redir:
        return redir

    if request.method == 'POST':
        Configuracion.guardar_general({
            'nombre_tienda':    request.form.get('nombre_tienda', '').strip(),
            'email_tienda':     request.form.get('email_tienda', '').strip(),
            'telefono_tienda':  request.form.get('telefono_tienda', '').strip(),
            'direccion_tienda': request.form.get('direccion_tienda', '').strip(),
            'moneda':           request.form.get('moneda', 'MXN'),
        })
        flash('Configuración guardada correctamente', 'success')
        return redirect(url_for('web.configuracion'))

    return render_template('admin/configuracion.html',
                           config=Configuracion.obtener_general())


# ================================================================
# ENVÍOS
# ================================================================

def configuracion_envios():
    usuario, redir = _verificar_admin()
    if redir:
        return redir

    if request.method == 'POST':
        marcas_raw = request.form.get('marcas_envio', '') or ''
        marcas = [m.strip() for m in marcas_raw.split(',') if m.strip()]

        Configuracion.guardar_envios({
            'costo_envio':              _to_float(request.form.get('costo_envio'), 0.0),
            'costo_envio_gratis_sobre': _to_float(request.form.get('costo_envio_gratis_sobre'), 0.0),
            'tiempo_entrega_dias':      _to_int(request.form.get('tiempo_entrega_dias'), 5),
            'marcas_envio':             marcas,
        })
        flash('Configuración de envíos guardada', 'success')
        return redirect(url_for('web.configuracion_envios'))

    return render_template('admin/configuracion_envios.html',
                           config=Configuracion.obtener_envios())


# ================================================================
# PAGOS
# ================================================================

def configuracion_pagos():
    usuario, redir = _verificar_admin()
    if redir:
        return redir

    if request.method == 'POST':
        Configuracion.guardar_pagos({
            'metodos_pago':     request.form.getlist('metodos_pago'),
            'moneda':           request.form.get('moneda', 'MXN'),
            'iva_porcentaje':   _to_float(request.form.get('iva_porcentaje'), 16.0),
            'stripe_key':       request.form.get('stripe_key', ''),
            'paypal_client_id': request.form.get('paypal_client_id', ''),
            'paypal_secret':    request.form.get('paypal_secret', ''),
        })
        flash('Configuración de pagos guardada', 'success')
        return redirect(url_for('web.configuracion_pagos'))

    return render_template('admin/configuracion_pagos.html',
                           config=Configuracion.obtener_pagos())


# ================================================================
# IMPUESTOS
# ================================================================

def configuracion_impuestos():
    usuario, redir = _verificar_admin()
    if redir:
        return redir

    if request.method == 'POST':
        Configuracion.guardar_impuestos({
            'iva_porcentaje':  _to_float(request.form.get('iva_porcentaje'), 16.0),
            'ieps_porcentaje': _to_float(request.form.get('ieps_porcentaje'), 0.0),
            'retencion_isr':   _to_float(request.form.get('retencion_isr'), 0.0),
        })
        flash('Configuración de impuestos guardada', 'success')
        return redirect(url_for('web.configuracion_impuestos'))

    return render_template('admin/configuracion_impuestos.html',
                           config=Configuracion.obtener_impuestos())


# ================================================================
# TIENDAS
# ================================================================

def configuracion_tiendas():
    usuario, redir = _verificar_admin()
    if redir:
        return redir

    if request.method == 'POST':
        tiendas = []
        nombres     = request.form.getlist('tienda_nombre[]')
        direcciones = request.form.getlist('tienda_direccion[]')
        telefonos   = request.form.getlist('tienda_telefono[]')

        for i in range(len(nombres)):
            if nombres[i] and nombres[i].strip():
                tiendas.append({
                    'nombre':    nombres[i].strip(),
                    'direccion': direcciones[i].strip() if i < len(direcciones) else '',
                    'telefono':  telefonos[i].strip()   if i < len(telefonos)   else '',
                    'activa':    True,
                })

        Configuracion.guardar_tiendas(tiendas)
        flash('Configuración de tiendas guardada', 'success')
        return redirect(url_for('web.configuracion_tiendas'))

    return render_template('admin/configuracion_tiendas.html',
                           tiendas=Configuracion.obtener_tiendas())


# ================================================================
# MIGRACIONES
# ================================================================

def migraciones():
    usuario, redir = _verificar_admin()
    if redir:
        return redir

    if request.method == 'POST':
        # Aquí puedes ejecutar tus migraciones reales
        # Ejemplo:
        # from app.migrations import ejecutar_todas
        # ejecutar_todas(current_app.db)
        flash('Migraciones ejecutadas correctamente', 'success')
        return redirect(url_for('web.migraciones'))

    return render_template('admin/migraciones.html')