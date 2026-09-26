# ================================================================
# app/decorators.py - Decoradores de autenticación y roles
# Web: sesión (cookie) | Móvil: JWT (Bearer)
# ================================================================

from functools import wraps
from flask import session, flash, redirect, url_for, request, jsonify, current_app
import sys

from app.jwt_utils import get_current_user_from_request


# ================================================================
# HELPER: RESOLVER USUARIO (sesión O JWT)
# ================================================================

def _es_peticion_api():
    """True si la petición viene de un cliente API (JSON)."""
    return (
        request.path.startswith('/api/')
        or request.headers.get('Accept', '').startswith('application/json')
    )


def _resolver_usuario_jwt():
    """
    Si no hay sesión y viene un JWT válido, inyecta sus datos en session
    para que el resto del código (que usa session.get(...)) funcione igual.
    Devuelve True si inyectó datos, False si no.
    """
    if 'user_id' in session:
        return False

    payload = get_current_user_from_request()
    if not payload:
        return False

    session['user_id'] = payload.get('user_id')
    session['email'] = payload.get('email')
    session['nombre'] = payload.get('nombre', 'Usuario')
    session['rol'] = payload.get('rol', 'cliente')

    # Evitar que Flask emita Set-Cookie en respuestas API
    session.modified = False
    return True


def _respuesta_no_autorizado(mensaje="Debes iniciar sesión para acceder a esta página."):
    """Devuelve JSON si es API, o flash+redirect si es web."""
    if _es_peticion_api():
        return jsonify({"error": mensaje}), 401
    flash(mensaje, "warning")
    return redirect(url_for('web.login'))


def _respuesta_prohibido(mensaje, redirect_endpoint=None):
    """Devuelve JSON 403 si es API, o flash+redirect si es web."""
    if _es_peticion_api():
        return jsonify({"error": mensaje}), 403
    flash(mensaje, "danger")
    return redirect(url_for(redirect_endpoint or 'web.raiz_tienda'))


# ================================================================
# HELPER: NORMALIZAR ROL
# ================================================================

def _get_rol_normalizado():
    rol_raw = (session.get('rol') or 'cliente')
    rol = str(rol_raw).strip().lower()

    if rol in ('admin', 'administrador', 'super_admin', 'superadmin', 'root'):
        return 'admin'
    if rol in ('vendedor', 'vendor', 'seller', 'vendedora'):
        return 'vendedor'
    return 'cliente'


# ⭐ NUEVO: Helper para saber si el usuario es vendedor de marketplace
def _es_vendedor_marketplace():
    """
    True si el usuario tiene una tienda de marketplace activa y aprobada.
    Chequea primero session['es_vendedor'] (rápido) y si no, consulta la BD.

    Este helper permite que los usuarios con rol='cliente' pero con tienda
    aprobada en el marketplace puedan acceder al panel de vendedor.
    """
    # 1) Atajo: si ya lo tenemos en sesión, confiar
    if session.get('es_vendedor'):
        return True

    # 2) Fallback: consultar la BD
    user_id = session.get('user_id')
    if not user_id:
        return False

    try:
        from bson import ObjectId
        from app.models.marketplace_model import Vendedor

        db = current_app.db
        v = Vendedor.obtener_por_user(db, user_id)

        if v and v.get('estado') == 'aprobado' and v.get('activo', True):
            # Sincronizar sesión para futuras peticiones (evita golpear BD cada vez)
            session['es_vendedor'] = True
            return True
    except Exception as e:
        print(f"⚠️ [_es_vendedor_marketplace] {e}", file=sys.stderr)

    return False


# ================================================================
# LOGIN REQUIRED
# ================================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        _resolver_usuario_jwt()
        if 'user_id' not in session:
            return _respuesta_no_autorizado()
        return f(*args, **kwargs)
    return decorated_function


# ================================================================
# ADMIN REQUIRED
# ================================================================

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        _resolver_usuario_jwt()
        if 'user_id' not in session:
            return _respuesta_no_autorizado()

        rol = _get_rol_normalizado()
        if rol != 'admin':
            print(
                f"⚠️ Acceso denegado (admin): Usuario {session.get('email')} "
                f"con rol normalizado '{rol}' (raw: '{session.get('rol')}')",
                file=sys.stderr
            )
            return _respuesta_prohibido("No tienes permisos de administrador.")

        return f(*args, **kwargs)
    return decorated_function


# ================================================================
# CLIENTE REQUIRED
# ================================================================

