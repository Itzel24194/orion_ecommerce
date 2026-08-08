# app/context_processors.py
from flask import session
from app.models.chat_model import Chat

def inject_carrito_total():
    """Inyecta el total de unidades del carrito en todas las plantillas"""
    total = 0
    carrito = session.get('carrito', [])
    for item in carrito:
        total += item.get('cantidad', 0)
    return {'total_unidades': total}

def inject_chat_session():
    """Inyecta el ID de sesión de chat en todas las plantillas"""
    # Si el usuario tiene una sesión de chat en la sesión HTTP, usarla
    if 'chat_session_id' in session:
        return {'chat_session_id': session['chat_session_id']}
    
    # Si no, crear una nueva sesión de chat
    usuario_id = session.get('user_id')
    nombre = session.get('nombre', 'Anónimo')
    
    # Usar el modelo para obtener o crear sesión
    sesion = Chat.obtener_o_crear_sesion(usuario_id, nombre)
    if sesion:
        session['chat_session_id'] = str(sesion['_id'])
        return {'chat_session_id': session['chat_session_id']}
    
    # Fallback: devolver vacío
    return {'chat_session_id': ''}