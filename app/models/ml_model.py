# app/controllers/ml_controller.py
# Controlador completo para Machine Learning (estilo Liverpool)
# ================================================================

from flask import render_template, request, redirect, url_for, session, flash, jsonify, current_app
import pandas as pd
import numpy as np
from app.services.ml_service import MLService
from app.models.usuarios_model import Usuario
from datetime import datetime
import sys
import json
import traceback
from sklearn.metrics import confusion_matrix, classification_report


def normalizar_rol(rol):
    """Normaliza el rol para comparación consistente"""
    if not rol:
        return 'cliente'
    rol = rol.lower().strip()
    if rol in ['administrador', 'admin', 'superadmin', 'root']:
        return 'admin'
    return rol


# ================================================================
# 1. PÁGINA PRINCIPAL DE ANÁLISIS SUPERVISADO
# ================================================================

def admin_analisis_supervisado():
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    
    usuario = Usuario.obtener_por_id(session['user_id'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('web.dashboard'))
    
    rol_normalizado = normalizar_rol(usuario.get('rol'))
    if rol_normalizado != 'admin':
        flash('No tienes permisos para acceder a esta sección', 'danger')
        return redirect(url_for('web.dashboard'))
    
    metricas = MLService.get_metricas_modelos()
    modelos_existen = MLService.verificar_modelos()
    umbrales = {
        'activo': MLService.UMBRAL_ABANDONO_BAJO,
        'bajo': MLService.UMBRAL_ABANDONO_MEDIO,
        'medio': MLService.UMBRAL_ABANDONO_ALTO,
        'abandono_confirmado': MLService.UMBRAL_ABANDONO_ENTRENAMIENTO
    }
    return render_template('admin/analisis_supervisado.html',
                         usuario=usuario,
                         metricas=metricas,
                         modelos_existen=modelos_existen,
                         umbrales=umbrales,
                         datetime=datetime)


# ================================================================
# 2. VENTAS
# ================================================================

def admin_entrenar_modelo_ventas():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    resultado = MLService.entrenar_modelo_ventas()
    return jsonify(resultado)

def admin_predecir_ventas():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    dias = request.args.get('dias', 7, type=int)
    dias = max(1, min(dias, 30))
    resultado = MLService.predecir_ventas(dias)
    return jsonify(resultado)


# ================================================================
# 3. ABANDONO
# ================================================================

def admin_entrenar_modelo_abandono():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    resultado = MLService.entrenar_modelo_abandono(force_retrain=True, solo_clientes=True)
    return jsonify(resultado)

def admin_predecir_abandono():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    usuario_id = request.args.get('usuario_id')
    resultado = MLService.predecir_abandono(usuario_id, solo_clientes=True)
    return jsonify(resultado)


# ================================================================
# 4. MÉTRICAS Y MATRIZ
# ================================================================

def admin_diagnosticar_abandono():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    resultado = MLService.diagnosticar_datos_abandono(solo_clientes=True)
    return jsonify(resultado)

def admin_metricas_modelos():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    metricas = MLService.get_metricas_planas()
    return jsonify(metricas)

def admin_matriz_confusion():
    """
    Retorna la matriz de confusión calculada sobre TODOS los clientes (135),
    para que coincida con el reporte de clasificación.
    """
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    try:
        modelo_data = MLService._cargar_modelo(MLService.MODELO_ABANDONO)
        if not modelo_data:
            return jsonify({'error': 'Modelo no encontrado'}), 404
        
        # Obtener todos los datos de clientes
        datos = MLService._obtener_datos_entrenamiento_abandono(solo_clientes=True)
        if len(datos) < 5:
            return jsonify({'error': 'Datos insuficientes'}), 400
        
        df = pd.DataFrame(datos)
        features = ['total_pedidos', 'total_gastado', 'dias_desde_ultima', 'promedio_mensual', 'variabilidad']
        X = df[features].values
        y = df['abandono'].values
        
        scaler = modelo_data['scaler']
        model = modelo_data['modelo']
        
        X_scaled = scaler.transform(X)
        y_pred = model.predict(X_scaled)
        
        # Matriz en orden sklearn: [[TN, FP], [FN, TP]]
        cm = confusion_matrix(y, y_pred).tolist()
        
        return jsonify({
            'success': True,
            'confusion_matrix': cm,
            'labels': ['No Abandona', 'Abandona']
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def admin_reporte_clasificacion():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    try:
        modelo_data = MLService._cargar_modelo(MLService.MODELO_ABANDONO)
        if not modelo_data:
            return jsonify({'error': 'Modelo no encontrado'}), 404
        
        datos = MLService._obtener_datos_entrenamiento_abandono(solo_clientes=True)
        if len(datos) < 5:
            return jsonify({'error': 'Datos insuficientes'}), 400
        
        df = pd.DataFrame(datos)
        features = ['total_pedidos', 'total_gastado', 'dias_desde_ultima', 'promedio_mensual', 'variabilidad']
        X = df[features].values
        y = df['abandono'].values
        
        scaler = modelo_data['scaler']
        model = modelo_data['modelo']
        
        X_scaled = scaler.transform(X)
        y_pred = model.predict(X_scaled)
        
        report = classification_report(y, y_pred, target_names=['No Abandona', 'Abandona'], output_dict=True)
        
        report_serializable = {}
        for key, value in report.items():
            if isinstance(value, dict):
                report_serializable[key] = {k: float(v) if isinstance(v, (int, float)) else v for k, v in value.items()}
            else:
                report_serializable[key] = float(value) if isinstance(value, (int, float)) else value
        
        return jsonify({
            'success': True,
            'reporte': report_serializable
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ================================================================
# 5. GESTIÓN DE MODELOS
# ================================================================

def admin_limpiar_modelos():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    resultado = MLService.limpiar_modelos()
    return jsonify(resultado)

def admin_verificar_modelos():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    resultado = MLService.verificar_modelos()
    return jsonify(resultado)


# ================================================================
# 6. UMBRALES
# ================================================================

def admin_ajustar_umbral():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    data = request.get_json() or {}
    nuevo_umbral_alto = data.get('umbral_alto')
    nuevo_umbral_medio = data.get('umbral_medio')
    nuevo_umbral_bajo = data.get('umbral_bajo')
    
    if nuevo_umbral_alto is not None and nuevo_umbral_alto < 0:
        return jsonify({'error': 'El umbral alto debe ser positivo'}), 400
    if nuevo_umbral_medio is not None and nuevo_umbral_medio < 0:
        return jsonify({'error': 'El umbral medio debe ser positivo'}), 400
    if nuevo_umbral_bajo is not None and nuevo_umbral_bajo < 0:
        return jsonify({'error': 'El umbral bajo debe ser positivo'}), 400
    
    if nuevo_umbral_bajo and nuevo_umbral_medio and nuevo_umbral_bajo >= nuevo_umbral_medio:
        return jsonify({'error': 'El umbral bajo debe ser menor que el medio'}), 400
    if nuevo_umbral_medio and nuevo_umbral_alto and nuevo_umbral_medio >= nuevo_umbral_alto:
        return jsonify({'error': 'El umbral medio debe ser menor que el alto'}), 400
    
    if nuevo_umbral_alto is not None:
        MLService.UMBRAL_ABANDONO_ALTO = nuevo_umbral_alto
        MLService.UMBRAL_ABANDONO_ENTRENAMIENTO = nuevo_umbral_alto
    if nuevo_umbral_medio is not None:
        MLService.UMBRAL_ABANDONO_MEDIO = nuevo_umbral_medio
    if nuevo_umbral_bajo is not None:
        MLService.UMBRAL_ABANDONO_BAJO = nuevo_umbral_bajo
    
    resultado = MLService.entrenar_modelo_abandono(force_retrain=True, solo_clientes=True)
    return jsonify(resultado)

def admin_get_umbrales():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    return jsonify({
        'success': True,
        'umbrales': {
            'activo': MLService.UMBRAL_ABANDONO_BAJO,
            'bajo': MLService.UMBRAL_ABANDONO_MEDIO,
            'medio': MLService.UMBRAL_ABANDONO_ALTO,
            'abandono_confirmado': MLService.UMBRAL_ABANDONO_ENTRENAMIENTO
        },
        'descripcion': {
            'activo': f"< {MLService.UMBRAL_ABANDONO_BAJO} días",
            'bajo': f"{MLService.UMBRAL_ABANDONO_BAJO}-{MLService.UMBRAL_ABANDONO_MEDIO-1} días",
            'medio': f"{MLService.UMBRAL_ABANDONO_MEDIO}-{MLService.UMBRAL_ABANDONO_ALTO-1} días",
            'alto': f"{MLService.UMBRAL_ABANDONO_ALTO}+ días"
        }
    })


# ================================================================
# 7. DASHBOARD
# ================================================================

def admin_dashboard_ml():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    respuesta = {
        'success': True,
        'modelos': {
            'ventas': {'existe': False, 'metricas': {}},
            'abandono': {'existe': False, 'metricas': {}}
        },
        'umbrales': {
            'activo': MLService.UMBRAL_ABANDONO_BAJO,
            'bajo': MLService.UMBRAL_ABANDONO_MEDIO,
            'medio': MLService.UMBRAL_ABANDONO_ALTO
        },
        'timestamp': datetime.now().isoformat()
    }
    
    ventas_data = MLService._cargar_modelo(MLService.MODELO_VENTAS)
    if ventas_data:
        respuesta['modelos']['ventas']['existe'] = True
        respuesta['modelos']['ventas']['metricas'] = {
            'mae': ventas_data.get('mae'),
            'rmse': ventas_data.get('rmse'),
            'r2': ventas_data.get('r2'),
            'n_muestras': ventas_data.get('n_muestras'),
            'fecha_entrenamiento': ventas_data.get('fecha_entrenamiento')
        }
    
    abandono_data = MLService._cargar_modelo(MLService.MODELO_ABANDONO)
    if abandono_data:
        respuesta['modelos']['abandono']['existe'] = True
        respuesta['modelos']['abandono']['metricas'] = {
            'accuracy': abandono_data.get('accuracy'),
            'n_muestras': abandono_data.get('n_muestras'),
            'fecha_entrenamiento': abandono_data.get('fecha_entrenamiento'),
            'umbrales': abandono_data.get('umbrales')
        }
    
    return jsonify(respuesta)


# ================================================================
# 8. IMPORTANCIA
# ================================================================

def admin_importancia_caracteristicas():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    modelo_data = MLService._cargar_modelo(MLService.MODELO_ABANDONO)
    if not modelo_data:
        return jsonify({'success': False, 'message': 'Modelo no encontrado'}), 404
    importancia = modelo_data.get('importancia', {})
    return jsonify({'success': True, 'importancia': importancia})


# ================================================================
# 9. SEGMENTACIÓN
# ================================================================

def admin_entrenar_modelo_segmentacion():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    n_clusters = request.args.get('n_clusters', 4, type=int)
    n_clusters = max(2, min(n_clusters, 10))
    resultado = MLService.entrenar_modelo_segmentacion(force_retrain=True, n_clusters=n_clusters)
    return jsonify(resultado)

def admin_obtener_metricas_segmentacion():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    metricas = MLService.obtener_metricas_segmentacion()
    if not metricas:
        return jsonify({'success': False, 'message': 'Modelo de segmentación no entrenado'}), 404
    metricas['_id'] = str(metricas.get('_id'))
    return jsonify({'success': True, 'metricas': metricas})

def admin_obtener_cluster_stats():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    usuario = Usuario.obtener_por_id(session['user_id'])
    if normalizar_rol(usuario.get('rol')) != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    cluster_stats = MLService.obtener_cluster_stats()
    if not cluster_stats:
        return jsonify({'success': False, 'message': 'Modelo de segmentación no entrenado o sin estadísticas'}), 404
    return jsonify({'success': True, 'cluster_stats': cluster_stats})