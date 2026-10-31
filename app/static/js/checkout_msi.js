// ================================================================
// app/static/js/checkout_msi.js
// Manejo del modal MSI — MODO SANDBOX 
// ================================================================

/**
 * Genera un token de SANDBOX localmente (sin llamar a ninguna API).
 * En producción esto lo haría  / Stripe.js / MercadoPago.js.
 *
 * @param {string} paymentSourceId  ID interno de la tarjeta guardada
 * @param {string} cvc              CVC de 3-4 dígitos
 * @returns {Promise<string>}       Token ID (tok_sandbox_...)
 */
function tokenizarTarjetaGuardada(paymentSourceId, cvc) {
    return new Promise((resolve, reject) => {
        if (!paymentSourceId || !cvc) {
            return reject(new Error(
                'Faltan el payment_source_id o el CVC.'
            ));
        }

        // Validación mínima del CVC (3 o 4 dígitos)
        if (!/^\d{3,4}$/.test(cvc)) {
            return reject(new Error(
                'El CVC debe tener 3 o 4 dígitos.'
            ));
        }

        console.log('[MSI-SANDBOX] Generando token local (sin API)...');
        console.log('[MSI-SANDBOX] payment_source_id:', paymentSourceId);

        // ⭐ Simulación local: token de un solo uso, sin red
        const tokenId = 'tok_sandbox_' +
            Date.now().toString(36) + '_' +
            Math.random().toString(36).slice(2, 10);

        console.log('[MSI-SANDBOX] Token generado:', tokenId);
        resolve(tokenId);
    });
}

/**
 * Actualiza el payment_source_id oculto cuando el usuario
 * selecciona una tarjeta del dropdown.
 */
function inicializarSelectorTarjetas() {
    const select = document.getElementById('tarjeta_guardada_id');
    if (!select) return;

    const updatePaymentSource = () => {
        const opt = select.options[select.selectedIndex];
        const psId = opt ? (opt.dataset.paymentSource || '') : '';

        const hiddenPs = document.getElementById('payment_source_id');
        if (hiddenPs) hiddenPs.value = psId;

        // Mostrar/ocultar el input del CVC según si hay tarjeta seleccionada
        const wrapper = document.getElementById('wrapper_cvc');
        if (wrapper) {
            wrapper.style.display = select.value ? 'block' : 'none';
        }

        // Limpiar el CVC al cambiar de tarjeta
        const cvcInput = document.getElementById('card_cvc');
        if (cvcInput) cvcInput.value = '';
    };

    select.addEventListener('change', updatePaymentSource);
    updatePaymentSource(); // estado inicial
}

/**
 * Submit del formulario MSI (SANDBOX).
 */
async function procesarPagoMSI(event) {
    event.preventDefault();

    const select           = document.getElementById('tarjeta_guardada_id');
    const paymentSourceId  = document.getElementById('payment_source_id')?.value || '';
    const cvc              = document.getElementById('card_cvc')?.value.trim() || '';
    const mesesMSI         = document.getElementById('meses_msi')?.value || '0';
    const btn              = event.target.querySelector('button[type="submit"]')
                             || document.getElementById('btnPagarMSI');

    // -------- Validaciones --------
    if (!select || !select.value) {
        alert('Selecciona una tarjeta guardada.');
        return;
    }
    if (!paymentSourceId) {
        alert('No se pudo identificar la tarjeta. Recarga la página.');
        return;
    }
    if (!cvc || cvc.length < 3 || cvc.length > 4) {
        alert('Ingresa el CVC de tu tarjeta (3 o 4 dígitos).');
        return;
    }

    // -------- Deshabilitar botón mientras procesa --------
    const originalHTML = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Procesando...';
    }

    try {
        // -------- 1) Token local (sandbox, sin API) --------
        const tokenId = await tokenizarTarjetaGuardada(paymentSourceId, cvc);

        // -------- 2) Enviar al backend (modo sandbox) --------
        const resp = await fetch('/api/checkout/msi', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                token_id:            tokenId,          // ⭐ token de sandbox local
                tarjeta_guardada_id: select.value,     // para resolver la tarjeta en metodos_pago
                meses_msi:           mesesMSI,
                tipo_envio:          document.getElementById('tipo_envio')?.value || 'domicilio',
                nombre:              document.getElementById('nombre')?.value   || '',
                email:               document.getElementById('email')?.value    || '',
                telefono:            document.getElementById('telefono')?.value || ''
            })
        });

        const data = await resp.json();

        if (data.success) {
            // Redirigir al pedido
            window.location.href = data.redirect;
        } else {
            alert(data.error || 'Error al procesar el pago.');
        }
    } catch (err) {
        console.error('[MSI-SANDBOX] Error:', err);
        alert(err.message || 'No se pudo procesar el pago.');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }
    }
}

// ================================================================
// Inicialización
// ================================================================
document.addEventListener('DOMContentLoaded', () => {
    inicializarSelectorTarjetas();

    const formMSI = document.getElementById('formMSI');
    if (formMSI) {
        formMSI.addEventListener('submit', procesarPagoMSI);
    }
});