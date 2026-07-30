# app/models/ventas_model.py
# ================================================================
# MODELO PARA REPORTE DE VENTAS - ESTILO LIVERPOOL CON LIMPIEZA
# ================================================================

from flask import current_app
from bson import ObjectId
from datetime import datetime, timedelta
from collections import defaultdict
import json
import re


class VentaReporte:
    """Modelo para generar reportes de ventas con limpieza de datos"""

    # ================================================================
    # MÉTODOS DE LIMPIEZA DE DATOS
    # ================================================================

    @staticmethod
    def _limpiar_texto(texto):
        """Eliminar espacios extras y caracteres especiales básicos"""
        if not texto or not isinstance(texto, str):
            return ''
        # Eliminar espacios múltiples
        texto = ' '.join(texto.split())
        # Eliminar caracteres de control
        texto = texto.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
        # Eliminar caracteres especiales no deseados (opcional)
        # texto = re.sub(r'[^\w\s\-áéíóúñÑ.,()]', '', texto)
        return texto.strip()

    @staticmethod
    def _limpiar_precio(valor):
        """Asegurar que el precio sea un número válido positivo"""
        try:
            valor = float(valor)
            return max(0, round(valor, 2))
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _limpiar_cantidad(valor):
        """Asegurar que la cantidad sea un entero válido positivo"""
        try:
            valor = int(valor)
            return max(0, valor)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _normalizar_nombre(nombre):
        """Normalizar nombre para consistencia"""
        if not nombre:
            return 'Sin nombre'
        nombre = VentaReporte._limpiar_texto(nombre)
        # Capitalizar palabras importantes
        palabras = nombre.split()
        palabras = [p.capitalize() if len(p) > 2 else p for p in palabras]
        return ' '.join(palabras)

    @staticmethod
    def _normalizar_categoria(nombre):
        """Normalizar nombre de categoría"""
        if not nombre:
            return 'Sin categoría'
        nombre = VentaReporte._limpiar_texto(nombre)
        return nombre.capitalize()

    @staticmethod
    def _normalizar_metodo_pago(metodo):
        """Normalizar método de pago"""
        if not metodo:
            return 'No especificado'
        metodo = VentaReporte._limpiar_texto(metodo)
        # Map de métodos de pago comunes
        mapa = {
            'tarjeta': 'Tarjeta',
            'credito': 'Tarjeta de Crédito',
            'debito': 'Tarjeta de Débito',
            'paypal': 'PayPal',
            'efectivo': 'Efectivo',
            'transferencia': 'Transferencia Bancaria',
            'oxxo': 'OXXO',
            'mercadopago': 'Mercado Pago'
        }
        metodo_lower = metodo.lower()
        for key, value in mapa.items():
            if key in metodo_lower:
                return value
        return metodo.capitalize()

    @staticmethod
    def _limpiar_email(email):
        """Validar y limpiar email"""
        if not email or not isinstance(email, str):
            return ''
        email = email.strip().lower()
        # Regex básico de email
        if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return email
        return ''

    @staticmethod
    def _validar_fecha(fecha):
        """Validar que la fecha sea válida"""
        if not fecha:
            return None
        if isinstance(fecha, datetime):
            return fecha
        try:
            return datetime.strptime(fecha, '%Y-%m-%d')
        except:
            try:
                return datetime.strptime(fecha, '%d/%m/%Y')
            except:
                return None

    @classmethod
    def get_collection(cls):
        """Obtener la colección de pedidos (las ventas están en pedidos con estado completado)"""
        return current_app.db.pedidos

    @classmethod
    def get_ventas(cls, fecha_inicio=None, fecha_fin=None, estado=None):
        """
        Obtener ventas con filtros y limpieza
        - fecha_inicio: datetime
        - fecha_fin: datetime
        - estado: str (opcional)
        """
        db = current_app.db
        filtro = {}
        
        # Solo pedidos que han sido pagados o entregados
        estados_venta = ['pagado', 'entregado', 'completado', 'confirmado']
        if estado:
            filtro['estado'] = estado
        else:
            filtro['estado'] = {'$in': estados_venta}
        
        # Filtro de fechas
        if fecha_inicio or fecha_fin:
            filtro_fechas = {}
            if fecha_inicio:
                filtro_fechas['$gte'] = cls._validar_fecha(fecha_inicio) or fecha_inicio
            if fecha_fin:
                filtro_fechas['$lte'] = (cls._validar_fecha(fecha_fin) or fecha_fin) + timedelta(days=1)
            filtro['created_at'] = filtro_fechas
        
        # Obtener ventas
        ventas = list(db.pedidos.find(filtro).sort('created_at', -1))
        
        # Enriquecer con items y limpiar datos
        for venta in ventas:
            venta['_id'] = str(venta['_id'])
            
            # 🔥 LIMPIEZA DE TOTALES
            venta['total'] = cls._limpiar_precio(venta.get('total', 0))
            venta['subtotal'] = cls._limpiar_precio(venta.get('subtotal', 0))
            venta['iva'] = cls._limpiar_precio(venta.get('iva', 0))
            venta['envio'] = cls._limpiar_precio(venta.get('envio', 0))
            venta['total_unidades'] = cls._limpiar_cantidad(venta.get('total_unidades', 0))
            
            # 🔥 LIMPIEZA DE TEXTO
            if venta.get('numero_pedido'):
                venta['numero_pedido'] = cls._limpiar_texto(venta['numero_pedido'])
            if venta.get('usuario_nombre'):
                venta['usuario_nombre'] = cls._normalizar_nombre(venta['usuario_nombre'])
            if venta.get('usuario_email'):
                venta['usuario_email'] = cls._limpiar_email(venta['usuario_email'])
            if venta.get('estado'):
                venta['estado'] = cls._limpiar_texto(venta['estado']).lower()
            if venta.get('metodo_pago'):
                venta['metodo_pago'] = cls._normalizar_metodo_pago(venta['metodo_pago'])
            
            # 🔥 LIMPIEZA DE ITEMS
            items = venta.get('items', [])
            if isinstance(items, list):
                items_limpios = []
                for item in items:
                    item_limpio = {
                        'id': str(item.get('id', '')),
                        'nombre': cls._normalizar_nombre(item.get('nombre', 'Producto')),
                        'precio': cls._limpiar_precio(item.get('precio', 0)),
                        'cantidad': cls._limpiar_cantidad(item.get('cantidad', 1)),
                        'imagen': cls._limpiar_texto(item.get('imagen', 'default.jpg')),
                        'foto': cls._limpiar_texto(item.get('foto', 'default.jpg')),
                        'sku': cls._limpiar_texto(item.get('sku', ''))
                    }
                    # Limpiar atributos si existen
                    if item.get('atributos'):
                        atributos_limpios = {}
                        for key, value in item['atributos'].items():
                            if isinstance(value, str):
                                atributos_limpios[key] = cls._limpiar_texto(value)
                            else:
                                atributos_limpios[key] = value
                        item_limpio['atributos'] = atributos_limpios
                    items_limpios.append(item_limpio)
                venta['items_list'] = items_limpios
            elif isinstance(items, dict):
                items_limpios = []
                for item in list(items.values()):
                    item_limpio = {
                        'id': str(item.get('id', '')),
                        'nombre': cls._normalizar_nombre(item.get('nombre', 'Producto')),
                        'precio': cls._limpiar_precio(item.get('precio', 0)),
                        'cantidad': cls._limpiar_cantidad(item.get('cantidad', 1)),
                        'imagen': cls._limpiar_texto(item.get('imagen', 'default.jpg')),
                        'foto': cls._limpiar_texto(item.get('foto', 'default.jpg')),
                        'sku': cls._limpiar_texto(item.get('sku', ''))
                    }
                    if item.get('atributos'):
                        atributos_limpios = {}
                        for key, value in item['atributos'].items():
                            if isinstance(value, str):
                                atributos_limpios[key] = cls._limpiar_texto(value)
                            else:
                                atributos_limpios[key] = value
                        item_limpio['atributos'] = atributos_limpios
                    items_limpios.append(item_limpio)
                venta['items_list'] = items_limpios
            else:
                venta['items_list'] = []
        
        return ventas

    @classmethod
    def get_resumen_ventas(cls, fecha_inicio=None, fecha_fin=None):
        """
        Obtener resumen de ventas para el dashboard con limpieza
        """
        ventas = cls.get_ventas(fecha_inicio, fecha_fin)
        
        # 🔥 FILTRAR VENTAS VÁLIDAS (total > 0)
        ventas_validas = [v for v in ventas if v.get('total', 0) > 0]
        
        total_ventas = len(ventas_validas)
        total_monto = sum(v.get('total', 0) for v in ventas_validas)
        total_unidades = sum(v.get('total_unidades', 0) for v in ventas_validas)
        
        # Calcular promedio
        promedio_venta = total_monto / total_ventas if total_ventas > 0 else 0
        
        # Ventas por día
        ventas_por_dia = defaultdict(lambda: {'monto': 0, 'cantidad': 0})
        for v in ventas_validas:
            fecha = v.get('created_at')
            if fecha:
                if isinstance(fecha, datetime):
                    dia = fecha.strftime('%Y-%m-%d')
                else:
                    try:
                        dia = datetime.strptime(str(fecha), '%Y-%m-%d').strftime('%Y-%m-%d')
                    except:
                        continue
                ventas_por_dia[dia]['monto'] += v.get('total', 0)
                ventas_por_dia[dia]['cantidad'] += 1
        
        # Ventas por categoría
        ventas_por_categoria = defaultdict(float)
        for v in ventas_validas:
            items = v.get('items_list', [])
            for item in items:
                # Intentar obtener categoría del producto
                categoria = cls._get_categoria_producto(item.get('id'))
                if categoria:
                    categoria_normalizada = cls._normalizar_categoria(categoria)
                    ventas_por_categoria[categoria_normalizada] += item.get('precio', 0) * item.get('cantidad', 1)
                else:
                    ventas_por_categoria['Sin categoría'] += item.get('precio', 0) * item.get('cantidad', 1)
        
        # Ventas por método de pago (usar el ya normalizado)
        ventas_por_metodo = defaultdict(float)
        for v in ventas_validas:
            metodo = v.get('metodo_pago', 'No especificado')
            if not metodo:
                metodo = 'No especificado'
            ventas_por_metodo[metodo] += v.get('total', 0)
        
        # Top productos (con nombres normalizados)
        productos_vendidos = defaultdict(int)
        for v in ventas_validas:
            items = v.get('items_list', [])
            for item in items:
                nombre = item.get('nombre', 'Producto')
                if not nombre:
                    nombre = 'Producto'
                productos_vendidos[nombre] += item.get('cantidad', 1)
        
        top_productos = sorted(productos_vendidos.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            'total_ventas': total_ventas,
            'total_monto': total_monto,
            'total_unidades': total_unidades,
            'promedio_venta': promedio_venta,
            'ventas_por_dia': dict(ventas_por_dia),
            'ventas_por_categoria': dict(ventas_por_categoria),
            'ventas_por_metodo': dict(ventas_por_metodo),
            'top_productos': top_productos,
            'ventas_raw': ventas_validas
        }

    @classmethod
    def _get_categoria_producto(cls, producto_id):
        """Obtener categoría de un producto por su ID"""
        if not producto_id:
            return None
        try:
            db = current_app.db
            producto = db.productos.find_one({'_id': ObjectId(producto_id)})
            if producto:
                categoria_id = producto.get('categoria_id')
                if categoria_id:
                    try:
                        categoria = db.categorias.find_one({'_id': ObjectId(categoria_id)})
                        if categoria:
                            return categoria.get('nombre')
                    except:
                        pass
            return None
        except:
            return None

    @classmethod
    def get_ventas_export(cls, fecha_inicio=None, fecha_fin=None):
        """
        Obtener datos para exportar (CSV/PDF) con limpieza completa
        """
        ventas = cls.get_ventas(fecha_inicio, fecha_fin)
        
        datos_export = []
        for v in ventas:
            # 🔥 LIMPIEZA DE DATOS DE LA VENTA
            fecha_str = ''
            if v.get('created_at'):
                if isinstance(v['created_at'], datetime):
                    fecha_str = v['created_at'].strftime('%d/%m/%Y %H:%M')
                else:
                    fecha_str = str(v['created_at'])
            
            numero_pedido = cls._limpiar_texto(v.get('numero_pedido', ''))
            total_pedido = cls._limpiar_precio(v.get('total', 0))
            metodo_pago = cls._normalizar_metodo_pago(v.get('metodo_pago', ''))
            cliente = cls._normalizar_nombre(v.get('usuario_nombre', ''))
            estado = cls._limpiar_texto(v.get('estado', '')).capitalize()
            
            for item in v.get('items_list', []):
                # 🔥 LIMPIEZA DE DATOS DEL ITEM
                producto = cls._normalizar_nombre(item.get('nombre', 'Producto'))
                cantidad = cls._limpiar_cantidad(item.get('cantidad', 0))
                precio_unitario = cls._limpiar_precio(item.get('precio', 0))
                subtotal = round(precio_unitario * cantidad, 2)
                
                datos_export.append({
                    'Fecha': fecha_str,
                    'Pedido': numero_pedido,
                    'Producto': producto,
                    'Cantidad': cantidad,
                    'Precio Unitario': precio_unitario,
                    'Subtotal': subtotal,
                    'Total Pedido': total_pedido,
                    'Método Pago': metodo_pago,
                    'Cliente': cliente,
                    'Estado': estado
                })
        
        return datos_export

    @classmethod
    def limpiar_datos_masiva(cls):
        """
        Limpieza masiva de datos en la base de datos
        """
        db = current_app.db
        resultados = {
            'pedidos_actualizados': 0,
            'pedidos_eliminados': 0,
            'productos_actualizados': 0,
            'errores': []
        }
        
        try:
            # 1. 🔥 ELIMINAR PEDIDOS CON TOTAL INVALIDO
            resultado = db.pedidos.delete_many({
                '$or': [
                    {'total': {'$lt': 0}},
                    {'total': {'$eq': 0}},
                    {'total': {'$exists': False}}
                ]
            })
            resultados['pedidos_eliminados'] = resultado.deleted_count
            
            # 2. 🔥 ACTUALIZAR PEDIDOS CON DATOS LIMPIOS
            pedidos = db.pedidos.find({})
            for pedido in pedidos:
                try:
                    datos_actualizar = {}
                    
                    # Limpiar totales
                    if 'total' in pedido:
                        datos_actualizar['total'] = cls._limpiar_precio(pedido['total'])
                    if 'subtotal' in pedido:
                        datos_actualizar['subtotal'] = cls._limpiar_precio(pedido['subtotal'])
                    if 'iva' in pedido:
                        datos_actualizar['iva'] = cls._limpiar_precio(pedido['iva'])
                    if 'envio' in pedido:
                        datos_actualizar['envio'] = cls._limpiar_precio(pedido['envio'])
                    if 'total_unidades' in pedido:
                        datos_actualizar['total_unidades'] = cls._limpiar_cantidad(pedido['total_unidades'])
                    
                    # Limpiar textos
                    if 'numero_pedido' in pedido:
                        datos_actualizar['numero_pedido'] = cls._limpiar_texto(pedido['numero_pedido'])
                    if 'usuario_nombre' in pedido:
                        datos_actualizar['usuario_nombre'] = cls._normalizar_nombre(pedido['usuario_nombre'])
                    if 'estado' in pedido:
                        datos_actualizar['estado'] = cls._limpiar_texto(pedido['estado']).lower()
                    if 'metodo_pago' in pedido:
                        datos_actualizar['metodo_pago'] = cls._normalizar_metodo_pago(pedido['metodo_pago'])
                    
                    if datos_actualizar:
                        db.pedidos.update_one(
                            {'_id': pedido['_id']},
                            {'$set': datos_actualizar}
                        )
                        resultados['pedidos_actualizados'] += 1
                        
                except Exception as e:
                    resultados['errores'].append(f"Error en pedido {pedido.get('_id')}: {str(e)}")
            
            # 3. 🔥 LIMPIAR PRODUCTOS
            productos = db.productos.find({})
            for producto in productos:
                try:
                    datos_actualizar = {}
                    if 'nombre' in producto:
                        datos_actualizar['nombre'] = cls._normalizar_nombre(producto['nombre'])
                    if 'descripcion' in producto:
                        datos_actualizar['descripcion'] = cls._limpiar_texto(producto['descripcion'])
                    if 'precio' in producto:
                        datos_actualizar['precio'] = cls._limpiar_precio(producto['precio'])
                    if 'stock' in producto:
                        datos_actualizar['stock'] = cls._limpiar_cantidad(producto['stock'])
                    
                    if datos_actualizar:
                        db.productos.update_one(
                            {'_id': producto['_id']},
                            {'$set': datos_actualizar}
                        )
                        resultados['productos_actualizados'] += 1
                        
                except Exception as e:
                    resultados['errores'].append(f"Error en producto {producto.get('_id')}: {str(e)}")
            
            return resultados
            
        except Exception as e:
            resultados['errores'].append(f"Error general: {str(e)}")
            return resultados