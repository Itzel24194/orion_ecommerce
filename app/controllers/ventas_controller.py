# app/controllers/ventas_controller.py
# ================================================================
# CONTROLADOR PARA REPORTE DE VENTAS - CON REGRESIÓN LINEAL Y PAGINACIÓN
# ================================================================

from flask import render_template, request, redirect, url_for, session, flash, jsonify, current_app, make_response
from datetime import datetime, timedelta
from bson import ObjectId
from app.models.ventas_model import VentaReporte
from app.models.usuarios_model import Usuario
import csv
import io
import sys
import re
import math


# ================================================================
# FUNCIONES DE LIMPIEZA DE DATOS
# ================================================================

def limpiar_texto(texto):
    """Eliminar espacios extras y caracteres especiales básicos"""
    if not texto or not isinstance(texto, str):
        return ''
    texto = ' '.join(texto.split())
    texto = texto.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    return texto.strip()

def limpiar_precio(valor):
    """Asegurar que el precio sea un número válido positivo"""
    try:
        valor = float(valor)
        return max(0, round(valor, 2))
    except (ValueError, TypeError):
        return 0.0

def limpiar_cantidad(valor):
    """Asegurar que la cantidad sea un entero válido positivo"""
    try:
        valor = int(valor)
        return max(0, valor)
    except (ValueError, TypeError):
        return 0

def normalizar_nombre(nombre):
    """Normalizar nombre para consistencia"""
    if not nombre:
        return 'Sin nombre'
    nombre = limpiar_texto(nombre)
    palabras = nombre.split()
    palabras = [p.capitalize() if len(p) > 2 else p for p in palabras]
    return ' '.join(palabras)

def normalizar_categoria(nombre):
    """Normalizar nombre de categoría"""
    if not nombre:
        return 'Sin categoría'
    return limpiar_texto(nombre).capitalize()

def normalizar_metodo_pago(metodo):
    """Normalizar método de pago"""
    if not metodo:
        return 'No especificado'
    metodo = limpiar_texto(metodo)
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

def limpiar_email(email):
    """Validar y limpiar email"""
    if not email or not isinstance(email, str):
        return ''
    email = email.strip().lower()
    if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return email
    return ''

def validar_fecha(fecha):
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


# ================================================================
# FUNCIÓN DE NORMALIZACIÓN DE ROL
# ================================================================

def normalizar_rol(rol):
    """Normaliza el rol para comparación consistente"""
    if not rol:
        return 'cliente'
    rol = rol.lower().strip()
    if rol in ['administrador', 'admin', 'superadmin', 'root']:
        return 'admin'
    return rol


# ================================================================
# CÁLCULO DE REGRESIÓN LINEAL (MÍNIMOS CUADRADOS)
# ================================================================

def calcular_regresion_lineal(datos):
    """
    Calcula la regresión lineal simple (y = mx + b) y el coeficiente R².
    datos: lista de tuplas (x, y) donde x es un índice numérico (día) e y es el monto.
    Retorna: (pendiente, intercepto, r2, predichos)
    """
    n = len(datos)
    if n < 2:
        return 0, 0, 0, []
    
    x = [d[0] for d in datos]
    y = [d[1] for d in datos]
    
    sum_x = sum(x)
    sum_y = sum(y)
    sum_x2 = sum(xi**2 for xi in x)
    sum_xy = sum(xi*yi for xi, yi in zip(x, y))
    
    denominador = n * sum_x2 - sum_x**2
    if denominador == 0:
        return 0, 0, 0, []
    
    pendiente = (n * sum_xy - sum_x * sum_y) / denominador
    intercepto = (sum_y - pendiente * sum_x) / n
    
    # Predicciones para los mismos puntos
    predichos = [pendiente * xi + intercepto for xi in x]
    
    # R²
    media_y = sum_y / n
    ss_total = sum((yi - media_y)**2 for yi in y)
    ss_res = sum((yi - pi)**2 for yi, pi in zip(y, predichos))
    r2 = 1 - (ss_res / ss_total) if ss_total > 0 else 0
    
    return pendiente, intercepto, r2, predichos


# ================================================================
# ADMIN - REPORTE DE VENTAS (CON LIMPIEZA, REGRESIÓN Y PAGINACIÓN)
# ================================================================

