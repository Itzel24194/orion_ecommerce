# app/controllers/chat_controller.py
from flask import request, jsonify, render_template, session, current_app
from app.models.chat_model import Chat
from datetime import datetime, timezone
import json

# Importar normalizar_rol desde user_controller o definirlo aquí
def normalizar_rol(rol):
    if not rol:
        return 'cliente'
    rol = rol.lower().strip()
    if rol in ['administrador', 'admin', 'superadmin', 'root']:
        return 'admin'
    return rol

# ================================================================
# FUNCIONES PARA EL WIDGET DEL CLIENTE
# ================================================================

def iniciar_conversacion():
    """Crea una nueva conversación para el cliente (widget)"""
    data = request.get_json()
    nombre = data.get('nombre', '').strip()
    email = data.get('email', '').strip()
    
    if not nombre:
        return jsonify({"success": False, "error": "El nombre es obligatorio"}), 400
    
    usuario_id = session.get('user_id')
    sesion = Chat.obtener_o_crear_sesion(usuario_id, nombre)
    if not sesion:
        return jsonify({"success": False, "error": "No se pudo crear la sesión"}), 500
    
    if email:
        Chat.collection.update_one(
            {"_id": sesion["_id"]},
            {"$set": {"email": email}}
        )
    
    return jsonify({
        "success": True,
        "conversacion_id": str(sesion["_id"])
    })

def obtener_conversacion():
    conversacion_id = request.args.get('conversacion_id')
    if not conversacion_id:
        return jsonify({"success": False, "error": "Falta conversacion_id"}), 400
    
    sesion = Chat.obtener_por_id(conversacion_id)
    if not sesion:
        return jsonify({"success": False, "error": "Conversación no encontrada"}), 404
    
    mensajes = sesion.get("mensajes", [])
    mensajes_formateados = []
    for m in mensajes:
        mensajes_formateados.append({
            "mensaje": m.get("texto", ""),
            "es_admin": m.get("es_admin", False),
            "fecha": m.get("fecha", datetime.now(timezone.utc)).isoformat(),
            "nombre_remitente": "Admin" if m.get("es_admin") else sesion.get("nombre_usuario", "Cliente")
        })
    
    return jsonify({
        "success": True,
        "mensajes": mensajes_formateados,
        "estado": sesion.get("estado", "activo")
    })

def enviar_mensaje_widget():
    data = request.get_json()
    conversacion_id = data.get('conversacion_id')
    mensaje = data.get('mensaje', '').strip()
    
    if not conversacion_id or not mensaje:
        return jsonify({"success": False, "error": "Faltan datos"}), 400
    
    sesion = Chat.obtener_por_id(conversacion_id)
    if not sesion:
        return jsonify({"success": False, "error": "Conversación no encontrada"}), 404
    
    Chat.agregar_mensaje(conversacion_id, mensaje, es_admin=False)
    return jsonify({"success": True})

# ================================================================
# FUNCIONES PARA EL PANEL DE ADMINISTRACIÓN
# ================================================================

def widget_chat():
    usuario_id = session.get('user_id')
    nombre = session.get('nombre', 'Cliente')
    if usuario_id:
        sesion = Chat.obtener_o_crear_sesion(usuario_id, nombre)
        session_id = str(sesion["_id"])
    else:
        if 'chat_session_id' not in session:
            nueva_sesion = Chat.crear_sesion(None, "Anónimo")
            session['chat_session_id'] = nueva_sesion
        session_id = session['chat_session_id']
    
    return render_template('tienda/widget_chat.html', session_id=session_id)

def enviar_mensaje():
    data = request.get_json()
    session_id = data.get('session_id')
    mensaje = data.get('mensaje', '').strip()
    
    if not session_id or not mensaje:
        return jsonify({"success": False, "error": "Faltan datos"}), 400
    
    sesion = Chat.obtener_por_id(session_id)
    if not sesion:
        return jsonify({"success": False, "error": "Sesión no encontrada"}), 404
    
    Chat.agregar_mensaje(session_id, mensaje, es_admin=False)
    return jsonify({"success": True})

