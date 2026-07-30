# app/controllers/combo_controller.py
from flask import request, jsonify, render_template, session, flash, redirect, url_for
from app.models.combo_model import Combo
from app.models.productos_model import Producto
from app.models.usuarios_model import Usuario
from bson import ObjectId

def normalizar_rol(rol):
    if not rol:
        return 'cliente'
    rol = rol.lower().strip()
    if rol in ['administrador', 'admin', 'superadmin', 'root']:
        return 'admin'
    return rol

# ================================================================
# FUNCIÓN AUXILIAR PARA CONVERTIR ObjectId A STRING (RECURSIVA)
# ================================================================
def convertir_objectid(doc):
    """Convierte recursivamente todos los ObjectId a string en un documento o lista."""
    if isinstance(doc, list):
        return [convertir_objectid(item) for item in doc]
    if isinstance(doc, dict):
        nuevo = {}
        for k, v in doc.items():
            if isinstance(v, ObjectId):
                nuevo[k] = str(v)
            elif isinstance(v, (list, dict)):
                nuevo[k] = convertir_objectid(v)
            else:
                nuevo[k] = v
        return nuevo
    return doc

# ================================================================
# PÁGINA PRINCIPAL DE COMBOS
# ================================================================

def admin_combos():
    if 'user_id' not in session:
        flash('Inicia sesión para acceder', 'warning')
        return redirect(url_for('web.login'))
    
    usuario = Usuario.obtener_por_id(session['user_id'])
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('web.dashboard'))
    
    if normalizar_rol(usuario.get('rol')) != 'admin':
        flash('No tienes permisos', 'danger')
        return redirect(url_for('web.dashboard'))
    
    productos = Producto.obtener_todos()
    return render_template('admin/combos.html', usuario=usuario, productos=productos)


# ================================================================
# API ENDPOINTS
# ================================================================

def api_combos_listar():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    combos = Combo.obtener_todos()
    for combo in combos:
        combo['_id'] = str(combo['_id'])
        if 'productos' in combo and combo['productos']:
            productos = Producto.obtener_por_ids(combo['productos'])
            combo['productos_detalle'] = convertir_objectid(productos)  # <--- CONVERTIR
    # Convertir todo el combo (por si hay otros ObjectId anidados)
    combos_convertidos = convertir_objectid(combos)
    return jsonify({'success': True, 'combos': combos_convertidos})


def api_combo_crear():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Datos inválidos'}), 400
    
    nombre = data.get('nombre', '').strip()
    if not nombre:
        return jsonify({'error': 'El nombre es obligatorio'}), 400
    
    productos = data.get('productos', [])
    if not productos:
        return jsonify({'error': 'Debe seleccionar al menos un producto'}), 400
    
    precio = data.get('precio')
    if precio is None or float(precio) <= 0:
        return jsonify({'error': 'El precio debe ser mayor a 0'}), 400
    
    descuento = data.get('descuento', 0)
    imagen = data.get('imagen', '')
    activo = data.get('activo', True)
    
    combo_data = {
        'nombre': nombre,
        'descripcion': data.get('descripcion', '').strip(),
        'productos': productos,
        'precio': float(precio),
        'descuento': float(descuento),
        'imagen': imagen,
        'activo': activo
    }
    
    try:
        combo_id = Combo.crear(combo_data)
        return jsonify({'success': True, 'combo_id': combo_id, 'message': 'Combo creado correctamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_combo_obtener(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    combo = Combo.obtener_por_id(id)
    if not combo:
        return jsonify({'error': 'Combo no encontrado'}), 404
    
    combo['_id'] = str(combo['_id'])
    if 'productos' in combo and combo['productos']:
        productos = Producto.obtener_por_ids(combo['productos'])
        combo['productos_detalle'] = convertir_objectid(productos)
    
    combo_convertido = convertir_objectid(combo)
    return jsonify({'success': True, 'combo': combo_convertido})


def api_combo_actualizar(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Datos inválidos'}), 400
    
    nombre = data.get('nombre', '').strip()
    if not nombre:
        return jsonify({'error': 'El nombre es obligatorio'}), 400
    
    productos = data.get('productos', [])
    if not productos:
        return jsonify({'error': 'Debe seleccionar al menos un producto'}), 400
    
    precio = data.get('precio')
    if precio is None or float(precio) <= 0:
        return jsonify({'error': 'El precio debe ser mayor a 0'}), 400
    
    descuento = data.get('descuento', 0)
    imagen = data.get('imagen', '')
    activo = data.get('activo', True)
    
    combo_data = {
        'nombre': nombre,
        'descripcion': data.get('descripcion', '').strip(),
        'productos': productos,
        'precio': float(precio),
        'descuento': float(descuento),
        'imagen': imagen,
        'activo': activo
    }
    
    try:
        actualizado = Combo.actualizar(id, combo_data)
        if actualizado:
            return jsonify({'success': True, 'message': 'Combo actualizado correctamente'})
        else:
            return jsonify({'error': 'No se pudo actualizar el combo'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_combo_eliminar(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    try:
        eliminado = Combo.eliminar(id)
        if eliminado:
            return jsonify({'success': True, 'message': 'Combo eliminado correctamente'})
        else:
            return jsonify({'error': 'No se pudo eliminar el combo'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500