// ================================================================
// app/static/js/checkout_msi.js
// Manejo del modal MSI con re-tokenización de tarjetas guardadas
// ================================================================

/**
 * Re-tokeniza una tarjeta guardada con su CVC.
 * Genera un token de un solo uso para el backend.
 *
 * @param {string} paymentSourceId  El src_... de la tarjeta guardada
 * @param {string} cvc              CVC de 3-4 dígitos
 * @returns {Promise<string>}       Token ID (tok_...)
 */
function tokenizarTarjetaGuardada(paymentSourceId, cvc) {
    return new Promise((resolve, reject) => {
        if (typeof Conekta === 'undefined') {
            return reject(new Error(
                'Conekta.js no está cargado. Recarga la página.'
            ));
        }
        if (!paymentSourceId || !cvc) {
            return reject(new Error(
                'Faltan el payment_source_id o el CVC.'
            ));
        }

        console.log('[MSI] Re-tokenizando tarjeta guardada...');
        console.log('[MSI] payment_source_id:', paymentSourceId);

        Conekta.Token.create(
            {
                card: {
                    payment_source_id: paymentSourceId,
                    cvc: cvc
                }
            },
            function success(token) {
                console.log('[MSI] Token generado:', token.id);
                resolve(token.id);
            },
            function error(err) {
                console.error('[MSI] Error tokenizando:', err);
                const msg = (err && (err.message_to_purchaser || err.message))
                            || 'Error al validar la tarjeta.';
                reject(new Error(msg));
            }
        );
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
 * Submit del formulario MSI.
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
        // -------- 1) Re-tokenizar en el navegador --------
        const tokenId = await tokenizarTarjetaGuardada(paymentSourceId, cvc);

        // -------- 2) Enviar al backend --------
        const resp = await fetch('/api/checkout/msi', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                token_id:            tokenId,          // ⭐ token re-tokenizado
                tarjeta_guardada_id: select.value,     // para resolver customer_id
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
        console.error('[MSI] Error:', err);
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