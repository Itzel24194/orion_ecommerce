# app/controllers/chat_controller.py
# ================================================================
# CONTROLADOR DEL CHATBOT CON NLP REAL (ESTILO LIVERPOOL)
# - No se cierran conversaciones: solo se archivan
# - El cliente siempre retoma su hilo activo
# - El admin puede ver activas y archivadas
# - Política de retención automática (12 meses)
# - Auditoría de accesos, exportación PDF y anonimización
# ================================================================

from flask import request, jsonify, render_template, session, make_response
from bson import ObjectId
from datetime import datetime, timezone
import random

from app.models.chat_model import Chat
from app.models.auditoria_model import AuditoriaChat
from app.services.nlp_service import NLPService
from app.services.pdf_chat_service import generar_pdf_historial


# ================================================================
# RESPUESTAS RÁPIDAS PARA ADMIN
# ================================================================

RESPUESTAS_RAPIDAS = [
    "¡Gracias por tu mensaje! Te atenderé enseguida.",
    "Excelente, voy a revisar tu solicitud.",
    "¿Podrías darme más detalles sobre tu consulta?",
    "Entendido, déjame verificar la información.",
    "¡Claro! Con gusto te ayudo con eso.",
    "Te agradezco por contactarnos. ¿Hay algo más en lo que pueda ayudarte?",
    "Perfecto, ya quedó registrado.",
    "Por supuesto, con gusto resuelvo tu duda.",
    "Gracias por tu paciencia, ya casi termino.",
    "¿Te parece si coordinamos una llamada para resolverlo mejor?"
]


# ================================================================
# HELPERS
# ================================================================

def normalizar_rol(rol):
    if not rol or not isinstance(rol, str):
        return 'cliente'
    rol = rol.lower().strip()
    if rol in ('administrador', 'admin', 'superadmin', 'root'):
        return 'admin'
    return rol


def _es_admin_autenticado():
    if 'user_id' not in session:
        return False, (jsonify({"success": False, "error": "No autenticado"}), 401)

    from app.models.usuarios_model import Usuario
    usuario = Usuario.obtener_por_id(session['user_id'])
    if not usuario:
        return False, (jsonify({"success": False, "error": "Usuario no encontrado"}), 404)

    if normalizar_rol(usuario.get('rol')) != 'admin':
        return False, (jsonify({"success": False, "error": "No autorizado"}), 403)

    return True, usuario


def _fecha_a_iso(fecha):
    if not fecha:
        return ''
    if isinstance(fecha, datetime):
        return fecha.isoformat()
    return str(fecha)


def _es_objectid_valido(session_id):
    return bool(session_id) and ObjectId.is_valid(str(session_id))


def _sesion_esta_archivada(sesion):
    if not sesion:
        return False
    return sesion.get("estado") == "archivada"


