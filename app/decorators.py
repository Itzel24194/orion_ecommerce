from functools import wraps
from flask import session, flash, redirect, url_for
import sys

def login_required(f):
    """Verifica que el usuario esté autenticado"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Debes iniciar sesión para acceder a esta página.", "warning")
            return redirect(url_for('web.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Verifica que el usuario sea administrador"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Debes iniciar sesión para acceder a esta página.", "warning")
            return redirect(url_for('web.login'))
        
        rol = session.get('rol', 'cliente')
        if rol != 'admin':
            print(f"⚠️ Acceso denegado: Usuario {session.get('email')} con rol {rol} intentó acceder a área admin", file=sys.stderr)
            flash("No tienes permisos de administrador.", "danger")
            return redirect(url_for('web.raiz_tienda'))
        return f(*args, **kwargs)
    return decorated_function

def cliente_required(f):
    """Verifica que el usuario sea cliente (no admin)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Debes iniciar sesión para acceder a esta página.", "warning")
            return redirect(url_for('web.login'))
        
        rol = session.get('rol', 'cliente')
        if rol == 'admin':
            print(f"⚠️ Acceso denegado: Admin {session.get('email')} intentó acceder a área de cliente", file=sys.stderr)
            flash("Los administradores no pueden acceder a esta sección de clientes.", "warning")
            return redirect(url_for('web.dashboard'))
        return f(*args, **kwargs)
    return decorated_function