def cliente_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        _resolver_usuario_jwt()
        if 'user_id' not in session:
            return _respuesta_no_autorizado()

        rol = _get_rol_normalizado()

        if rol == 'admin':
            print(
                f"⚠️ Acceso denegado (cliente): Admin {session.get('email')} "
                f"intentó acceder a área de cliente",
                file=sys.stderr
            )
            return _respuesta_prohibido(
                "Los administradores no pueden acceder a esta sección de clientes.",
                'web.dashboard'
            )

        if rol == 'vendedor':
            print(
                f"⚠️ Acceso denegado (cliente): Vendedor {session.get('email')} "
                f"intentó acceder a área de cliente",
                file=sys.stderr
            )
            return _respuesta_prohibido(
                "Los vendedores tienen su propio panel de gestión.",
                'web.vendedor_dashboard'
            )

        return f(*args, **kwargs)
    return decorated_function


# ================================================================
# VENDEDOR REQUIRED  ⭐ MODIFICADO para aceptar Marketplace
# ================================================================

def vendedor_required(f):
    """
    Permite acceso a:
      • rol == 'vendedor'   (vendedor nativo)
      • rol == 'admin'      (acceso total)
      • es_vendedor == True (vendedor del marketplace)  ⭐ NUEVO
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        _resolver_usuario_jwt()
        if 'user_id' not in session:
            return _respuesta_no_autorizado()

        rol = _get_rol_normalizado()

        # 1) Vendedor nativo o admin → acceso directo
        if rol in ('vendedor', 'admin'):
            return f(*args, **kwargs)

        # 2) ⭐ NUEVO: cliente con tienda de marketplace aprobada
        if _es_vendedor_marketplace():
            return f(*args, **kwargs)

        # 3) Sin permisos
        print(
            f"⚠️ Acceso denegado (vendedor): Usuario {session.get('email')} "
            f"con rol normalizado '{rol}' (raw: '{session.get('rol')}') "
            f"es_vendedor={session.get('es_vendedor')} "
            f"intentó acceder a área de vendedor",
            file=sys.stderr
        )
        return _respuesta_prohibido("No tienes permisos de vendedor para acceder a esta sección.")
    return decorated_function


# ================================================================
# ROL REQUIRED (genérico)
# ================================================================

def rol_required(*roles_permitidos):
    roles_norm = {str(r).strip().lower() for r in roles_permitidos}

    if 'admin' in roles_norm or 'administrador' in roles_norm:
        roles_norm.update(['admin', 'administrador', 'superadmin', 'super_admin'])
    if 'vendedor' in roles_norm or 'seller' in roles_norm or 'vendor' in roles_norm:
        roles_norm.update(['vendedor', 'seller', 'vendor'])
    if 'cliente' in roles_norm:
        roles_norm.update(['cliente', 'client', 'customer'])

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            _resolver_usuario_jwt()
            if 'user_id' not in session:
                return _respuesta_no_autorizado()

            rol_raw = str(session.get('rol') or 'cliente').strip().lower()
            if rol_raw in roles_norm:
                return f(*args, **kwargs)

            print(
                f"⚠️ Acceso denegado: Usuario {session.get('email')} con rol '{rol_raw}' "
                f"intentó acceder a ruta que requiere uno de {sorted(roles_norm)}",
                file=sys.stderr
            )
            return _respuesta_prohibido("No tienes permisos para acceder a esta sección.")
        return decorated_function
    return decorator


# ================================================================
# PERMISO REQUIRED
# ================================================================

def permiso_required(permiso):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            _resolver_usuario_jwt()
            if 'user_id' not in session:
                return _respuesta_no_autorizado()

            try:
                from app.config.roles_permisos import PERMISOS_FLAT
            except ImportError:
                return _respuesta_prohibido("Error de configuración de permisos.")

            rol = _get_rol_normalizado()
            if rol == 'admin':
                return f(*args, **kwargs)

            permisos = PERMISOS_FLAT.get(rol, [])
            if permiso in permisos:
                return f(*args, **kwargs)

            print(
                f"⚠️ Permiso denegado: {session.get('email')} (rol={rol}) no tiene '{permiso}'",
                file=sys.stderr
            )
            return _respuesta_prohibido("No tienes permiso para realizar esta acción.")
        return decorated_function
    return decorator


# ================================================================
# DEBUG
# ================================================================

def debug_rol():
    from flask import jsonify
    return jsonify({
        'user_id': session.get('user_id'),
        'email': session.get('email'),
        'nombre': session.get('nombre'),
        'rol_raw': session.get('rol'),
        'rol_normalizado': _get_rol_normalizado(),
        # ⭐ NUEVO: exponer es_vendedor para debug
        'es_vendedor': bool(session.get('es_vendedor', False)),
        'es_vendedor_marketplace': _es_vendedor_marketplace(),
    })