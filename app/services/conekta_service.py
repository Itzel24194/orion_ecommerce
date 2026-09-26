# app/services/conekta_service.py
import base64
import json
import sys
import requests
from app.config.payment_config import (
    CONEKTA_PRIVATE_KEY,
    CONEKTA_PUBLIC_KEY,
    CONEKTA_API_URL
)


def _auth_header():
    token = base64.b64encode(f'{CONEKTA_PRIVATE_KEY}:'.encode()).decode()
    return {
        'Accept': 'application/vnd.conekta-v2.1.0+json',
        'Content-Type': 'application/json',
        'Authorization': f'Basic {token}'
    }


# ================================================================
# PASO 1 — CREAR ORDEN (sin charges)
# ================================================================

def crear_orden_con_msi(monto_total, descripcion, customer_info,
                        line_items, meses_sin_intereses=0, moneda='MXN'):
    """
    PASO 1: crea la orden en Conekta SIN charges.

    ⭐ Si `customer_info` trae `customer_id`, se incluye en el payload.
       Sin esto, Conekta rechaza cualquier cargo con `payment_source_id`
       (error "no customer to be associated with the payment_source_id").
    """
    try:
        # ---------------------------------------------------------
        # Construir customer_info respetando customer_id
        # ---------------------------------------------------------
        customer_info_payload = {
            'name':  customer_info.get('nombre')   or 'Cliente ORION',
            'email': customer_info.get('email')    or 'cliente@orion.com',
            'phone': customer_info.get('telefono') or '+525555555555',
        }

        # ⭐ CRUCIAL: incluir customer_id si viene del controller
        cid = customer_info.get('customer_id')
        if cid:
            customer_info_payload['customer_id'] = cid
            print(f"👤 [Conekta] Orden con customer_id={cid}", file=sys.stderr)

        payload = {
            'currency': moneda,
            'customer_info': customer_info_payload,
            'line_items': [],
            'metadata': {
                'origen': 'ORION E-commerce',
                'descripcion': descripcion,
                'msi_meses': str(meses_sin_intereses),
            }
        }

        total_cents = 0
        for item in line_items:
            unit_price_cents = int(round(float(item.get('unit_price', 0)) * 100))
            quantity = int(item.get('quantity', 1))
            total_cents += unit_price_cents * quantity
            payload['line_items'].append({
                'name': str(item.get('name', 'Producto'))[:250],
                'unit_price': unit_price_cents,
                'quantity': quantity,
            })

        esperado_cents = int(round(float(monto_total) * 100))
        if total_cents != esperado_cents:
            diff = esperado_cents - total_cents
            print(f"⚠️ [Conekta] ajuste line_items: {diff}¢", file=sys.stderr)
            if diff != 0:
                payload['line_items'].append({
                    'name': 'Ajuste',
                    'unit_price': diff,
                    'quantity': 1,
                })

        r = requests.post(
            f'{CONEKTA_API_URL}/orders',
            headers=_auth_header(),
            data=json.dumps(payload),
            timeout=30
        )

        if r.status_code in (200, 201):
            data = r.json()
            return {'success': True, 'order_id': data.get('id'), 'raw': data}
        else:
            print(f"❌ [Conekta] order {r.status_code}: {r.text}", file=sys.stderr)
            return {'success': False, 'error': r.text, 'status_code': r.status_code}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ================================================================
# PASO 2a — COBRAR CON TOKEN (tarjeta nueva)
# ================================================================

def crear_cargo_con_token(order_id, token_id, monto_total, meses_sin_intereses=0):
    """
    Agrega un cargo a una orden existente usando un token fresco.

    Este es el flujo para TARJETA NUEVA: el frontend genera un token
    con Conekta.Token.create y lo manda al backend.

    Endpoint: POST /orders/{order_id}/charges
    """
    try:
        payment_method = {'type': 'card', 'token_id': token_id}
        if meses_sin_intereses and meses_sin_intereses > 0:
            payment_method['monthly_installments'] = int(meses_sin_intereses)

        payload = {'payment_method': payment_method}

        print(f"💳 [Conekta] POST /orders/{order_id}/charges (token={token_id[:12]}...)",
              file=sys.stderr)

        r = requests.post(
            f'{CONEKTA_API_URL}/orders/{order_id}/charges',
            headers=_auth_header(),
            data=json.dumps(payload),
            timeout=30
        )

        if r.status_code in (200, 201):
            return {'success': True, 'raw': r.json()}
        else:
            print(f"❌ [Conekta] charges {r.status_code}: {r.text}", file=sys.stderr)
            return {'success': False, 'error': r.text}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ================================================================
