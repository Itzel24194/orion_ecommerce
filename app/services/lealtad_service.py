# app/services/lealtad_service.py
# ================================================================
# SERVICIO DE LEALTAD - REGLAS CON REGENERACIÓN
# ================================================================

from datetime import datetime, timezone, timedelta
import secrets
import string


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _safe_list(v):
    return v if isinstance(v, list) else []


def _to_aware(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except Exception:
            return None
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _nuevo_codigo(prefijo='LC'):
    return f"{prefijo}-" + ''.join(
        secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)
    )


# ================================================================
# HELPERS DE CUPONES Y COOLDOWNS
# ================================================================

def _cupones_activos_de_tipo(registro, tipo_regla):
    """Devuelve lista de cupones NO usados del tipo dado."""
    resultado = []
    for c in _safe_list(registro.get('cupones_personalizados')):
        if not isinstance(c, dict):
            continue
        if c.get('tipo_regla') != tipo_regla:
            continue
        if c.get('usado', False):
            continue
        resultado.append(c)
    return resultado


def _dias_desde_ultimo_de_tipo(registro, tipo_regla):
    """Días desde el último cupón (usado o no) de ese tipo. None si nunca hubo."""
    ahora = datetime.now(timezone.utc)
    ultimo = None
    for c in _safe_list(registro.get('cupones_personalizados')):
        if not isinstance(c, dict):
            continue
        if c.get('tipo_regla') != tipo_regla:
            continue
        fecha = _to_aware(c.get('creado_en') or c.get('valido_hasta') or c.get('usado_en'))
        if not fecha:
            continue
        if ultimo is None or fecha > ultimo:
            ultimo = fecha
    if ultimo is None:
        return None
    return (ahora - ultimo).days


def _puede_regenerar(registro, tipo_regla, cooldown_dias=30):
    """
    True si el cliente puede recibir un cupón NUEVO de ese tipo.
    - Bloquea si ya tiene uno ACTIVO (no usado) de ese tipo.
    - Bloquea si el último cupón de ese tipo fue hace menos de `cooldown_dias`.
    - Permite si el último fue hace más de `cooldown_dias` O si nunca tuvo uno.
    """
    if _cupones_activos_de_tipo(registro, tipo_regla):
        return False, "Ya tiene un cupón activo de este tipo"

    dias = _dias_desde_ultimo_de_tipo(registro, tipo_regla)
    if dias is not None and dias < cooldown_dias:
        return False, f"Último cupón hace {dias} días (esperar {cooldown_dias})"

    return True, ""


def _tiene_cupon_activo(registro, tipo_regla):
    """Compatibilidad con código previo."""
    return bool(_cupones_activos_de_tipo(registro, tipo_regla))