def _registrar_auditoria(accion, session_id=None, detalles=None):
    """Helper para registrar auditoría rápidamente."""
    try:
        ok, usuario = _es_admin_autenticado()
        if ok and usuario:
            AuditoriaChat.registrar(
                usuario_id=session.get('user_id'),
                usuario_nombre=usuario.get('nombre', 'Admin'),
                accion=accion,
                session_id=session_id,
                detalles=detalles,
                ip=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
    except Exception as e:
        print(f"[Auditoria] Error: {e}")


def _normalizar_sesion_para_template(sesion):
    if not sesion:
        return None

    mensajes = sesion.get('mensajes', [])
    ultimo = mensajes[-1] if mensajes else None

    updated = sesion.get('updated_at')
    if isinstance(updated, str):
        try:
            updated = datetime.fromisoformat(updated.replace('Z', '+00:00'))
        except Exception:
            updated = datetime.now(timezone.utc)
    elif isinstance(updated, datetime):
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
    else:
        updated = datetime.now(timezone.utc)

    return {
        '_id': sesion.get('_id'),
        '_id_str': str(sesion.get('_id')),
        'nombre_usuario': sesion.get('nombre_usuario', 'Cliente'),
        'email': sesion.get('email', ''),
        'estado': sesion.get('estado', 'activo'),
        'updated_at': updated,
        'created_at': sesion.get('created_at'),
        'ultimo_mensaje': ultimo,
        'no_leidos': Chat.contar_no_leidos(str(sesion.get('_id')))
    }


# ================================================================
# WIDGET CLIENTE
# ================================================================

def iniciar_conversacion():
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}

    nombre = (data.get('nombre') or '').strip()
    email = (data.get('email') or '').strip()

    if not nombre:
        return jsonify({"success": False, "error": "El nombre es obligatorio"}), 400

    usuario_id = session.get('user_id')
    sesion_previa = Chat.obtener_sesion_activa(usuario_id)
    es_nueva = sesion_previa is None

    sesion = Chat.obtener_o_crear_sesion(usuario_id, nombre)
    if not sesion:
        return jsonify({"success": False, "error": "No se pudo crear la sesión"}), 500

    if email:
        try:
            Chat.collection.update_one(
                {"_id": sesion["_id"]},
                {"$set": {"email": email}}
            )
        except Exception as e:
            print(f"[Chat] Error guardando email: {e}")

    if es_nueva and not sesion.get("mensajes"):
        mensaje_bienvenida = (
            f"¡Hola {nombre}! 👋 Soy el asistente virtual de ORION. "
            f"¿Cómo puedo ayudarte hoy?"
        )
        Chat.agregar_mensaje(str(sesion["_id"]), mensaje_bienvenida, es_admin=True, es_ia=True)

    return jsonify({
        "success": True,
        "conversacion_id": str(sesion["_id"]),
        "es_nueva": es_nueva
    })


def obtener_conversacion():
    conversacion_id = request.args.get('conversacion_id')
    ultimo = request.args.get('ultimo')

    if not _es_objectid_valido(conversacion_id):
        return jsonify({"success": False, "error": "conversacion_id inválido"}), 400

    sesion = Chat.obtener_por_id(conversacion_id)
    if not sesion:
        return jsonify({"success": False, "error": "Conversación no encontrada"}), 404

    mensajes = Chat.obtener_mensajes(conversacion_id, desde_fecha=ultimo, limite=200)

    mensajes_formateados = []
    ultimo_msg_fecha = ''
    for m in mensajes:
        fecha_iso = _fecha_a_iso(m.get("fecha")) or datetime.now(timezone.utc).isoformat()
        ultimo_msg_fecha = fecha_iso
        mensajes_formateados.append({
            "mensaje": m.get("texto", ""),
            "es_admin": m.get("es_admin", False),
            "es_ia": m.get("es_ia", False),
            "fecha": fecha_iso,
            "nombre_remitente": "Admin" if m.get("es_admin") else sesion.get("nombre_usuario", "Cliente")
        })

    return jsonify({
        "success": True,
        "mensajes": mensajes_formateados,
        "hay_nuevos": len(mensajes_formateados) > 0,
        "ultimo_msg": ultimo_msg_fecha,
        "estado": sesion.get("estado", "activo")
    })


def enviar_mensaje_widget():
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}

    conversacion_id = data.get('conversacion_id')
    mensaje = (data.get('mensaje') or '').strip()

    if not _es_objectid_valido(conversacion_id) or not mensaje:
        return jsonify({"success": False, "error": "Faltan datos o ID inválido"}), 400

    sesion = Chat.obtener_por_id(conversacion_id)
    if not sesion:
        return jsonify({"success": False, "error": "Conversación no encontrada"}), 404

    if _sesion_esta_archivada(sesion):
        Chat.reactivar_sesion(conversacion_id)
        print(f"[Chat] Sesión {conversacion_id} reactivada por mensaje del cliente")

    Chat.agregar_mensaje(conversacion_id, mensaje, es_admin=False, es_ia=False)

    nombre_usuario = sesion.get('nombre_usuario', '')
    try:
        resultado_nlp = NLPService.generar_respuesta(mensaje, nombre_usuario)
    except Exception as e:
        print(f"[Chat] Error en NLP: {e}")
        resultado_nlp = {
            "respuesta": "Gracias por tu mensaje. Un asesor se pondrá en contacto contigo pronto. 📝",
            "intencion": "default",
            "confianza": 0.0,
            "entidades": {"productos": [], "pedidos": [], "ciudades": [], "fechas": []},
            "es_frecuente": False
        }

    respuesta = resultado_nlp["respuesta"]

    mensaje_lower = mensaje.lower()
    if "humano" in mensaje_lower or "asesor" in mensaje_lower or "persona real" in mensaje_lower:
        respuesta += " Un asesor humano estará contigo en breve. 👤"

    Chat.agregar_mensaje(conversacion_id, respuesta, es_admin=True, es_ia=True)

    return jsonify({
        "success": True,
        "respuesta_automatica": respuesta,
        "intencion": resultado_nlp.get("intencion", "default"),
        "confianza": resultado_nlp.get("confianza", 0.0),
        "entidades": resultado_nlp.get("entidades", {}),
        "es_frecuente": resultado_nlp.get("es_frecuente", False)
    })


