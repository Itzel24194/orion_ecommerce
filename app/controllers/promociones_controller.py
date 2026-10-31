# app/controllers/promociones_controller.py
# ================================================================
# Controlador completo para promociones estilo Liverpool
# ================================================================
import os
import logging
import traceback
from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId

from flask import (
    render_template, request, redirect, url_for, session,
    current_app, flash, jsonify, Response,
)

from app.models.promocion_model import Promocion
from app.models.productos_model import Producto
from app.models.categorias_model import Categoria
from app.models.usuarios_model import Usuario

logger = logging.getLogger(__name__)


# ================================================================
# HELPERS SEGUROS
# ================================================================
def _safe_object_id(value):
    """Devuelve ObjectId válido o None."""
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return None


def _to_dt(value):
    """Convierte a datetime naive UTC o None. Acepta datetime, date, string ISO, string YYYY-MM-DD."""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000 if value > 1e12 else value, tz=timezone.utc).replace(tzinfo=None)
        except (OSError, ValueError, OverflowError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            d = datetime.fromisoformat(s.replace('Z', '+00:00'))
            if d.tzinfo is not None:
                d = d.astimezone(timezone.utc).replace(tzinfo=None)
            return d
        except ValueError:
            pass
        for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%d-%m-%Y'):
            try:
                return datetime.strptime(s[:10], fmt)
            except ValueError:
                continue
    return None


def _normalize_segmentos(segmentos):
    """Devuelve lista de segmentos en minúsculas y sin None."""
    if not segmentos:
        return ['todos']
    out = []
    for s in segmentos:
        if s is None:
            continue
        v = str(s).strip().lower()
        if v and v not in out:
            out.append(v)
    return out or ['todos']


def _safe_float(valor, default=0.0):
    if valor is None or valor == '':
        return default
    try:
        return float(valor)
    except (ValueError, TypeError):
        return default


def _safe_int(valor, default=0):
    if valor is None or valor == '':
        return default
    try:
        return int(valor)
    except (ValueError, TypeError):
        return default


def _parse_form_date(field_name):
    raw = request.form.get(field_name)
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d')
    except ValueError:
        raise ValueError(f'Fecha inválida en "{field_name}": {raw}')


# ================================================================
# ASIGNACIÓN AUTOMÁTICA DE SEGMENTOS
# ================================================================
def asignar_segmento_automatico(data):
    tipo = data.get('tipo')
    descuento_valor = data.get('descuento_valor', 0)
    descuento_tipo = data.get('descuento_tipo', 'porcentaje')
    monto_minimo = data.get('monto_minimo', 0)
    prioridad = data.get('prioridad', 0)
    cantidad_requerida = data.get('cantidad_requerida', 0)

    segmentos = []

    if tipo in ('combo', 'cantidad'):
        segmentos = ['frecuente', 'todos']
    elif tipo == 'abandono_carrito':
        segmentos = ['inactivo']
    elif tipo == 'cumpleanos':
        segmentos = ['nuevo', 'inactivo']
    elif prioridad == 2:
        segmentos = ['vip']
    elif tipo == 'envio_gratis':
        segmentos = ['frecuente', 'vip'] if monto_minimo > 200 else ['todos']
    else:
        descuento_efectivo = descuento_valor
        if descuento_tipo == 'porcentaje':
            if descuento_efectivo >= 20:
                segmentos = ['vip'] if monto_minimo >= 500 else ['frecuente', 'vip']
            elif descuento_efectivo >= 10:
                segmentos = ['inactivo', 'todos'] if monto_minimo < 200 else ['frecuente', 'todos']
            else:
                segmentos = ['todos']
        else:  # monto fijo
            if descuento_efectivo >= 200 and monto_minimo >= 500:
                segmentos = ['vip']
            elif descuento_efectivo >= 50:
                segmentos = ['frecuente', 'todos']
            else:
                segmentos = ['todos']

    return _normalize_segmentos(segmentos)


# ================================================================
# FILTRO BASE DE VIGENCIA (sin $or duplicado)
# ================================================================
def _filtro_vigente():
    """Filtro Mongo para promociones activas y vigentes. Sin $or duplicado."""
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    return {
        'activo': True,
        '$and': [
            {'$or': [{'fecha_inicio': {'$lte': ahora}}, {'fecha_inicio': None}]},
            {'$or': [{'fecha_fin': {'$gte': ahora}}, {'fecha_fin': None}]},
        ],
    }


# ================================================================
# PROMOCIONES DESTACADAS
# ================================================================
def obtener_promociones_destacadas(usuario_id=None, limite=6):
    db = current_app.db
    try:
        filtro = _filtro_vigente()
        filtro['mostrar_en_home'] = True
        promociones = list(db.promociones.find(filtro).sort('prioridad', -1).limit(limite))
    except Exception as e:
        logger.error(f'obtener_promociones_destacadas: {e}')
        return []

    if usuario_id:
        try:
            segmento_usuario = (Usuario.obtener_segmento(usuario_id) or '').lower()
        except Exception:
            segmento_usuario = ''
        promociones = [
            p for p in promociones
            if 'todos' in _normalize_segmentos(p.get('segmentos')) or
               segmento_usuario in _normalize_segmentos(p.get('segmentos'))
        ]
    return promociones


# ================================================================
# OBTENER PROMOCIONES DISPONIBLES (con todos los filtros)
# ================================================================
def obtener_promociones_disponibles(usuario_id, productos=None):
    db = current_app.db
    try:
        promociones = list(db.promociones.find(_filtro_vigente()).sort('prioridad', -1))
    except Exception as e:
        logger.error(f'obtener_promociones_disponibles: {e}')
        return []

    if usuario_id:
        uid_oid = _safe_object_id(usuario_id)
        try:
            segmento_usuario = (Usuario.obtener_segmento(usuario_id) or '').lower()
        except Exception:
            segmento_usuario = ''
        filtradas = []
        for p in promociones:
            segs = _normalize_segmentos(p.get('segmentos'))
            if 'todos' in segs or segmento_usuario in segs:
                filtradas.append(p)
        promociones = filtradas

        # Filtro por usos
        restantes = []
        for p in promociones:
            pid_oid = _safe_object_id(p.get('_id'))
            if not pid_oid:
                continue
            usos_por_usuario = p.get('usos_por_usuario')
            if usos_por_usuario and uid_oid:
                try:
                    usos_actuales = db.pedidos.count_documents({
                        'usuario_id': uid_oid,
                        'promocion_id': pid_oid,
                    })
                    if usos_actuales >= usos_por_usuario:
                        continue
                except Exception:
                    pass
            uso_maximo = p.get('uso_maximo')
            if uso_maximo:
                try:
                    usos_totales = db.pedidos.count_documents({'promocion_id': pid_oid})
                    if usos_totales >= uso_maximo:
                        continue
                except Exception:
                    pass
            restantes.append(p)
        promociones = restantes

    if productos and len(productos) > 0:
        ids_carrito = {str(prod.get('producto_id')) for prod in productos if prod.get('producto_id')}
        categorias_carrito = set()
        for prod in productos:
            pid = _safe_object_id(prod.get('producto_id'))
            if not pid:
                continue
            try:
                producto = db.productos.find_one({'_id': pid})
                if producto and producto.get('categoria_id') is not None:
                    categorias_carrito.add(str(producto['categoria_id']))
            except Exception:
                continue

        filtradas = []
        for p in promociones:
            prods_apl = {str(x) for x in (p.get('productos_aplicables') or []) if x is not None}
            if prods_apl and not (prods_apl & ids_carrito):
                continue
            cats_apl = {str(x) for x in (p.get('categorias_aplicables') or []) if x is not None}
            if cats_apl and not (cats_apl & categorias_carrito):
                continue
            filtradas.append(p)
        promociones = filtradas

    return promociones


# ================================================================
# VALIDAR SI UNA PROMO APLICA
# ================================================================
def es_valida(promocion, usuario_id, monto, productos, metodo_pago=''):
    db = current_app.db
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)

    if not promocion:
        return False, 'Promoción no encontrada', {}

    if not promocion.get('activo', False):
        return False, 'Esta promoción no está activa', {}

    fecha_inicio = _to_dt(promocion.get('fecha_inicio'))
    fecha_fin = _to_dt(promocion.get('fecha_fin'))
    if fecha_inicio and fecha_inicio > ahora:
        return False, 'Esta promoción aún no ha comenzado', {}
    if fecha_fin and fecha_fin < ahora:
        return False, 'Esta promoción ha expirado', {}

    pid_oid = _safe_object_id(promocion.get('_id'))
    uid_oid = _safe_object_id(usuario_id)

    uso_maximo = promocion.get('uso_maximo')
    if uso_maximo and pid_oid:
        try:
            usos_totales = db.pedidos.count_documents({'promocion_id': pid_oid})
            if usos_totales >= uso_maximo:
                return False, 'Esta promoción ya alcanzó su límite de usos', {}
        except Exception:
            pass

    if uid_oid and pid_oid:
        usos_por_usuario = promocion.get('usos_por_usuario')
        if usos_por_usuario:
            try:
                usos_actuales = db.pedidos.count_documents({
                    'usuario_id': uid_oid,
                    'promocion_id': pid_oid,
                })
                if usos_actuales >= usos_por_usuario:
                    return False, 'Ya has usado esta promoción el número máximo de veces', {}
            except Exception:
                pass

    segmentos = _normalize_segmentos(promocion.get('segmentos'))
    if 'todos' not in segmentos and usuario_id:
        try:
            segmento_usuario = (Usuario.obtener_segmento(usuario_id) or '').lower()
            if segmento_usuario not in segmentos:
                return False, 'Esta promoción no aplica para tu perfil', {}
        except Exception:
            pass

    monto_minimo = promocion.get('monto_minimo', 0) or 0
    if monto < monto_minimo:
        return False, f'El monto mínimo requerido es ${monto_minimo:.2f} y tu carrito tiene ${monto:.2f}', {}

    metodos_pago = [str(m).strip().lower() for m in (promocion.get('metodos_pago') or []) if m]
    if metodos_pago and metodo_pago:
        if str(metodo_pago).strip().lower() not in metodos_pago:
            return False, 'Esta promoción no aplica para el método de pago seleccionado', {}

    # Cálculo del descuento
    descuento = 0
    tipo = promocion.get('tipo')

    if tipo in ('descuento_directo', 'pago'):
        if promocion.get('descuento_tipo') == 'porcentaje':
            descuento = monto * (float(promocion.get('descuento_valor', 0) or 0) / 100)
        else:
            descuento = float(promocion.get('descuento_valor', 0) or 0)
    elif tipo == 'envio_gratis':
        descuento = 0
    elif tipo == 'cantidad':
        if productos:
            req = int(promocion.get('cantidad_requerida', 0) or 0)
            gratis = int(promocion.get('cantidad_gratis', 0) or 0)
            for prod in productos:
                if int(prod.get('cantidad', 0) or 0) >= req > 0:
                    descuento = gratis * float(prod.get('precio', 0) or 0)
                    break
    elif tipo == 'combo':
        combo = [str(x) for x in (promocion.get('combo_productos') or []) if x is not None]
        if combo and productos:
            en_carrito = {str(prod.get('producto_id')) for prod in productos if prod.get('producto_id')}
            if set(combo).issubset(en_carrito):
                base = sum(
                    float(prod.get('precio', 0) or 0)
                    for prod in productos
                    if str(prod.get('producto_id')) in combo
                )
                descuento = base * (float(promocion.get('combo_descuento', 0) or 0) / 100)

    descuento = max(0, min(descuento, monto))
    monto_final = max(0, monto - descuento)

    return True, 'Promoción válida', {
        'descuento': round(descuento, 2),
        'monto_final': round(monto_final, 2),
    }