# CUSTOMER API (para guardar tarjetas)
# ================================================================

def crear_o_actualizar_customer(usuario_id, nombre, email, telefono,
                                conekta_customer_id=None):
    """
    Crea o actualiza un Customer en Conekta.
    Retorna el customer_id.
    """
    try:
        payload = {
            'name': nombre or 'Cliente ORION',
            'email': email or 'cliente@orion.com',
            'phone': telefono or '+525555555555',
            'metadata': {'usuario_id': str(usuario_id), 'origen': 'ORION'},
        }

        if conekta_customer_id:
            r = requests.put(
                f'{CONEKTA_API_URL}/customers/{conekta_customer_id}',
                headers=_auth_header(),
                data=json.dumps(payload),
                timeout=30
            )
        else:
            r = requests.post(
                f'{CONEKTA_API_URL}/customers',
                headers=_auth_header(),
                data=json.dumps(payload),
                timeout=30
            )

        if r.status_code in (200, 201):
            data = r.json()
            return {'success': True, 'customer_id': data.get('id'), 'raw': data}
        else:
            return {'success': False, 'error': r.text}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def crear_payment_source(customer_id, token_id, tipo='card'):
    """
    Registra un payment_source (tarjeta) bajo un customer.
    El token se genera UNA VEZ con Conekta.Token.create en el navegador.
    """
    try:
        payload = {
            'type': tipo,
            'token_id': token_id,
        }

        print(f"💾 [Conekta] POST /customers/{customer_id}/payment_sources",
              file=sys.stderr)

        r = requests.post(
            f'{CONEKTA_API_URL}/customers/{customer_id}/payment_sources',
            headers=_auth_header(),
            data=json.dumps(payload),
            timeout=30
        )

        if r.status_code in (200, 201):
            data = r.json()
            return {
                'success': True,
                'payment_source_id': data.get('id'),
                'raw': data,
            }
        else:
            print(f"❌ [Conekta] payment_source {r.status_code}: {r.text}",
                  file=sys.stderr)
            return {'success': False, 'error': r.text}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ================================================================
# PASO 2b — COBRAR CON PAYMENT_SOURCE (tarjeta guardada, MIT)
# ================================================================

def cobrar_orden_con_payment_source(order_id, customer_id, payment_source_id,
                                     cvc=None, meses_sin_intereses=0):
    """
    Cobra una orden usando una tarjeta guardada (MIT — Merchant Initiated
    Transaction).

    ⚠️ NO se envía CVC. Conekta lo rechaza con `not_pci` cuando va en
       texto plano. La asociación del customer_id a la orden es suficiente
       para cobrar como MIT.

    ⚠️ El parámetro `cvc` se mantiene solo por compatibilidad de firma,
       pero se IGNORA completamente.

    Endpoint: POST /orders/{order_id}/charges
    """
    try:
        payment_method = {
            'type': 'card',
            'payment_source_id': payment_source_id,
        }
        # ⚠️ Nunca enviamos CVC — Conekta lo rechazaría con not_pci
        if meses_sin_intereses and meses_sin_intereses > 0:
            payment_method['monthly_installments'] = int(meses_sin_intereses)

        payload = {'payment_method': payment_method}

        print(f"💳 [Conekta] POST /orders/{order_id}/charges "
              f"payment_source={payment_source_id} (MIT, sin cvc)",
              file=sys.stderr)

        r = requests.post(
            f'{CONEKTA_API_URL}/orders/{order_id}/charges',
            headers=_auth_header(),
            data=json.dumps(payload),
            timeout=30
        )

        if r.status_code in (200, 201):
            return {'success': True, 'raw': r.json()}
        else:
            print(f"❌ [Conekta] charges {r.status_code}: {r.text}", file=sys.stderr)
            return {'success': False, 'error': r.text}
    except Exception as e:
        return {'success': False, 'error': str(e)}