# ================================================================
# PANEL ADMIN
# ================================================================

def admin_chat_panel():
    if 'user_id' not in session:
        return render_template('admin/login_required.html')

    from app.models.usuarios_model import Usuario
    usuario = Usuario.obtener_por_id(session['user_id'])
    if not usuario:
        return "Usuario no encontrado", 404

    if normalizar_rol(usuario.get('rol')) != 'admin':
        return "Acceso no autorizado", 403

    sesiones_raw = Chat.obtener_sesiones_activas()
    sesiones = []
    for ses in sesiones_raw:
        normalizada = _normalizar_sesion_para_template(ses)
        if normalizada:
            sesiones.append(normalizada)

    stats = Chat.estadisticas()

    return render_template(
        'admin/chat_panel.html',
        sesiones=sesiones,
        respuestas_rapidas=RESPUESTAS_RAPIDAS,
        stats=stats
    )


def admin_enviar_mensaje():
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}

    session_id = data.get('session_id')
    mensaje = (data.get('mensaje') or '').strip()

    if not _es_objectid_valido(session_id) or not mensaje:
        return jsonify({"success": False, "error": "Faltan datos o ID inválido"}), 400

    sesion = Chat.obtener_por_id(session_id)
    if not sesion:
        return jsonify({"success": False, "error": "Sesión no encontrada"}), 404

    if _sesion_esta_archivada(sesion):
        Chat.reactivar_sesion(session_id)

    Chat.agregar_mensaje(session_id, mensaje, es_admin=True, es_ia=False)
    Chat.marcar_como_visto(session_id)

    _registrar_auditoria('enviar_mensaje', session_id=session_id)

    return jsonify({"success": True})


def admin_generar_respuesta_ia():
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}

    mensaje_cliente = (data.get('mensaje') or '').strip()
    session_id = data.get('session_id')

    if not mensaje_cliente:
        return jsonify({"success": False, "error": "Falta mensaje"}), 400

    nombre_usuario = ''
    if _es_objectid_valido(session_id):
        sesion = Chat.obtener_por_id(session_id)
        if sesion:
            nombre_usuario = sesion.get('nombre_usuario', '')

    try:
        resultado = NLPService.generar_respuesta(mensaje_cliente, nombre_usuario)
    except Exception as e:
        print(f"[Chat] Error en NLP: {e}")
        resultado = {
            "respuesta": "Entendido. ¿Podrías darme más detalles para ayudarte mejor?",
            "intencion": "default",
            "confianza": 0.0,
            "entidades": {}
        }

    return jsonify({
        "success": True,
        "respuesta": resultado["respuesta"],
        "intencion": resultado.get("intencion", "default"),
        "confianza": resultado.get("confianza", 0.0),
        "entidades": resultado.get("entidades", {})
    })


# ================================================================
# ARCHIVAR / LISTAR ARCHIVADAS
# ================================================================

def admin_archivar_sesion():
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}

    session_id = data.get('session_id')

    if not _es_objectid_valido(session_id):
        return jsonify({"success": False, "error": "ID inválido"}), 400

    sesion = Chat.obtener_por_id(session_id)
    if not sesion:
        return jsonify({"success": False, "error": "Sesión no encontrada"}), 404

    mensaje_despedida = (
        "La conversación ha sido archivada. Si necesitas más ayuda, "
        "no dudes en escribirnos nuevamente. ¡Gracias! 👋"
    )
    Chat.agregar_mensaje(session_id, mensaje_despedida, es_admin=True, es_ia=True)
    Chat.archivar_sesion(session_id)

    _registrar_auditoria('archivar', session_id=session_id)

    return jsonify({"success": True})