def admin_reporte_ventas():
    """
    Panel de Reporte de Ventas - Estilo Liverpool con limpieza, regresión lineal y paginación
    """
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
    
    # 🔥 LIMPIEZA DE FILTROS
    fecha_inicio_str = request.args.get('fecha_inicio')
    fecha_fin_str = request.args.get('fecha_fin')
    
    if fecha_inicio_str:
        fecha_inicio_str = limpiar_texto(fecha_inicio_str)
    if fecha_fin_str:
        fecha_fin_str = limpiar_texto(fecha_fin_str)
    
    fecha_inicio = None
    fecha_fin = None
    
    if not fecha_inicio_str and not fecha_fin_str:
        fecha_fin = datetime.now()
        fecha_inicio = fecha_fin - timedelta(days=30)
    else:
        if fecha_inicio_str:
            try:
                fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
            except:
                pass
        if fecha_fin_str:
            try:
                fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
            except:
                pass
    
    # Obtener resumen de ventas (ya incluye limpieza en el modelo)
    resumen = VentaReporte.get_resumen_ventas(fecha_inicio, fecha_fin)
    
    # 🔥 LIMPIEZA DE DATOS PARA GRÁFICOS
    ventas_por_dia = resumen.get('ventas_por_dia', {})
    labels_dias = sorted(ventas_por_dia.keys())
    montos_dias = [limpiar_precio(ventas_por_dia[dia]['monto']) for dia in labels_dias]
    cantidades_dias = [limpiar_cantidad(ventas_por_dia[dia]['cantidad']) for dia in labels_dias]
    
    # 🔥 LIMPIEZA DE CATEGORÍAS
    categorias = resumen.get('ventas_por_categoria', {})
    categorias_ordenadas = sorted(categorias.items(), key=lambda x: x[1], reverse=True)
    labels_categorias = [normalizar_categoria(cat) for cat, _ in categorias_ordenadas]
    montos_categorias = [limpiar_precio(monto) for _, monto in categorias_ordenadas]
    
    # 🔥 LIMPIEZA DE MÉTODOS DE PAGO
    metodos = resumen.get('ventas_por_metodo', {})
    labels_metodos = [normalizar_metodo_pago(met) for met in metodos.keys()]
    montos_metodos = [limpiar_precio(monto) for monto in metodos.values()]
    
    # 🔥 LIMPIEZA DE TOP PRODUCTOS
    top_productos_raw = resumen.get('top_productos', [])
    top_productos = []
    for producto, cantidad in top_productos_raw:
        nombre_limpio = normalizar_nombre(producto)
        cantidad_limpia = limpiar_cantidad(cantidad)
        top_productos.append((nombre_limpio, cantidad_limpia))
    
    # 🔥 LIMPIEZA DE VENTAS RAW (LISTA COMPLETA)
    ventas_raw = resumen.get('ventas_raw', [])
    ventas_limpias = []
    for v in ventas_raw:
        venta_limpia = {
            '_id': v.get('_id', ''),
            'numero_pedido': limpiar_texto(v.get('numero_pedido', '')),
            'total': limpiar_precio(v.get('total', 0)),
            'subtotal': limpiar_precio(v.get('subtotal', 0)),
            'iva': limpiar_precio(v.get('iva', 0)),
            'envio': limpiar_precio(v.get('envio', 0)),
            'total_unidades': limpiar_cantidad(v.get('total_unidades', 0)),
            'usuario_nombre': normalizar_nombre(v.get('usuario_nombre', '')),
            'metodo_pago': normalizar_metodo_pago(v.get('metodo_pago', '')),
            'estado': limpiar_texto(v.get('estado', '')).lower(),
            'created_at': v.get('created_at'),
            'items_list': v.get('items_list', [])
        }
        ventas_limpias.append(venta_limpia)
    
    # ================================================================
    # PAGINACIÓN (NUEVO)
    # ================================================================
    total_ventas_count = len(ventas_limpias)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 20
    
    start = (page - 1) * per_page
    end = start + per_page
    ventas_pagina = ventas_limpias[start:end]
    total_pages = (total_ventas_count + per_page - 1) // per_page if total_ventas_count > 0 else 1
    
    # ================================================================
    # CÁLCULO DE REGRESIÓN LINEAL
    # ================================================================
    fechas_ordenadas = sorted(ventas_por_dia.keys())
    if len(fechas_ordenadas) >= 2:
        indices = list(range(len(fechas_ordenadas)))
        montos = [ventas_por_dia[f]['monto'] for f in fechas_ordenadas]
        datos_reg = list(zip(indices, montos))
        
        pendiente, intercepto, r2, predichos = calcular_regresion_lineal(datos_reg)
        
        ultimo_idx = indices[-1] if indices else 0
        futuros_indices = list(range(ultimo_idx + 1, ultimo_idx + 8))  # 7 días futuros
        futuros_predichos = [pendiente * i + intercepto for i in futuros_indices]
        
        fechas_str = [datetime.strptime(f, '%Y-%m-%d').strftime('%d/%m') for f in fechas_ordenadas]
        ultima_fecha = datetime.strptime(fechas_ordenadas[-1], '%Y-%m-%d') if fechas_ordenadas else datetime.now()
        futuras_fechas_str = [(ultima_fecha + timedelta(days=i+1)).strftime('%d/%m') for i in range(7)]
        
        proximo_dia = futuros_predichos[0] if futuros_predichos else 0
        
        regresion_data = {
            'pendiente': pendiente,
            'intercepto': intercepto,
            'r2': r2,
            'n_puntos': len(datos_reg),
            'fechas': fechas_str,
            'reales': montos,
            'predichos': predichos,
            'futuros_fechas': futuras_fechas_str,
            'futuros_predichos': futuros_predichos,
            'proximo_dia': proximo_dia
        }
    else:
        regresion_data = {
            'pendiente': 0,
            'intercepto': 0,
            'r2': 0,
            'n_puntos': 0,
            'fechas': [],
            'reales': [],
            'predichos': [],
            'futuros_fechas': [],
            'futuros_predichos': [],
            'proximo_dia': 0
        }
    
    # Totales para la vista
    total_ventas = limpiar_cantidad(resumen.get('total_ventas', 0))
    total_monto = limpiar_precio(resumen.get('total_monto', 0))
    total_unidades = limpiar_cantidad(resumen.get('total_unidades', 0))
    promedio_venta = limpiar_precio(resumen.get('promedio_venta', 0))
    
    return render_template('admin/reporte_ventas.html',
                         resumen=resumen,
                         fecha_inicio=fecha_inicio,
                         fecha_fin=fecha_fin,
                         labels_dias=labels_dias,
                         montos_dias=montos_dias,
                         cantidades_dias=cantidades_dias,
                         labels_categorias=labels_categorias,
                         montos_categorias=montos_categorias,
                         labels_metodos=labels_metodos,
                         montos_metodos=montos_metodos,
                         top_productos=top_productos,
                         ventas=ventas_limpias,          # lista completa (por si se necesita)
                         ventas_pagina=ventas_pagina,     # solo la página actual
                         total_ventas_count=total_ventas_count,
                         page=page,
                         per_page=per_page,
                         total_pages=total_pages,
                         total_ventas=total_ventas,
                         total_monto=total_monto,
                         total_unidades=total_unidades,
                         promedio_venta=promedio_venta,
                         regresion=regresion_data,
                         datetime=datetime)


