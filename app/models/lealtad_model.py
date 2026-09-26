# app/models/lealtad_model.py
# ================================================================
# MODELO DE LEALTAD - CLIENTE CONSENTIDO
# ================================================================

from app.config.database_config import db
from bson import ObjectId
from datetime import datetime, timezone, timedelta


class Lealtad:
    collection = db.lealtad

    # ============================================================
    # CONFIGURACIÓN DE NIVELES
    # ============================================================

    NIVELES = [
        {
            'nombre': 'Bronce',
            'emoji': '🥉',
            'min_gasto': 0,
            'max_gasto': 5000,
            'multiplicador_puntos': 1.0,
            'descuento_base': 0,
            'envio_gratis': False,
            'color': '#CD7F32',
            'beneficios': [
                '1 punto por cada $10 de compra',
                'Acceso a promociones generales'
            ]
        },
        {
            'nombre': 'Plata',
            'emoji': '🥈',
            'min_gasto': 5000,
            'max_gasto': 20000,
            'multiplicador_puntos': 1.5,
            'descuento_base': 3,
            'envio_gratis': False,
            'color': '#A9AFBC',
            'beneficios': [
                '1.5 puntos por cada $10 de compra',
                '3% de descuento en todas las compras',
                'Acceso anticipado a ofertas'
            ]
        },
        {
            'nombre': 'Oro',
            'emoji': '🥇',
            'min_gasto': 20000,
            'max_gasto': 50000,
            'multiplicador_puntos': 2.0,
            'descuento_base': 5,
            'envio_gratis': True,
            'color': '#C99B2E',
            'beneficios': [
                '2 puntos por cada $10 de compra',
                '5% de descuento en todas las compras',
                'Envío gratis en pedidos mayores a $500',
                'Atención preferencial'
            ]
        },
        {
            'nombre': 'Diamante',
            'emoji': '💎',
            'min_gasto': 50000,
            'max_gasto': 999999999,
            'multiplicador_puntos': 3.0,
            'descuento_base': 10,
            'envio_gratis': True,
            'color': '#7A5FE0',
            'beneficios': [
                '3 puntos por cada $10 de compra',
                '10% de descuento en todas las compras',
                'Envío gratis SIN mínimo',
                'Acceso a productos exclusivos',
                'Concierge personal 24/7'
            ]
        }
    ]

    PUNTOS_POR_PESO = 0.1
    VALOR_PUNTO = 0.1

    # ============================================================
    # CREAR / OBTENER
    # ============================================================

    @staticmethod
    def obtener_o_crear(usuario_id, nombre_usuario="Cliente"):
        """Obtiene el registro de lealtad del usuario o lo crea."""
        if not usuario_id:
            return None

        usuario_id_str = str(usuario_id)
        registro = Lealtad.collection.find_one({"usuario_id": usuario_id_str})

        if registro:
            return registro

        nuevo = {
            "usuario_id": usuario_id_str,
            "nombre_usuario": nombre_usuario,
            "nivel": "Bronce",
            "puntos_disponibles": 0,
            "puntos_historicos": 0,
            "gasto_total": 0.0,
            "compras_realizadas": 0,
            "cupones_personalizados": [],
            "historial_puntos": [],
            "fecha_ingreso": datetime.now(timezone.utc),
            "ultima_actividad": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }

        result = Lealtad.collection.insert_one(nuevo)
        nuevo['_id'] = result.inserted_id
        return nuevo

    @staticmethod
    def obtener_por_usuario(usuario_id):
        """Obtiene el registro de lealtad del usuario."""
        if not usuario_id:
            return None
        return Lealtad.collection.find_one({"usuario_id": str(usuario_id)})

    # ============================================================
    # ACUMULAR PUNTOS POR COMPRA
    # ============================================================

    @staticmethod
    def acumular_puntos(usuario_id, monto_compra, numero_pedido=None):
        """Acumula puntos cuando el cliente hace una compra."""
        if not usuario_id or monto_compra <= 0:
            return None

        registro = Lealtad.obtener_o_crear(usuario_id)
        if not registro:
            return None

        nivel_actual = Lealtad._calcular_nivel(registro['gasto_total'])
        multiplicador = Lealtad._obtener_multiplicador(nivel_actual)

        puntos_base = monto_compra * Lealtad.PUNTOS_POR_PESO
        puntos_ganados = int(puntos_base * multiplicador)

        nuevo_gasto = registro['gasto_total'] + monto_compra
        nuevo_nivel = Lealtad._calcular_nivel(nuevo_gasto)

        entrada_historial = {
            "tipo": "compra",
            "puntos": puntos_ganados,
            "monto": monto_compra,
            "multiplicador": multiplicador,
            "pedido": numero_pedido,
            "fecha": datetime.now(timezone.utc),
            "descripcion": f"Compra de ${monto_compra:.2f} ({multiplicador}x)"
        }

        Lealtad.collection.update_one(
            {"usuario_id": str(usuario_id)},
            {
                "$inc": {
                    "puntos_disponibles": puntos_ganados,
                    "puntos_historicos": puntos_ganados,
                    "compras_realizadas": 1
                },
                "$set": {
                    "gasto_total": nuevo_gasto,
                    "nivel": nuevo_nivel,
                    "ultima_actividad": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                },
                "$push": {"historial_puntos": entrada_historial}
            }
        )

        return {
            "puntos_ganados": puntos_ganados,
            "multiplicador": multiplicador,
            "nivel_anterior": nivel_actual,
            "nivel_nuevo": nuevo_nivel,
            "subio_nivel": nivel_actual != nuevo_nivel,
            "puntos_totales": registro['puntos_disponibles'] + puntos_ganados
        }

    # ============================================================
    # CANJEAR PUNTOS
    # ============================================================

    @staticmethod
    def canjear_puntos(usuario_id, puntos_a_canjear, motivo="Canje manual"):
        """Canjea puntos del cliente."""
        if not usuario_id or puntos_a_canjear <= 0:
            return None

        registro = Lealtad.obtener_por_usuario(usuario_id)
        if not registro:
            return None

        if registro['puntos_disponibles'] < puntos_a_canjear:
            return {
                "success": False,
                "error": f"Puntos insuficientes. Tienes {registro['puntos_disponibles']}"
            }

        valor_pesos = puntos_a_canjear * Lealtad.VALOR_PUNTO

        entrada_historial = {
            "tipo": "canje",
            "puntos": -puntos_a_canjear,
            "monto": valor_pesos,
            "fecha": datetime.now(timezone.utc),
            "descripcion": f"{motivo} (${valor_pesos:.2f})"
        }

        Lealtad.collection.update_one(
            {"usuario_id": str(usuario_id)},
            {
                "$inc": {"puntos_disponibles": -puntos_a_canjear},
                "$set": {
                    "ultima_actividad": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                },
                "$push": {"historial_puntos": entrada_historial}
            }
        )

        return {
            "success": True,
            "puntos_canjeados": puntos_a_canjear,
            "valor_pesos": valor_pesos,
            "puntos_restantes": registro['puntos_disponibles'] - puntos_a_canjear
        }

    # ============================================================
    # AJUSTAR PUNTOS MANUALMENTE (admin)
    # ============================================================

    @staticmethod
    def ajustar_puntos(usuario_id, puntos, motivo="Ajuste admin"):
        """Suma o resta puntos manualmente."""
        if not usuario_id:
            return None

        registro = Lealtad.obtener_o_crear(usuario_id)
        if not registro:
            return None

        entrada_historial = {
            "tipo": "ajuste",
            "puntos": puntos,
            "fecha": datetime.now(timezone.utc),
            "descripcion": motivo
        }

        nuevo_saldo = max(0, registro['puntos_disponibles'] + puntos)
        nuevo_historico = registro.get('puntos_historicos', 0)
        if puntos > 0:
            nuevo_historico += puntos

        Lealtad.collection.update_one(
            {"usuario_id": str(usuario_id)},
            {
                "$set": {
                    "puntos_disponibles": nuevo_saldo,
                    "puntos_historicos": nuevo_historico,
                    "ultima_actividad": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                },
                "$push": {"historial_puntos": entrada_historial}
            }
        )

        return {
            "success": True,
            "puntos_nuevos": nuevo_saldo,
            "puntos_ajustados": puntos
        }

    # ============================================================
    # CUPONES PERSONALIZADOS
    # ============================================================

    @staticmethod
    def agregar_cupon_personalizado(usuario_id, cupon):
        """Agrega un cupón personalizado al cliente."""
        if not usuario_id or not cupon:
            return False

        registro = Lealtad.obtener_o_crear(usuario_id)
        if not registro:
            return False

        cupon['fecha_asignacion'] = datetime.now(timezone.utc)
        cupon['usado'] = False

        Lealtad.collection.update_one(
            {"usuario_id": str(usuario_id)},
            {
                "$push": {"cupones_personalizados": cupon},
                "$set": {"updated_at": datetime.now(timezone.utc)}
            }
        )
        return True

    @staticmethod
    def marcar_cupon_usado(usuario_id, cupon_id):
        """Marca un cupón como usado."""
        if not usuario_id or not cupon_id:
            return False

        result = Lealtad.collection.update_one(
            {
                "usuario_id": str(usuario_id),
                "cupones_personalizados.id": cupon_id
            },
            {
                "$set": {
                    "cupones_personalizados.$.usado": True,
                    "cupones_personalizados.$.fecha_uso": datetime.now(timezone.utc)
                }
            }
        )
        return result.modified_count > 0

    # ============================================================
    # CÁLCULO DE NIVELES
    # ============================================================

    @staticmethod
    def _calcular_nivel(gasto_total):
        """Devuelve el nivel según el gasto total."""
        for nivel in Lealtad.NIVELES:
            if nivel['min_gasto'] <= gasto_total < nivel['max_gasto']:
                return nivel['nombre']
        return 'Diamante'

    @staticmethod
    def _obtener_multiplicador(nombre_nivel):
        """Obtiene el multiplicador de puntos según el nivel."""
        for nivel in Lealtad.NIVELES:
            if nivel['nombre'] == nombre_nivel:
                return nivel['multiplicador_puntos']
        return 1.0

    @staticmethod
    def obtener_info_nivel(nombre_nivel):
        """Devuelve toda la info del nivel."""
        for nivel in Lealtad.NIVELES:
            if nivel['nombre'] == nombre_nivel:
                return nivel
        return Lealtad.NIVELES[0]

    @staticmethod
    def obtener_progreso_nivel(gasto_total):
        """Devuelve el progreso hacia el siguiente nivel."""
        nivel_actual = Lealtad._calcular_nivel(gasto_total)

        for i, nivel in enumerate(Lealtad.NIVELES):
            if nivel['nombre'] == nivel_actual:
                if i == len(Lealtad.NIVELES) - 1:
                    return {
                        "nivel_actual": nivel_actual,
                        "siguiente_nivel": None,
                        "progreso_pct": 100,
                        "gasto_actual": gasto_total,
                        "gasto_para_siguiente": 0,
                        "gasto_restante": 0
                    }
                siguiente = Lealtad.NIVELES[i + 1]
                rango = siguiente['min_gasto'] - nivel['min_gasto']
                avance = gasto_total - nivel['min_gasto']
                pct = (avance / rango * 100) if rango > 0 else 100

                return {
                    "nivel_actual": nivel_actual,
                    "siguiente_nivel": siguiente['nombre'],
                    "progreso_pct": round(min(pct, 100), 1),
                    "gasto_actual": gasto_total,
                    "gasto_para_siguiente": siguiente['min_gasto'],
                    "gasto_restante": max(0, siguiente['min_gasto'] - gasto_total)
                }

        return {
            "nivel_actual": "Bronce",
            "siguiente_nivel": "Plata",
            "progreso_pct": 0,
            "gasto_actual": gasto_total,
            "gasto_para_siguiente": 5000,
            "gasto_restante": 5000
        }

    # ============================================================
    # LISTADOS PARA ADMIN
    # ============================================================

    @staticmethod
    def listar_por_nivel(nivel=None, limite=100):
        """Lista clientes filtrados por nivel."""
        filtro = {}
        if nivel:
            filtro['nivel'] = nivel

        return list(
            Lealtad.collection.find(filtro)
            .sort("gasto_total", -1)
            .limit(limite)
        )

    @staticmethod
    def estadisticas():
        """Estadísticas generales del programa de lealtad."""
        total_clientes = Lealtad.collection.count_documents({})

        distribucion = {}
        for nivel in Lealtad.NIVELES:
            distribucion[nivel['nombre']] = Lealtad.collection.count_documents({
                "nivel": nivel['nombre']
            })

        pipeline_puntos = [
            {"$group": {
                "_id": None,
                "puntos_totales": {"$sum": "$puntos_disponibles"},
                "puntos_historicos": {"$sum": "$puntos_historicos"},
                "gasto_total": {"$sum": "$gasto_total"}
            }}
        ]
        resultado = list(Lealtad.collection.aggregate(pipeline_puntos))
        totales = resultado[0] if resultado else {
            "puntos_totales": 0,
            "puntos_historicos": 0,
            "gasto_total": 0
        }

        return {
            "total_clientes": total_clientes,
            "distribucion_niveles": distribucion,
            "puntos_disponibles": totales.get('puntos_totales', 0),
            "puntos_historicos": totales.get('puntos_historicos', 0),
            "gasto_total": totales.get('gasto_total', 0)
        }