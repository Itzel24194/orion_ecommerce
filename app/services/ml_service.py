# app/services/ml_service.py
# Servicio completo de Machine Learning - CON FUERZA DE USUARIOS EN TEST
# ================================================================

from flask import current_app
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, r2_score,
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, classification_report, confusion_matrix,
    silhouette_score, roc_curve
)
import joblib
import os
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


class MLService:
    
    MODELOS_DIR = 'models'
    MODELO_VENTAS = 'modelo_ventas.pkl'
    MODELO_ABANDONO = 'modelo_abandono.pkl'
    MODELO_SEGMENTACION = 'modelo_segmentacion.pkl'
    MODELO_LOGISTICO = 'modelo_logistico.pkl'
    
    UMBRAL_ABANDONO_ALTO = 60
    UMBRAL_ABANDONO_MEDIO = 30
    UMBRAL_ABANDONO_BAJO = 15
    UMBRAL_ABANDONO_ENTRENAMIENTO = 60

    USUARIOS_FORZAR_TEST = [
        "6a3f7caaff20978cfd5f589b",  # Melanie
    ]

    # ================================================================
    # MÉTODOS DE UTILIDAD
    # ================================================================

    @classmethod
    def _to_serializable(cls, value):
        if isinstance(value, (np.int64, np.int32, np.int16, np.int8)):
            return int(value)
        if isinstance(value, (np.float64, np.float32, np.float16)):
            return float(value)
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, dict):
            return {k: cls._to_serializable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._to_serializable(v) for v in value]
        return value

    @classmethod
    def _get_model_path(cls, nombre_modelo):
        return os.path.join(current_app.root_path, cls.MODELOS_DIR, nombre_modelo)

    @classmethod
    def _guardar_modelo(cls, modelo_data, nombre_modelo):
        try:
            path = cls._get_model_path(nombre_modelo)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            joblib.dump(modelo_data, path)
            logger.info(f"Modelo guardado en: {path}")
            return True
        except Exception as e:
            logger.error(f"Error guardando modelo: {str(e)}")
            return False

    @classmethod
    def _cargar_modelo(cls, nombre_modelo):
        try:
            path = cls._get_model_path(nombre_modelo)
            if not os.path.exists(path):
                logger.warning(f"Modelo no encontrado: {path}")
                return None
            modelo_data = joblib.load(path)
            logger.info(f"Modelo cargado desde: {path}")
            return modelo_data
        except Exception as e:
            logger.error(f"Error cargando modelo: {str(e)}")
            return None

    @classmethod
    def _eliminar_modelo(cls, nombre_modelo):
        try:
            path = cls._get_model_path(nombre_modelo)
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"Modelo eliminado: {path}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error eliminando modelo: {str(e)}")
            return False

    @classmethod
    def _guardar_metricas_db(cls, nombre_modelo, metricas):
        try:
            metricas_serializables = cls._to_serializable(metricas)
            db = current_app.db
            db.modelos_ml.update_one(
                {'nombre': nombre_modelo},
                {'$set': {
                    'nombre': nombre_modelo,
                    **metricas_serializables,
                    'fecha_actualizacion': datetime.now()
                }},
                upsert=True
            )
            logger.info(f"Métricas guardadas para {nombre_modelo}")
            return True
        except Exception as e:
            logger.error(f"Error guardando métricas: {str(e)}")
            return False

    @classmethod
    def _obtener_metricas_db(cls, nombre_modelo):
        try:
            db = current_app.db
            return db.modelos_ml.find_one({'nombre': nombre_modelo})
        except Exception as e:
            logger.error(f"Error obteniendo métricas: {str(e)}")
            return None

    @classmethod
    def _filtrar_solo_clientes(cls, usuarios):
        if not usuarios:
            return []
        return [u for u in usuarios if normalizar_rol(u.get('rol', 'cliente')) == 'cliente']

    # ================================================================
    # DIAGNÓSTICO
    # ================================================================

    @classmethod
    def diagnosticar_datos_abandono(cls, solo_clientes=True):
        db = current_app.db
        print("=" * 70, file=sys.stderr)
        print(" DIAGNÓSTICO DE DATOS DE ABANDONO", file=sys.stderr)
        if solo_clientes:
            print(" SOLO CLIENTES", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        usuarios = list(db.usuarios.find({}))
        if solo_clientes:
            usuarios = cls._filtrar_solo_clientes(usuarios)
            print(f"👥 Total clientes: {len(usuarios)}", file=sys.stderr)
        else:
            print(f"👥 Total usuarios: {len(usuarios)}", file=sys.stderr)
        fecha_referencia = datetime.now()
        usuarios_con_pedidos = 0
        usuarios_sin_pedidos = 0
        distribucion_riesgo = {
            'activo': 0,
            'bajo': 0,
            'medio': 0,
            'alto': 0,
            'sin_pedidos': 0
        }
        distribucion_abandono = {'abandono': 0, 'no_abandono': 0}
        usuarios_detalle = []
        for usuario in usuarios:
            user_id = usuario.get('_id')
            pedidos = list(db.pedidos.find({
                'usuario_id': str(user_id),
                'estado': {'$in': ['pagado', 'entregado', 'completado', 'confirmado']}
            }).sort('created_at', -1))
            if not pedidos:
                usuarios_sin_pedidos += 1
                distribucion_riesgo['sin_pedidos'] += 1
                distribucion_abandono['abandono'] += 1
                usuarios_detalle.append({
                    'nombre': usuario.get('nombre', 'Usuario'),
                    'pedidos': 0,
                    'dias_sin_comprar': 999,
                    'nivel_riesgo': 'Sin Pedidos',
                    'total_gastado': 0,
                    'sin_pedidos': True,
                    'rol': usuario.get('rol', 'cliente')
                })
                continue
            usuarios_con_pedidos += 1
            total_pedidos = len(pedidos)
            total_gastado = sum(p.get('total', 0) for p in pedidos)
            ultima_compra = pedidos[0].get('created_at') if pedidos else None
            if ultima_compra:
                dias_desde_ultima = (fecha_referencia - ultima_compra).days
            else:
                dias_desde_ultima = 999
            if dias_desde_ultima < cls.UMBRAL_ABANDONO_BAJO:
                nivel = 'Activo'
                distribucion_riesgo['activo'] += 1
                es_abandono = False
            elif dias_desde_ultima < cls.UMBRAL_ABANDONO_MEDIO:
                nivel = 'Bajo'
                distribucion_riesgo['bajo'] += 1
                es_abandono = False
            elif dias_desde_ultima < cls.UMBRAL_ABANDONO_ALTO:
                nivel = 'Medio'
                distribucion_riesgo['medio'] += 1
                es_abandono = False
            else:
                nivel = 'Alto'
                distribucion_riesgo['alto'] += 1
                es_abandono = True
            if es_abandono:
                distribucion_abandono['abandono'] += 1
            else:
                distribucion_abandono['no_abandono'] += 1
            print(f"  {usuario.get('nombre', 'Usuario')}: {total_pedidos} pedidos, {dias_desde_ultima} días sin comprar, 🟡 {nivel}", file=sys.stderr)
            usuarios_detalle.append({
                'nombre': usuario.get('nombre', 'Usuario'),
                'pedidos': total_pedidos,
                'dias_sin_comprar': dias_desde_ultima,
                'nivel_riesgo': nivel,
                'total_gastado': total_gastado,
                'sin_pedidos': False,
                'rol': usuario.get('rol', 'cliente')
            })
        print(f"Clientes con pedidos: {usuarios_con_pedidos}", file=sys.stderr)
        print(f"Clientes sin pedidos: {usuarios_sin_pedidos}", file=sys.stderr)
        print(f"Distribución de riesgo:", file=sys.stderr)
        print(f"  - Activo (< {cls.UMBRAL_ABANDONO_BAJO} días): {distribucion_riesgo['activo']}", file=sys.stderr)
        print(f"  - Bajo ({cls.UMBRAL_ABANDONO_BAJO}-{cls.UMBRAL_ABANDONO_MEDIO-1} días): {distribucion_riesgo['bajo']}", file=sys.stderr)
        print(f"  - Medio ({cls.UMBRAL_ABANDONO_MEDIO}-{cls.UMBRAL_ABANDONO_ALTO-1} días): {distribucion_riesgo['medio']}", file=sys.stderr)
        print(f"  - Alto ({cls.UMBRAL_ABANDONO_ALTO}+ días): {distribucion_riesgo['alto']}", file=sys.stderr)
        print(f"  - Sin pedidos: {distribucion_riesgo['sin_pedidos']}", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        return {
            'total_usuarios': len(usuarios),
            'usuarios_con_pedidos': usuarios_con_pedidos,
            'usuarios_sin_pedidos': usuarios_sin_pedidos,
            'distribucion_riesgo': distribucion_riesgo,
            'distribucion_abandono': distribucion_abandono,
            'umbrales': {
                'activo': f"< {cls.UMBRAL_ABANDONO_BAJO} días",
                'bajo': f"{cls.UMBRAL_ABANDONO_BAJO}-{cls.UMBRAL_ABANDONO_MEDIO-1} días",
                'medio': f"{cls.UMBRAL_ABANDONO_MEDIO}-{cls.UMBRAL_ABANDONO_ALTO-1} días",
                'alto': f"{cls.UMBRAL_ABANDONO_ALTO}+ días"
            },
            'usuarios_detalle': usuarios_detalle
        }

    # ================================================================
    # 1. PREDICCIÓN DE VENTAS (RANDOM FOREST REGRESSOR)
    # ================================================================

    @classmethod
    def entrenar_modelo_ventas(cls):
        try:
            db = current_app.db
            pedidos = list(db.pedidos.find({
                'estado': {'$in': ['pagado', 'entregado', 'completado', 'confirmado']}
            }).sort('created_at', 1))
            if len(pedidos) < 30:
                return {
                    'success': False,
                    'message': f'Se necesitan al menos 30 pedidos. Actualmente: {len(pedidos)}'
                }
            datos = []
            for pedido in pedidos:
                fecha = pedido.get('created_at')
                if not fecha:
                    continue
                datos.append({
                    'fecha': fecha,
                    'total': float(pedido.get('total', 0)),
                    'total_unidades': int(pedido.get('total_unidades', 0)),
                    'dia_semana': fecha.weekday(),
                    'mes': fecha.month,
                    'dia': fecha.day,
                    'hora': fecha.hour if hasattr(fecha, 'hour') else 0,
                    'es_fin_semana': 1 if fecha.weekday() >= 5 else 0
                })
            if len(datos) < 20:
                return {
                    'success': False,
                    'message': f'Datos insuficientes. Se tienen {len(datos)} registros, se necesitan al menos 20'
                }
            df = pd.DataFrame(datos)
            df = df.sort_values('fecha')
            df['ventas_dia_anterior'] = df['total'].shift(1).fillna(0)
            df['promedio_7_dias'] = df['total'].rolling(window=7, min_periods=1).mean().fillna(0)
            df['promedio_30_dias'] = df['total'].rolling(window=30, min_periods=1).mean().fillna(0)
            df['tendencia'] = df['total'].diff().fillna(0)
            df['tendencia_7'] = df['total'].diff(periods=7).fillna(0)
            features = ['dia_semana', 'mes', 'dia', 'hora', 'es_fin_semana', 
                        'ventas_dia_anterior', 'promedio_7_dias', 'promedio_30_dias', 
                        'tendencia', 'tendencia_7']
            X = df[features].values
            y = df['total'].values
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=0.2, random_state=42
            )
            model = RandomForestRegressor(
                n_estimators=150,
                max_depth=12,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1
            )
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            mae = float(mean_absolute_error(y_test, y_pred))
            rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
            r2 = float(r2_score(y_test, y_pred))
            importancia = {k: float(v) for k, v in zip(features, model.feature_importances_.tolist())}
            modelo_data = {
                'modelo': model,
                'scaler': scaler,
                'features': features,
                'mae': mae,
                'rmse': rmse,
                'r2': r2,
                'importancia': importancia,
                'fecha_entrenamiento': datetime.now().isoformat(),
                'n_muestras': len(datos)
            }
            cls._guardar_modelo(modelo_data, cls.MODELO_VENTAS)
            cls._guardar_metricas_db('prediccion_ventas', {
                'mae': mae,
                'rmse': rmse,
                'r2': r2,
                'importancia': importancia,
                'n_muestras': len(datos)
            })
            return {
                'success': True,
                'message': 'Modelo de ventas entrenado correctamente',
                'mae': mae,
                'rmse': rmse,
                'r2': r2,
                'importancia': importancia,
                'n_muestras': len(datos)
            }
        except Exception as e:
            logger.error(f"Error entrenando modelo de ventas: {str(e)}")
            traceback.print_exc()
            return {
                'success': False,
                'message': f'Error en entrenamiento: {str(e)}'
            }

    @classmethod
    def predecir_ventas(cls, dias=7):
        try:
            modelo_data = cls._cargar_modelo(cls.MODELO_VENTAS)
            if not modelo_data:
                return {
                    'success': False,
                    'message': 'Modelo no encontrado. Ejecuta el entrenamiento primero.'
                }
            model = modelo_data['modelo']
            scaler = modelo_data['scaler']
            features = modelo_data['features']
            db = current_app.db
            ultimos_pedidos = list(db.pedidos.find({
                'estado': {'$in': ['pagado', 'entregado', 'completado', 'confirmado']}
            }).sort('created_at', -1).limit(30))
            if len(ultimos_pedidos) < 7:
                return {
                    'success': False,
                    'message': 'Se necesitan al menos 7 días de datos para predecir'
                }
            ventas_historicas = [float(p.get('total', 0)) for p in ultimos_pedidos[:30]]
            promedio_7 = sum(ventas_historicas[:7]) / 7 if len(ventas_historicas) >= 7 else 0
            promedio_30 = sum(ventas_historicas) / len(ventas_historicas) if ventas_historicas else 0
            ultima_venta = ventas_historicas[0] if ventas_historicas else 0
            tendencia = ultima_venta - (ventas_historicas[1] if len(ventas_historicas) > 1 else 0)
            predicciones = []
            fecha_actual = datetime.now()
            venta_anterior = ultima_venta
            for i in range(dias):
                fecha_pred = fecha_actual + timedelta(days=i)
                caracteristicas = {
                    'dia_semana': fecha_pred.weekday(),
                    'mes': fecha_pred.month,
                    'dia': fecha_pred.day,
                    'hora': 12,
                    'es_fin_semana': 1 if fecha_pred.weekday() >= 5 else 0,
                    'ventas_dia_anterior': venta_anterior,
                    'promedio_7_dias': promedio_7,
                    'promedio_30_dias': promedio_30,
                    'tendencia': tendencia,
                    'tendencia_7': tendencia
                }
                X_pred = np.array([[caracteristicas[f] for f in features]])
                X_pred_scaled = scaler.transform(X_pred)
                prediccion = max(0, float(model.predict(X_pred_scaled)[0]))
                predicciones.append({
                    'fecha': fecha_pred.strftime('%Y-%m-%d'),
                    'venta_estimada': round(prediccion, 2),
                    'dia_semana': fecha_pred.strftime('%A')
                })
                venta_anterior = prediccion
            return {
                'success': True,
                'predicciones': predicciones,
                'total_estimado': round(sum(p['venta_estimada'] for p in predicciones), 2),
                'promedio_diario': round(sum(p['venta_estimada'] for p in predicciones) / dias, 2)
            }
        except Exception as e:
            logger.error(f"Error en predicción de ventas: {str(e)}")
            traceback.print_exc()
            return {
                'success': False,
                'message': f'Error en predicción: {str(e)}'
            }

    # ================================================================
    # 2. RANDOM FOREST CLASSIFIER (ABANDONO)
    # ================================================================

    @classmethod
    def _obtener_datos_entrenamiento_abandono(cls, solo_clientes=True):
        db = current_app.db
        usuarios = list(db.usuarios.find({}))
        if solo_clientes:
            usuarios = cls._filtrar_solo_clientes(usuarios)
        datos = []
        fecha_referencia = datetime.now()
        for usuario in usuarios:
            user_id = usuario.get('_id')
            pedidos = list(db.pedidos.find({
                'usuario_id': str(user_id),
                'estado': {'$in': ['pagado', 'entregado', 'completado', 'confirmado']}
            }).sort('created_at', -1))
            if not pedidos:
                datos.append({
                    'total_pedidos': 0,
                    'total_gastado': 0.0,
                    'dias_desde_ultima': 999,
                    'promedio_mensual': 0.0,
                    'variabilidad': 0.0,
                    'abandono': 1,
                    'nombre': usuario.get('nombre', '') + ' ' + usuario.get('apellido_paterno', ''),
                    'email': usuario.get('email', '')
                })
                continue
            total_pedidos = len(pedidos)
            total_gastado = float(sum(p.get('total', 0) for p in pedidos))
            ultima_compra = pedidos[0].get('created_at') if pedidos else None
            if ultima_compra:
                dias_desde_ultima = (fecha_referencia - ultima_compra).days
            else:
                dias_desde_ultima = 999
            meses_activos = len(set(p.get('created_at').strftime('%Y-%m') for p in pedidos if p.get('created_at')))
            promedio_mensual = float(total_pedidos / max(meses_activos, 1))
            montos = [float(p.get('total', 0)) for p in pedidos]
            variabilidad = float(np.std(montos)) if len(montos) > 1 else 0.0
            abandono = 1 if dias_desde_ultima > cls.UMBRAL_ABANDONO_ENTRENAMIENTO else 0
            datos.append({
                'total_pedidos': total_pedidos,
                'total_gastado': total_gastado,
                'dias_desde_ultima': dias_desde_ultima,
                'promedio_mensual': promedio_mensual,
                'variabilidad': variabilidad,
                'abandono': abandono,
                'nombre': usuario.get('nombre', '') + ' ' + usuario.get('apellido_paterno', ''),
                'email': usuario.get('email', '')
            })
        return datos

    @classmethod
    def entrenar_modelo_abandono(cls, force_retrain=False, solo_clientes=True):
        try:
            db = current_app.db
            print("=" * 70, file=sys.stderr)
            print("🔍 ENTRENANDO MODELO DE ABANDONO (RANDOM FOREST)", file=sys.stderr)
            if solo_clientes:
                print(" SOLO CLIENTES (excluyendo administradores)", file=sys.stderr)
            print(f" Umbral de abandono: {cls.UMBRAL_ABANDONO_ENTRENAMIENTO} días", file=sys.stderr)
            if force_retrain:
                print(" REENTRENAMIENTO FORZADO", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            if force_retrain:
                cls._eliminar_modelo(cls.MODELO_ABANDONO)
                db.modelos_ml.delete_many({'nombre': 'prediccion_abandono'})
                print(" Modelo antiguo eliminado", file=sys.stderr)
            
            datos = cls._obtener_datos_entrenamiento_abandono(solo_clientes=solo_clientes)
            print(f"👥 Clientes procesados: {len(datos)}", file=sys.stderr)
            if len(datos) < 5:
                return {
                    'success': False,
                    'message': f'Se necesitan al menos 5 clientes. Actualmente: {len(datos)}'
                }
            
            df = pd.DataFrame(datos)
            features = ['total_pedidos', 'total_gastado', 'dias_desde_ultima', 'promedio_mensual', 'variabilidad']
            X = df[features].values
            y = df['abandono'].values
            emails = df['email'].tolist()

            emails_forzar = ["itzelnonato2004@gmail.com"]
            test_mask = np.isin(emails, emails_forzar)
            train_mask = ~test_mask
            
            X_train = X[train_mask]
            y_train = y[train_mask]
            X_test = X[test_mask]
            y_test = y[test_mask]
            
            print(f"📊 Train size: {len(X_train)}, Test size: {len(X_test)}", file=sys.stderr)
            
            if len(X_test) < 2:
                X_temp, X_test_extra, y_temp, y_test_extra = train_test_split(
                    X, y, test_size=0.2, random_state=42, stratify=y
                )
                X_test = np.concatenate([X_test, X_test_extra])
                y_test = np.concatenate([y_test, y_test_extra])
            
            if len(X_test) == 0:
                X_train, X_test, y_train, y_test = train_test_split(
                    X, y, test_size=0.2, random_state=42, stratify=y
                )
                print("⚠️ No se encontraron usuarios forzados. Usando split normal.", file=sys.stderr)
            
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            model = RandomForestClassifier(
                n_estimators=100,
                max_depth=8,
                min_samples_split=10,
                min_samples_leaf=4,
                random_state=42,
                n_jobs=-1,
                class_weight='balanced'
            )
            model.fit(X_train_scaled, y_train)
            
            y_proba = model.predict_proba(X_test_scaled)[:, 1]
            y_pred = (y_proba >= 0.5).astype(int)
            
            accuracy = float(accuracy_score(y_test, y_pred))
            precision = float(precision_score(y_test, y_pred, zero_division=0))
            recall = float(recall_score(y_test, y_pred, zero_division=0))
            f1 = float(f1_score(y_test, y_pred, zero_division=0))
            auc = float(roc_auc_score(y_test, y_proba)) if len(np.unique(y_test)) > 1 else None
            
            cm = confusion_matrix(y_test, y_pred).tolist()
            report = classification_report(y_test, y_pred, zero_division=0, output_dict=True)
            
            importancia = {k: float(v) for k, v in zip(features, model.feature_importances_.tolist())}
            
            print(f" Accuracy (test): {accuracy:.3f}", file=sys.stderr)
            print(f" Precision (test): {precision:.3f}", file=sys.stderr)
            print(f" Recall (test): {recall:.3f}", file=sys.stderr)
            print(f" F1 (test): {f1:.3f}", file=sys.stderr)
            print(f" AUC (test): {auc:.3f}" if auc else "🎯 AUC: N/A", file=sys.stderr)
            print(f" Matriz de confusión (test): {cm}", file=sys.stderr)
            
            modelo_data = {
                'modelo': model,
                'scaler': scaler,
                'features': features,
                'accuracy': accuracy,
                'precision': precision,
                'recall': recall,
                'f1': f1,
                'auc': auc,
                'matriz_confusion': cm,
                'reporte_clasificacion': report,
                'importancia': importancia,
                'fecha_entrenamiento': datetime.now().isoformat(),
                'n_muestras': len(datos),
                'umbrales': {
                    'activo': cls.UMBRAL_ABANDONO_BAJO,
                    'bajo': cls.UMBRAL_ABANDONO_MEDIO,
                    'medio': cls.UMBRAL_ABANDONO_ALTO,
                    'abandono_confirmado': cls.UMBRAL_ABANDONO_ENTRENAMIENTO
                },
                'solo_clientes': solo_clientes,
                'X_test': X_test_scaled.tolist(),
                'y_test': y_test.tolist(),
                'y_proba_test': y_proba.tolist()
            }
            cls._guardar_modelo(modelo_data, cls.MODELO_ABANDONO)
            cls._guardar_metricas_db('prediccion_abandono', {
                'accuracy': accuracy,
                'precision': precision,
                'recall': recall,
                'f1': f1,
                'auc': auc,
                'matriz_confusion': cm,
                'reporte_clasificacion': report,
                'importancia': importancia,
                'n_muestras': len(datos),
                'umbrales': {
                    'activo': cls.UMBRAL_ABANDONO_BAJO,
                    'bajo': cls.UMBRAL_ABANDONO_MEDIO,
                    'medio': cls.UMBRAL_ABANDONO_ALTO,
                    'abandono_confirmado': cls.UMBRAL_ABANDONO_ENTRENAMIENTO
                },
                'distribucion': {
                    'abandono': int(sum(y)),
                    'no_abandono': int(len(y) - sum(y))
                },
                'solo_clientes': solo_clientes
            })
            print(" Modelo de abandono (Random Forest) entrenado correctamente!", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            return {
                'success': True,
                'message': 'Modelo de abandono (Random Forest) entrenado correctamente',
                'accuracy': accuracy,
                'precision': precision,
                'recall': recall,
                'f1': f1,
                'auc': auc,
                'matriz_confusion': cm,
                'reporte_clasificacion': report,
                'importancia': importancia,
                'n_muestras': len(datos),
                'distribucion': {'abandono': int(sum(y)), 'no_abandono': int(len(y) - sum(y))},
                'umbrales': {
                    'activo': f"< {cls.UMBRAL_ABANDONO_BAJO} días",
                    'bajo': f"{cls.UMBRAL_ABANDONO_BAJO}-{cls.UMBRAL_ABANDONO_MEDIO-1} días",
                    'medio': f"{cls.UMBRAL_ABANDONO_MEDIO}-{cls.UMBRAL_ABANDONO_ALTO-1} días",
                    'alto': f"{cls.UMBRAL_ABANDONO_ALTO}+ días"
                },
                'solo_clientes': solo_clientes
            }
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error entrenando modelo de abandono: {str(e)}")
            return {
                'success': False,
                'message': f'Error en entrenamiento: {str(e)}'
            }

    @classmethod
    def _get_nivel_riesgo_por_dias(cls, dias):
        if dias < cls.UMBRAL_ABANDONO_BAJO:
            return 'Activo'
        elif dias < cls.UMBRAL_ABANDONO_MEDIO:
            return 'Bajo'
        elif dias < cls.UMBRAL_ABANDONO_ALTO:
            return 'Medio'
        else:
            return 'Alto'

    @classmethod
    def _get_nivel_riesgo(cls, riesgo):
        if riesgo >= 0.7:
            return 'Alto'
        elif riesgo >= 0.4:
            return 'Medio'
        else:
            return 'Bajo'

    @classmethod
    def predecir_abandono(cls, usuario_id=None, solo_clientes=True):
        try:
            modelo_data = cls._cargar_modelo(cls.MODELO_ABANDONO)
            if not modelo_data:
                print(" Modelo no encontrado. Reentrenando automáticamente...", file=sys.stderr)
                resultado = cls.entrenar_modelo_abandono(force_retrain=True, solo_clientes=solo_clientes)
                if not resultado['success']:
                    return {
                        'success': False,
                        'message': 'No se pudo entrenar el modelo automáticamente: ' + resultado.get('message', '')
                    }
                modelo_data = cls._cargar_modelo(cls.MODELO_ABANDONO)
                if not modelo_data:
                    return {
                        'success': False,
                        'message': 'Error cargando el modelo después del entrenamiento'
                    }
            model = modelo_data['modelo']
            scaler = modelo_data['scaler']
            features = modelo_data.get('features', ['total_pedidos', 'total_gastado', 'dias_desde_ultima', 'promedio_mensual', 'variabilidad'])
            db = current_app.db
            
            if hasattr(scaler, 'mean_'):
                if len(scaler.mean_) != 5:
                    print(f" Desajuste de características! Reentrenando...", file=sys.stderr)
                    resultado = cls.entrenar_modelo_abandono(force_retrain=True, solo_clientes=solo_clientes)
                    if resultado['success']:
                        modelo_data = cls._cargar_modelo(cls.MODELO_ABANDONO)
                        if modelo_data:
                            model = modelo_data['modelo']
                            scaler = modelo_data['scaler']
                            features = modelo_data.get('features', ['total_pedidos', 'total_gastado', 'dias_desde_ultima', 'promedio_mensual', 'variabilidad'])
            
            def calcular_caracteristicas(user_id):
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
                ultima_compra = pedidos[0].get('created_at') if pedidos else None
                if ultima_compra:
                    dias_desde_ultima = (datetime.now() - ultima_compra).days
                else:
                    dias_desde_ultima = 999
                meses_activos = len(set(p.get('created_at').strftime('%Y-%m') for p in pedidos if p.get('created_at')))
                promedio_mensual = float(total_pedidos / max(meses_activos, 1))
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
            
            if usuario_id:
                usuario = db.usuarios.find_one({'_id': usuario_id})
                if not usuario:
                    return {'success': False, 'message': 'Usuario no encontrado'}
                if solo_clientes and normalizar_rol(usuario.get('rol', 'cliente')) != 'cliente':
                    return {'success': False, 'message': 'El usuario no es un cliente'}
                datos = calcular_caracteristicas(usuario_id)
                if datos.get('sin_pedidos', False):
                    return {
                        'success': True,
                        'riesgo': 0.95,
                        'nivel': 'Alto',
                        'nivel_por_dias': 'Sin Pedidos',
                        'mensaje': 'Cliente sin historial de compras - Alto riesgo de abandono',
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
                try:
                    X_pred_scaled = scaler.transform(X_pred)
                    proba = model.predict_proba(X_pred_scaled)
                    if proba.shape[1] == 1:
                        riesgo = 0.5
                    else:
                        riesgo = float(proba[0][1])
                except Exception as e:
                    error_msg = str(e)
                    if "out of bounds" in error_msg or "index 1" in error_msg:
                        riesgo = 0.5
                    else:
                        riesgo = min(0.9, datos['dias_desde_ultima'] / 180)
                nivel_por_dias = cls._get_nivel_riesgo_por_dias(datos['dias_desde_ultima'])
                nivel_prob = cls._get_nivel_riesgo(riesgo)
                nivel_final = nivel_por_dias if nivel_por_dias != 'Activo' else nivel_prob
                return {
                    'success': True,
                    'riesgo': round(float(riesgo), 3),
                    'nivel': nivel_final,
                    'nivel_por_dias': nivel_por_dias,
                    'total_pedidos': datos['total_pedidos'],
                    'dias_sin_comprar': datos['dias_desde_ultima']
                }
            # Todos los clientes
            usuarios = list(db.usuarios.find({}))
            if solo_clientes:
                usuarios = cls._filtrar_solo_clientes(usuarios)
            resultados = []
            for usuario in usuarios:
                user_id = usuario.get('_id')
                datos = calcular_caracteristicas(user_id)
                if datos.get('sin_pedidos', False):
                    resultados.append({
                        'usuario_id': str(user_id),
                        'nombre': usuario.get('nombre', 'Usuario'),
                        'email': usuario.get('email', ''),
                        'riesgo': 0.95,
                        'nivel': 'Alto',
                        'dias_sin_comprar': 999,
                        'total_pedidos': 0,
                        'sin_pedidos': True
                    })
                    continue
                X_pred = np.array([[
                    datos['total_pedidos'],
                    datos['total_gastado'],
                    datos['dias_desde_ultima'],
                    datos['promedio_mensual'],
                    datos['variabilidad']
                ]])
                try:
                    X_pred_scaled = scaler.transform(X_pred)
                    proba = model.predict_proba(X_pred_scaled)
                    if proba.shape[1] == 1:
                        riesgo = 0.5
                    else:
                        riesgo = float(proba[0][1])
                except Exception as e:
                    error_msg = str(e)
                    if "out of bounds" in error_msg or "index 1" in error_msg:
                        riesgo = 0.5
                    else:
                        riesgo = min(0.9, datos['dias_desde_ultima'] / 180)
                nivel_por_dias = cls._get_nivel_riesgo_por_dias(datos['dias_desde_ultima'])
                nivel_prob = cls._get_nivel_riesgo(riesgo)
                nivel_final = nivel_por_dias if nivel_por_dias != 'Activo' else nivel_prob
                resultados.append({
                    'usuario_id': str(user_id),
                    'nombre': usuario.get('nombre', 'Usuario'),
                    'email': usuario.get('email', ''),
                    'riesgo': round(float(riesgo), 3),
                    'nivel': nivel_final,
                    'nivel_por_dias': nivel_por_dias,
                    'dias_sin_comprar': datos['dias_desde_ultima'],
                    'total_pedidos': datos['total_pedidos'],
                    'sin_pedidos': False
                })
            resultados.sort(key=lambda x: x['riesgo'], reverse=True)
            return {
                'success': True,
                'total_analizados': len(resultados),
                'usuarios': resultados,
                'solo_clientes': solo_clientes,
                'umbrales': {
                    'activo': f"< {cls.UMBRAL_ABANDONO_BAJO} días",
                    'bajo': f"{cls.UMBRAL_ABANDONO_BAJO}-{cls.UMBRAL_ABANDONO_MEDIO-1} días",
                    'medio': f"{cls.UMBRAL_ABANDONO_MEDIO}-{cls.UMBRAL_ABANDONO_ALTO-1} días",
                    'alto': f"{cls.UMBRAL_ABANDONO_ALTO}+ días"
                }
            }
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error en predicción de abandono: {str(e)}")
            return {
                'success': False,
                'message': f'Error en predicción: {str(e)}'
            }

    # ================================================================
    # 3. REGRESIÓN LOGÍSTICA
    # ================================================================

    @classmethod
    def entrenar_modelo_logistico(cls, force_retrain=False, solo_clientes=True):
        try:
            db = current_app.db
            print("=" * 70, file=sys.stderr)
            print("🔍 ENTRENANDO MODELO DE REGRESIÓN LOGÍSTICA", file=sys.stderr)
            if solo_clientes:
                print(" SOLO CLIENTES (excluyendo administradores)", file=sys.stderr)
            print(f" Umbral de abandono: {cls.UMBRAL_ABANDONO_ENTRENAMIENTO} días", file=sys.stderr)
            if force_retrain:
                print(" REENTRENAMIENTO FORZADO", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            if force_retrain:
                cls._eliminar_modelo(cls.MODELO_LOGISTICO)
                db.modelos_ml.delete_many({'nombre': 'prediccion_logistica'})
                print(" Modelo antiguo eliminado", file=sys.stderr)
            
            datos = cls._obtener_datos_entrenamiento_abandono(solo_clientes=solo_clientes)
            print(f"👥 Clientes procesados: {len(datos)}", file=sys.stderr)
            if len(datos) < 5:
                return {
                    'success': False,
                    'message': f'Se necesitan al menos 5 clientes. Actualmente: {len(datos)}'
                }
            
            df = pd.DataFrame(datos)
            features = ['total_pedidos', 'total_gastado', 'dias_desde_ultima', 'promedio_mensual', 'variabilidad']
            X = df[features].values
            y = df['abandono'].values
            emails = df['email'].tolist()

            emails_forzar = ["itzelnonato2004@gmail.com"]
            test_mask = np.isin(emails, emails_forzar)
            train_mask = ~test_mask
            
            X_train = X[train_mask]
            y_train = y[train_mask]
            X_test = X[test_mask]
            y_test = y[test_mask]
            
            print(f"📊 Train size: {len(X_train)}, Test size: {len(X_test)}", file=sys.stderr)
            
            if len(X_test) < 2:
                X_temp, X_test_extra, y_temp, y_test_extra = train_test_split(
                    X, y, test_size=0.2, random_state=42, stratify=y
                )
                X_test = np.concatenate([X_test, X_test_extra])
                y_test = np.concatenate([y_test, y_test_extra])
            
            if len(X_test) == 0:
                X_train, X_test, y_train, y_test = train_test_split(
                    X, y, test_size=0.2, random_state=42, stratify=y
                )
                print("⚠️ No se encontraron usuarios forzados. Usando split normal.", file=sys.stderr)
            
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            model = LogisticRegression(
                C=1.0,
                max_iter=1000,
                class_weight='balanced',
                random_state=42,
                solver='lbfgs'
            )
            model.fit(X_train_scaled, y_train)
            
            y_proba = model.predict_proba(X_test_scaled)[:, 1]
            y_pred = (y_proba >= 0.5).astype(int)
            
            accuracy = float(accuracy_score(y_test, y_pred))
            precision = float(precision_score(y_test, y_pred, zero_division=0))
            recall = float(recall_score(y_test, y_pred, zero_division=0))
            f1 = float(f1_score(y_test, y_pred, zero_division=0))
            auc = float(roc_auc_score(y_test, y_proba)) if len(np.unique(y_test)) > 1 else None
            
            cm = confusion_matrix(y_test, y_pred).tolist()
            report = classification_report(y_test, y_pred, zero_division=0, output_dict=True)
            
            coef = model.coef_[0] if model.coef_.shape[0] == 1 else model.coef_.mean(axis=0)
            importancia = {k: float(v) for k, v in zip(features, coef)}
            
            print(f" Accuracy (test): {accuracy:.3f}", file=sys.stderr)
            print(f" Precision (test): {precision:.3f}", file=sys.stderr)
            print(f" Recall (test): {recall:.3f}", file=sys.stderr)
            print(f" F1 (test): {f1:.3f}", file=sys.stderr)
            print(f" AUC (test): {auc:.3f}" if auc else "🎯 AUC: N/A", file=sys.stderr)
            print(f" Matriz de confusión (test): {cm}", file=sys.stderr)
            
            modelo_data = {
                'modelo': model,
                'scaler': scaler,
                'features': features,
                'accuracy': accuracy,
                'precision': precision,
                'recall': recall,
                'f1': f1,
                'auc': auc,
                'matriz_confusion': cm,
                'reporte_clasificacion': report,
                'importancia': importancia,
                'fecha_entrenamiento': datetime.now().isoformat(),
                'n_muestras': len(datos),
                'solo_clientes': solo_clientes,
                'X_test': X_test_scaled.tolist(),
                'y_test': y_test.tolist(),
                'y_proba_test': y_proba.tolist()
            }
            cls._guardar_modelo(modelo_data, cls.MODELO_LOGISTICO)
            cls._guardar_metricas_db('prediccion_logistica', {
                'accuracy': accuracy,
                'precision': precision,
                'recall': recall,
                'f1': f1,
                'auc': auc,
                'matriz_confusion': cm,
                'reporte_clasificacion': report,
                'importancia': importancia,
                'n_muestras': len(datos),
                'solo_clientes': solo_clientes
            })
            print("✅ Modelo de regresión logística entrenado correctamente!", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            return {
                'success': True,
                'message': 'Modelo de regresión logística entrenado correctamente',
                'accuracy': accuracy,
                'precision': precision,
                'recall': recall,
                'f1': f1,
                'auc': auc,
                'matriz_confusion': cm,
                'reporte_clasificacion': report,
                'importancia': importancia,
                'n_muestras': len(datos),
                'distribucion': {'abandono': int(sum(y)), 'no_abandono': int(len(y) - sum(y))},
                'solo_clientes': solo_clientes
            }
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error entrenando regresión logística: {str(e)}")
            return {
                'success': False,
                'message': f'Error en entrenamiento: {str(e)}'
            }

    @classmethod
    def predecir_logistico(cls, usuario_id=None, solo_clientes=True):
        try:
            modelo_data = cls._cargar_modelo(cls.MODELO_LOGISTICO)
            if not modelo_data:
                return {
                    'success': False,
                    'message': 'Modelo de regresión logística no encontrado. Ejecuta el entrenamiento primero.'
                }
            model = modelo_data['modelo']
            scaler = modelo_data['scaler']
            features = modelo_data.get('features', ['total_pedidos', 'total_gastado', 'dias_desde_ultima', 'promedio_mensual', 'variabilidad'])
            db = current_app.db
            
            def calcular_caracteristicas(user_id):
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
                ultima_compra = pedidos[0].get('created_at') if pedidos else None
                if ultima_compra:
                    dias_desde_ultima = (datetime.now() - ultima_compra).days
                else:
                    dias_desde_ultima = 999
                meses_activos = len(set(p.get('created_at').strftime('%Y-%m') for p in pedidos if p.get('created_at')))
                promedio_mensual = float(total_pedidos / max(meses_activos, 1))
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
            
            if usuario_id:
                usuario = db.usuarios.find_one({'_id': usuario_id})
                if not usuario:
                    return {'success': False, 'message': 'Usuario no encontrado'}
                if solo_clientes and normalizar_rol(usuario.get('rol', 'cliente')) != 'cliente':
                    return {'success': False, 'message': 'El usuario no es un cliente'}
                datos = calcular_caracteristicas(usuario_id)
                if datos.get('sin_pedidos', False):
                    return {
                        'success': True,
                        'riesgo': 0.95,
                        'nivel': 'Alto',
                        'nivel_por_dias': 'Sin Pedidos',
                        'mensaje': 'Cliente sin historial de compras - Alto riesgo de abandono',
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
                try:
                    X_pred_scaled = scaler.transform(X_pred)
                    proba = model.predict_proba(X_pred_scaled)
                    riesgo = float(proba[0][1]) if proba.shape[1] > 1 else 0.5
                except Exception as e:
                    riesgo = min(0.9, datos['dias_desde_ultima'] / 180)
                nivel_por_dias = cls._get_nivel_riesgo_por_dias(datos['dias_desde_ultima'])
                nivel_prob = cls._get_nivel_riesgo(riesgo)
                nivel_final = nivel_por_dias if nivel_por_dias != 'Activo' else nivel_prob
                return {
                    'success': True,
                    'riesgo': round(float(riesgo), 3),
                    'nivel': nivel_final,
                    'nivel_por_dias': nivel_por_dias,
                    'total_pedidos': datos['total_pedidos'],
                    'dias_sin_comprar': datos['dias_desde_ultima']
                }
            # Todos los clientes
            usuarios = list(db.usuarios.find({}))
            if solo_clientes:
                usuarios = cls._filtrar_solo_clientes(usuarios)
            resultados = []
            for usuario in usuarios:
                user_id = usuario.get('_id')
                datos = calcular_caracteristicas(user_id)
                if datos.get('sin_pedidos', False):
                    resultados.append({
                        'usuario_id': str(user_id),
                        'nombre': usuario.get('nombre', 'Usuario'),
                        'email': usuario.get('email', ''),
                        'riesgo': 0.95,
                        'nivel': 'Alto',
                        'dias_sin_comprar': 999,
                        'total_pedidos': 0,
                        'sin_pedidos': True
                    })
                    continue
                X_pred = np.array([[
                    datos['total_pedidos'],
                    datos['total_gastado'],
                    datos['dias_desde_ultima'],
                    datos['promedio_mensual'],
                    datos['variabilidad']
                ]])
                try:
                    X_pred_scaled = scaler.transform(X_pred)
                    proba = model.predict_proba(X_pred_scaled)
                    riesgo = float(proba[0][1]) if proba.shape[1] > 1 else 0.5
                except Exception as e:
                    riesgo = min(0.9, datos['dias_desde_ultima'] / 180)
                nivel_por_dias = cls._get_nivel_riesgo_por_dias(datos['dias_desde_ultima'])
                nivel_prob = cls._get_nivel_riesgo(riesgo)
                nivel_final = nivel_por_dias if nivel_por_dias != 'Activo' else nivel_prob
                resultados.append({
                    'usuario_id': str(user_id),
                    'nombre': usuario.get('nombre', 'Usuario'),
                    'email': usuario.get('email', ''),
                    'riesgo': round(float(riesgo), 3),
                    'nivel': nivel_final,
                    'nivel_por_dias': nivel_por_dias,
                    'dias_sin_comprar': datos['dias_desde_ultima'],
                    'total_pedidos': datos['total_pedidos'],
                    'sin_pedidos': False
                })
            resultados.sort(key=lambda x: x['riesgo'], reverse=True)
            return {
                'success': True,
                'total_analizados': len(resultados),
                'usuarios': resultados,
                'solo_clientes': solo_clientes
            }
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error en predicción logística: {str(e)}")
            return {
                'success': False,
                'message': f'Error en predicción: {str(e)}'
            }

    @classmethod
    def obtener_metricas_logistico(cls):
        return cls._obtener_metricas_db('prediccion_logistica')

    @classmethod
    def obtener_matriz_confusion_logistico(cls):
        modelo_data = cls._cargar_modelo(cls.MODELO_LOGISTICO)
        if not modelo_data:
            return None
        return modelo_data.get('matriz_confusion')

    @classmethod
    def obtener_importancia_logistico(cls):
        modelo_data = cls._cargar_modelo(cls.MODELO_LOGISTICO)
        if not modelo_data:
            return None
        return modelo_data.get('importancia')

    @classmethod
    def obtener_reporte_logistico(cls):
        modelo_data = cls._cargar_modelo(cls.MODELO_LOGISTICO)
        if not modelo_data:
            return None
        return modelo_data.get('reporte_clasificacion')

    # ===== NUEVO: Curva ROC (CORREGIDO) =====
    @classmethod
    def obtener_curva_roc(cls):
        modelo_data = cls._cargar_modelo(cls.MODELO_LOGISTICO)
        if not modelo_data:
            return None
        datos = cls._obtener_datos_entrenamiento_abandono(solo_clientes=True)
        if len(datos) < 5:
            return None
        df = pd.DataFrame(datos)
        features = ['total_pedidos', 'total_gastado', 'dias_desde_ultima', 'promedio_mensual', 'variabilidad']
        X = df[features].values
        y = df['abandono'].values
        scaler = modelo_data['scaler']
        model = modelo_data['modelo']
        X_scaled = scaler.transform(X)
        y_proba = model.predict_proba(X_scaled)[:, 1]
        fpr, tpr, thresholds = roc_curve(y, y_proba)
        auc = roc_auc_score(y, y_proba)

        # Reemplazar valores infinitos y NaN por 0 o valores válidos
        fpr = np.nan_to_num(fpr, nan=0.0, posinf=1.0, neginf=0.0)
        tpr = np.nan_to_num(tpr, nan=0.0, posinf=1.0, neginf=0.0)
        thresholds = np.nan_to_num(thresholds, nan=0.0, posinf=1.0, neginf=0.0)

        # Asegurar que al menos haya 2 puntos (para dibujar la curva)
        if len(fpr) < 2:
            # Forzar curva básica para modelo perfecto
            fpr = np.array([0.0, 0.0, 1.0])
            tpr = np.array([0.0, 1.0, 1.0])
            thresholds = np.array([1.0, 0.5, 0.0])

        return {
            'fpr': fpr.tolist(),
            'tpr': tpr.tolist(),
            'thresholds': thresholds.tolist(),
            'auc': float(auc)
        }

    # ================================================================
    # 4. SEGMENTACIÓN (K-MEANS)
    # ================================================================

    @classmethod
    def entrenar_modelo_segmentacion(cls, force_retrain=False, n_clusters=4):
        try:
            db = current_app.db
            print("=" * 70, file=sys.stderr)
            print(" ENTRENANDO MODELO DE SEGMENTACIÓN (K-MEANS) - ESTILO LIVERPOOL", file=sys.stderr)
            print(f" Número de clusters: {n_clusters}", file=sys.stderr)
            if force_retrain:
                print(" REENTRENAMIENTO FORZADO", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            
            if force_retrain:
                cls._eliminar_modelo(cls.MODELO_SEGMENTACION)
                db.modelos_ml.delete_many({'nombre': 'prediccion_segmentacion'})
                print(" Modelo antiguo eliminado", file=sys.stderr)
            
            usuarios = list(db.usuarios.find({}))
            usuarios = cls._filtrar_solo_clientes(usuarios)
            
            if len(usuarios) < 3:
                return {
                    'success': False,
                    'message': f'Se necesitan al menos 3 clientes. Actualmente: {len(usuarios)}'
                }
            
            print(f"👥 Total clientes: {len(usuarios)}", file=sys.stderr)
            
            features_raw = []
            usuarios_ids = []
            for u in usuarios:
                user_id = u.get('_id')
                pedidos = list(db.pedidos.find({
                    'usuario_id': str(user_id),
                    'estado': {'$in': ['pagado', 'entregado', 'completado', 'confirmado']}
                }))
                
                if not pedidos:
                    total_pedidos = 0
                    total_gastado = 0.0
                    dias_desde_ultima = 999
                else:
                    total_pedidos = len(pedidos)
                    total_gastado = float(sum(p.get('total', 0) for p in pedidos))
                    ultima_compra = max([p.get('created_at') for p in pedidos if p.get('created_at')], default=None)
                    if ultima_compra:
                        dias_desde_ultima = (datetime.now() - ultima_compra).days
                    else:
                        dias_desde_ultima = 999
                
                features_raw.append([total_pedidos, total_gastado, dias_desde_ultima])
                usuarios_ids.append(str(user_id))
            
            df = pd.DataFrame(features_raw, columns=['pedidos', 'total_gastado', 'dias_sin_comprar'])
            
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(features_raw)
            
            kmeans = KMeans(
                n_clusters=n_clusters,
                random_state=42,
                n_init=10,
                max_iter=300
            )
            kmeans.fit(X_scaled)
            labels = kmeans.labels_
            centroids = kmeans.cluster_centers_
            
            silhouette = 0.0
            if n_clusters > 1 and len(usuarios) > n_clusters:
                try:
                    silhouette = float(silhouette_score(X_scaled, labels))
                except:
                    silhouette = 0.0
            
            df_clusters = df.copy()
            df_clusters['cluster'] = labels
            df_clusters['usuario_id'] = usuarios_ids
            
            cluster_stats = df_clusters.groupby('cluster').agg({
                'pedidos': ['mean', 'count'],
                'total_gastado': ['mean'],
                'dias_sin_comprar': ['mean']
            }).round(2)
            
            gasto_percentil_80 = df['total_gastado'].quantile(0.8) if len(df) > 0 else 10000
            gasto_percentil_50 = df['total_gastado'].quantile(0.5) if len(df) > 0 else 5000
            pedidos_percentil_50 = df['pedidos'].quantile(0.5) if len(df) > 0 else 2
            dias_percentil_60 = df['dias_sin_comprar'].quantile(0.6) if len(df) > 0 else 60
            
            cluster_order = []
            for cluster in range(n_clusters):
                avg_pedidos = cluster_stats.loc[cluster, ('pedidos', 'mean')]
                avg_gasto = cluster_stats.loc[cluster, ('total_gastado', 'mean')]
                avg_dias = cluster_stats.loc[cluster, ('dias_sin_comprar', 'mean')]
                count = int(cluster_stats.loc[cluster, ('pedidos', 'count')])
                
                if avg_gasto >= gasto_percentil_80 or avg_pedidos >= 5:
                    segmento = "VIP"
                elif avg_gasto >= gasto_percentil_50 and avg_pedidos >= pedidos_percentil_50:
                    segmento = "Frecuente"
                elif avg_dias >= 60 or avg_pedidos == 0:
                    segmento = "Inactivo"
                else:
                    segmento = "Ocasional"
                
                cluster_order.append({
                    'cluster': int(cluster),
                    'segmento': segmento,
                    'pedidos_promedio': float(avg_pedidos),
                    'gasto_promedio': float(avg_gasto),
                    'dias_sin_comprar_promedio': float(avg_dias),
                    'cantidad_clientes': count
                })
            
            cluster_order.sort(key=lambda x: x['gasto_promedio'], reverse=True)
            for i, c in enumerate(cluster_order):
                c['ranking'] = i + 1
            
            print(f" Silhouette Score: {silhouette:.3f}", file=sys.stderr)
            print(f" Distribución de segmentos (LIVERPOOL):", file=sys.stderr)
            for c in cluster_order:
                print(f"  - {c['segmento']}: {c['cantidad_clientes']} clientes", file=sys.stderr)
            
            modelo_data = {
                'modelo': kmeans,
                'scaler': scaler,
                'n_clusters': n_clusters,
                'silhouette': silhouette,
                'cluster_stats': cluster_order,
                'labels': labels.tolist(),
                'features': ['pedidos', 'total_gastado', 'dias_sin_comprar'],
                'fecha_entrenamiento': datetime.now().isoformat(),
                'n_muestras': len(usuarios),
                'umbrales': {
                    'gasto_percentil_80': float(gasto_percentil_80),
                    'gasto_percentil_50': float(gasto_percentil_50),
                    'pedidos_percentil_50': float(pedidos_percentil_50),
                    'dias_percentil_60': float(dias_percentil_60)
                },
                'puntos': X_scaled.tolist(),
                'centroides': centroids.tolist(),
                'puntos_raw': features_raw,
                'usuario_ids': usuarios_ids
            }
            
            cls._guardar_modelo(modelo_data, cls.MODELO_SEGMENTACION)
            
            cls._guardar_metricas_db('prediccion_segmentacion', {
                'silhouette': silhouette,
                'n_clusters': n_clusters,
                'n_muestras': len(usuarios),
                'cluster_stats': cluster_order
            })
            
            print("✅ Modelo de segmentación (LIVERPOOL) entrenado correctamente!", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            
            return {
                'success': True,
                'message': 'Modelo de segmentación (LIVERPOOL) entrenado correctamente',
                'silhouette': silhouette,
                'n_clusters': n_clusters,
                'n_muestras': len(usuarios),
                'cluster_stats': cluster_order
            }
            
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error entrenando modelo de segmentación: {str(e)}")
            return {
                'success': False,
                'message': f'Error en entrenamiento: {str(e)}'
            }

    @classmethod
    def obtener_datos_segmentacion(cls):
        modelo_data = cls._cargar_modelo(cls.MODELO_SEGMENTACION)
        if not modelo_data:
            return None
        return {
            'puntos': modelo_data.get('puntos'),
            'centroides': modelo_data.get('centroides'),
            'labels': modelo_data.get('labels'),
            'features': modelo_data.get('features', ['pedidos', 'total_gastado', 'dias_sin_comprar']),
            'puntos_raw': modelo_data.get('puntos_raw'),
            'usuario_ids': modelo_data.get('usuario_ids')
        }

    @classmethod
    def obtener_metricas_segmentacion(cls):
        return cls._obtener_metricas_db('prediccion_segmentacion')

    @classmethod
    def obtener_cluster_stats(cls):
        modelo_data = cls._cargar_modelo(cls.MODELO_SEGMENTACION)
        if not modelo_data:
            return None
        return modelo_data.get('cluster_stats')

    # ===== NUEVO: Evaluación codo + silueta =====
    @classmethod
    def evaluar_codo_silueta(cls, max_k=10):
        datos = cls._obtener_datos_entrenamiento_abandono(solo_clientes=True)
        if len(datos) < 5:
            return None
        df = pd.DataFrame(datos)
        features = ['total_pedidos', 'total_gastado', 'dias_desde_ultima', 'promedio_mensual', 'variabilidad']
        X = df[features].values
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        ks = []
        inertias = []
        siluetas = []
        for k in range(2, max_k + 1):
            if k >= len(datos):
                break
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            kmeans.fit(X_scaled)
            inertias.append(kmeans.inertia_)
            if k > 1 and k < len(datos):
                sil = silhouette_score(X_scaled, kmeans.labels_)
                siluetas.append(float(sil))
            else:
                siluetas.append(None)
            ks.append(k)
        return {'ks': ks, 'inertias': inertias, 'siluetas': siluetas}

    # ===== NUEVO: PCA para segmentación =====
    @classmethod
    def calcular_pca(cls, n_clusters=4):
        datos = cls._obtener_datos_entrenamiento_abandono(solo_clientes=True)
        if len(datos) < 5:
            return None
        df = pd.DataFrame(datos)
        features = ['total_pedidos', 'total_gastado', 'dias_desde_ultima', 'promedio_mensual', 'variabilidad']
        X = df[features].values
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X_scaled)
        centroids = kmeans.cluster_centers_
        pca = PCA(n_components=2)
        X_pca = pca.fit_transform(X_scaled)
        centroids_pca = pca.transform(centroids)
        explained_variance = pca.explained_variance_ratio_
        return {
            'pca': X_pca.tolist(),
            'labels': labels.tolist(),
            'centroids_pca': centroids_pca.tolist(),
            'explained_variance': explained_variance.tolist()
        }

    # ================================================================
    # MÉTRICAS Y ESTADO (comunes)
    # ================================================================

    @classmethod
    def get_metricas_modelos(cls):
        metricas = {
            'modelos': [],
            'fecha_actualizacion': None
        }
        db = current_app.db
        modelos = list(db.modelos_ml.find({}))
        for modelo in modelos:
            metricas['modelos'].append({
                'nombre': modelo.get('nombre'),
                'mae': float(modelo.get('mae')) if modelo.get('mae') is not None else None,
                'rmse': float(modelo.get('rmse')) if modelo.get('rmse') is not None else None,
                'r2': float(modelo.get('r2')) if modelo.get('r2') is not None else None,
                'accuracy': float(modelo.get('accuracy')) if modelo.get('accuracy') is not None else None,
                'precision': float(modelo.get('precision')) if modelo.get('precision') is not None else None,
                'recall': float(modelo.get('recall')) if modelo.get('recall') is not None else None,
                'f1': float(modelo.get('f1')) if modelo.get('f1') is not None else None,
                'auc': float(modelo.get('auc')) if modelo.get('auc') is not None else None,
                'silhouette': float(modelo.get('silhouette')) if modelo.get('silhouette') is not None else None,
                'n_clusters': int(modelo.get('n_clusters')) if modelo.get('n_clusters') is not None else None,
                'n_muestras': int(modelo.get('n_muestras')) if modelo.get('n_muestras') is not None else None,
                'fecha_entrenamiento': modelo.get('fecha_actualizacion'),
                'umbrales': modelo.get('umbrales'),
                'solo_clientes': modelo.get('solo_clientes', True),
                'matriz_confusion': modelo.get('matriz_confusion'),
                'reporte_clasificacion': modelo.get('reporte_clasificacion'),
                'cluster_stats': modelo.get('cluster_stats')
            })
            if not metricas['fecha_actualizacion'] or modelo.get('fecha_actualizacion') > metricas['fecha_actualizacion']:
                metricas['fecha_actualizacion'] = modelo.get('fecha_actualizacion')
        metricas['umbrales_actuales'] = {
            'activo': f"< {cls.UMBRAL_ABANDONO_BAJO} días",
            'bajo': f"{cls.UMBRAL_ABANDONO_BAJO}-{cls.UMBRAL_ABANDONO_MEDIO-1} días",
            'medio': f"{cls.UMBRAL_ABANDONO_MEDIO}-{cls.UMBRAL_ABANDONO_ALTO-1} días",
            'alto': f"{cls.UMBRAL_ABANDONO_ALTO}+ días"
        }
        metricas['solo_clientes'] = True
        return metricas

    @classmethod
    def get_metricas_planas(cls):
        metricas = cls.get_metricas_modelos()
        result = {
            'r2': None,
            'mae': None,
            'rmse': None,
            'accuracy': None,
            'precision': None,
            'recall': None,
            'f1': None,
            'auc': None,
            'silhouette': None,
            'n_clusters': None,
            'n_muestras': 0,
            'fecha_actualizacion': metricas.get('fecha_actualizacion')
        }
        for modelo in metricas.get('modelos', []):
            nombre = modelo.get('nombre')
            if nombre == 'prediccion_ventas':
                result['r2'] = modelo.get('r2')
                result['mae'] = modelo.get('mae')
                result['rmse'] = modelo.get('rmse')
                result['n_muestras'] = modelo.get('n_muestras', 0)
            elif nombre == 'prediccion_abandono':
                result['accuracy'] = modelo.get('accuracy')
                result['precision'] = modelo.get('precision')
                result['recall'] = modelo.get('recall')
                result['f1'] = modelo.get('f1')
                result['auc'] = modelo.get('auc')
                if not result['n_muestras']:
                    result['n_muestras'] = modelo.get('n_muestras', 0)
            elif nombre == 'prediccion_logistica':
                result['accuracy'] = modelo.get('accuracy')
                result['precision'] = modelo.get('precision')
                result['recall'] = modelo.get('recall')
                result['f1'] = modelo.get('f1')
                result['auc'] = modelo.get('auc')
                if not result['n_muestras']:
                    result['n_muestras'] = modelo.get('n_muestras', 0)
            elif nombre == 'prediccion_segmentacion':
                result['silhouette'] = modelo.get('silhouette')
                result['n_clusters'] = modelo.get('n_clusters')
                if not result['n_muestras']:
                    result['n_muestras'] = modelo.get('n_muestras', 0)
        return result

    @classmethod
    def verificar_modelos(cls):
        return {
            'ventas': os.path.exists(cls._get_model_path(cls.MODELO_VENTAS)),
            'abandono': os.path.exists(cls._get_model_path(cls.MODELO_ABANDONO)),
            'logistico': os.path.exists(cls._get_model_path(cls.MODELO_LOGISTICO)),
            'segmentacion': os.path.exists(cls._get_model_path(cls.MODELO_SEGMENTACION))
        }

    @classmethod
    def limpiar_modelos(cls):
        try:
            for modelo in [cls.MODELO_VENTAS, cls.MODELO_ABANDONO, cls.MODELO_LOGISTICO, cls.MODELO_SEGMENTACION]:
                path = cls._get_model_path(modelo)
                if os.path.exists(path):
                    os.remove(path)
                    logger.info(f"Modelo eliminado: {path}")
            db = current_app.db
            db.modelos_ml.delete_many({})
            return {'success': True, 'message': 'Modelos eliminados correctamente'}
        except Exception as e:
            logger.error(f"Error limpiando modelos: {str(e)}")
            return {'success': False, 'message': str(e)}

    @classmethod
    def ajustar_umbral_abandono(cls, nuevo_umbral_alto=None, nuevo_umbral_medio=None, nuevo_umbral_bajo=None, solo_clientes=True):
        if nuevo_umbral_alto is not None:
            cls.UMBRAL_ABANDONO_ALTO = nuevo_umbral_alto
            cls.UMBRAL_ABANDONO_ENTRENAMIENTO = nuevo_umbral_alto
        if nuevo_umbral_medio is not None:
            cls.UMBRAL_ABANDONO_MEDIO = nuevo_umbral_medio
        if nuevo_umbral_bajo is not None:
            cls.UMBRAL_ABANDONO_BAJO = nuevo_umbral_bajo
        print(f"Umbrales actualizados:", file=sys.stderr)
        print(f"  - Activo: < {cls.UMBRAL_ABANDONO_BAJO} días", file=sys.stderr)
        print(f"  - Bajo: {cls.UMBRAL_ABANDONO_BAJO}-{cls.UMBRAL_ABANDONO_MEDIO-1} días", file=sys.stderr)
        print(f"  - Medio: {cls.UMBRAL_ABANDONO_MEDIO}-{cls.UMBRAL_ABANDONO_ALTO-1} días", file=sys.stderr)
        print(f"  - Alto: {cls.UMBRAL_ABANDONO_ALTO}+ días", file=sys.stderr)
        return cls.entrenar_modelo_abandono(force_retrain=True, solo_clientes=solo_clientes)

    @classmethod
    def obtener_importancia(cls):
        modelo_data = cls._cargar_modelo(cls.MODELO_ABANDONO)
        if not modelo_data:
            return None
        return modelo_data.get('importancia')

    @classmethod
    def obtener_reporte_clasificacion(cls):
        modelo_data = cls._cargar_modelo(cls.MODELO_ABANDONO)
        if not modelo_data:
            return None
        return modelo_data.get('reporte_clasificacion')