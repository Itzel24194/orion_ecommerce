# ================================================================
# app/controllers/marca_controller.py
# CONTROLADOR DE MARCAS - Estilo MARCANET
# ================================================================

from flask import (
    render_template, request, redirect, url_for,
    flash, jsonify, current_app, send_file, Response
)
from app.models.marcas_model import Marca
from bson import ObjectId
from datetime import datetime
import sys
import io
import os
import csv
from io import StringIO

# ================================================================
# IMPORTS OPCIONALES
# ================================================================

# Playwright (para scraping del IMPI)
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_DISPONIBLE = True
except ImportError:
    PLAYWRIGHT_DISPONIBLE = False

# Servicio de PDF (para generar fichas)
try:
    from app.services.pdf_marcas_service import (
        generar_pdf_marca,
        nombre_archivo_pdf,
        generar_pdf_todas_marcas,
        generar_pdf_resultado_impi,
        nombre_archivo_pdf_resultado
    )
    PDF_DISPONIBLE = True
except ImportError as e:
    print(f"[Marca] PDF service no disponible: {e}", file=sys.stderr)
    PDF_DISPONIBLE = False


# ================================================================
# ============  VISTAS PRINCIPALES  ===============================
# ================================================================

def listar_marcas():
    """Vista principal del panel de marcas."""
    filtros = {}
    if request.args.get('q'):
        filtros['q'] = request.args['q']
    if request.args.get('status'):
        filtros['status'] = request.args['status']

    marcas = Marca.obtener_todas(filtros)
    stats = Marca.estadisticas()

    return render_template('admin/marcas.html',
                          marcas=marcas,
                          stats=stats)


def ver_marca(id):
    """Ver detalle de una marca específica."""
    marca = Marca.obtener_por_id(id)
    if not marca:
        flash("Marca no encontrada", "danger")
        return redirect(url_for('web.lista_marcas'))

    return render_template('admin/marcas.html',
                         marcas=Marca.obtener_todas(),
                         marca_seleccionada=marca,
                         stats=Marca.estadisticas())


# ================================================================
# ============  CRUD  =============================================
# ================================================================