class LealtadService:

    # ============================================================
    # REGLAS
    # Cada regla devuelve:
    #   - dict cupón si aplica
    #   - {"_omitido": True, "motivo": "..."} si NO aplica pero se quiere registrar el motivo
    #   - None si no aplica y no vale la pena registrar motivo
    # ============================================================

    @staticmethod
    def _regla_bienvenida(usuario_id, registro):
        """Bienvenida: solo UNA VEZ en la vida del cliente."""
        compras = _safe_int(registro.get('compras_realizadas', 0))
        gasto = _safe_float(registro.get('gasto_total', 0))

        # Ya tuvo bienvenida alguna vez → no regenerar NUNCA
        if _dias_desde_ultimo_de_tipo(registro, 'bienvenida') is not None:
            return {"_omitido": True, "motivo": "Ya recibió bienvenida anteriormente"}

        if _tiene_cupon_activo(registro, 'bienvenida'):
            return {"_omitido": True, "motivo": "Ya tiene cupón de bienvenida activo"}

        if compras > 5:
            return {"_omitido": True, "motivo": f"Cliente con {compras} compras no aplica bienvenida"}

        if gasto > 5000:
            return {"_omitido": True, "motivo": "Gasto alto · no aplica bienvenida"}

        return {
            "id": f"BIENVENIDA-{str(usuario_id)[:8]}-{int(datetime.now().timestamp())}",
            "tipo_regla": "bienvenida",
            "motivo": "Cliente nuevo en el programa",
            "titulo": "¡Bienvenido a ORION!",
            "descripcion": "10% de descuento en tu próxima compra",
            "tipo": "porcentaje",
            "valor": 10,
            "min_compra": 300,
            "creado_en": datetime.now(timezone.utc),
            "valido_hasta": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "color": "#00A650",
        }

    @staticmethod
    def _regla_nivel(usuario_id, registro):
        """
        Cupón de nivel con REGENERACIÓN cada 30 días.
        Aplica a TODOS los niveles (incluido Bronce) si tiene 1+ compras.
        """
        nivel = registro.get('nivel') or 'Bronce'
        compras = _safe_int(registro.get('compras_realizadas', 0))

        # Sin compras → no aplica
        if compras < 1:
            return {"_omitido": True, "motivo": f"Sin compras registradas ({compras})"}

        # Cooldown de 30 días (o bloqueo si ya tiene activo)
        puede, razon = _puede_regenerar(registro, 'nivel', cooldown_dias=30)
        if not puede:
            return {"_omitido": True, "motivo": razon}

        config = {
            'Bronce':   {'valor': 5,  'min_compra': 300, 'envio_gratis': False, 'regalo': False, 'color': '#CD7F32'},
            'Plata':    {'valor': 5,  'min_compra': 500, 'envio_gratis': False, 'regalo': False, 'color': '#A9AFBC'},
            'Oro':      {'valor': 8,  'min_compra': 0,   'envio_gratis': True,  'regalo': False, 'color': '#C99B2E'},
            'Diamante': {'valor': 15, 'min_compra': 0,   'envio_gratis': True,  'regalo': True,  'color': '#7A5FE0'},
        }
        cfg = config.get(nivel, config['Bronce'])

        desc = f"{cfg['valor']}% de descuento"
        if cfg['envio_gratis']:
            desc += " + envío gratis"
        if cfg['regalo']:
            desc += " + regalo"

        return {
            "id": f"{nivel.upper()}-{str(usuario_id)[:8]}-{int(datetime.now().timestamp())}",
            "tipo_regla": "nivel",
            "motivo": f"Beneficio {nivel} · {compras} compra(s)",
            "titulo": f"Beneficio {nivel}",
            "descripcion": desc,
            "tipo": "porcentaje",
            "valor": cfg['valor'],
            "min_compra": cfg['min_compra'],
            "envio_gratis": cfg['envio_gratis'],
            "regalo": cfg['regalo'],
            "creado_en": datetime.now(timezone.utc),
            "valido_hasta": (datetime.now(timezone.utc) + timedelta(days=45)).isoformat(),
            "color": cfg['color'],
        }

    @staticmethod
    def _regla_reactivacion(usuario_id, registro):
        """Reactivación: solo si el cliente lleva 30+ días sin comprar. Cooldown 60 días."""
        puede, razon = _puede_regenerar(registro, 'reactivacion', cooldown_dias=60)
        if not puede:
            return {"_omitido": True, "motivo": razon}

        ultima = _to_aware(registro.get('ultima_actividad') or registro.get('updated_at'))
        if not ultima:
            return None

        dias = (datetime.now(timezone.utc) - ultima).days
        if dias < 30:
            return None

        return {
            "id": f"REACTIVA-{str(usuario_id)[:8]}-{int(datetime.now().timestamp())}",
            "tipo_regla": "reactivacion",
            "motivo": f"Inactivo {dias} días",
            "titulo": "¡Te extrañamos!",
            "descripcion": "20% de descuento para tu regreso",
            "tipo": "porcentaje",
            "valor": 20,
            "min_compra": 200,
            "creado_en": datetime.now(timezone.utc),
            "valido_hasta": (datetime.now(timezone.utc) + timedelta(days=15)).isoformat(),
            "color": "#FF9900",
        }

    @staticmethod
    def _regla_proximo_nivel(usuario_id, registro):
        """Próximo nivel: si está a menos de $2,000 de subir. Cooldown 30 días."""
        puede, razon = _puede_regenerar(registro, 'proximo_nivel', cooldown_dias=30)
        if not puede:
            return {"_omitido": True, "motivo": razon}

        from app.models.lealtad_model import Lealtad
        gasto = _safe_float(registro.get('gasto_total', 0))
        try:
            progreso = Lealtad.obtener_progreso_nivel(gasto) or {}
        except Exception:
            return None

        restante = _safe_float(progreso.get('gasto_restante', 0))
        siguiente = progreso.get('siguiente_nivel')
        if not siguiente:
            return None
        if not (0 < restante <= 2000):
            return None

        return {
            "id": f"NIVEL-{str(usuario_id)[:8]}-{int(datetime.now().timestamp())}",
            "tipo_regla": "proximo_nivel",
            "motivo": f"A ${restante:.0f} de {siguiente}",
            "titulo": f"¡Cerca de {siguiente}!",
            "descripcion": f"Te faltan ${restante:.0f} para subir de nivel",
            "tipo": "monto_fijo",
            "valor": 100,
            "min_compra": 500,
            "creado_en": datetime.now(timezone.utc),
            "valido_hasta": (datetime.now(timezone.utc) + timedelta(days=15)).isoformat(),
            "color": "#E6007E",
        }

    _NOMBRES_REGLAS = (
        '_regla_bienvenida',
        '_regla_nivel',
        '_regla_reactivacion',
        '_regla_proximo_nivel',
    )

    # ============================================================
    # GENERACIÓN POR CLIENTE
    # ============================================================

    @staticmethod
    def generar_cupones_para_cliente(usuario_id, detalle=False):
        from app.models.lealtad_model import Lealtad

        registro = Lealtad.obtener_por_usuario(usuario_id)
        if not registro:
            if detalle:
                return {"generados": [], "omitidos": [], "motivos": ["Cliente sin registro de lealtad"]}
            return []

        # IDs activos (no usados) para evitar duplicados exactos por ID
        cupones_actuales = _safe_list(registro.get('cupones_personalizados'))
        ids_activos = set()
        for c in cupones_actuales:
            if not isinstance(c, dict):
                continue
            if not c.get('usado', False):
                cid = c.get('id') or c.get('codigo')
                if cid:
                    ids_activos.add(cid)

        generados = []
        omitidos = []
        motivos = []

        for regla_nombre in LealtadService._NOMBRES_REGLAS:
            regla_fn = getattr(LealtadService, regla_nombre, None)
            if not callable(regla_fn):
                motivos.append(f"Regla {regla_nombre} no es callable")
                continue

            try:
                cupon = regla_fn(usuario_id, registro)
            except Exception as e:
                motivos.append(f"Error en {regla_nombre}: {e}")
                print(f'[lealtad_service] Error en {regla_nombre}: {e}', flush=True)
                continue

            if not cupon:
                continue

            # Regla devolvió motivo de omisión explícito
            if isinstance(cupon, dict) and cupon.get('_omitido'):
                omitidos.append({
                    "id": cupon.get('id') or regla_nombre,
                    "tipo_regla": cupon.get('tipo_regla') or regla_nombre.replace('_regla_', ''),
                    "motivo": cupon.get('motivo') or 'No aplica',
                })
                continue

            if cupon['id'] in ids_activos:
                omitidos.append({
                    "id": cupon['id'],
                    "tipo_regla": cupon.get('tipo_regla'),
                    "motivo": "Ya tiene este cupón activo (id duplicado)",
                })
                continue

            try:
                if hasattr(Lealtad, 'agregar_cupon_personalizado'):
                    Lealtad.agregar_cupon_personalizado(usuario_id, cupon)
                else:
                    filtro_uid = {'$or': [
                        {'usuario_id': str(usuario_id)},
                        {'usuario_id': usuario_id},
                    ]}
                    try:
                        from bson import ObjectId
                        filtro_uid['$or'].append({'usuario_id': ObjectId(str(usuario_id))})
                    except Exception:
                        pass
                    Lealtad.collection.update_one(
                        filtro_uid,
                        {'$push': {'cupones_personalizados': cupon}}
                    )
                generados.append({
                    "id": cupon['id'],
                    "tipo_regla": cupon.get('tipo_regla'),
                    "titulo": cupon.get('titulo'),
                    "motivo": cupon.get('motivo'),
                })
                ids_activos.add(cupon['id'])
            except Exception as e:
                motivos.append(f"No se pudo guardar {cupon['id']}: {e}")
                print(f'[lealtad_service] No se pudo guardar {cupon["id"]}: {e}', flush=True)

        if detalle:
            return {"generados": generados, "omitidos": omitidos, "motivos": motivos}
        return [g['id'] for g in generados]

    # ============================================================
    # GENERACIÓN MASIVA
    # ============================================================

    @staticmethod
    def generar_cupones_masivos(nivel_objetivo=None, monto_minimo=None):
        from app.models.lealtad_model import Lealtad

        if nivel_objetivo in (None, '', 'null', 'None', 'todos'):
            nivel_objetivo = None

        filtro = {}
        if nivel_objetivo:
            filtro['nivel'] = nivel_objetivo
        if monto_minimo:
            try:
                filtro['gasto_total'] = {"$gte": float(monto_minimo)}
            except (TypeError, ValueError):
                pass

        try:
            clientes = list(Lealtad.collection.find(filtro))
        except Exception as e:
            print(f'[lealtad_service] Error listando clientes: {e}', flush=True)
            return {
                "clientes_procesados": 0,
                "total_generados": 0,
                "total_omitidos": 0,
                "detalle": [],
                "error": str(e),
            }

        print(f'[lealtad_service] Procesando {len(clientes)} clientes (filtro={filtro})', flush=True)

        detalle = []
        total_gen = 0
        total_omi = 0

        for cliente in clientes:
            uid = cliente.get('usuario_id')
            if not uid:
                continue

            try:
                res = LealtadService.generar_cupones_para_cliente(uid, detalle=True)
            except Exception as e:
                res = {"generados": [], "omitidos": [], "motivos": [str(e)]}
                print(f'[lealtad_service] Error cliente {uid}: {e}', flush=True)

            g = res.get('generados', [])
            o = res.get('omitidos', [])
            m = res.get('motivos', [])

            total_gen += len(g)
            total_omi += len(o)

            detalle.append({
                "usuario_id": str(uid),
                "nombre": cliente.get('nombre_usuario') or 'Cliente',
                "nivel": cliente.get('nivel') or 'Bronce',
                "generados": g,
                "omitidos": o,
                "motivos": m,
            })

        print(
            f'[lealtad_service] Resultado: {total_gen} generados, '
            f'{total_omi} omitidos en {len(clientes)} clientes',
            flush=True
        )

        return {
            "clientes_procesados": len(clientes),
            "total_generados": total_gen,
            "total_omitidos": total_omi,
            "detalle": detalle,
            "error": None,
        }

    # ============================================================
    # RESTO (sin cambios)
    # ============================================================

    @staticmethod
    def procesar_compra(usuario_id, monto, numero_pedido=None):
        from app.models.lealtad_model import Lealtad
        monto = _safe_float(monto)
        if monto <= 0:
            return None
        try:
            resultado_puntos = Lealtad.acumular_puntos(usuario_id, monto, numero_pedido)
        except Exception as e:
            print(f'[lealtad_service] Error acumular_puntos: {e}', flush=True)
            return None
        if not resultado_puntos:
            return None
        cupones = LealtadService.generar_cupones_para_cliente(usuario_id)
        return {
            **resultado_puntos,
            "cupones_generados": len(cupones),
            "cupones": cupones,
        }

    @staticmethod
    def calcular_beneficios_checkout(usuario_id, subtotal):
        from app.models.lealtad_model import Lealtad
        subtotal = _safe_float(subtotal)
        registro = Lealtad.obtener_por_usuario(usuario_id)
        if not registro:
            return {
                "descuento_lealtad": 0,
                "descuento_puntos": 0,
                "puntos_disponibles": 0,
                "envio_gratis": False,
                "puntos_a_ganar": 0,
                "multiplicador": 1.0,
                "nivel": "Bronce",
                "emoji_nivel": "🥉",
                "color_nivel": "#CD7F32",
            }
        nivel = registro.get('nivel') or 'Bronce'
        try:
            info_nivel = Lealtad.obtener_info_nivel(nivel) or {}
        except Exception:
            info_nivel = {}
        descuento_base = _safe_float(info_nivel.get('descuento_base', 0))
        descuento_nivel = subtotal * (descuento_base / 100.0)
        envio_gratis = False
        if info_nivel.get('envio_gratis'):
            if nivel == 'Diamante':
                envio_gratis = True
            elif subtotal >= 500:
                envio_gratis = True
        multiplicador = _safe_float(info_nivel.get('multiplicador_puntos', 1.0), 1.0)
        puntos_por_peso = _safe_float(getattr(Lealtad, 'PUNTOS_POR_PESO', 0.1), 0.1)
        puntos_a_ganar = int(subtotal * puntos_por_peso * multiplicador)
        valor_punto = _safe_float(getattr(Lealtad, 'VALOR_PUNTO', 0.01), 0.01)
        puntos_disponibles = _safe_int(registro.get('puntos_disponibles', 0))
        valor_puntos = puntos_disponibles * valor_punto
        return {
            "descuento_lealtad": round(descuento_nivel, 2),
            "descuento_puntos": round(valor_puntos, 2),
            "puntos_disponibles": puntos_disponibles,
            "envio_gratis": envio_gratis,
            "puntos_a_ganar": puntos_a_ganar,
            "multiplicador": multiplicador,
            "nivel": nivel,
            "emoji_nivel": info_nivel.get('emoji', '🥉'),
            "color_nivel": info_nivel.get('color', '#CD7F32'),
        }