# ================================================================
# ADMIN — LISTAR
# ================================================================
def _require_admin():
    """Devuelve (user_dict | None, response_redirect | None)."""
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return None, redirect(url_for('web.login'))
    db = current_app.db
    uid = _safe_object_id(session['user_id'])
    usuario = db.usuarios.find_one({'_id': uid}) if uid else None
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        session.clear()
        return None, redirect(url_for('web.login'))
    if usuario.get('rol', 'cliente').lower() not in ('admin', 'superadmin', 'administrador'):
        flash('No tienes permisos de administrador', 'danger')
        return None, redirect(url_for('web.raiz_tienda'))
    return usuario, None


def admin_listar_promociones():
    usuario, redirect_resp = _require_admin()
    if redirect_resp:
        return redirect_resp

    try:
        tipo = request.args.get('tipo', '')
        estado = request.args.get('estado', '')
        busqueda = request.args.get('busqueda', '')

        filtros = {}
        if tipo:
            filtros['tipo'] = tipo
        if estado == 'activo':
            filtros['activo'] = True
        elif estado == 'inactivo':
            filtros['activo'] = False
        if busqueda:
            filtros['nombre'] = busqueda

        promociones = Promocion.obtener_todos(filtros)
        todas = Promocion.obtener_todos()

        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        activas = [p for p in todas if p.get('activo')]
        expiradas = [
            p for p in todas
            if p.get('fecha_fin') and _to_dt(p['fecha_fin']) and _to_dt(p['fecha_fin']) < ahora
        ]
        proximas = [
            p for p in todas
            if p.get('fecha_inicio') and _to_dt(p['fecha_inicio']) and _to_dt(p['fecha_inicio']) > ahora
        ]

        return render_template(
            'admin/promociones.html', # ✅ AQUÍ SE RENDERIZA LA TABLA (LISTA)
            promociones=promociones,
            promos_activas=len(activas),
            promos_expiradas=len(expiradas),
            promos_proximas=len(proximas),
            promos_finalizadas=len(expiradas),
            total=len(todas),
            datetime=datetime,
            ahora=ahora,
        )
    except Exception as e:
        traceback.print_exc()
        logger.error(f'admin_listar_promociones: {e}')
        flash(f'Error al cargar promociones: {e}', 'danger')
        return redirect(url_for('web.dashboard'))