def admin_cerrar_sesion():
    return admin_archivar_sesion()


def admin_obtener_sesiones():
    ok, resp = _es_admin_autenticado()
    if not ok:
        return resp

    sesiones = Chat.obtener_sesiones_activas()
    data = []
    for ses in sesiones:
        mensajes = ses.get('mensajes', [])
        ultimo = mensajes[-1] if mensajes else None
        data.append({
            "_id": str(ses['_id']),
            "nombre_usuario": ses.get('nombre_usuario', 'Cliente'),
            "ultimo_mensaje": ultimo.get('texto', '') if ultimo else '',
            "fecha_ultimo": _fecha_a_iso(ultimo.get('fecha')) if ultimo else '',
            "no_leidos": Chat.contar_no_leidos(str(ses['_id']))
        })
    return jsonify({"success": True, "sesiones": data})


def admin_obtener_sesiones_archivadas():
    ok, resp = _es_admin_autenticado()
    if not ok:
        return resp

    sesiones = Chat.obtener_sesiones_archivadas()
    data = []
    for ses in sesiones:
        mensajes = ses.get('mensajes', [])
        ultimo = mensajes[-1] if mensajes else None
        data.append({
            "_id": str(ses['_id']),
            "nombre_usuario": ses.get('nombre_usuario', 'Cliente'),
            "ultimo_mensaje": ultimo.get('texto', '') if ultimo else '',
            "fecha_ultimo": _fecha_a_iso(ultimo.get('fecha')) if ultimo else '',
            "no_leidos": 0
        })
    return jsonify({"success": True, "sesiones": data})


def admin_reactivar_sesion():
    ok, resp = _es_admin_autenticado()
    if not ok:
        return resp

    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}

    session_id = data.get('session_id')

    if not _es_objectid_valido(session_id):
        return jsonify({"success": False, "error": "ID inválido"}), 400

    Chat.reactivar_sesion(session_id)
    _registrar_auditoria('reactivar', session_id=session_id)
    return jsonify({"success": True})


def admin_obtener_mensajes_sesion():
    session_id = request.args.get('session_id')
    ultimo = request.args.get('ultimo')

    if not _es_objectid_valido(session_id):
        return jsonify({"success": False, "error": "session_id inválido"}), 400

    # Auditoría: solo la primera vez
    if not ultimo:
        _registrar_auditoria('ver_conversacion', session_id=session_id)

    try:
        limite = int(request.args.get('limite', 50))
    except (ValueError, TypeError):
        limite = 50
    limite = max(1, min(limite, 200))

    if ultimo:
        mensajes = Chat.obtener_mensajes(session_id, desde_fecha=ultimo, limite=limite)
    else:
        mensajes = Chat.obtener_mensajes(session_id, desde_fecha=None, limite=limite)

    data = []
    ultimo_msg_fecha = ''
    for m in mensajes:
        fecha_iso = _fecha_a_iso(m.get("fecha")) or datetime.now(timezone.utc).isoformat()
        ultimo_msg_fecha = fecha_iso
        data.append({
            "texto": m.get("texto", ""),
            "es_admin": m.get("es_admin", False),
            "es_ia": m.get("es_ia", False),
            "fecha": fecha_iso
        })

    return jsonify({
        "success": True,
        "mensajes": data,
        "hay_nuevos": len(data) > 0,
        "ultimo_msg": ultimo_msg_fecha
    })


# ================================================================
# POLÍTICA DE RETENCIÓN
# ================================================================