def agregar_marca():
    """Registra una nueva marca."""
    if request.method != 'POST':
        return redirect(url_for('web.lista_marcas'))

    nombre = (request.form.get('nombre') or '').strip()
    rfc = (request.form.get('rfc') or '').upper().strip()
    correo = (request.form.get('correo') or '').strip()
    telefono = (request.form.get('telefono') or '').strip()
    direccion = (request.form.get('direccion') or '').strip()

    if not nombre:
        flash("El nombre comercial es requerido", "danger")
        return redirect(url_for('web.lista_marcas'))

    if Marca.buscar_por_nombre(nombre):
        flash("Ya existe una marca con ese nombre", "danger")
        return redirect(url_for('web.lista_marcas'))

    data = {
        "nombre_comercial": nombre,
        "nombre_normalizado": nombre.upper().replace(' ', ''),
        "rfc": rfc,
        "correo": correo,
        "telefono": telefono,
        "direccion": direccion,
        "status": "pendiente",
        "datos_impi": [],
        "activa": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    Marca.crear(data)
    flash(f"Marca '{nombre}' registrada exitosamente.", "success")
    return redirect(url_for('web.lista_marcas'))


def editar_marca(id):
    """Edita los datos de una marca."""
    if request.method != 'POST':
        return redirect(url_for('web.lista_marcas'))

    data = {
        "nombre_comercial": (request.form.get('nombre') or '').strip(),
        "nombre_normalizado": (request.form.get('nombre') or '').strip().upper().replace(' ', ''),
        "rfc": (request.form.get('rfc') or '').upper().strip(),
        "correo": (request.form.get('correo') or '').strip(),
        "telefono": (request.form.get('telefono') or '').strip(),
        "direccion": (request.form.get('direccion') or '').strip(),
        "updated_at": datetime.utcnow()
    }

    Marca.actualizar_datos(id, data)
    flash("Datos actualizados correctamente.", "success")
    return redirect(url_for('web.lista_marcas'))


def aprobar_marca(id):
    """Aprueba una marca (status → activo)."""
    Marca.actualizar_con_notas(id, "activo", "Aprobada por administrador")
    flash("Marca aprobada exitosamente.", "success")
    return redirect(url_for('web.lista_marcas'))


def negar_marca(id):
    """Niega una marca con motivo."""
    motivo = request.form.get('motivo', 'No especificado')
    Marca.actualizar_con_notas(id, "negado", f"Negada: {motivo}")
    flash("Marca denegada.", "info")
    return redirect(url_for('web.lista_marcas'))


def eliminar_marca(id):
    """Elimina una marca."""
    try:
        Marca.borrar(id)
        flash("Marca eliminada exitosamente.", "success")
    except Exception as e:
        flash(f"Error al eliminar: {e}", "danger")
    return redirect(url_for('web.lista_marcas'))


def toggle_marca(id):
    """Activa/Desactiva una marca."""
    if request.method == 'POST':
        marca = Marca.obtener_por_id(id)
        if marca:
            nuevo_estado = not marca.get('activa', True)
            Marca.actualizar_datos(id, {
                'activa': nuevo_estado,
                'updated_at': datetime.utcnow()
            })
            flash(f'Marca {"activada" if nuevo_estado else "desactivada"} correctamente', 'success')
        else:
            flash('Marca no encontrada', 'danger')
    return redirect(url_for('web.lista_marcas'))


# ================================================================
# ============  SCRAPING IMPI (MARCANET)  ========================
# ================================================================

def _lanzar_navegador(p):
    """
    Intenta lanzar el navegador con varias estrategias (fallback para Windows).
    Retorna (browser, context) o (None, None).
    """
    estrategias = [
        # 1️⃣ Chrome instalado en el sistema
        {
            'nombre': 'Chrome (canal sistema)',
            'fn': lambda: p.chromium.launch(
                headless=True,
                slow_mo=200,
                channel='chrome',
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
        },
        # 2️⃣ Edge instalado en el sistema
        {
            'nombre': 'Edge (canal sistema)',
            'fn': lambda: p.chromium.launch(
                headless=True,
                slow_mo=200,
                channel='msedge',
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
        },
        # 3️⃣ Chromium por defecto
        {
            'nombre': 'Chromium por defecto',
            'fn': lambda: p.chromium.launch(
                headless=True,
                slow_mo=200,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
        },
        # 4️⃣ Chromium headless nuevo
        {
            'nombre': 'Chromium headless=new',
            'fn': lambda: p.chromium.launch(
                headless=True,
                slow_mo=200,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--headless=new',
                    '--disable-gpu',
                    '--disable-dev-shm-usage'
                ]
            )
        },
    ]

    for estrategia in estrategias:
        try:
            print(f"[IMPI] Intentando lanzar: {estrategia['nombre']}", file=sys.stderr)
            browser = estrategia['fn']()
            print(f"[IMPI] ✅ Navegador lanzado: {estrategia['nombre']}", file=sys.stderr)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1400, 'height': 900},
                locale='es-MX'
            )
            return browser, context
        except Exception as e:
            print(f"[IMPI] ⚠️ Falló '{estrategia['nombre']}': {e}", file=sys.stderr)
            continue

    return None, None


def buscar_y_guardar_impi(id):
    """
    Busca la marca en el Acervo de Marcas del IMPI (MARCANET).
    Guarda screenshots y HTML en /static/debug_impi/ para inspección.
    """
    marca = Marca.obtener_por_id(id)
    if not marca:
        flash("Marca no encontrada", "danger")
        return redirect(url_for('web.lista_marcas'))

    nombre = marca.get('nombre_comercial', '')
    if not nombre:
        flash("La marca no tiene nombre comercial", "warning")
        return redirect(url_for('web.lista_marcas'))

    # Carpeta de debug
    debug_dir = os.path.join(current_app.root_path, 'static', 'debug_impi')
    os.makedirs(debug_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    datos = []

    if PLAYWRIGHT_DISPONIBLE:
        try:
            with sync_playwright() as p:
                print("\n" + "=" * 70, file=sys.stderr)
                print(f"[IMPI DEBUG] INICIANDO SCRAPING - {timestamp}", file=sys.stderr)
                print("=" * 70, file=sys.stderr)

                browser, context = _lanzar_navegador(p)

                if not browser:
                    flash(
                        "No se pudo abrir ningún navegador para el scraping. "
                        "Revisa la terminal para más detalles.",
                        "danger"
                    )
                    return redirect(url_for('web.lista_marcas'))

                page = context.new_page()

                # ============================================
                # 1. NAVEGAR
                # ============================================
                print("[DEBUG] Navegando al sitio...", file=sys.stderr)
                page.goto(
                    "https://acervomarcas.impi.gob.mx:8181/marcanet/vistas/common/home.pgi",
                    wait_until="networkidle",
                    timeout=60000
                )

                try:
                    page.screenshot(
                        path=os.path.join(debug_dir, f'01_inicio_{timestamp}.png'),
                        full_page=True
                    )
                    print(f"[DEBUG] Screenshot inicial guardado", file=sys.stderr)
                except Exception as e:
                    print(f"[DEBUG] No se pudo guardar screenshot 01: {e}", file=sys.stderr)

                # ============================================
                # 2. LLENAR CAMPO
                # ============================================
                print("[DEBUG] Buscando campo de búsqueda...", file=sys.stderr)
                campo = page.wait_for_selector(
                    'input[type="text"], input[name*="denominacion"], input[id*="denominacion"]',
                    timeout=20000
                )
                campo.fill(nombre)
                print(f"[DEBUG] Campo llenado con: {nombre}", file=sys.stderr)

                # ============================================
                # 3. CLIC BUSCAR
                # ============================================
                print("[DEBUG] Haciendo clic en Buscar...", file=sys.stderr)
                try:
                    boton = page.wait_for_selector(
                        'button:has-text("Buscar"), input[type="submit"], button[type="submit"]',
                        timeout=10000
                    )
                    boton.click()
                except Exception as e:
                    print(f"[DEBUG] No se encontró botón, intentando ENTER: {e}", file=sys.stderr)
                    campo.press('Enter')

                # ============================================
                # 4. ESPERAR TABLA
                # ============================================
                print("[DEBUG] Esperando tabla...", file=sys.stderr)
                page.wait_for_selector('table', state='visible', timeout=30000)
                page.wait_for_timeout(3000)

                try:
                    page.screenshot(
                        path=os.path.join(debug_dir, f'02_resultados_{timestamp}.png'),
                        full_page=True
                    )
                    print(f"[DEBUG] Screenshot de resultados guardado", file=sys.stderr)
                except Exception as e:
                    print(f"[DEBUG] No se pudo guardar screenshot 02: {e}", file=sys.stderr)

                try:
                    html_content = page.content()
                    html_path = os.path.join(debug_dir, f'03_html_{timestamp}.html')
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    print(f"[DEBUG] HTML guardado en: {html_path}", file=sys.stderr)
                except Exception as e:
                    print(f"[DEBUG] No se pudo guardar HTML: {e}", file=sys.stderr)

                # ============================================
                # 5. ANÁLISIS DE TABLAS
                # ============================================
                tablas = page.query_selector_all('table')
                print(f"\n[DEBUG] Total de tablas en la página: {len(tablas)}", file=sys.stderr)

                for idx_t, tabla in enumerate(tablas):
                    filas_t = tabla.query_selector_all('tr')
                    print(f"\n[DEBUG] ===== TABLA #{idx_t}: {len(filas_t)} filas =====", file=sys.stderr)

                    for idx_f, fila in enumerate(filas_t[:3]):
                        celdas = fila.query_selector_all('td, th')
                        textos = []
                        for c in celdas:
                            txt = c.inner_text().strip()
                            textos.append(txt[:25] if txt else '(vacío)')
                        print(f"  Fila {idx_f}: {len(celdas)} celdas → {textos}", file=sys.stderr)

                # ============================================
                # 6. DETECTAR TABLA CORRECTA
                # ============================================
                print(f"\n[DEBUG] Buscando tabla de resultados...", file=sys.stderr)

                tabla_correcta = None
                for tabla in tablas:
                    filas_t = tabla.query_selector_all('tr')
                    if len(filas_t) >= 3:
                        for fila in filas_t:
                            celdas = fila.query_selector_all('td')
                            if len(celdas) >= 6:
                                tabla_correcta = tabla
                                print(f"[DEBUG] ✓ Tabla encontrada con filas de {len(celdas)} celdas", file=sys.stderr)
                                break
                        if tabla_correcta:
                            break

                if not tabla_correcta and tablas:
                    print("[DEBUG] No se detectó tabla específica, usando la más grande", file=sys.stderr)
                    tabla_correcta = max(tablas, key=lambda t: len(t.query_selector_all('tr')))

                # ============================================
                # 7. EXTRAER DATOS
                # ============================================
                if tabla_correcta:
                    filas = tabla_correcta.query_selector_all('tr')
                    print(f"\n[DEBUG] Procesando {len(filas)} filas", file=sys.stderr)

                    for idx_f, f in enumerate(filas):
                        celdas = f.query_selector_all('td')
                        print(f"[DEBUG] Fila {idx_f}: {len(celdas)} celdas", file=sys.stderr)

                        if len(celdas) >= 6:
                            registro = {
                                "solicitud": celdas[0].inner_text().strip(),
                                "tipo": celdas[1].inner_text().strip(),
                                "expediente": celdas[2].inner_text().strip(),
                                "registro": celdas[3].inner_text().strip(),
                                "denominacion": celdas[4].inner_text().strip(),
                                "clase": celdas[5].inner_text().strip()
                            }
                            datos.append(registro)
                            print(f"[DEBUG] ✓ Registro: {registro}", file=sys.stderr)

                        elif len(celdas) >= 4:
                            textos = [c.inner_text().strip() for c in celdas]
                            print(f"[DEBUG] Ajustando fila: {textos}", file=sys.stderr)
                            registro = {
                                "solicitud": textos[0] if len(textos) > 0 else '',
                                "tipo": textos[1] if len(textos) > 1 else '',
                                "expediente": textos[2] if len(textos) > 2 else '',
                                "registro": textos[3] if len(textos) > 3 else '',
                                "denominacion": textos[4] if len(textos) > 4 else '',
                                "clase": textos[5] if len(textos) > 5 else ''
                            }
                            if registro['denominacion'] or registro['expediente']:
                                datos.append(registro)

                browser.close()
                print(f"\n[DEBUG] ✅ TOTAL EXTRAÍDO: {len(datos)} registros", file=sys.stderr)
                print("=" * 70, file=sys.stderr)

        except PlaywrightTimeoutError as e:
            print(f"[IMPI] Timeout: {e}", file=sys.stderr)
            flash("El sitio del IMPI no respondió a tiempo. Intenta nuevamente.", "warning")
            return redirect(url_for('web.lista_marcas'))
        except Exception as e:
            print(f"[IMPI] Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            flash(f"Error técnico durante la extracción: {str(e)}", "danger")
            return redirect(url_for('web.lista_marcas'))
    else:
        print("[IMPI] Playwright no disponible. Generando datos demo.", file=sys.stderr)
        datos = [
            {
                "solicitud": "MX/2024/123456",
                "tipo": "Nominativa",
                "expediente": "2024-123456",
                "registro": "2345678",
                "denominacion": nombre,
                "clase": "25"
            },
        ]

    Marca.actualizar_resultados_impi(id, datos)

    if len(datos) > 0:
        flash(f"Se extrajeron {len(datos)} registros de la marca '{nombre}'.", "success")
    else:
        flash(f"No se encontraron registros para '{nombre}'. Revisa /static/debug_impi/", "warning")

    return redirect(url_for('web.lista_marcas'))


# ================================================================
# ============  PDFs  =============================================
# ================================================================

def descargar_pdf_marca(id):
    """Descarga un PDF con la ficha completa de una marca."""
    if not PDF_DISPONIBLE:
        flash("Servicio de PDF no disponible. Instala fpdf o reportlab.", "danger")
        return redirect(url_for('web.lista_marcas'))

    marca = Marca.obtener_por_id(id)
    if not marca:
        flash("Marca no encontrada", "danger")
        return redirect(url_for('web.lista_marcas'))

    try:
        pdf_bytes = generar_pdf_marca(marca)
        filename = nombre_archivo_pdf(marca)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print(f"[PDF Marca] Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        flash(f"Error al generar el PDF: {str(e)}", "danger")
        return redirect(url_for('web.lista_marcas'))


def descargar_pdf_todas_marcas():
    """Descarga un PDF con TODAS las marcas."""
    if not PDF_DISPONIBLE:
        flash("Servicio de PDF no disponible.", "danger")
        return redirect(url_for('web.lista_marcas'))

    try:
        marcas = Marca.obtener_todas()
        if not marcas:
            flash("No hay marcas para exportar", "warning")
            return redirect(url_for('web.lista_marcas'))

        pdf_bytes = generar_pdf_todas_marcas(marcas)
        fecha = datetime.now().strftime('%Y%m%d_%H%M')
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"Reporte_Marcas_{fecha}.pdf"
        )
    except Exception as e:
        print(f"[PDF Masivo] Error: {e}", file=sys.stderr)
        flash(f"Error al generar el PDF: {str(e)}", "danger")
        return redirect(url_for('web.lista_marcas'))


def descargar_pdf_resultado_impi(marca_id, index):
    """
    Descarga PDF individual de un resultado del Acervo IMPI.
    `index` es la posición del resultado en el array `datos_impi`.
    """
    if not PDF_DISPONIBLE:
        flash("Servicio de PDF no disponible.", "danger")
        return redirect(url_for('web.lista_marcas'))

    marca = Marca.obtener_por_id(marca_id)
    if not marca:
        flash("Marca no encontrada", "danger")
        return redirect(url_for('web.lista_marcas'))

    datos_impi = marca.get('datos_impi') or []

    try:
        index = int(index)
    except (ValueError, TypeError):
        flash("Índice de resultado inválido", "danger")
        return redirect(url_for('web.lista_marcas'))

    if index < 0 or index >= len(datos_impi):
        flash("Resultado no encontrado en el acervo", "danger")
        return redirect(url_for('web.lista_marcas'))

    item = datos_impi[index]

    try:
        pdf_bytes = generar_pdf_resultado_impi(marca, item, index)
        filename = nombre_archivo_pdf_resultado(marca, item, index)

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print(f"[PDF Resultado IMPI] Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        flash(f"Error al generar el PDF: {str(e)}", "danger")
        return redirect(url_for('web.lista_marcas'))


# ================================================================
# ============  EXPORTAR CSV  =====================================
# ================================================================

def exportar_marcas_csv():
    """Exporta todas las marcas a CSV."""
    marcas = Marca.obtener_todas()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Nombre', 'RFC', 'Correo', 'Teléfono',
        'Dirección', 'Estado', 'Registros IMPI'
    ])

    for m in marcas:
        writer.writerow([
            m.get('nombre_comercial', ''),
            m.get('rfc', ''),
            m.get('correo', ''),
            m.get('telefono', ''),
            m.get('direccion', ''),
            m.get('status', ''),
            len(m.get('datos_impi') or [])
        ])

    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename=marcas.csv'
    return response


# ================================================================
# ============  APIs JSON  ========================================
# ================================================================

def api_marcas():
    marcas = Marca.obtener_todas()
    for m in marcas:
        m['_id'] = str(m['_id'])
        for k, v in list(m.items()):
            if hasattr(v, 'isoformat'):
                m[k] = v.isoformat()
    return jsonify({'success': True, 'marcas': marcas})


def api_marca(id):
    marca = Marca.obtener_por_id(id)
    if not marca:
        return jsonify({'success': False, 'message': 'Marca no encontrada'}), 404

    marca['_id'] = str(marca['_id'])
    for k, v in list(marca.items()):
        if hasattr(v, 'isoformat'):
            marca[k] = v.isoformat()
    return jsonify({'success': True, 'marca': marca})


def buscar_marcas():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'success': True, 'marcas': []})

    marcas = Marca.buscar_por_nombre(query, parcial=True, limit=10)
    for m in marcas:
        m['_id'] = str(m['_id'])
    return jsonify({'success': True, 'marcas': marcas})


