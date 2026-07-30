# app/controllers/clasificacion_controller.py
# Controlador para Clasificación Binaria
# ========================================

from flask import render_template, request, jsonify, session, send_file
from app.services.clasificacion_service import ClasificacionBinariaService
from app.models.usuarios_model import Usuario
import io
import sys
import traceback

def normalizar_rol(rol):
    if not rol:
        return 'cliente'
    rol = rol.lower().strip()
    if rol in ['administrador', 'admin', 'superadmin', 'root']:
        return 'admin'
    return rol

# ================================================================
# VISTA PRINCIPAL
# ================================================================

def clasificacion_binaria_view():
    """Panel de Clasificación Binaria"""
    if 'user_id' not in session:
        return redirect(url_for('web.login'))
    usuario = Usuario.obtener_por_id(session['user_id'])
    if not usuario or normalizar_rol(usuario.get('rol')) != 'admin':
        return redirect(url_for('web.dashboard'))
    return render_template('admin/clasificacion_binaria.html', usuario=usuario)

# ================================================================
# ENDPOINTS API
# ================================================================

def api_entrenar():
    """Entrena el modelo de clasificación binaria."""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403

    # Obtener parámetros de la request (opcional)
    data = request.get_json() or {}
    params = data.get('params')  # dict con grid de hiperparámetros
    solo_clientes = data.get('solo_clientes', True)
    cv_folds = data.get('cv_folds', 5)

    resultado = ClasificacionBinariaService.entrenar(
        params=params,
        solo_clientes=solo_clientes,
        cv_folds=cv_folds
    )
    return jsonify(resultado)

def api_predecir():
    """Predice el riesgo de abandono para todos o un usuario específico."""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403

    usuario_id = request.args.get('usuario_id')
    solo_clientes = request.args.get('solo_clientes', 'true').lower() == 'true'

    resultado = ClasificacionBinariaService.predecir(
        usuario_id=usuario_id,
        solo_clientes=solo_clientes
    )
    return jsonify(resultado)

def api_metricas():
    """Obtiene las métricas guardadas del modelo."""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403

    metricas = ClasificacionBinariaService.obtener_metricas()
    if metricas:
        # Convertir ObjectId a string
        metricas['_id'] = str(metricas['_id'])
        return jsonify({'success': True, 'metricas': metricas})
    return jsonify({'success': False, 'message': 'No hay métricas disponibles'})

def api_exportar():
    """Exporta los resultados de la predicción a CSV."""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403

    csv_data = ClasificacionBinariaService.exportar_resultados()
    if csv_data is None:
        return jsonify({'error': 'No hay datos para exportar'}), 404

    return send_file(
        io.BytesIO(csv_data.encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='riesgo_abandono.csv'
    )