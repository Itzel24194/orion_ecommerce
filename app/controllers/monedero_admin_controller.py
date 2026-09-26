# app/controllers/monedero_admin_controller.py
# ================================================================
# CONTROLADOR ADMIN — MONEDERO DIGITAL ORION
# ================================================================

import csv
import io
from flask import (
    render_template, jsonify, request, session,
    redirect, url_for, flash, current_app, make_response
)
from bson import ObjectId
from datetime import datetime

# ⭐ FIX: MonederoAdmin vive en monedero_admin_model, NO en monedero_model
from app.models.monedero_admin_model import MonederoAdmin


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


def _serializar(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serializar(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serializar(v) for v in obj]
    return obj


# ================================================================
# PANEL PRINCIPAL
# ================================================================

def admin_monedero_panel():
    usuario, redir = _verificar_admin()
    if redir:
        return redir

    stats = MonederoAdmin.estadisticas_globales()
    grafico = MonederoAdmin.datos_grafico_movimientos(dias=30)

    return render_template(
        'admin/monedero.html',
        stats=stats,
        grafico=grafico,
    )


# ================================================================
# LISTA DE CLIENTES
# ================================================================

def admin_monedero_clientes():
    usuario, redir = _verificar_admin()
    if redir:
        return redir

    q = (request.args.get('q') or '').strip()
    page = max(1, int(request.args.get('page', 1) or 1))
    per_page = 25
    skip = (page - 1) * per_page

    if q:
        monederos = MonederoAdmin.buscar_por_email_o_nombre(q)
        total = len(monederos)
        monederos = monederos[skip:skip + per_page]
    else:
        monederos = MonederoAdmin.listar_todos(limite=per_page, skip=skip)
        total = MonederoAdmin.contar_todos()

    total_paginas = max(1, (total + per_page - 1) // per_page)
    monederos = _serializar(monederos)

    return render_template(
        'admin/monedero_clientes.html',
        monederos=monederos,
        q=q,
        page=page,
        total=total,
        total_paginas=total_paginas,
    )


# ================================================================
# DETALLE
# ================================================================

def admin_monedero_cliente(usuario_id):
    usuario, redir = _verificar_admin()
    if redir:
        return redir

    detalle = MonederoAdmin.obtener_detalle_admin(usuario_id)
    if not detalle:
        flash('Monedero no encontrado para este usuario', 'danger')
        return redirect(url_for('web.admin_monedero_clientes'))

    detalle = _serializar(detalle)
    return render_template('admin/monedero_cliente.html', detalle=detalle)


# ================================================================
# AJUSTAR SALDO
# ================================================================

def admin_monedero_ajustar(usuario_id):
    admin, redir = _verificar_admin()
    if redir:
        return redir

    data = request.get_json(silent=True) or request.form

    try:
        monto = float(data.get('monto', 0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Monto inválido'}), 400

    if monto == 0:
        return jsonify({'success': False, 'error': 'El monto no puede ser cero'}), 400

    motivo = (data.get('motivo') or '').strip()
    if not motivo:
        return jsonify({'success': False, 'error': 'El motivo es obligatorio'}), 400

    resultado = MonederoAdmin.ajustar_saldo(
        usuario_id=usuario_id,
        monto=monto,
        motivo=motivo,
        admin_id=admin['_id'],
    )

    if not resultado.get('success'):
        return jsonify(resultado), 400

    return jsonify(resultado)


# ================================================================
# BLOQUEAR / DESBLOQUEAR
# ================================================================

def admin_monedero_toggle(usuario_id):
    admin, redir = _verificar_admin()
    if redir:
        return redir

    data = request.get_json(silent=True) or request.form
    accion = (data.get('accion') or '').strip().lower()

    if accion == 'bloquear':
        motivo = (data.get('motivo') or '').strip() or 'Bloqueado por administrador'
        resultado = MonederoAdmin.bloquear(usuario_id, motivo)
    elif accion == 'desbloquear':
        resultado = MonederoAdmin.desbloquear(usuario_id)
    else:
        return jsonify({'success': False, 'error': 'Acción inválida'}), 400

    return jsonify(resultado)


# ================================================================
# CONFIGURACIÓN
# ================================================================

def admin_monedero_config():
    usuario, redir = _verificar_admin()
    if redir:
        return redir

    if request.method == 'POST':
        config = {
            'saldo_maximo': float(request.form.get('saldo_maximo', 50000) or 50000),
            'saldo_minimo_recarga': float(request.form.get('saldo_minimo_recarga', 50) or 50),
            'recarga_maxima': float(request.form.get('recarga_maxima', 20000) or 20000),
            'permitir_transferencias': request.form.get('permitir_transferencias') == 'on',
            'comision_transferencia': float(request.form.get('comision_transferencia', 0) or 0),
            'cashback_porcentaje': float(request.form.get('cashback_porcentaje', 0) or 0),
        }
        MonederoAdmin.guardar_config(config)
        flash('Configuración del monedero guardada', 'success')
        return redirect(url_for('web.admin_monedero_config'))

    config = MonederoAdmin.obtener_config()
    return render_template('admin/monedero_configuracion.html', config=config)


# ================================================================
# API JSON
# ================================================================

def api_admin_monedero_stats():
    usuario, redir = _verificar_admin()
    if redir:
        return jsonify({'success': False, 'error': 'No autorizado'}), 403

    return jsonify({'success': True, 'stats': MonederoAdmin.estadisticas_globales()})


def api_admin_monedero_top():
    usuario, redir = _verificar_admin()
    if redir:
        return jsonify({'success': False, 'error': 'No autorizado'}), 403

    db = current_app.db
    top = list(db.monedero.find({}).sort('saldo', -1).limit(10))

    resultado = []
    for m in top:
        uid = m.get('usuario_id')
        u = None
        try:
            u = db.usuarios.find_one({'_id': ObjectId(str(uid))})
        except Exception:
            pass
        resultado.append({
            'usuario_id': str(uid),
            'nombre': u.get('nombre', 'Sin nombre') if u else 'Sin usuario',
            'email': u.get('email', '') if u else '',
            'saldo': float(m.get('saldo') or 0),
        })

    return jsonify({'success': True, 'top': resultado})


# ================================================================
# API del gráfico (para recargar sin refresh)
# ================================================================

def api_admin_monedero_grafico():
    usuario, redir = _verificar_admin()
    if redir:
        return jsonify({'success': False, 'error': 'No autorizado'}), 403

    dias = int(request.args.get('dias', 30) or 30)
    dias = max(7, min(dias, 90))

    return jsonify({
        'success': True,
        'grafico': MonederoAdmin.datos_grafico_movimientos(dias=dias),
    })


# ================================================================
# EXPORTAR CSV
# ================================================================

def admin_monedero_exportar_csv():
    usuario, redir = _verificar_admin()
    if redir:
        return redir

    filas = MonederoAdmin.exportar_csv()

    # Crear CSV en memoria
    output = io.StringIO()
    # BOM para que Excel abra bien con acentos
    output.write('\ufeff')

    if filas:
        campos = list(filas[0].keys())
        writer = csv.DictWriter(output, fieldnames=campos)
        writer.writeheader()
        writer.writerows(filas)

    csv_data = output.getvalue()
    output.close()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'monedero_orion_{timestamp}.csv'

    response = make_response(csv_data)
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'

    return response