# ================================================================
# ADMIN - EXPORTAR VENTAS A CSV (CON LIMPIEZA)
# ================================================================

def admin_exportar_ventas_csv():
    """Exportar ventas a CSV - Estilo Liverpool con limpieza"""
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    
    usuario = Usuario.obtener_por_id(session['user_id'])
    rol_normalizado = normalizar_rol(usuario.get('rol'))
    if rol_normalizado != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.dashboard'))
    
    fecha_inicio_str = request.args.get('fecha_inicio')
    fecha_fin_str = request.args.get('fecha_fin')
    
    if fecha_inicio_str:
        fecha_inicio_str = limpiar_texto(fecha_inicio_str)
    if fecha_fin_str:
        fecha_fin_str = limpiar_texto(fecha_fin_str)
    
    fecha_inicio = None
    fecha_fin = None
    
    if fecha_inicio_str:
        try:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
        except:
            pass
    if fecha_fin_str:
        try:
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
        except:
            pass
    
    datos = VentaReporte.get_ventas_export(fecha_inicio, fecha_fin)
    
    # Formatear fecha para mejor compatibilidad (YYYY-MM-DD HH:MM)
    datos_limpios = []
    for row in datos:
        fecha_raw = row.get('Fecha', '')
        if fecha_raw:
            try:
                dt = datetime.strptime(fecha_raw, '%d/%m/%Y %H:%M')
                fecha_formateada = dt.strftime('%Y-%m-%d %H:%M')
            except:
                fecha_formateada = fecha_raw
        else:
            fecha_formateada = ''
        
        row_limpio = {
            'Fecha': fecha_formateada,
            'Pedido': limpiar_texto(row.get('Pedido', '')),
            'Producto': normalizar_nombre(row.get('Producto', '')),
            'Cantidad': limpiar_cantidad(row.get('Cantidad', 0)),
            'Precio Unitario': limpiar_precio(row.get('Precio Unitario', 0)),
            'Subtotal': limpiar_precio(row.get('Subtotal', 0)),
            'Total Pedido': limpiar_precio(row.get('Total Pedido', 0)),
            'Método Pago': normalizar_metodo_pago(row.get('Método Pago', '')),
            'Cliente': normalizar_nombre(row.get('Cliente', '')),
            'Estado': limpiar_texto(row.get('Estado', '')).capitalize()
        }
        datos_limpios.append(row_limpio)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    if datos_limpios:
        headers = list(datos_limpios[0].keys())
        writer.writerow(headers)
        for row in datos_limpios:
            writer.writerow([row.get(h, '') for h in headers])
    else:
        writer.writerow(['No hay datos disponibles para el período seleccionado'])
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=ventas_{datetime.now().strftime("%Y%m%d")}.csv'
    
    return response