def obtener_mensajes():
    session_id = request.args.get('session_id')
    ultimo = request.args.get('ultimo')
    
    if not session_id:
        return jsonify({"success": False, "error": "Falta session_id"}), 400
    
    mensajes = Chat.obtener_mensajes(session_id, desde_fecha=ultimo)
    data = []
    for m in mensajes:
        data.append({
            "texto": m.get("texto", ""),
            "es_admin": m.get("es_admin", False),
            "fecha": m.get("fecha", datetime.now(timezone.utc)).isoformat()
        })
    
    Chat.marcar_como_visto(session_id)
    return jsonify({"success": True, "mensajes": data})

def admin_chat_panel():
    """Panel de administración para el chat"""
    if 'user_id' not in session:
        return render_template('admin/login_required.html')
    
    from app.models.usuarios_model import Usuario
    usuario = Usuario.obtener_por_id(session['user_id'])
    if not usuario:
        return "Usuario no encontrado", 404
    
    # Normalizar el rol antes de comparar
    rol_usuario = normalizar_rol(usuario.get('rol'))
    if rol_usuario != 'admin':
        return "Acceso no autorizado", 403
    
    sesiones = Chat.obtener_sesiones_activas()
    for ses in sesiones:
        mensajes = ses.get('mensajes', [])
        if mensajes:
            ses['ultimo_mensaje'] = mensajes[-1]
        ses['no_leidos'] = Chat.contar_no_leidos(str(ses['_id']))
        ses['_id_str'] = str(ses['_id'])
    
    return render_template('admin/chat_panel.html', sesiones=sesiones)

def admin_enviar_mensaje():
    data = request.get_json()
    session_id = data.get('session_id')
    mensaje = data.get('mensaje', '').strip()
    
    if not session_id or not mensaje:
        return jsonify({"success": False, "error": "Faltan datos"}), 400
    
    sesion = Chat.obtener_por_id(session_id)
    if not sesion:
        return jsonify({"success": False, "error": "Sesión no encontrada"}), 404
    
    Chat.agregar_mensaje(session_id, mensaje, es_admin=True)
    return jsonify({"success": True})

def admin_cerrar_sesion():
    data = request.get_json()
    session_id = data.get('session_id')
    if not session_id:
        return jsonify({"success": False, "error": "Falta session_id"}), 400
    
    Chat.cerrar_sesion(session_id)
    return jsonify({"success": True})

def admin_obtener_sesiones():
    sesiones = Chat.obtener_sesiones_activas()
    data = []
    for ses in sesiones:
        mensajes = ses.get('mensajes', [])
        data.append({
            "_id": str(ses['_id']),
            "nombre_usuario": ses.get('nombre_usuario', 'Cliente'),
            "ultimo_mensaje": mensajes[-1].get('texto', '') if mensajes else '',
            "fecha_ultimo": mensajes[-1].get('fecha', datetime.now(timezone.utc)).isoformat() if mensajes else '',
            "no_leidos": Chat.contar_no_leidos(str(ses['_id']))
        })
    return jsonify({"success": True, "sesiones": data})

def admin_obtener_mensajes_sesion():
    session_id = request.args.get('session_id')
    if not session_id:
        return jsonify({"success": False, "error": "Falta session_id"}), 400
    
    mensajes = Chat.obtener_mensajes(session_id)
    data = []
    for m in mensajes:
        data.append({
            "texto": m.get("texto", ""),
            "es_admin": m.get("es_admin", False),
            "fecha": m.get("fecha", datetime.now(timezone.utc)).isoformat()
        })
    return jsonify({"success": True, "mensajes": data})

def crear_sesion():
    usuario_id = session.get('user_id')
    nombre = session.get('nombre', 'Anónimo')
    sesion = Chat.obtener_o_crear_sesion(usuario_id, nombre)
    if sesion:
        session['chat_session_id'] = str(sesion['_id'])
        return jsonify({'success': True, 'session_id': str(sesion['_id'])})
    return jsonify({'success': False, 'error': 'No se pudo crear sesión'}), 500