def obtener_marcas_activas():
    marcas = Marca.obtener_todas({'status': 'activo', 'activa': True})
    for m in marcas:
        m['_id'] = str(m['_id'])
    return jsonify({'success': True, 'marcas': marcas})


def obtener_marca_por_rfc():
    rfc = request.args.get('rfc', '').upper().strip()
    if not rfc:
        return jsonify({'success': False, 'message': 'RFC requerido'}), 400

    marca = Marca.buscar_por_rfc(rfc)
    if not marca:
        return jsonify({'success': False, 'message': 'Marca no encontrada'}), 404

    marca['_id'] = str(marca['_id'])
    return jsonify({'success': True, 'marca': marca})


def estadisticas_marcas():
    return jsonify({'success': True, 'estadisticas': Marca.estadisticas()})


def buscar_marcas_fonetica():
    nombre = request.args.get('nombre', '').strip()
    if not nombre:
        return jsonify({'success': True, 'marcas': []})

    marcas = Marca.buscar_fonetica(nombre)
    for m in marcas:
        m['_id'] = str(m['_id'])
    return jsonify({'success': True, 'marcas': marcas})


# ================================================================
# ============  DEBUG  ============================================
# ================================================================

def debug_funciones():
    """Lista las funciones del módulo (para verificar)."""
    funciones = [n for n in dir() if not n.startswith('_') and callable(globals().get(n))]
    return jsonify({'funciones': sorted(funciones)})