def admin_previsualizar_retencion():
    ok, resp = _es_admin_autenticado()
    if not ok:
        return resp

    try:
        data = Chat.previsualizar_retencion()
        _registrar_auditoria('previsualizar_retencion')
        return jsonify({"success": True, **data})
    except Exception as e:
        print(f"[Chat] Error previsualizando retención: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def admin_ejecutar_retencion():
    ok, resp = _es_admin_autenticado()
    if not ok:
        return resp

    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}

    dias = data.get('dias')
    if dias is not None:
        try:
            dias = int(dias)
            if dias < 1 or dias > 3650:
                return jsonify({"success": False, "error": "dias debe estar entre 1 y 3650"}), 400
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "dias inválido"}), 400

    try:
        eliminadas = Chat.eliminar_sesiones_archivadas(dias=dias)
        _registrar_auditoria('ejecutar_retencion', detalles={'eliminadas': eliminadas})
        return jsonify({
            "success": True,
            "eliminadas": eliminadas,
            "dias_retencion": dias or Chat.DIAS_RETENCION_ARCHIVADAS
        })
    except Exception as e:
        print(f"[Chat] Error ejecutando retención: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ================================================================
# AUDITORÍA
# ================================================================

def admin_listar_auditoria():
    ok, resp = _es_admin_autenticado()
    if not ok:
        return resp

    try:
        filtros = {
            'usuario_id': request.args.get('usuario_id'),
            'session_id': request.args.get('session_id'),
            'accion': request.args.get('accion'),
        }
        limite = int(request.args.get('limite', 100))
        registros = AuditoriaChat.listar(filtros, limite=limite)
        return jsonify({"success": True, "registros": registros})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def admin_estadisticas_auditoria():
    ok, resp = _es_admin_autenticado()
    if not ok:
        return resp

    try:
        return jsonify({"success": True, "stats": AuditoriaChat.estadisticas()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ================================================================
# EXPORTAR PDF
# ================================================================

def admin_exportar_historial_pdf():
    ok, usuario = _es_admin_autenticado()
    if not ok:
        return usuario

    session_id = request.args.get('session_id')
    if not _es_objectid_valido(session_id):
        return jsonify({"success": False, "error": "ID inválido"}), 400

    try:
        sesion = Chat.obtener_sesion_completa(session_id)
        if not sesion:
            return jsonify({"success": False, "error": "Conversación no encontrada"}), 404

        pdf_bytes = generar_pdf_historial(sesion)

        _registrar_auditoria('exportar', session_id=session_id)

        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        nombre_archivo = f'chat_{session_id[:8]}_{datetime.now().strftime("%Y%m%d")}.pdf'
        response.headers['Content-Disposition'] = f'attachment; filename={nombre_archivo}'
        return response

    except Exception as e:
        print(f"[Chat] Error exportando PDF: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ================================================================
# ANONIMIZAR
# ================================================================

def admin_anonimizar_sesion():
    ok, usuario = _es_admin_autenticado()
    if not ok:
        return usuario

    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}

    session_id = data.get('session_id')
    if not _es_objectid_valido(session_id):
        return jsonify({"success": False, "error": "ID inválido"}), 400

    sesion = Chat.obtener_por_id(session_id)
    if not sesion:
        return jsonify({"success": False, "error": "Conversación no encontrada"}), 404

    if sesion.get('anonimizada'):
        return jsonify({"success": False, "error": "Ya está anonimizada"}), 400

    exito = Chat.anonimizar_sesion(session_id)
    if not exito:
        return jsonify({"success": False, "error": "No se pudo anonimizar"}), 500

    _registrar_auditoria('anonimizar', session_id=session_id)
    return jsonify({"success": True})


# ================================================================
# SCHEDULER
# ================================================================

def admin_info_scheduler():
    ok, resp = _es_admin_autenticado()
    if not ok:
        return resp

    try:
        from app.scheduler import listar_tareas
        return jsonify({"success": True, "tareas": listar_tareas()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ================================================================
# NLP
# ================================================================

def admin_entrenar_nlp():
    ok, resp = _es_admin_autenticado()
    if not ok:
        return resp

    try:
        resultado = NLPService.entrenar(forzar=True)
        _registrar_auditoria('entrenar_nlp')
        return jsonify(resultado)
    except Exception as e:
        print(f"[Chat] Error entrenando NLP: {e}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500


def admin_info_nlp():
    ok, resp = _es_admin_autenticado()
    if not ok:
        return resp

    try:
        return jsonify({"success": True, "info": NLPService.info_modelo()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def admin_probar_nlp():
    ok, resp = _es_admin_autenticado()
    if not ok:
        return resp

    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}

    mensaje = (data.get('mensaje') or '').strip()
    if not mensaje:
        return jsonify({"success": False, "error": "Falta mensaje"}), 400

    try:
        resultado = NLPService.generar_respuesta(mensaje)
        return jsonify({"success": True, **resultado})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ================================================================
# SESIÓN GENÉRICA
# ================================================================

def crear_sesion():
    try:
        usuario_id = session.get('user_id')
        nombre = session.get('nombre', 'Anónimo') or 'Anónimo'
        sesion = Chat.obtener_o_crear_sesion(usuario_id, nombre)
        if sesion:
            session['chat_session_id'] = str(sesion['_id'])
            return jsonify({'success': True, 'session_id': str(sesion['_id'])})
        return jsonify({'success': False, 'error': 'No se pudo crear sesión'}), 500
    except Exception as e:
        print(f"[Chat] Error creando sesión: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

      # ================================================================
# DASHBOARD DE AUDITORÍA
# ================================================================

def admin_dashboard_auditoria():
    """Renderiza el dashboard visual de auditoría."""
    if 'user_id' not in session:
        return render_template('admin/login_required.html')

    from app.models.usuarios_model import Usuario
    usuario = Usuario.obtener_por_id(session['user_id'])
    if not usuario:
        return "Usuario no encontrado", 404

    if normalizar_rol(usuario.get('rol')) != 'admin':
        return "Acceso no autorizado", 403

    return render_template('admin/auditoria_dashboard.html')


def admin_datos_dashboard_auditoria():
    """Devuelve los datos agregados para el dashboard de auditoría."""
    ok, resp = _es_admin_autenticado()
    if not ok:
        return resp

    try:
        from app.models.auditoria_model import AuditoriaChat
        from app.config.database_config import db
        from datetime import datetime, timezone, timedelta

        # === 1. Últimos 30 días ===
        hace_30 = datetime.now(timezone.utc) - timedelta(days=30)

        # Acciones por día (últimos 30 días)
        pipeline_dias = [
            {"$match": {"fecha": {"$gte": hace_30}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$fecha"}},
                "total": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]
        acciones_por_dia = list(AuditoriaChat.collection.aggregate(pipeline_dias))
        acciones_por_dia = [{"fecha": r["_id"], "total": r["total"]} for r in acciones_por_dia]

        # Acciones por tipo
        pipeline_acciones = [
            {"$group": {"_id": "$accion", "total": {"$sum": 1}}},
            {"$sort": {"total": -1}}
        ]
        acciones_por_tipo_raw = list(AuditoriaChat.collection.aggregate(pipeline_acciones))
        acciones_por_tipo = []
        for r in acciones_por_tipo_raw:
            acciones_por_tipo.append({
                "accion": r["_id"],
                "label": AuditoriaChat.ACCIONES.get(r["_id"], r["_id"]),
                "total": r["total"]
            })

        # Top admins por actividad
        pipeline_admins = [
            {"$group": {
                "_id": "$usuario_nombre",
                "total": {"$sum": 1}
            }},
            {"$sort": {"total": -1}},
            {"$limit": 10}
        ]
        top_admins = list(AuditoriaChat.collection.aggregate(pipeline_admins))
        top_admins = [{"nombre": r["_id"] or "Anónimo", "total": r["total"]} for r in top_admins]

        # === 2. Totales generales ===
        total_registros = AuditoriaChat.collection.count_documents({})

        hace_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        registros_hoy = AuditoriaChat.collection.count_documents({"fecha": {"$gte": hace_24h}})

        hace_7d = datetime.now(timezone.utc) - timedelta(days=7)
        registros_semana = AuditoriaChat.collection.count_documents({"fecha": {"$gte": hace_7d}})

        # Admins únicos
        admins_unicos = len(AuditoriaChat.collection.distinct("usuario_nombre"))

        # === 3. Últimos 20 registros ===
        ultimos = AuditoriaChat.listar({}, limite=20)

        return jsonify({
            "success": True,
            "totales": {
                "total": total_registros,
                "hoy": registros_hoy,
                "semana": registros_semana,
                "admins_unicos": admins_unicos
            },
            "acciones_por_dia": acciones_por_dia,
            "acciones_por_tipo": acciones_por_tipo,
            "top_admins": top_admins,
            "ultimos": ultimos
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500  