# ================================================================
# ADMIN - EXPORTAR VENTAS A PDF (CON LIMPIEZA Y REGRESIÓN LINEAL)
# ================================================================

def admin_exportar_ventas_pdf():
    """Exportar ventas a PDF - Estilo Liverpool con limpieza y regresión lineal"""
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    
    usuario = Usuario.obtener_por_id(session['user_id'])
    rol_normalizado = normalizar_rol(usuario.get('rol'))
    if rol_normalizado != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.dashboard'))
    
    fecha_inicio_str = request.args.get('fecha_inicio')
    fecha_fin_str = request.args.get('fecha_fin')
    
    if fecha_inicio_str:
        fecha_inicio_str = limpiar_texto(fecha_inicio_str)
    if fecha_fin_str:
        fecha_fin_str = limpiar_texto(fecha_fin_str)
    
    fecha_inicio = None
    fecha_fin = None
    
    if fecha_inicio_str:
        try:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
        except:
            pass
    if fecha_fin_str:
        try:
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
        except:
            pass
    
    resumen = VentaReporte.get_resumen_ventas(fecha_inicio, fecha_fin)
    ventas = resumen.get('ventas_raw', [])
    
    resumen_limpio = {
        'total_ventas': limpiar_cantidad(resumen.get('total_ventas', 0)),
        'total_monto': limpiar_precio(resumen.get('total_monto', 0)),
        'total_unidades': limpiar_cantidad(resumen.get('total_unidades', 0)),
        'promedio_venta': limpiar_precio(resumen.get('promedio_venta', 0)),
        'top_productos': [(normalizar_nombre(p), limpiar_cantidad(c)) for p, c in resumen.get('top_productos', [])],
        'ventas_por_categoria': {normalizar_categoria(k): limpiar_precio(v) for k, v in resumen.get('ventas_por_categoria', {}).items()},
        'ventas_por_metodo': {normalizar_metodo_pago(k): limpiar_precio(v) for k, v in resumen.get('ventas_por_metodo', {}).items()}
    }
    
    # ===== CALCULAR REGRESIÓN LINEAL PARA EL PDF =====
    ventas_por_dia = resumen.get('ventas_por_dia', {})
    fechas_ordenadas = sorted(ventas_por_dia.keys())
    regresion_data = {}
    if len(fechas_ordenadas) >= 2:
        indices = list(range(len(fechas_ordenadas)))
        montos = [ventas_por_dia[f]['monto'] for f in fechas_ordenadas]
        datos_reg = list(zip(indices, montos))
        
        pendiente, intercepto, r2, predichos = calcular_regresion_lineal(datos_reg)
        
        ultimo_idx = indices[-1] if indices else 0
        futuros_indices = list(range(ultimo_idx + 1, ultimo_idx + 8))  # 7 días
        futuros_predichos = [pendiente * i + intercepto for i in futuros_indices]
        
        ultima_fecha = datetime.strptime(fechas_ordenadas[-1], '%Y-%m-%d') if fechas_ordenadas else datetime.now()
        futuras_fechas_str = [(ultima_fecha + timedelta(days=i+1)).strftime('%d/%m/%Y') for i in range(7)]
        
        regresion_data = {
            'pendiente': pendiente,
            'intercepto': intercepto,
            'r2': r2,
            'n_puntos': len(datos_reg),
            'proximo_dia': futuros_predichos[0] if futuros_predichos else 0,
            'futuros_fechas': futuras_fechas_str,
            'futuros_predichos': futuros_predichos
        }
    else:
        regresion_data = {
            'pendiente': 0,
            'intercepto': 0,
            'r2': 0,
            'n_puntos': 0,
            'proximo_dia': 0,
            'futuros_fechas': [],
            'futuros_predichos': []
        }
    
    pdf_content = generar_pdf_ventas(resumen_limpio, ventas, fecha_inicio, fecha_fin, regresion_data)
    
    response = make_response(pdf_content)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=ventas_{datetime.now().strftime("%Y%m%d")}.pdf'
    
    return response