# ================================================================
# ADMIN — CREAR
# ================================================================
def admin_crear_promocion():
    usuario, redirect_resp = _require_admin()
    if redirect_resp:
        return redirect_resp

    if request.method == 'POST':
        try:
            tipo = request.form.get('tipo')
            if not tipo:
                flash('Debes seleccionar un tipo de promoción', 'danger')
                return redirect(url_for('web.admin_crear_promocion'))

            data_temp = {
                'tipo': tipo,
                'descuento_valor': _safe_float(request.form.get('descuento_valor', 0)),
                'descuento_tipo': request.form.get('descuento_tipo'),
                'monto_minimo': _safe_float(request.form.get('monto_minimo', 0)),
                'prioridad': _safe_int(request.form.get('prioridad', 0)),
                'cantidad_requerida': _safe_int(request.form.get('cantidad_requerida', 0)),
            }
            segmentos = asignar_segmento_automatico(data_temp)

            productos_aplicables = [p for p in request.form.getlist('productos_aplicables') if p and p.strip()]
            categorias_aplicables = [c for c in request.form.getlist('categorias_aplicables') if c and c.strip()]
            marcas_aplicables = [m for m in request.form.getlist('marcas_aplicables') if m and m.strip()]
            metodos_pago = [m for m in request.form.getlist('metodos_pago') if m and m.strip()]
            combo_productos = [p for p in request.form.getlist('combo_productos') if p and p.strip()]

            fecha_inicio = _parse_form_date('fecha_inicio')
            fecha_fin = _parse_form_date('fecha_fin')

            codigo = (request.form.get('codigo') or '').strip() or None

            data = {
                'nombre': (request.form.get('nombre') or '').strip(),
                'descripcion': (request.form.get('descripcion') or '').strip(),
                'tipo': tipo,
                'activo': request.form.get('activo') == '1',
                'prioridad': _safe_int(request.form.get('prioridad', 0)),
                'imagen': (request.form.get('imagen') or '').strip(),
                'codigo': codigo,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'descuento_tipo': request.form.get('descuento_tipo'),
                'descuento_valor': _safe_float(request.form.get('descuento_valor', 0)),
                'monto_minimo': _safe_float(request.form.get('monto_minimo', 0)),
                'cantidad_requerida': _safe_int(request.form.get('cantidad_requerida', 0)),
                'cantidad_gratis': _safe_int(request.form.get('cantidad_gratis', 0)),
                'combo_productos': combo_productos,
                'combo_descuento': _safe_float(request.form.get('combo_descuento', 0)),
                'productos_aplicables': productos_aplicables,
                'categorias_aplicables': categorias_aplicables,
                'marcas_aplicables': marcas_aplicables,
                'segmentos': segmentos,
                'metodos_pago': metodos_pago,
                'uso_maximo': _safe_int(request.form.get('uso_maximo', 0)) or None,
                'usos_por_usuario': _safe_int(request.form.get('usos_por_usuario', 0)) or None,
                'mostrar_en_home': request.form.get('mostrar_en_home') == '1',
                'mostrar_en_producto': request.form.get('mostrar_en_producto') == '1',
            }

            # Validaciones por tipo
            if data['tipo'] in ('descuento_directo', 'pago'):
                if not data['descuento_tipo'] or data['descuento_valor'] <= 0:
                    flash('Debes especificar un descuento válido', 'danger')
                    return redirect(url_for('web.admin_crear_promocion'))
            if data['tipo'] == 'cantidad':
                if data['cantidad_requerida'] <= 0 or data['cantidad_gratis'] <= 0:
                    flash('Debes especificar cantidad requerida y gratuita', 'danger')
                    return redirect(url_for('web.admin_crear_promocion'))
            if data['tipo'] == 'combo':
                if not data['combo_productos'] or len(data['combo_productos']) < 2:
                    flash('Debes seleccionar al menos 2 productos para el combo', 'danger')
                    return redirect(url_for('web.admin_crear_promocion'))

            Promocion.crear(data)
            flash('Promoción creada exitosamente', 'success')
            return redirect(url_for('web.admin_listar_promociones'))

        except ValueError as e:
            flash(str(e), 'danger')
            return redirect(url_for('web.admin_crear_promocion'))
        except Exception as e:
            traceback.print_exc()
            logger.error(f'admin_crear_promocion: {e}')
            flash(f'Error al crear promoción: {e}', 'danger')
            return redirect(url_for('web.admin_crear_promocion'))

    try:
        db = current_app.db
        productos = Producto.obtener_todos()
        categorias = Categoria.obtener_todas()
        marcas = list(db.marcas.find().sort('nombre', 1))
        return render_template(
            'admin/promocion_crear.html',
            productos=productos,
            categorias=categorias,
            marcas=marcas,
            ahora=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    except Exception as e:
        traceback.print_exc()
        logger.error(f'admin_crear_promocion (GET): {e}')
        flash(f'Error al cargar el formulario: {e}', 'danger')
        return redirect(url_for('web.admin_listar_promociones'))


# ================================================================
# ADMIN — EDITAR
# ================================================================
def admin_editar_promocion(promocion_id):
    usuario, redirect_resp = _require_admin()
    if redirect_resp:
        return redirect_resp

    try:
        promocion = Promocion.obtener_por_id(promocion_id)
        if not promocion:
            flash('Promoción no encontrada', 'danger')
            return redirect(url_for('web.admin_listar_promociones'))
    except Exception as e:
        traceback.print_exc()
        logger.error(f'admin_editar_promocion (obtener): {e}')
        flash('Error al obtener la promoción', 'danger')
        return redirect(url_for('web.admin_listar_promociones'))

    if request.method == 'POST':
        try:
            tipo = request.form.get('tipo')
            if not tipo:
                flash('Debes seleccionar un tipo de promoción', 'danger')
                return redirect(url_for('web.admin_editar_promocion', promocion_id=promocion_id))

            data_temp = {
                'tipo': tipo,
                'descuento_valor': _safe_float(request.form.get('descuento_valor', 0)),
                'descuento_tipo': request.form.get('descuento_tipo'),
                'monto_minimo': _safe_float(request.form.get('monto_minimo', 0)),
                'prioridad': _safe_int(request.form.get('prioridad', 0)),
                'cantidad_requerida': _safe_int(request.form.get('cantidad_requerida', 0)),
            }
            segmentos = asignar_segmento_automatico(data_temp)

            productos_aplicables = [p for p in request.form.getlist('productos_aplicables') if p and p.strip()]
            categorias_aplicables = [c for c in request.form.getlist('categorias_aplicables') if c and c.strip()]
            marcas_aplicables = [m for m in request.form.getlist('marcas_aplicables') if m and m.strip()]
            metodos_pago = [m for m in request.form.getlist('metodos_pago') if m and m.strip()]
            combo_productos = [p for p in request.form.getlist('combo_productos') if p and p.strip()]

            fecha_inicio = _parse_form_date('fecha_inicio')
            fecha_fin = _parse_form_date('fecha_fin')

            codigo = (request.form.get('codigo') or '').strip() or None

            data = {
                'nombre': (request.form.get('nombre') or '').strip(),
                'descripcion': (request.form.get('descripcion') or '').strip(),
                'tipo': tipo,
                'activo': request.form.get('activo') == '1',
                'prioridad': _safe_int(request.form.get('prioridad', 0)),
                'imagen': (request.form.get('imagen') or '').strip(),
                'codigo': codigo,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'descuento_tipo': request.form.get('descuento_tipo'),
                'descuento_valor': _safe_float(request.form.get('descuento_valor', 0)),
                'monto_minimo': _safe_float(request.form.get('monto_minimo', 0)),
                'cantidad_requerida': _safe_int(request.form.get('cantidad_requerida', 0)),
                'cantidad_gratis': _safe_int(request.form.get('cantidad_gratis', 0)),
                'combo_productos': combo_productos,
                'combo_descuento': _safe_float(request.form.get('combo_descuento', 0)),
                'productos_aplicables': productos_aplicables,
                'categorias_aplicables': categorias_aplicables,
                'marcas_aplicables': marcas_aplicables,
                'segmentos': segmentos,
                'metodos_pago': metodos_pago,
                'uso_maximo': _safe_int(request.form.get('uso_maximo', 0)) or None,
                'usos_por_usuario': _safe_int(request.form.get('usos_por_usuario', 0)) or None,
                'mostrar_en_home': request.form.get('mostrar_en_home') == '1',
                'mostrar_en_producto': request.form.get('mostrar_en_producto') == '1',
            }

            Promocion.actualizar(promocion_id, data)
            flash('Promoción actualizada exitosamente', 'success')
            return redirect(url_for('web.admin_listar_promociones'))
        except ValueError as e:
            flash(str(e), 'danger')
            return redirect(url_for('web.admin_editar_promocion', promocion_id=promocion_id))
        except Exception as e:
            traceback.print_exc()
            logger.error(f'admin_editar_promocion (POST): {e}')
            flash(f'Error al actualizar promoción: {e}', 'danger')
            return redirect(url_for('web.admin_editar_promocion', promocion_id=promocion_id))

    try:
        db = current_app.db
        productos = Producto.obtener_todos()
        categorias = Categoria.obtener_todas()
        marcas = list(db.marcas.find().sort('nombre', 1))
        return render_template(
            'admin/promocion_crear.html',
            promocion=promocion,
            productos=productos,
            categorias=categorias,
            marcas=marcas,
            datetime=datetime,
            ahora=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    except Exception as e:
        traceback.print_exc()
        logger.error(f'admin_editar_promocion (GET): {e}')
        flash(f'Error al cargar el formulario: {e}', 'danger')
        return redirect(url_for('web.admin_listar_promociones'))


# ================================================================
# ADMIN — ELIMINAR
# ================================================================
def admin_eliminar_promocion(promocion_id):
    usuario, redirect_resp = _require_admin()
    if redirect_resp:
        return redirect_resp

    if request.method == 'POST':
        try:
            if Promocion.eliminar(promocion_id):
                flash('Promoción eliminada correctamente', 'success')
            else:
                flash('Error al eliminar la promoción', 'danger')
        except Exception as e:
            traceback.print_exc()
            logger.error(f'admin_eliminar_promocion: {e}')
            flash(f'Error al eliminar promoción: {e}', 'danger')
    return redirect(url_for('web.admin_listar_promociones'))


# ================================================================
# ADMIN — ESTADÍSTICAS
# ================================================================
def admin_promocion_estadisticas(promocion_id):
    usuario, redirect_resp = _require_admin()
    if redirect_resp:
        return redirect_resp

    try:
        promocion = Promocion.obtener_por_id(promocion_id)
        if not promocion:
            flash('Promoción no encontrada', 'danger')
            return redirect(url_for('web.admin_listar_promociones'))

        estadisticas = Promocion.obtener_estadisticas(promocion_id)

        pid_oid = _safe_object_id(promocion_id)
        pedidos = []
        if pid_oid:
            pedidos = list(current_app.db.pedidos.find({
                '$or': [
                    {'promocion_id': str(promocion_id)},
                    {'promocion_id': pid_oid},
                ]
            }).sort('created_at', -1).limit(20))

        for pedido in pedidos:
            pedido['_id'] = str(pedido['_id'])
            uid = _safe_object_id(pedido.get('usuario_id'))
            if uid:
                try:
                    u = current_app.db.usuarios.find_one({'_id': uid})
                    pedido['usuario_nombre'] = u.get('nombre', 'Desconocido') if u else 'Desconocido'
                except Exception:
                    pedido['usuario_nombre'] = 'Desconocido'

        return render_template(
            'admin/promocion_estadisticas.html', # ✅ AQUÍ SE RENDERIZAN LAS ESTADÍSTICAS
            promocion=promocion,
            estadisticas=estadisticas,
            pedidos=pedidos,
            datetime=datetime,
            ahora=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    except Exception as e:
        traceback.print_exc()
        logger.error(f'admin_promocion_estadisticas: {e}')
        flash(f'Error al cargar estadísticas: {e}', 'danger')
        return redirect(url_for('web.admin_listar_promociones'))


# ================================================================
# CLIENTE — LISTAR PROMOCIONES
# ================================================================
def _carrito_total():
    """Devuelve (monto, lista_productos) a partir del carrito en sesión."""
    carrito = session.get('carrito', {})
    monto = 0.0
    productos = []

    def _procesar(item):
        nonlocal monto
        if not isinstance(item, dict):
            return
        precio = _safe_float(item.get('precio', 0))
        cantidad = _safe_int(item.get('cantidad', 1), 1)
        monto += precio * cantidad
        productos.append({
            'producto_id': item.get('id') or item.get('producto_id'),
            'cantidad': cantidad,
            'precio': precio,
        })

    if isinstance(carrito, dict):
        for it in carrito.values():
            _procesar(it)
    elif isinstance(carrito, list):
        for it in carrito:
            _procesar(it)

    return monto, productos


def listar_promociones_cliente():
    if 'user_id' not in session:
        flash('Inicia sesión para ver promociones', 'warning')
        return redirect(url_for('web.login'))

    db = current_app.db
    uid_oid = _safe_object_id(session['user_id'])
    usuario = db.usuarios.find_one({'_id': uid_oid}) if uid_oid else None
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('web.login'))

    try:
        segmento_usuario = (Usuario.obtener_segmento(session['user_id']) or '').lower()
        logger.debug(f'Segmento usuario {session["user_id"]}: {segmento_usuario}')

        monto_carrito, productos_carrito = _carrito_total()

        destacadas = obtener_promociones_destacadas(session['user_id'])
        disponibles = obtener_promociones_disponibles(session['user_id'], productos=productos_carrito)

        for promo in disponibles:
            promo['cumple_minimo'] = monto_carrito >= (promo.get('monto_minimo', 0) or 0)
            promo['monto_carrito'] = monto_carrito

        usadas_ids = []
        if uid_oid:
            promociones_usadas = list(db.pedidos.find({
                'usuario_id': uid_oid,
                'promocion_id': {'$exists': True},
            }))
            usadas_ids = [str(p.get('promocion_id')) for p in promociones_usadas if p.get('promocion_id')]

        return render_template(
            'tienda/mis_promociones.html',
            destacadas=destacadas,
            disponibles=disponibles,
            usadas_ids=usadas_ids,
            segmento=segmento_usuario,
            monto_carrito=monto_carrito,
            datetime=datetime,
            ahora=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    except Exception as e:
        traceback.print_exc()
        logger.error(f'listar_promociones_cliente: {e}')
        flash('Error al cargar promociones', 'danger')
        return redirect(url_for('web.raiz_tienda'))


# ================================================================
# CLIENTE — APLICAR
# ================================================================
def aplicar_promocion():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401

    data = request.get_json() or {}
    promocion_id = data.get('promocion_id')
    if not promocion_id:
        return jsonify({'success': False, 'message': 'Selecciona una promoción'}), 400

    monto_carrito, productos_carrito = _carrito_total()
    if data.get('monto_carrito'):
        monto_carrito = _safe_float(data.get('monto_carrito'), monto_carrito)

    metodo_pago = data.get('metodo_pago', '')

    try:
        promocion = Promocion.obtener_por_id(promocion_id)
        if not promocion:
            return jsonify({'success': False, 'message': 'Promoción no encontrada'}), 404

        valida, mensaje, detalles = es_valida(
            promocion, session['user_id'], monto_carrito, productos_carrito, metodo_pago
        )
        if not valida:
            return jsonify({'success': False, 'message': mensaje}), 400

        Promocion.registrar_uso(promocion_id, session['user_id'], detalles.get('descuento', 0))

        session['promocion_aplicada'] = {
            'id': str(promocion_id),
            'nombre': promocion.get('nombre'),
            'codigo': promocion.get('codigo'),
            'descuento': detalles.get('descuento', 0),
            'monto_final': detalles.get('monto_final', monto_carrito),
        }
        session.modified = True

        return jsonify({
            'success': True,
            'message': 'Promoción aplicada correctamente',
            'descuento': detalles.get('descuento', 0),
            'monto_final': detalles.get('monto_final', monto_carrito),
        })
    except Exception as e:
        traceback.print_exc()
        logger.error(f'aplicar_promocion: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


# ================================================================
# CLIENTE — QUITAR
# ================================================================
def quitar_promocion():
    if 'promocion_aplicada' in session:
        session.pop('promocion_aplicada', None)
        session.modified = True
        return jsonify({'success': True, 'message': 'Promoción eliminada'})
    return jsonify({'success': False, 'message': 'No hay promoción aplicada'})


# ================================================================
# CLIENTE — VALIDAR CÓDIGO
# ================================================================
def validar_codigo_promocion():
    data = request.get_json() or {}
    codigo = (data.get('codigo') or '').strip().upper()
    if not codigo:
        return jsonify({'success': False, 'message': 'Ingresa un código'}), 400

    try:
        promocion = Promocion.obtener_por_codigo(codigo)
        if not promocion:
            return jsonify({'success': False, 'message': 'Código no válido'}), 404

        valida, mensaje, detalles = es_valida(
            promocion,
            session.get('user_id'),
            _safe_float(data.get('monto_carrito', 0)),
            data.get('productos_carrito', []) or [],
        )
        if not valida:
            return jsonify({'success': False, 'message': mensaje}), 400

        return jsonify({
            'success': True,
            'message': 'Código válido',
            'promocion': {
                'id': str(promocion.get('_id', '')),
                'nombre': promocion.get('nombre'),
                'descuento': detalles.get('descuento', 0),
            },
        })
    except Exception as e:
        traceback.print_exc()
        logger.error(f'validar_codigo_promocion: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


# ================================================================
# CLIENTE — PROMOS EN CARRITO (API)
# ================================================================
def promociones_carrito():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Inicia sesión'}), 401

    try:
        monto_carrito, productos_carrito = _carrito_total()
        promociones = obtener_promociones_disponibles(session['user_id'], productos=productos_carrito)
        return jsonify({
            'success': True,
            'promociones': promociones,
            'monto_carrito': monto_carrito,
        })
    except Exception as e:
        traceback.print_exc()
        logger.error(f'promociones_carrito: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


# ================================================================
# ADMIN — TOGGLE
# ================================================================
def admin_toggle_promocion(promocion_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401

    uid_oid = _safe_object_id(session['user_id'])
    usuario = current_app.db.usuarios.find_one({'_id': uid_oid}) if uid_oid else None
    if not usuario:
        return jsonify({'success': False, 'message': 'Usuario no encontrado'}), 404
    if usuario.get('rol', 'cliente').lower() not in ('admin', 'superadmin', 'administrador'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 403

    try:
        promocion = Promocion.obtener_por_id(promocion_id)
        if not promocion:
            return jsonify({'success': False, 'message': 'Promoción no encontrada'}), 404
        nuevo_estado = not promocion.get('activo', True)
        Promocion.toggle_activo(promocion_id, nuevo_estado)
        return jsonify({'success': True, 'activo': nuevo_estado, 'message': 'Promoción actualizada'})
    except Exception as e:
        traceback.print_exc()
        logger.error(f'admin_toggle_promocion: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


# ================================================================
# ADMIN — ACCIÓN MASIVA
# ================================================================
def admin_promocion_accion_masiva():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401

    uid_oid = _safe_object_id(session['user_id'])
    usuario = current_app.db.usuarios.find_one({'_id': uid_oid}) if uid_oid else None
    if not usuario:
        return jsonify({'success': False, 'message': 'Usuario no encontrado'}), 404
    if usuario.get('rol', 'cliente').lower() not in ('admin', 'superadmin', 'administrador'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 403

    data = request.get_json() or {}
    ids = data.get('ids', []) or []
    accion = data.get('accion', '')
    if not ids:
        return jsonify({'success': False, 'message': 'No hay promociones seleccionadas'}), 400

    try:
        count = 0
        for pid in ids:
            if accion == 'activar':
                Promocion.toggle_activo(pid, True); count += 1
            elif accion == 'inactivar':
                Promocion.toggle_activo(pid, False); count += 1
            elif accion == 'eliminar':
                Promocion.eliminar(pid); count += 1
        return jsonify({'success': True, 'message': f'Acción "{accion}" completada para {count} promociones'})
    except Exception as e:
        traceback.print_exc()
        logger.error(f'admin_promocion_accion_masiva: {e}')
        return jsonify({'success': False, 'message': str(e)}), 500


# ================================================================
# ADMIN — EXPORTAR CSV
# ================================================================
def admin_promociones_exportar_csv():
    usuario, redirect_resp = _require_admin()
    if redirect_resp:
        return redirect_resp

    try:
        import csv
        from io import StringIO

        promociones = Promocion.obtener_todos()
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'ID', 'Nombre', 'Tipo', 'Activo', 'Código',
            'Fecha Inicio', 'Fecha Fin', 'Usos Actuales', 'Uso Máximo', 'Segmentos',
        ])
        for p in promociones:
            writer.writerow([
                str(p.get('_id', '')),
                p.get('nombre', ''),
                p.get('tipo', ''),
                p.get('activo', False),
                p.get('codigo', ''),
                p.get('fecha_inicio', ''),
                p.get('fecha_fin', ''),
                p.get('usos_actuales', 0),
                p.get('uso_maximo', ''),
                ', '.join(_normalize_segmentos(p.get('segmentos'))),
            ])
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=promociones.csv'},
        )
    except Exception as e:
        traceback.print_exc()
        logger.error(f'admin_promociones_exportar_csv: {e}')
        flash('Error al exportar promociones', 'danger')
        return redirect(url_for('web.admin_listar_promociones'))


def admin_promociones_exportar_pdf():
    flash('Exportación a PDF aún no implementada', 'warning')
    return redirect(url_for('web.admin_listar_promociones'))


# ================================================================
# ADMIN — API JSON (dashboard)
# ================================================================
def admin_promociones_api():
    usuario, redirect_resp = _require_admin()
    if redirect_resp:
        return jsonify({'error': 'No autorizado'}), 401

    try:
        promociones = Promocion.obtener_todos()
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        activas = [p for p in promociones if p.get('activo')]
        expiradas = [
            p for p in promociones
            if p.get('fecha_fin') and _to_dt(p['fecha_fin']) and _to_dt(p['fecha_fin']) < ahora
        ]
        proximas = [
            p for p in promociones
            if p.get('fecha_inicio') and _to_dt(p['fecha_inicio']) and _to_dt(p['fecha_inicio']) > ahora
        ]
        return jsonify({
            'total': len(promociones),
            'activas': len(activas),
            'expiradas': len(expiradas),
            'proximas': len(proximas),
            'por_tipo': {
                tipo: len([p for p in promociones if p.get('tipo') == tipo])
                for tipo in set(p.get('tipo') for p in promociones if p.get('tipo'))
            },
        })
    except Exception as e:
        traceback.print_exc()
        logger.error(f'admin_promociones_api: {e}')
        return jsonify({'error': str(e)}), 500


def promociones_disponibles_api():
    if 'user_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    try:
        disponibles = obtener_promociones_disponibles(session['user_id'])
        return jsonify({'success': True, 'promociones': disponibles})
    except Exception as e:
        traceback.print_exc()
        logger.error(f'promociones_disponibles_api: {e}')
        return jsonify({'error': str(e)}), 500