# app/services/clasificacion_service.py
# Servicio de Clasificación Binaria (Abandono de clientes)
# ============================================================

from flask import current_app
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix, classification_report,
    log_loss, matthews_corrcoef
)
import joblib
import os
import json
import logging
import sys
import traceback

logger = logging.getLogger(__name__)

def normalizar_rol(rol):
    if not rol:
        return 'cliente'
    rol = rol.lower().strip()
    if rol in ['administrador', 'admin', 'superadmin', 'root']:
        return 'admin'
    return rol

class ClasificacionBinariaService:
    """
    Servicio especializado en clasificación binaria (abandono de clientes)
    utilizando Random Forest con optimización de hiperparámetros.
    """

    MODELO_DIR = 'models'
    NOMBRE_MODELO = 'clasificacion_binaria_rf.pkl'
    NOMBRE_SCALER = 'clasificacion_binaria_scaler.pkl'

    # Umbrales de riesgo (días sin comprar)
    UMBRAL_ALTO = 60
    UMBRAL_MEDIO = 30
    UMBRAL_BAJO = 15
    UMBRAL_ABANDONO = 60   # para etiquetar abandono

    @classmethod
    def _get_model_path(cls, nombre):
        return os.path.join(current_app.root_path, cls.MODELO_DIR, nombre)

    @classmethod
    def _guardar_modelo(cls, modelo, scaler):
        try:
            os.makedirs(cls._get_model_path(''), exist_ok=True)
            joblib.dump(modelo, cls._get_model_path(cls.NOMBRE_MODELO))
            joblib.dump(scaler, cls._get_model_path(cls.NOMBRE_SCALER))
            logger.info("Modelo y escalador guardados correctamente.")
            return True
        except Exception as e:
            logger.error(f"Error guardando modelo: {str(e)}")
            return False

    @classmethod
    def _cargar_modelo(cls):
        try:
            modelo = joblib.load(cls._get_model_path(cls.NOMBRE_MODELO))
            scaler = joblib.load(cls._get_model_path(cls.NOMBRE_SCALER))
            return modelo, scaler
        except Exception as e:
            logger.warning(f"Error cargando modelo: {str(e)}")
            return None, None

    @classmethod
    def _obtener_datos_entrenamiento(cls, solo_clientes=True):
        """Obtiene datos de usuarios y pedidos para entrenamiento."""
        db = current_app.db
        usuarios = list(db.usuarios.find({}))
        if solo_clientes:
            usuarios = [u for u in usuarios if normalizar_rol(u.get('rol', 'cliente')) == 'cliente']

        datos = []
        fecha_ref = datetime.now()

        for usuario in usuarios:
            user_id = usuario.get('_id')
            pedidos = list(db.pedidos.find({
                'usuario_id': str(user_id),
                'estado': {'$in': ['pagado', 'entregado', 'completado', 'confirmado']}
            }).sort('created_at', -1))

            total_pedidos = len(pedidos)
            total_gastado = float(sum(p.get('total', 0) for p in pedidos)) if pedidos else 0.0

            if pedidos:
                ultima_compra = pedidos[0].get('created_at')
                dias_desde_ultima = (fecha_ref - ultima_compra).days if ultima_compra else 999
                meses_activos = len(set(p.get('created_at').strftime('%Y-%m') for p in pedidos if p.get('created_at')))
                promedio_mensual = total_pedidos / max(meses_activos, 1)
                montos = [float(p.get('total', 0)) for p in pedidos]
                variabilidad = float(np.std(montos)) if len(montos) > 1 else 0.0
            else:
                dias_desde_ultima = 999
                promedio_mensual = 0.0
                variabilidad = 0.0

            # Etiqueta de abandono (1 si supera el umbral)
            abandono = 1 if dias_desde_ultima > cls.UMBRAL_ABANDONO else 0

            datos.append({
                'total_pedidos': total_pedidos,
                'total_gastado': total_gastado,
                'dias_desde_ultima': dias_desde_ultima,
                'promedio_mensual': promedio_mensual,
                'variabilidad': variabilidad,
                'abandono': abandono,
                'usuario_id': str(user_id),
                'nombre': usuario.get('nombre', '') + ' ' + (usuario.get('apellido_paterno', '') or ''),
                'email': usuario.get('email', '')
            })

        return datos

    @classmethod
    def entrenar(cls, params=None, solo_clientes=True, cv_folds=5):
        """
        Entrena el modelo de clasificación binaria con GridSearchCV.

        Args:
            params (dict): Diccionario con hiperparámetros a probar.
                           Ej: {'n_estimators': [50, 100, 200], 'max_depth': [5, 10, None]}
            solo_clientes (bool): Si solo incluir clientes (excluye admins).
            cv_folds (int): Número de folds para validación cruzada.

        Returns:
            dict: Resultados del entrenamiento.
        """
        try:
            db = current_app.db
            logger.info("Iniciando entrenamiento de clasificación binaria...")

            # Obtener datos
            datos = cls._obtener_datos_entrenamiento(solo_clientes=solo_clientes)
            if len(datos) < 10:
                return {'success': False, 'message': 'Se necesitan al menos 10 clientes.'}

            df = pd.DataFrame(datos)
            features = ['total_pedidos', 'total_gastado', 'dias_desde_ultima', 'promedio_mensual', 'variabilidad']
            X = df[features].values
            y = df['abandono'].values

            # Escalado
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            # Dividir en entrenamiento y prueba
            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=0.2, random_state=42, stratify=y
            )

            # Grid de hiperparámetros (por defecto)
            if params is None:
                param_grid = {
                    'n_estimators': [50, 100, 200],
                    'max_depth': [5, 10, None],
                    'min_samples_split': [2, 5, 10],
                    'class_weight': ['balanced', None]
                }
            else:
                param_grid = params

            # Modelo base
            base_model = RandomForestClassifier(random_state=42, n_jobs=-1)

            # GridSearchCV con validación cruzada
            grid_search = GridSearchCV(
                estimator=base_model,
                param_grid=param_grid,
                cv=cv_folds,
                scoring='roc_auc',
                n_jobs=-1,
                verbose=1
            )
            grid_search.fit(X_train, y_train)

            # Mejor modelo
            best_model = grid_search.best_estimator_

            # Evaluación en test
            y_pred = best_model.predict(X_test)
            y_proba = best_model.predict_proba(X_test)[:, 1]

            # Métricas
            accuracy = float(accuracy_score(y_test, y_pred))
            precision = float(precision_score(y_test, y_pred, zero_division=0))
            recall = float(recall_score(y_test, y_pred, zero_division=0))
            f1 = float(f1_score(y_test, y_pred, zero_division=0))
            auc = float(roc_auc_score(y_test, y_proba))
            logloss = float(log_loss(y_test, y_proba))
            mcc = float(matthews_corrcoef(y_test, y_pred))

            # Validación cruzada en todo el conjunto (opcional)
            cv_scores = cross_val_score(best_model, X_scaled, y, cv=cv_folds, scoring='roc_auc')
            cv_mean = float(cv_scores.mean())
            cv_std = float(cv_scores.std())

            # Matriz de confusión y reporte
            cm = confusion_matrix(y_test, y_pred).tolist()
            report = classification_report(y_test, y_pred, target_names=['No Abandona', 'Abandona'], output_dict=True)

            # Importancia de características
            importancia = {k: float(v) for k, v in zip(features, best_model.feature_importances_.tolist())}

            # Guardar modelo y escalador
            cls._guardar_modelo(best_model, scaler)

            # Guardar métricas en BD
            db.modelos_ml.update_one(
                {'nombre': 'clasificacion_binaria'},
                {'$set': {
                    'nombre': 'clasificacion_binaria',
                    'accuracy': accuracy,
                    'precision': precision,
                    'recall': recall,
                    'f1': f1,
                    'auc': auc,
                    'logloss': logloss,
                    'mcc': mcc,
                    'cv_mean': cv_mean,
                    'cv_std': cv_std,
                    'matriz_confusion': cm,
                    'reporte_clasificacion': report,
                    'importancia': importancia,
                    'mejores_parametros': grid_search.best_params_,
                    'n_muestras': len(datos),
                    'fecha_actualizacion': datetime.now(),
                    'umbrales': {
                        'activo': cls.UMBRAL_BAJO,
                        'bajo': cls.UMBRAL_MEDIO,
                        'medio': cls.UMBRAL_ALTO,
                        'abandono': cls.UMBRAL_ABANDONO
                    },
                    'solo_clientes': solo_clientes
                }},
                upsert=True
            )

            resultado = {
                'success': True,
                'message': 'Modelo entrenado correctamente.',
                'accuracy': accuracy,
                'precision': precision,
                'recall': recall,
                'f1': f1,
                'auc': auc,
                'logloss': logloss,
                'mcc': mcc,
                'cv_mean': cv_mean,
                'cv_std': cv_std,
                'matriz_confusion': cm,
                'reporte': report,
                'importancia': importancia,
                'mejores_parametros': grid_search.best_params_,
                'n_muestras': len(datos)
            }
            logger.info("Entrenamiento completado exitosamente.")
            return resultado

        except Exception as e:
            logger.error(f"Error en entrenamiento: {str(e)}")
            traceback.print_exc()
            return {'success': False, 'message': f'Error: {str(e)}'}

    @classmethod
    def predecir(cls, usuario_id=None, solo_clientes=True):
        """
        Predice el riesgo de abandono para todos los clientes o uno específico.

        Args:
            usuario_id (str): ID de usuario (opcional). Si se omite, predice para todos.
            solo_clientes (bool): Si solo clientes.

        Returns:
            dict: Resultados de predicción.
        """
        try:
            modelo, scaler = cls._cargar_modelo()
            if modelo is None:
                return {'success': False, 'message': 'Modelo no entrenado. Ejecuta entrenamiento primero.'}

            db = current_app.db
            features = ['total_pedidos', 'total_gastado', 'dias_desde_ultima', 'promedio_mensual', 'variabilidad']

            def obtener_caracteristicas(user_id):
                pedidos = list(db.pedidos.find({
                    'usuario_id': str(user_id),
                    'estado': {'$in': ['pagado', 'entregado', 'completado', 'confirmado']}
                }))
                if not pedidos:
                    return {
                        'total_pedidos': 0,
                        'total_gastado': 0.0,
                        'dias_desde_ultima': 999,
                        'promedio_mensual': 0.0,
                        'variabilidad': 0.0,
                        'sin_pedidos': True
                    }
                total_pedidos = len(pedidos)
                total_gastado = float(sum(p.get('total', 0) for p in pedidos))
                ultima_compra = pedidos[0].get('created_at')
                dias_desde_ultima = (datetime.now() - ultima_compra).days if ultima_compra else 999
                meses_activos = len(set(p.get('created_at').strftime('%Y-%m') for p in pedidos if p.get('created_at')))
                promedio_mensual = total_pedidos / max(meses_activos, 1)
                montos = [float(p.get('total', 0)) for p in pedidos]
                variabilidad = float(np.std(montos)) if len(montos) > 1 else 0.0
                return {
                    'total_pedidos': total_pedidos,
                    'total_gastado': total_gastado,
                    'dias_desde_ultima': dias_desde_ultima,
                    'promedio_mensual': promedio_mensual,
                    'variabilidad': variabilidad,
                    'sin_pedidos': False
                }

            # Si se pide un usuario específico
            if usuario_id:
                usuario = db.usuarios.find_one({'_id': usuario_id})
                if not usuario:
                    return {'success': False, 'message': 'Usuario no encontrado.'}
                if solo_clientes and normalizar_rol(usuario.get('rol', 'cliente')) != 'cliente':
                    return {'success': False, 'message': 'El usuario no es cliente.'}

                datos = obtener_caracteristicas(usuario_id)
                if datos.get('sin_pedidos', False):
                    return {
                        'success': True,
                        'riesgo': 0.95,
                        'nivel': 'Alto',
                        'mensaje': 'Sin historial de compras',
                        'total_pedidos': 0,
                        'dias_sin_comprar': 999
                    }
                X_pred = np.array([[
                    datos['total_pedidos'],
                    datos['total_gastado'],
                    datos['dias_desde_ultima'],
                    datos['promedio_mensual'],
                    datos['variabilidad']
                ]])
                X_pred_scaled = scaler.transform(X_pred)
                proba = modelo.predict_proba(X_pred_scaled)[0][1]
                riesgo = float(proba)
                nivel = cls._get_nivel_riesgo(riesgo)
                return {
                    'success': True,
                    'riesgo': round(riesgo, 3),
                    'nivel': nivel,
                    'total_pedidos': datos['total_pedidos'],
                    'dias_sin_comprar': datos['dias_desde_ultima']
                }

            # Todos los clientes
            usuarios = list(db.usuarios.find({}))
            if solo_clientes:
                usuarios = [u for u in usuarios if normalizar_rol(u.get('rol', 'cliente')) == 'cliente']

            resultados = []
            for usuario in usuarios:
                user_id = usuario.get('_id')
                datos = obtener_caracteristicas(user_id)
                if datos.get('sin_pedidos', False):
                    resultados.append({
                        'usuario_id': str(user_id),
                        'nombre': usuario.get('nombre', '') + ' ' + (usuario.get('apellido_paterno', '') or ''),
                        'email': usuario.get('email', ''),
                        'riesgo': 0.95,
                        'nivel': 'Alto',
                        'dias_sin_comprar': 999,
                        'total_pedidos': 0
                    })
                    continue

                X_pred = np.array([[
                    datos['total_pedidos'],
                    datos['total_gastado'],
                    datos['dias_desde_ultima'],
                    datos['promedio_mensual'],
                    datos['variabilidad']
                ]])
                X_pred_scaled = scaler.transform(X_pred)
                proba = modelo.predict_proba(X_pred_scaled)[0][1]
                riesgo = float(proba)
                nivel = cls._get_nivel_riesgo(riesgo)
                resultados.append({
                    'usuario_id': str(user_id),
                    'nombre': usuario.get('nombre', '') + ' ' + (usuario.get('apellido_paterno', '') or ''),
                    'email': usuario.get('email', ''),
                    'riesgo': round(riesgo, 3),
                    'nivel': nivel,
                    'dias_sin_comprar': datos['dias_desde_ultima'],
                    'total_pedidos': datos['total_pedidos']
                })

            resultados.sort(key=lambda x: x['riesgo'], reverse=True)
            return {
                'success': True,
                'total_analizados': len(resultados),
                'clientes': resultados,
                'umbrales': {
                    'activo': f"< {cls.UMBRAL_BAJO} días",
                    'bajo': f"{cls.UMBRAL_BAJO}-{cls.UMBRAL_MEDIO-1} días",
                    'medio': f"{cls.UMBRAL_MEDIO}-{cls.UMBRAL_ALTO-1} días",
                    'alto': f"{cls.UMBRAL_ALTO}+ días"
                }
            }

        except Exception as e:
            logger.error(f"Error en predicción: {str(e)}")
            traceback.print_exc()
            return {'success': False, 'message': f'Error: {str(e)}'}

    @classmethod
    def _get_nivel_riesgo(cls, riesgo):
        if riesgo >= 0.7:
            return 'Alto'
        elif riesgo >= 0.4:
            return 'Medio'
        else:
            return 'Bajo'

    @classmethod
    def obtener_metricas(cls):
        """Obtiene las métricas guardadas en la base de datos."""
        db = current_app.db
        return db.modelos_ml.find_one({'nombre': 'clasificacion_binaria'})

    @classmethod
    def exportar_resultados(cls):
        """Exporta los resultados de la última predicción a CSV."""
        # Primero predecimos para todos
        resultado = cls.predecir(solo_clientes=True)
        if not resultado['success']:
            return None
        clientes = resultado.get('clientes', [])
        if not clientes:
            return None
        df = pd.DataFrame(clientes)
        return df.to_csv(index=False)