def _normalizar_unicode(texto):
    """Reemplaza caracteres Unicode problemáticos por equivalentes ASCII"""
    if not isinstance(texto, str):
        return texto
    # Mapeo de caracteres comunes
    replacements = {
        '\u2013': '-',   # guión largo
        '\u2014': '--',  # guión aún más largo
        '\u2018': "'",   # comilla simple izquierda
        '\u2019': "'",   # comilla simple derecha
        '\u201c': '"',   # comilla doble izquierda
        '\u201d': '"',   # comilla doble derecha
        '\u2026': '...', # puntos suspensivos
        '\u00a0': ' ',   # espacio no rompible
    }
    for unicode_char, ascii_char in replacements.items():
        texto = texto.replace(unicode_char, ascii_char)
    # Eliminar cualquier otro carácter no ASCII (opcional)
    # texto = texto.encode('ascii', 'ignore').decode('ascii')
    return texto


def generar_pdf_ventas(resumen, ventas, fecha_inicio, fecha_fin, regresion):
    """Generar PDF simple con datos de ventas, incluyendo regresión lineal"""
    fecha_inicio_str = fecha_inicio.strftime('%d/%m/%Y') if fecha_inicio else 'Inicio'
    fecha_fin_str = fecha_fin.strftime('%d/%m/%Y') if fecha_fin else 'Hoy'
    
    lineas = [
        "=" * 60,
        "              REPORTE DE VENTAS ORION",
        "=" * 60,
        "",
        f"Periodo: {fecha_inicio_str} a {fecha_fin_str}",
        f"Fecha de generación: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        "",
        "-" * 60,
        "RESUMEN DE VENTAS",
        "-" * 60,
        f"Total Pedidos: {resumen.get('total_ventas', 0)}",
        f"Total Ventas: ${resumen.get('total_monto', 0):.2f}",
        f"Total Unidades: {resumen.get('total_unidades', 0)}",
        f"Promedio por Venta: ${resumen.get('promedio_venta', 0):.2f}",
        "",
        "-" * 60,
        "TOP 10 PRODUCTOS MÁS VENDIDOS",
        "-" * 60,
    ]
    
    top_productos = resumen.get('top_productos', [])
    if top_productos:
        for i, (producto, cantidad) in enumerate(top_productos[:10], 1):
            lineas.append(f"{i}. {producto} - {cantidad} unidades")
    else:
        lineas.append("No hay datos disponibles")
    
    lineas.append("")
    lineas.append("-" * 60)
    lineas.append("VENTAS POR CATEGORÍA")
    lineas.append("-" * 60)
    
    categorias = resumen.get('ventas_por_categoria', {})
    if categorias:
        for categoria, monto in sorted(categorias.items(), key=lambda x: x[1], reverse=True):
            lineas.append(f"{categoria}: ${monto:.2f}")
    else:
        lineas.append("No hay datos disponibles")
    
    lineas.append("")
    lineas.append("-" * 60)
    lineas.append("VENTAS POR MÉTODO DE PAGO")
    lineas.append("-" * 60)
    
    metodos = resumen.get('ventas_por_metodo', {})
    if metodos:
        for metodo, monto in metodos.items():
            lineas.append(f"{metodo}: ${monto:.2f}")
    else:
        lineas.append("No hay datos disponibles")
    
    # ===== SECCIÓN DE REGRESIÓN LINEAL =====
    lineas.append("")
    lineas.append("-" * 60)
    lineas.append("REGRESIÓN LINEAL – PRONÓSTICO DE VENTAS")
    lineas.append("-" * 60)
    
    if regresion.get('n_puntos', 0) >= 2:
        pendiente = regresion['pendiente']
        intercepto = regresion['intercepto']
        r2 = regresion['r2']
        proximo_dia = regresion['proximo_dia']
        
        lineas.append(f"Ecuación: y = {pendiente:.2f}x + {intercepto:.2f}")
        lineas.append(f"Coeficiente de determinación (R²): {r2:.4f}")
        lineas.append(f"Datos usados: {regresion['n_puntos']} días")
        lineas.append(f"Próximo día estimado: ${proximo_dia:.2f}")
        lineas.append("")
        lineas.append("Proyección para los próximos 7 días:")
        futuros_fechas = regresion.get('futuros_fechas', [])
        futuros_predichos = regresion.get('futuros_predichos', [])
        if futuros_fechas and futuros_predichos:
            for fecha, monto in zip(futuros_fechas, futuros_predichos):
                lineas.append(f"  {fecha}: ${monto:.2f}")
        else:
            lineas.append("  No hay datos suficientes para proyectar.")
    else:
        lineas.append("No hay suficientes datos para calcular regresión lineal (se necesitan al menos 2 días con ventas).")
    
    lineas.append("")
    lineas.append("=" * 60)
    lineas.append("       Fin del reporte")
    lineas.append("=" * 60)
    
    # Normalizar caracteres Unicode antes de codificar
    lineas_normalizadas = [_normalizar_unicode(linea) for linea in lineas]
    
    def _pdf_escape(text):
        # Escapar paréntesis y barras invertidas para PDF
        text = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        return text
    
    stream_lines = [
        "BT",
        "/F1 10 Tf",
        "50 760 Td",
        "12 TL"
    ]
    for i, linea in enumerate(lineas_normalizadas):
        stream_lines.append(f"({_pdf_escape(linea)}) Tj")
        if i < len(lineas_normalizadas) - 1:
            stream_lines.append("T*")
    stream_lines.append("ET")
    
    # Ahora codificar a latin-1 (todos los caracteres son ASCII después de la normalización)
    stream = "\n".join(stream_lines).encode('latin-1')
    
    objects = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    )
    objects.append(
        f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode('latin-1') + stream + b"\nendstream\nendobj\n"
    )
    objects.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    
    pdf = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    position = len(pdf[0])
    for obj in objects:
        offsets.append(position)
        pdf.append(obj)
        position += len(obj)
    
    xref_lines = [b"xref\n0 6\n0000000000 65535 f \n"]
    for offset in offsets[1:]:
        xref_lines.append(f"{offset:010} 00000 n \n".encode('latin-1'))
    
    startxref = position
    pdf.extend(xref_lines)
    pdf.append(
        f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF\n".encode('latin-1')
    )
    
    return b"".join(pdf)


