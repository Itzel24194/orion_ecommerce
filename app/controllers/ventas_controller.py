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
        
        # 🔥 fechas "bonitas" (dd/mm) SOLO para mostrar en el eje/tooltip
        fechas_str = [datetime.strptime(f, '%Y-%m-%d').strftime('%d/%m') for f in fechas_ordenadas]
        ultima_fecha = datetime.strptime(fechas_ordenadas[-1], '%Y-%m-%d') if fechas_ordenadas else datetime.now()
        futuras_fechas_str = [(ultima_fecha + timedelta(days=i+1)).strftime('%d/%m') for i in range(7)]
        
        proximo_dia = futuros_predichos[0] if futuros_predichos else 0
        
        regresion_data = {
            'pendiente': pendiente,
            'intercepto': intercepto,
            'r2': r2,
            'n_puntos': len(datos_reg),
            'fechas': fechas_str,             # dd/mm -> solo para mostrar
            'fechas_iso': fechas_ordenadas,    # 🔥 YYYY-MM-DD -> para el clic/redirección al detalle
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
            'fechas_iso': [],
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


# ================================================================
# GENERADOR DE PDF — SIN DEPENDENCIAS EXTERNAS
# ================================================================
# Se mantiene 100% con la librería estándar (sin reportlab / weasyprint)
# para no introducir nuevas dependencias en el proyecto, pero ahora con:
#   - Encabezado con banda de color y título
#   - Tarjetas KPI (igual que el dashboard)
#   - Tablas con encabezado, filas alternadas y columnas alineadas
#   - Secciones con línea divisoria y acento de color
#   - Paginación automática (salto de página cuando el contenido no cabe)
#   - Pie de página con número de página y fecha de generación
#   - Codificación WinAnsi en las fuentes -> corrige acentos y ñ,
#     que antes se perdían o se veían mal (á, é, í, ó, ú, ñ, ¿, ¡)
# ================================================================

def _normalizar_unicode(texto):
    """Reemplaza caracteres Unicode tipográficos (no cubiertos por
    WinAnsiEncoding) por equivalentes simples."""
    if not isinstance(texto, str):
        return texto
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
    return texto


def _pdf_escape(text):
    """Escapa paréntesis y barras invertidas para que el texto sea
    válido dentro de una cadena literal de PDF: (texto)"""
    if not isinstance(text, str):
        text = str(text)
    return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _truncar(texto, max_chars):
    texto = str(texto)
    if len(texto) <= max_chars:
        return texto
    return texto[:max(0, max_chars - 1)] + '…'.replace('…', '...')


class PDFBuilder:
    """Generador de PDF minimalista (sin dependencias externas) con
    soporte para múltiples páginas, texto en negritas/color, tarjetas
    KPI y tablas básicas, pensado para reportes tipo dashboard."""

    PAGE_WIDTH = 612
    PAGE_HEIGHT = 792
    MARGIN_LEFT = 45
    MARGIN_RIGHT = 45
    MARGIN_TOP = 45
    MARGIN_BOTTOM = 50

    COLOR_PRIMARY = (0.902, 0.0, 0.494)    # #E6007E
    COLOR_PRIMARY_DARK = (0.722, 0.0, 0.373)
    COLOR_NAVY = (0.078, 0.129, 0.239)     # #14213D
    COLOR_MUTED = (0.42, 0.45, 0.5)
    COLOR_SUCCESS = (0.0, 0.651, 0.314)    # #00A650
    COLOR_WARNING = (1.0, 0.6, 0.0)        # #FF9900
    COLOR_INFO = (0.0, 0.455, 0.761)       # #0074C2
    COLOR_LIGHT = (0.96, 0.96, 0.98)
    COLOR_WHITE = (1, 1, 1)
    COLOR_BLACK = (0.05, 0.05, 0.08)

    def __init__(self):
        self.pages = []
        self.page_num = 0
        self.y = 0
        self._new_page()

    # ---------------- utilidades internas ----------------
    def _new_page(self):
        self.page_num += 1
        self.pages.append([])
        self.y = self.PAGE_HEIGHT - self.MARGIN_TOP
        if self.page_num > 1:
            self._raw_text(self.MARGIN_LEFT, self.y, "Reporte de Ventas - ORION (continuacion)",
                            size=8, color=self.COLOR_MUTED)
            self.y -= 22

    def _cmd(self, s):
        self.pages[-1].append(s)

    def _ensure_space(self, altura):
        if self.y - altura < self.MARGIN_BOTTOM:
            self._dibujar_pie()
            self._new_page()

    def _dibujar_pie(self):
        self._set_color(*self.COLOR_MUTED, stroke=True)
        self._cmd(f"0.6 w {self.MARGIN_LEFT} 40 m {self.PAGE_WIDTH - self.MARGIN_RIGHT} 40 l S")
        texto = f"Pagina {self.page_num}  -  Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        self._raw_text(self.MARGIN_LEFT, 27, texto, size=7.5, color=self.COLOR_MUTED)
        self._raw_text(self.PAGE_WIDTH - self.MARGIN_RIGHT - 60, 27, "ORION Admin", size=7.5, color=self.COLOR_MUTED)

    # ---------------- primitivas de dibujo ----------------
    def _set_color(self, r, g, b, stroke=False):
        op = "RG" if stroke else "rg"
        self._cmd(f"{r:.3f} {g:.3f} {b:.3f} {op}")

    def _rect(self, x, y, w, h, color=None, stroke_color=None, line_width=1):
        if stroke_color:
            self._set_color(*stroke_color, stroke=True)
            self._cmd(f"{line_width} w")
        if color:
            self._set_color(*color, stroke=False)
        self._cmd(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re")
        if color and stroke_color:
            self._cmd("B")
        elif color:
            self._cmd("f")
        elif stroke_color:
            self._cmd("S")

    def _raw_text(self, x, y, text, size=10, bold=False, color=None):
        if color:
            self._set_color(*color, stroke=False)
        font = "/F2" if bold else "/F1"
        texto = _pdf_escape(_normalizar_unicode(str(text)))
        self._cmd(f"BT {font} {size:.1f} Tf {x:.2f} {y:.2f} Td ({texto}) Tj ET")

    # ---------------- API pública de contenido ----------------
    def titulo_principal(self, texto, subtitulo=None):
        self._ensure_space(64)
        alto_banda = 54
        self._rect(0, self.y - (alto_banda - 40), self.PAGE_WIDTH, alto_banda, color=self.COLOR_NAVY)
        self._raw_text(self.MARGIN_LEFT, self.y - 12, texto, size=18, bold=True, color=self.COLOR_WHITE)
        if subtitulo:
            self._raw_text(self.MARGIN_LEFT, self.y - 28, subtitulo, size=9, color=(0.85, 0.87, 0.93))
        self.y -= (alto_banda - 40 + 16)

    def seccion(self, texto):
        self._ensure_space(34)
        self._rect(self.MARGIN_LEFT, self.y - 3, 4, 15, color=self.COLOR_PRIMARY)
        self._raw_text(self.MARGIN_LEFT + 12, self.y, texto, size=12.5, bold=True, color=self.COLOR_NAVY)
        self.y -= 9
        self._set_color(0.90, 0.91, 0.95, stroke=True)
        self._cmd(f"0.75 w {self.MARGIN_LEFT} {self.y:.2f} m {self.PAGE_WIDTH - self.MARGIN_RIGHT} {self.y:.2f} l S")
        self.y -= 16

    def parrafo(self, texto, size=9.5, color=None, bold=False):
        self._ensure_space(size + 7)
        self._raw_text(self.MARGIN_LEFT, self.y, texto, size=size, bold=bold, color=color or self.COLOR_BLACK)
        self.y -= (size + 7)

    def espacio(self, alto=8):
        self.y -= alto

    def tarjetas_kpi(self, tarjetas):
        """tarjetas: lista de tuplas (etiqueta, valor, color_rgb)"""
        self._ensure_space(62)
        n = max(1, len(tarjetas))
        ancho_total = self.PAGE_WIDTH - self.MARGIN_LEFT - self.MARGIN_RIGHT
        gap = 10
        ancho = (ancho_total - gap * (n - 1)) / n
        x = self.MARGIN_LEFT
        y_top = self.y
        for etiqueta, valor, color in tarjetas:
            self._rect(x, y_top - 52, ancho, 52, color=self.COLOR_LIGHT)
            self._rect(x, y_top - 4, ancho, 4, color=color)
            self._raw_text(x + 10, y_top - 23, _truncar(valor, 22), size=14, bold=True, color=self.COLOR_NAVY)
            self._raw_text(x + 10, y_top - 40, _truncar(etiqueta, 26), size=7.2, color=self.COLOR_MUTED)
            x += ancho + gap
        self.y = y_top - 52 - 18

    def tabla(self, encabezados, filas, anchos=None):
        ancho_total = self.PAGE_WIDTH - self.MARGIN_LEFT - self.MARGIN_RIGHT
        if not anchos:
            anchos = [ancho_total / len(encabezados)] * len(encabezados)

        def _dibujar_encabezado():
            self._ensure_space(24)
            x = self.MARGIN_LEFT
            self._rect(self.MARGIN_LEFT, self.y - 5, ancho_total, 20, color=self.COLOR_NAVY)
            for i, enc in enumerate(encabezados):
                self._raw_text(x + 7, self.y + 1, enc, size=8, bold=True, color=self.COLOR_WHITE)
                x += anchos[i]
            self.y -= 22

        _dibujar_encabezado()
        for idx_fila, fila in enumerate(filas):
            if self.y - 17 < self.MARGIN_BOTTOM:
                self._dibujar_pie()
                self._new_page()
                _dibujar_encabezado()
            if idx_fila % 2 == 0:
                self._rect(self.MARGIN_LEFT, self.y - 4, ancho_total, 17, color=self.COLOR_LIGHT)
            x = self.MARGIN_LEFT
            for i, val in enumerate(fila):
                es_bold = (i == 0)
                self._raw_text(x + 7, self.y, str(val), size=8.3, bold=es_bold, color=self.COLOR_NAVY)
                x += anchos[i]
            self.y -= 17
        self.y -= 10

    def render(self):
        self._dibujar_pie()
        return self._build_pdf_bytes()

    # ---------------- construcción binaria del PDF ----------------
    def _build_pdf_bytes(self):
        n_pages = len(self.pages)
        pages_obj_id = 2
        page_ids = [3 + i * 2 for i in range(n_pages)]
        content_ids = [4 + i * 2 for i in range(n_pages)]
        font_regular_id = 2 * n_pages + 3
        font_bold_id = font_regular_id + 1

        objects = []
        kids = " ".join(f"{pid} 0 R" for pid in page_ids)
        objects.append((1, f"<< /Type /Catalog /Pages {pages_obj_id} 0 R >>"))
        objects.append((pages_obj_id, f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>"))

        for i in range(n_pages):
            pid = page_ids[i]
            cid = content_ids[i]
            objects.append((pid,
                f"<< /Type /Page /Parent {pages_obj_id} 0 R /MediaBox [0 0 {self.PAGE_WIDTH} {self.PAGE_HEIGHT}] "
                f"/Contents {cid} 0 R /Resources << /Font << /F1 {font_regular_id} 0 R /F2 {font_bold_id} 0 R >> >> >>"))
            stream_bytes = "\n".join(self.pages[i]).encode('latin-1', errors='replace')
            objects.append((cid, ("STREAM", stream_bytes)))

        objects.append((font_regular_id,
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"))
        objects.append((font_bold_id,
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"))

        objects.sort(key=lambda o: o[0])

        pdf_chunks = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
        offsets = {}
        position = len(pdf_chunks[0])
        max_id = objects[-1][0]

        for obj_id, content in objects:
            offsets[obj_id] = position
            if isinstance(content, tuple) and content[0] == "STREAM":
                stream_bytes = content[1]
                header = f"{obj_id} 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode('latin-1')
                footer = b"\nendstream\nendobj\n"
                chunk = header + stream_bytes + footer
            else:
                chunk = f"{obj_id} 0 obj\n{content}\nendobj\n".encode('latin-1')
            pdf_chunks.append(chunk)
            position += len(chunk)

        xref_start = position
        xref_lines = [f"xref\n0 {max_id + 1}\n0000000000 65535 f \n"]
        for i in range(1, max_id + 1):
            off = offsets.get(i)
            xref_lines.append(f"{off:010} 00000 n \n" if off is not None else "0000000000 00000 f \n")
        pdf_chunks.append("".join(xref_lines).encode('latin-1'))
        pdf_chunks.append(
            f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode('latin-1')
        )

        return b"".join(pdf_chunks)


def generar_pdf_ventas(resumen, ventas, fecha_inicio, fecha_fin, regresion):
    """Genera el PDF del reporte de ventas: encabezado, tarjetas KPI,
    tablas de productos/categorías/métodos de pago y proyección de la
    regresión lineal, con paginación automática y pie de página."""
    fecha_inicio_str = fecha_inicio.strftime('%d/%m/%Y') if fecha_inicio else 'Inicio'
    fecha_fin_str = fecha_fin.strftime('%d/%m/%Y') if fecha_fin else 'Hoy'

    doc = PDFBuilder()
    doc.titulo_principal(
        "Reporte de Ventas - ORION",
        subtitulo=f"Periodo: {fecha_inicio_str}  -  {fecha_fin_str}"
    )
    doc.espacio(4)

    # ----- Resumen general -----
    doc.seccion("Resumen General")
    doc.tarjetas_kpi([
        ("TOTAL PEDIDOS", str(resumen.get('total_ventas', 0)), PDFBuilder.COLOR_PRIMARY),
        ("TOTAL VENTAS", f"${resumen.get('total_monto', 0):.2f}", PDFBuilder.COLOR_SUCCESS),
        ("UNIDADES VENDIDAS", str(resumen.get('total_unidades', 0)), PDFBuilder.COLOR_WARNING),
        ("PROMEDIO POR VENTA", f"${resumen.get('promedio_venta', 0):.2f}", PDFBuilder.COLOR_INFO),
    ])

    # ----- Top productos -----
    doc.seccion("Top 10 Productos Mas Vendidos")
    top_productos = resumen.get('top_productos', [])
    if top_productos:
        filas = [(str(i), _truncar(producto, 55), f"{cantidad} u.")
                 for i, (producto, cantidad) in enumerate(top_productos[:10], 1)]
        doc.tabla(["#", "Producto", "Unidades"], filas, anchos=[32, 385, 88])
    else:
        doc.parrafo("No hay datos disponibles.", color=PDFBuilder.COLOR_MUTED)

    # ----- Categorías -----
    doc.seccion("Ventas por Categoria")
    categorias = resumen.get('ventas_por_categoria', {})
    if categorias:
        total_cat = sum(categorias.values()) or 1
        filas = []
        for categoria, monto in sorted(categorias.items(), key=lambda x: x[1], reverse=True):
            pct = (monto / total_cat) * 100
            filas.append((_truncar(categoria, 42), f"${monto:.2f}", f"{pct:.1f}%"))
        doc.tabla(["Categoria", "Monto", "% del Total"], filas, anchos=[285, 130, 90])
    else:
        doc.parrafo("No hay datos disponibles.", color=PDFBuilder.COLOR_MUTED)

    # ----- Métodos de pago -----
    doc.seccion("Ventas por Metodo de Pago")
    metodos = resumen.get('ventas_por_metodo', {})
    if metodos:
        total_met = sum(metodos.values()) or 1
        filas = []
        for metodo, monto in sorted(metodos.items(), key=lambda x: x[1], reverse=True):
            pct = (monto / total_met) * 100
            filas.append((_truncar(metodo, 42), f"${monto:.2f}", f"{pct:.1f}%"))
        doc.tabla(["Metodo de Pago", "Monto", "% del Total"], filas, anchos=[285, 130, 90])
    else:
        doc.parrafo("No hay datos disponibles.", color=PDFBuilder.COLOR_MUTED)

    # ----- Regresión lineal / proyección -----
    doc.seccion("Regresion Lineal - Pronostico de Ventas")
    if regresion.get('n_puntos', 0) >= 2:
        pendiente = regresion['pendiente']
        intercepto = regresion['intercepto']
        r2 = regresion['r2']
        proximo_dia = regresion['proximo_dia']

        doc.tarjetas_kpi([
            ("ECUACION", f"y={pendiente:.2f}x+{intercepto:.2f}", PDFBuilder.COLOR_PRIMARY),
            ("R2 (AJUSTE)", f"{r2:.4f}", PDFBuilder.COLOR_INFO),
            ("DATOS USADOS", f"{regresion['n_puntos']} dias", PDFBuilder.COLOR_WARNING),
            ("PROX. DIA EST.", f"${proximo_dia:.2f}", PDFBuilder.COLOR_SUCCESS),
        ])

        doc.parrafo("Proyeccion para los proximos 7 dias:", bold=True, size=9.5, color=PDFBuilder.COLOR_NAVY)
        futuros_fechas = regresion.get('futuros_fechas', [])
        futuros_predichos = regresion.get('futuros_predichos', [])
        if futuros_fechas and futuros_predichos:
            filas = [(fecha, f"${monto:.2f}") for fecha, monto in zip(futuros_fechas, futuros_predichos)]
            doc.tabla(["Fecha", "Monto Estimado"], filas, anchos=[260, 245])
        else:
            doc.parrafo("No hay datos suficientes para proyectar.", color=PDFBuilder.COLOR_MUTED)
    else:
        doc.parrafo(
            "No hay suficientes datos para calcular la regresion lineal "
            "(se necesitan al menos 2 dias con ventas).",
            color=PDFBuilder.COLOR_MUTED
        )

    return doc.render()


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


# ================================================================
# 🆕 ADMIN - DETALLE DE VENTAS POR FECHA (API PARA MODAL) - CORREGIDO
# ================================================================

def admin_detalle_ventas_por_fecha():
    """
    API para obtener el detalle completo de ventas de un día específico.
    Se usa en el modal del reporte de ventas al hacer clic en una barra o punto del gráfico.

    🔥 CORREGIDO: antes esto consultaba una colección 'ventas' (campo 'fecha') que
    no es la misma que usa el reporte/regresión (colección 'pedidos', campo 'created_at'),
    por eso siempre salía vacío. Ahora reutilizamos VentaReporte.get_ventas() para
    garantizar que se lea exactamente la misma fuente de datos que la gráfica.
    """
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'No autenticado'}), 401
    
    usuario = Usuario.obtener_por_id(session['user_id'])
    rol_normalizado = normalizar_rol(usuario.get('rol'))
    if rol_normalizado != 'admin':
        return jsonify({'success': False, 'error': 'No autorizado'}), 403
    
    fecha_str = request.args.get('fecha')
    if not fecha_str:
        return jsonify({'success': False, 'error': 'Fecha no proporcionada'}), 400
    
    # Limpiar fecha
    fecha_str = limpiar_texto(fecha_str)
    
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
    except ValueError:
        try:
            fecha = datetime.strptime(fecha_str, '%d/%m/%Y')
            fecha_str = fecha.strftime('%Y-%m-%d')
        except ValueError:
            return jsonify({'success': False, 'error': 'Formato de fecha inválido. Usa YYYY-MM-DD'}), 400
    
    # 🔥 Mismo modelo/colección/campo que usa el reporte (pedidos + created_at)
    pedidos_dia = VentaReporte.get_ventas(fecha_inicio=fecha, fecha_fin=fecha)
    pedidos_dia = [v for v in pedidos_dia if v.get('total', 0) > 0]
    
    if not pedidos_dia:
        return jsonify({
            'success': True,
            'fecha': fecha_str,
            'total_ventas': 0,
            'total_monto': 0.0,
            'total_unidades': 0,
            'total_clientes': 0,
            'productos': [],
            'clientes': [],
            'metodos_pago': {},
            'ventas': []
        })
    
    total_monto = limpiar_precio(sum(v.get('total', 0) for v in pedidos_dia))
    total_unidades = limpiar_cantidad(sum(v.get('total_unidades', 0) for v in pedidos_dia))
    
    # Procesar productos vendidos (agrupar por nombre) usando items_list ya limpio
    productos_vendidos = {}
    clientes = set()
    metodos_pago = {}
    
    for venta in pedidos_dia:
        cliente = venta.get('usuario_nombre') or 'Anónimo'
        clientes.add(cliente)
        
        metodo = venta.get('metodo_pago') or 'No especificado'
        metodos_pago[metodo] = metodos_pago.get(metodo, 0) + 1
        
        for item in venta.get('items_list', []):
            nombre = item.get('nombre', 'Producto sin nombre')
            cantidad = limpiar_cantidad(item.get('cantidad', 0))
            precio = limpiar_precio(item.get('precio', 0))
            
            if nombre not in productos_vendidos:
                productos_vendidos[nombre] = {
                    'nombre': nombre,
                    'cantidad': 0,
                    'total': 0.0,
                    'precio_unitario': precio
                }
            productos_vendidos[nombre]['cantidad'] += cantidad
            productos_vendidos[nombre]['total'] += limpiar_precio(precio * cantidad)
    
    # Convertir a lista y ordenar por cantidad
    lista_productos = sorted(
        productos_vendidos.values(),
        key=lambda x: x['cantidad'],
        reverse=True
    )
    
    # Preparar lista de ventas individuales (con hora)
    ventas_lista = []
    for v in pedidos_dia[:20]:  # Últimas 20 ventas
        hora = 'N/A'
        if v.get('created_at'):
            try:
                hora = v['created_at'].strftime('%H:%M')
            except:
                pass
        ventas_lista.append({
            'numero_pedido': v.get('numero_pedido', 'N/A'),
            'cliente': v.get('usuario_nombre', 'Anónimo'),
            'total': limpiar_precio(v.get('total', 0)),
            'metodo_pago': v.get('metodo_pago', 'N/A'),
            'estado': (v.get('estado') or 'pagada').capitalize(),
            'hora': hora
        })
    
    response = {
        'success': True,
        'fecha': fecha_str,
        'total_ventas': len(pedidos_dia),
        'total_monto': total_monto,
        'total_unidades': total_unidades,
        'total_clientes': len(clientes),
        'productos': lista_productos[:20],  # Top 20 productos
        'clientes': sorted(list(clientes))[:20],
        'metodos_pago': metodos_pago,
        'ventas': ventas_lista
    }
    
    return jsonify(response)


# ================================================================
# 🆕 ADMIN - DETALLE DE VENTAS POR DÍA (PÁGINA COMPLETA) - CORREGIDO
# ================================================================

def admin_detalle_ventas_dia(fecha_str):
    """
    Página de detalle de ventas para un día específico.
    Muestra productos, clientes, métodos de pago y lista de ventas en una página independiente.

    🔥 CORREGIDO: antes esto consultaba una colección 'ventas' (campo 'fecha') que
    no es la misma que usa el reporte/regresión (colección 'pedidos', campo 'created_at'),
    por eso siempre salía vacío. Ahora reutilizamos VentaReporte.get_ventas() para
    garantizar que se lea exactamente la misma fuente de datos que la gráfica.
    """
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    
    usuario = Usuario.obtener_por_id(session['user_id'])
    rol_normalizado = normalizar_rol(usuario.get('rol'))
    if rol_normalizado != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.dashboard'))
    
    # Limpiar fecha
    fecha_str = limpiar_texto(fecha_str)
    
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
    except ValueError:
        try:
            fecha = datetime.strptime(fecha_str, '%d/%m/%Y')
        except ValueError:
            flash('Formato de fecha inválido. Usa YYYY-MM-DD', 'danger')
            return redirect(url_for('web.admin_reporte_ventas'))
    
    # 🔥 Mismo modelo/colección/campo que usa el reporte (pedidos + created_at)
    pedidos_dia = VentaReporte.get_ventas(fecha_inicio=fecha, fecha_fin=fecha)
    pedidos_dia = [v for v in pedidos_dia if v.get('total', 0) > 0]
    
    total_ventas = len(pedidos_dia)
    total_monto = limpiar_precio(sum(v.get('total', 0) for v in pedidos_dia))
    total_unidades = limpiar_cantidad(sum(v.get('total_unidades', 0) for v in pedidos_dia))
    
    # Procesar productos vendidos (agrupar por nombre) usando items_list ya limpio
    productos_vendidos = {}
    clientes = set()
    metodos_pago = {}
    
    for venta in pedidos_dia:
        cliente = venta.get('usuario_nombre') or 'Anónimo'
        clientes.add(cliente)
        
        metodo = venta.get('metodo_pago') or 'No especificado'
        metodos_pago[metodo] = metodos_pago.get(metodo, 0) + 1
        
        for item in venta.get('items_list', []):
            nombre = item.get('nombre', 'Producto sin nombre')
            cantidad = limpiar_cantidad(item.get('cantidad', 0))
            precio = limpiar_precio(item.get('precio', 0))
            
            if nombre not in productos_vendidos:
                productos_vendidos[nombre] = {
                    'nombre': nombre,
                    'cantidad': 0,
                    'total': 0.0,
                    'precio_unitario': precio
                }
            productos_vendidos[nombre]['cantidad'] += cantidad
            productos_vendidos[nombre]['total'] += limpiar_precio(precio * cantidad)
    
    # Ordenar productos por cantidad
    lista_productos = sorted(
        productos_vendidos.values(),
        key=lambda x: x['cantidad'],
        reverse=True
    )
    
    # Ventas individuales con hora
    ventas_lista = []
    for v in pedidos_dia:
        hora = 'N/A'
        if v.get('created_at'):
            try:
                hora = v['created_at'].strftime('%H:%M')
            except:
                pass
        ventas_lista.append({
            'numero_pedido': v.get('numero_pedido', 'N/A'),
            'cliente': v.get('usuario_nombre', 'Anónimo'),
            'total': limpiar_precio(v.get('total', 0)),
            'metodo_pago': v.get('metodo_pago', 'N/A'),
            'estado': (v.get('estado') or 'pagada').capitalize(),
            'hora': hora
        })
    
    # Preparar datos para la vista
    fecha_formateada = fecha.strftime('%d/%m/%Y')
    fecha_iso = fecha.strftime('%Y-%m-%d')
    
    return render_template('admin/detalle_ventas_dia.html',
                         fecha=fecha,
                         fecha_formateada=fecha_formateada,
                         fecha_iso=fecha_iso,
                         total_ventas=total_ventas,
                         total_monto=total_monto,
                         total_unidades=total_unidades,
                         total_clientes=len(clientes),
                         productos=lista_productos,
                         clientes=sorted(list(clientes)),
                         metodos_pago=metodos_pago,
                         ventas=ventas_lista,
                         datetime=datetime)