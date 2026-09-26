# app/services/lealtad_service.py
# ================================================================
# SERVICIO DE LEALTAD - MOTOR DE REGLAS PERSONALIZADAS
# Asigna cupones automáticamente según el comportamiento del cliente
# ================================================================

from datetime import datetime, timezone, timedelta
import random


class LealtadService:

    # ============================================================
    # MOTOR DE ASIGNACIÓN AUTOMÁTICA DE CUPONES
    # ============================================================

    @staticmethod
    def generar_cupones_para_cliente(usuario_id):
        """
        Analiza el comportamiento del cliente y genera cupones personalizados.
        Se llama después de cada compra o periódicamente.
        """
        # Import lazy para evitar circular import
        from app.models.lealtad_model import Lealtad

        registro = Lealtad.obtener_por_usuario(usuario_id)
        if not registro:
            return []

        cupones_generados = []
        nivel = registro.get('nivel', 'Bronce')
        gasto = registro.get('gasto_total', 0)
        compras = registro.get('compras_realizadas', 0)

        # === Regla 1: Bienvenida ===
        if compras == 1:
            cupones_generados.append({
                "id": f"BIENVENIDA-{usuario_id[:8]}",
                "titulo": "¡Bienvenido a ORION!",
                "descripcion": "10% de descuento en tu próxima compra",
                "tipo": "porcentaje",
                "valor": 10,
                "min_compra": 300,
                "valido_hasta": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
                "color": "#00A650"
            })

        # === Regla 2: Fidelización por nivel ===
        if nivel == 'Plata' and compras >= 3:
            cupones_generados.append({
                "id": f"PLATA-{usuario_id[:8]}",
                "titulo": "Beneficio Plata",
                "descripcion": "5% extra de descuento este mes",
                "tipo": "porcentaje",
                "valor": 5,
                "min_compra": 500,
                "valido_hasta": (datetime.now(timezone.utc) + timedelta(days=15)).isoformat(),
                "color": "#A9AFBC"
            })

        if nivel == 'Oro':
            cupones_generados.append({
                "id": f"ORO-{usuario_id[:8]}",
                "titulo": "Beneficio Oro VIP",
                "descripcion": "Envío gratis + 8% de descuento",
                "tipo": "porcentaje",
                "valor": 8,
                "min_compra": 0,
                "envio_gratis": True,
                "valido_hasta": (datetime.now(timezone.utc) + timedelta(days=20)).isoformat(),
                "color": "#C99B2E"
            })

        if nivel == 'Diamante':
            cupones_generados.append({
                "id": f"DIAMANTE-{usuario_id[:8]}",
                "titulo": "Beneficio Diamante Exclusivo",
                "descripcion": "15% de descuento + envío gratis + regalo sorpresa",
                "tipo": "porcentaje",
                "valor": 15,
                "min_compra": 0,
                "envio_gratis": True,
                "regalo": True,
                "valido_hasta": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
                "color": "#7A5FE0"
            })

        # === Regla 3: Reactivación (cliente inactivo) ===
        ultima = registro.get('ultima_actividad')
        if ultima:
            if isinstance(ultima, str):
                try:
                    ultima = datetime.fromisoformat(ultima.replace('Z', '+00:00'))
                except Exception:
                    ultima = None
            if ultima:
                # Asegurar que la fecha sea aware
                if ultima.tzinfo is None:
                    ultima = ultima.replace(tzinfo=timezone.utc)

                dias_inactivo = (datetime.now(timezone.utc) - ultima).days
                if 30 <= dias_inactivo < 90:
                    cupones_generados.append({
                        "id": f"REACTIVA-{usuario_id[:8]}",
                        "titulo": "¡Te extrañamos!",
                        "descripcion": "20% de descuento para tu regreso",
                        "tipo": "porcentaje",
                        "valor": 20,
                        "min_compra": 200,
                        "valido_hasta": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
                        "color": "#FF9900"
                    })

        # === Regla 4: Próximo a subir de nivel ===
        progreso = Lealtad.obtener_progreso_nivel(gasto)
        if progreso['gasto_restante'] > 0 and progreso['gasto_restante'] <= 1000:
            cupones_generados.append({
                "id": f"NIVEL-{usuario_id[:8]}",
                "titulo": f"¡Estás cerca de {progreso['siguiente_nivel']}!",
                "descripcion": f"Te faltan solo ${progreso['gasto_restante']:.0f} para subir de nivel",
                "tipo": "monto_fijo",
                "valor": 100,
                "min_compra": 500,
                "valido_hasta": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                "color": "#E6007E"
            })

        # === Guardar cupones en el cliente (evitar duplicados) ===
        cupones_actuales = registro.get('cupones_personalizados', [])
        ids_existentes = {c.get('id') for c in cupones_actuales if not c.get('usado')}

        for cupon in cupones_generados:
            if cupon['id'] not in ids_existentes:
                Lealtad.agregar_cupon_personalizado(usuario_id, cupon)

        return cupones_generados

    # ============================================================
    # PROCESAR COMPRA (acumular puntos + generar cupones)
    # ============================================================

    @staticmethod
    def procesar_compra(usuario_id, monto, numero_pedido=None):
        """Procesa una compra completa: puntos + cupones automáticos."""
        from app.models.lealtad_model import Lealtad

        resultado_puntos = Lealtad.acumular_puntos(usuario_id, monto, numero_pedido)

        if not resultado_puntos:
            return None

        # Generar cupones después de la compra
        cupones = LealtadService.generar_cupones_para_cliente(usuario_id)

        return {
            **resultado_puntos,
            "cupones_generados": len(cupones),
            "cupones": cupones
        }

    # ============================================================
    # CÁLCULO DE BENEFICIOS EN CHECKOUT
    # ============================================================

    @staticmethod
    def calcular_beneficios_checkout(usuario_id, subtotal):
        """Calcula los beneficios aplicables al checkout."""
        from app.models.lealtad_model import Lealtad

        registro = Lealtad.obtener_por_usuario(usuario_id)
        if not registro:
            return {
                "descuento_lealtad": 0,
                "descuento_puntos": 0,
                "envio_gratis": False,
                "puntos_a_ganar": 0,
                "nivel": "Bronce",
                "emoji_nivel": "🥉",
                "color_nivel": "#CD7F32"
            }

        nivel = registro.get('nivel', 'Bronce')
        info_nivel = Lealtad.obtener_info_nivel(nivel)

        # Descuento por nivel
        descuento_nivel = subtotal * (info_nivel.get('descuento_base', 0) / 100)

        # Envío gratis
        envio_gratis = False
        if info_nivel.get('envio_gratis'):
            if nivel == 'Diamante':
                envio_gratis = True  # Sin mínimo
            elif subtotal >= 500:
                envio_gratis = True  # Con mínimo

        # Puntos a ganar
        multiplicador = info_nivel.get('multiplicador_puntos', 1.0)
        puntos_a_ganar = int(subtotal * Lealtad.PUNTOS_POR_PESO * multiplicador)

        # Valor de puntos disponibles
        valor_puntos = registro.get('puntos_disponibles', 0) * Lealtad.VALOR_PUNTO

        return {
            "descuento_lealtad": round(descuento_nivel, 2),
            "descuento_puntos": round(valor_puntos, 2),
            "puntos_disponibles": registro.get('puntos_disponibles', 0),
            "envio_gratis": envio_gratis,
            "puntos_a_ganar": puntos_a_ganar,
            "multiplicador": multiplicador,
            "nivel": nivel,
            "emoji_nivel": info_nivel.get('emoji', '🥉'),
            "color_nivel": info_nivel.get('color', '#CD7F32')
        }

    # ============================================================
    # GENERACIÓN MASIVA DE CUPONES (admin)
    # ============================================================

    @staticmethod
    def generar_cupones_masivos(nivel_objetivo=None, monto_minimo=None):
        """Genera cupones para todos los clientes de un nivel."""
        from app.models.lealtad_model import Lealtad

        filtro = {}
        if nivel_objetivo:
            filtro['nivel'] = nivel_objetivo
        if monto_minimo:
            filtro['gasto_total'] = {"$gte": monto_minimo}

        clientes = list(Lealtad.collection.find(filtro))
        total_generados = 0

        for cliente in clientes:
            cupones = LealtadService.generar_cupones_para_cliente(cliente['usuario_id'])
            total_generados += len(cupones)

        return {
            "clientes_procesados": len(clientes),
            "cupones_generados": total_generados
        }