# ================================================================
# API - DATOS DE VENTAS (CON LIMPIEZA)
# ================================================================

def admin_ventas_api():
    """API para obtener datos de ventas (para gráficos en tiempo real) con limpieza"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    usuario = Usuario.obtener_por_id(session['user_id'])
    rol_normalizado = normalizar_rol(usuario.get('rol'))
    if rol_normalizado != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    periodo = request.args.get('periodo', '30dias')
    periodo = limpiar_texto(periodo)
    
    fecha_fin = datetime.now()
    if periodo == '7dias':
        fecha_inicio = fecha_fin - timedelta(days=7)
    elif periodo == '15dias':
        fecha_inicio = fecha_fin - timedelta(days=15)
    elif periodo == '30dias':
        fecha_inicio = fecha_fin - timedelta(days=30)
    elif periodo == '90dias':
        fecha_inicio = fecha_fin - timedelta(days=90)
    elif periodo == '12meses':
        fecha_inicio = fecha_fin - timedelta(days=365)
    else:
        fecha_inicio = fecha_fin - timedelta(days=30)
    
    resumen = VentaReporte.get_resumen_ventas(fecha_inicio, fecha_fin)
    
    ventas_por_dia = {}
    for dia, data in resumen.get('ventas_por_dia', {}).items():
        ventas_por_dia[dia] = {
            'monto': limpiar_precio(data['monto']),
            'cantidad': limpiar_cantidad(data['cantidad'])
        }
    
    ventas_por_categoria = {}
    for cat, monto in resumen.get('ventas_por_categoria', {}).items():
        ventas_por_categoria[normalizar_categoria(cat)] = limpiar_precio(monto)
    
    ventas_por_metodo = {}
    for metodo, monto in resumen.get('ventas_por_metodo', {}).items():
        ventas_por_metodo[normalizar_metodo_pago(metodo)] = limpiar_precio(monto)
    
    top_productos = []
    for producto, cantidad in resumen.get('top_productos', []):
        top_productos.append((normalizar_nombre(producto), limpiar_cantidad(cantidad)))
    
    return jsonify({
        'success': True,
        'total_ventas': limpiar_cantidad(resumen.get('total_ventas', 0)),
        'total_monto': limpiar_precio(resumen.get('total_monto', 0)),
        'total_unidades': limpiar_cantidad(resumen.get('total_unidades', 0)),
        'promedio_venta': limpiar_precio(resumen.get('promedio_venta', 0)),
        'ventas_por_dia': ventas_por_dia,
        'ventas_por_categoria': ventas_por_categoria,
        'ventas_por_metodo': ventas_por_metodo,
        'top_productos': top_productos
    })


def admin_ventas_resumen_api():
    """API para resumen de ventas (KPIs) con limpieza"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    usuario = Usuario.obtener_por_id(session['user_id'])
    rol_normalizado = normalizar_rol(usuario.get('rol'))
    if rol_normalizado != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    fecha_inicio_str = request.args.get('fecha_inicio')
    fecha_fin_str = request.args.get('fecha_fin')
    
    if fecha_inicio_str:
        fecha_inicio_str = limpiar_texto(fecha_inicio_str)
    if fecha_fin_str:
        fecha_fin_str = limpiar_texto(fecha_fin_str)
    
    fecha_inicio = None
    fecha_fin = None
    
    if fecha_inicio_str:
        try:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
        except:
            pass
    if fecha_fin_str:
        try:
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
        except:
            pass
    
    resumen = VentaReporte.get_resumen_ventas(fecha_inicio, fecha_fin)
    
    return jsonify({
        'success': True,
        'total_ventas': limpiar_cantidad(resumen.get('total_ventas', 0)),
        'total_monto': limpiar_precio(resumen.get('total_monto', 0)),
        'total_unidades': limpiar_cantidad(resumen.get('total_unidades', 0)),
        'promedio_venta': limpiar_precio(resumen.get('promedio_venta', 0))
    })


# ================================================================
# FUNCIÓN DE LIMPIEZA MASIVA (EJECUCIÓN ÚNICA)
# ================================================================

def admin_limpiar_datos_ventas():
    """Endpoint para ejecutar limpieza masiva de datos de ventas"""
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    usuario = Usuario.obtener_por_id(session['user_id'])
    rol_normalizado = normalizar_rol(usuario.get('rol'))
    if rol_normalizado != 'admin':
        return jsonify({'error': 'No autorizado'}), 403
    
    try:
        resultados = VentaReporte.limpiar_datos_masiva()
        return jsonify({
            'success': True,
            'message': 'Limpieza de datos completada',
            'resultados': resultados
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500