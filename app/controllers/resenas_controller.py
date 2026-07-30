# app/controllers/resenas_controller.py
from flask import request, jsonify, render_template, session, flash, redirect, url_for
from app.models.resenas_model import Resena
from app.models.productos_model import Producto
from app.models.usuarios_model import Usuario
from bson import ObjectId
from datetime import datetime

def normalizar_rol(rol):
    if not rol:
        return 'cliente'
    rol = rol.lower().strip()
    if rol in ['administrador', 'admin', 'superadmin', 'root']:
        return 'admin'
    return rol

# ================================================================
# FUNCIÓN AUXILIAR PARA CONVERTIR ObjectId A STRING
# ================================================================
def convertir_objectid(doc):
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
# PÁGINA PRINCIPAL DE RESEÑAS (ADMIN)
# ================================================================

def admin_resenas():
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
    
    return render_template('admin/resenas.html', usuario=usuario)


# ================================================================
# API ENDPOINTS PARA ADMIN
# ================================================================

def api_resenas_listar():
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    estado = request.args.get('estado')  # pendiente, aprobado, rechazado, todos
    resenas = Resena.obtener_todas()
    
    if estado and estado != 'todos':
        resenas = [r for r in resenas if r.get('estado') == estado]
    
    # Enriquecer con nombres de productos y usuarios
    for resena in resenas:
        resena['_id'] = str(resena['_id'])
        
        if 'producto_id' in resena:
            producto = Producto.obtener_por_id(resena['producto_id'])
            resena['producto_nombre'] = producto.get('nombre', 'Producto eliminado') if producto else 'Producto eliminado'
        
        if 'usuario_id' in resena:
            usuario = Usuario.obtener_por_id(resena['usuario_id'])
            resena['usuario_nombre'] = usuario.get('nombre', 'Usuario eliminado') if usuario else 'Usuario eliminado'
            resena['usuario_email'] = usuario.get('email', '') if usuario else ''
    
    resenas_convertidas = convertir_objectid(resenas)
    stats = Resena.contar_por_estado()
    
    return jsonify({
        'success': True,
        'resenas': resenas_convertidas,
        'stats': stats
    })


def api_resena_aprobar(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    try:
        resultado = Resena.actualizar_estado(id, 'aprobado')
        if resultado:
            return jsonify({'success': True, 'message': 'Reseña aprobada correctamente'})
        else:
            return jsonify({'error': 'No se pudo aprobar la reseña'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_resena_rechazar(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    try:
        resultado = Resena.actualizar_estado(id, 'rechazado')
        if resultado:
            return jsonify({'success': True, 'message': 'Reseña rechazada correctamente'})
        else:
            return jsonify({'error': 'No se pudo rechazar la reseña'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_resena_responder(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Datos inválidos'}), 400
    
    respuesta = data.get('respuesta', '').strip()
    if not respuesta:
        return jsonify({'error': 'La respuesta es obligatoria'}), 400
    
    try:
        resultado = Resena.responder_admin(id, respuesta)
        if resultado:
            return jsonify({'success': True, 'message': 'Respuesta enviada correctamente'})
        else:
            return jsonify({'error': 'No se pudo enviar la respuesta'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_resena_eliminar(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    try:
        resultado = Resena.eliminar(id, None)  # admin sin verificar usuario
        if resultado and resultado.deleted_count > 0:
            return jsonify({'success': True, 'message': 'Reseña eliminada correctamente'})
        else:
            return jsonify({'error': 'No se pudo eliminar la reseña'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def api_resena_obtener(id):
    if 'user_id' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    resena = Resena.obtener_por_id(id)
    if not resena:
        return jsonify({'error': 'Reseña no encontrada'}), 404
    
    resena['_id'] = str(resena['_id'])
    
    if 'producto_id' in resena:
        producto = Producto.obtener_por_id(resena['producto_id'])
        resena['producto_nombre'] = producto.get('nombre', 'Producto eliminado') if producto else 'Producto eliminado'
    
    if 'usuario_id' in resena:
        usuario = Usuario.obtener_por_id(resena['usuario_id'])
        resena['usuario_nombre'] = usuario.get('nombre', 'Usuario eliminado') if usuario else 'Usuario eliminado'
        resena['usuario_email'] = usuario.get('email', '') if usuario else ''
    
    resena_convertida = convertir_objectid(resena)
    return jsonify({'success': True, 'resena': resena_convertida})