# app/models/configuracion_model.py
# ================================================================
# MODELO DE CONFIGURACIÓN DEL SISTEMA
# ================================================================

from datetime import datetime, timezone
from flask import current_app


class Configuracion:
    """Acceso a la colección `configuracion` (documentos con _id string)."""

    COLECCION = 'configuracion'

    # ------------------------------------------------------------
    # GENERAL
    # ------------------------------------------------------------
    @staticmethod
    def obtener_general():
        db = current_app.db
        doc = db[Configuracion.COLECCION].find_one({'_id': 'general'})
        return doc or {
            '_id': 'general',
            'nombre_tienda': 'ORION System',
            'email_tienda': '',
            'telefono_tienda': '',
            'direccion_tienda': '',
            'moneda': 'MXN',
        }

    @staticmethod
    def guardar_general(data):
        db = current_app.db
        data['updated_at'] = datetime.now(timezone.utc)
        return db[Configuracion.COLECCION].update_one(
            {'_id': 'general'}, {'$set': data}, upsert=True
        )

    # ------------------------------------------------------------
    # ENVÍOS
    # ------------------------------------------------------------
    @staticmethod
    def obtener_envios():
        db = current_app.db
        doc = db[Configuracion.COLECCION].find_one({'_id': 'envios'})
        return doc or {
            '_id': 'envios',
            'costo_envio': 0.0,
            'costo_envio_gratis_sobre': 0.0,
            'tiempo_entrega_dias': 5,
            'marcas_envio': [],
        }

    @staticmethod
    def guardar_envios(data):
        db = current_app.db
        data['updated_at'] = datetime.now(timezone.utc)
        return db[Configuracion.COLECCION].update_one(
            {'_id': 'envios'}, {'$set': data}, upsert=True
        )

    # ------------------------------------------------------------
    # PAGOS
    # ------------------------------------------------------------
    @staticmethod
    def obtener_pagos():
        db = current_app.db
        doc = db[Configuracion.COLECCION].find_one({'_id': 'pagos'})
        return doc or {
            '_id': 'pagos',
            'metodos_pago': ['tarjeta', 'paypal', 'oxxo'],
            'moneda': 'MXN',
            'iva_porcentaje': 16.0,
            'stripe_key': '',
            'paypal_client_id': '',
            'paypal_secret': '',
        }

    @staticmethod
    def guardar_pagos(data):
        db = current_app.db
        data['updated_at'] = datetime.now(timezone.utc)
        return db[Configuracion.COLECCION].update_one(
            {'_id': 'pagos'}, {'$set': data}, upsert=True
        )

    # ------------------------------------------------------------
    # IMPUESTOS
    # ------------------------------------------------------------
    @staticmethod
    def obtener_impuestos():
        db = current_app.db
        doc = db[Configuracion.COLECCION].find_one({'_id': 'impuestos'})
        return doc or {
            '_id': 'impuestos',
            'iva_porcentaje': 16.0,
            'ieps_porcentaje': 0.0,
            'retencion_isr': 0.0,
        }

    @staticmethod
    def guardar_impuestos(data):
        db = current_app.db
        data['updated_at'] = datetime.now(timezone.utc)
        return db[Configuracion.COLECCION].update_one(
            {'_id': 'impuestos'}, {'$set': data}, upsert=True
        )

    # ------------------------------------------------------------
    # TIENDAS
    # ------------------------------------------------------------
    @staticmethod
    def obtener_tiendas():
        db = current_app.db
        doc = db[Configuracion.COLECCION].find_one({'_id': 'tiendas'})
        if not doc:
            return []
        return doc.get('tiendas', [])

    @staticmethod
    def guardar_tiendas(tiendas):
        db = current_app.db
        return db[Configuracion.COLECCION].update_one(
            {'_id': 'tiendas'},
            {'$set': {'tiendas': tiendas, 'updated_at': datetime.now(timezone.utc)}},
            upsert=True
        )