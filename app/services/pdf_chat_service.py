# app/services/pdf_chat_service.py
# ================================================================
# SERVICIO PARA EXPORTAR HISTORIAL DE CHAT A PDF
# Usa reportlab para generar PDFs profesionales
# ================================================================

from datetime import datetime
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable
)


# ================================================================
# COLORES CORPORATIVOS
# ================================================================

ROSA_ORION = colors.HexColor('#e10098')
ROSA_CLARO = colors.HexColor('#fae6f2')
ROSA_OSCURO = colors.HexColor('#c00080')
MORADO_IA = colors.HexColor('#6c5ce7')
MORADO_CLARO = colors.HexColor('#ede8fd')
TEXTO = colors.HexColor('#1a1a2e')
TEXTO_GRIS = colors.HexColor('#888888')
FONDO = colors.HexColor('#f8f9fa')
BORDE = colors.HexColor('#e8e8e8')
EXITO = colors.HexColor('#29a744')


# ================================================================
# UTILIDADES
# ================================================================

def _fmt_fecha(fecha):
    if isinstance(fecha, datetime):
        return fecha.strftime('%d/%m/%Y %H:%M')
    return str(fecha) if fecha else 'N/A'


def _normalizar(texto):
    """Convierte a string seguro."""
    if texto is None:
        return ''
    return str(texto)


# ================================================================
# GENERADOR DE PDF
# ================================================================

def generar_pdf_historial(sesion, incluir_metadatos=True):
    """
    Genera un PDF con el historial completo de una conversación.
    Retorna bytes.
    """
    buffer = BytesIO()

    # --- Datos ---
    nombre_cliente = _normalizar(sesion.get('nombre_usuario', 'Cliente'))
    email = _normalizar(sesion.get('email', 'No proporcionado'))
    estado = _normalizar(sesion.get('estado', 'activo'))
    session_id = _normalizar(sesion.get('_id', ''))
    anonimizada = sesion.get('anonimizada', False)

    fecha_creacion = _fmt_fecha(sesion.get('created_at'))
    fecha_ultima = _fmt_fecha(sesion.get('updated_at'))

    mensajes = sesion.get('mensajes', [])
    total_mensajes = len(mensajes)
    total_cliente = sum(1 for m in mensajes if not m.get('es_admin'))
    total_admin = sum(1 for m in mensajes if m.get('es_admin') and not m.get('es_ia'))
    total_ia = sum(1 for m in mensajes if m.get('es_ia'))

    # --- Documento ---
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f'Reporte de Conversación - {nombre_cliente}',
        author='ORION - Sistema de Atención al Cliente'
    )

    # --- Estilos ---
    styles = getSampleStyleSheet()

    estilo_titulo = ParagraphStyle(
        'TituloOrion',
        parent=styles['Heading1'],
        fontSize=26,
        textColor=ROSA_ORION,
        alignment=TA_LEFT,
        spaceAfter=4
    )

    estilo_subtitulo = ParagraphStyle(
        'SubtituloOrion',
        parent=styles['Normal'],
        fontSize=10,
        textColor=TEXTO_GRIS,
        alignment=TA_LEFT,
        spaceAfter=18
    )

    estilo_seccion = ParagraphStyle(
        'SeccionOrion',
        parent=styles['Heading2'],
        fontSize=13,
        textColor=ROSA_ORION,
        spaceBefore=10,
        spaceAfter=8
    )

    estilo_label = ParagraphStyle(
        'LabelOrion',
        parent=styles['Normal'],
        fontSize=9,
        textColor=TEXTO_GRIS,
        leading=13
    )

    estilo_valor = ParagraphStyle(
        'ValorOrion',
        parent=styles['Normal'],
        fontSize=10,
        textColor=TEXTO,
        leading=13
    )

    estilo_mensaje = ParagraphStyle(
        'MensajeOrion',
        parent=styles['Normal'],
        fontSize=10,
        textColor=TEXTO,
        leading=14,
        spaceAfter=4
    )

    estilo_remitente = ParagraphStyle(
        'RemitenteOrion',
        parent=styles['Normal'],
        fontSize=9,
        leading=12
    )

    # --- Contenido ---
    story = []

    # ------------------------------------------------------------
    # ENCABEZADO
    # ------------------------------------------------------------
    story.append(Paragraph("ORION", estilo_titulo))
    story.append(Paragraph("Sistema de Atención al Cliente", estilo_subtitulo))

    # Línea rosa
    story.append(HRFlowable(
        width="100%", thickness=3, color=ROSA_ORION,
        spaceBefore=0, spaceAfter=14
    ))

    # Título del reporte
    story.append(Paragraph("Reporte de Conversación", ParagraphStyle(
        'ReporteTitulo',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=TEXTO,
        spaceAfter=4
    )))
    story.append(Paragraph(f"ID: {session_id}", estilo_subtitulo))

    # ------------------------------------------------------------
    # INFO DEL CLIENTE
    # ------------------------------------------------------------
    story.append(Paragraph("Información del Cliente", estilo_seccion))

    # Badge de anonimizada
    badge_anon = ""
    if anonimizada:
        badge_anon = '<font color="#c00080"><b>[ANONIMIZADA]</b></font>'

    info_data = [
        [Paragraph("<b>Nombre:</b>", estilo_label), Paragraph(nombre_cliente, estilo_valor)],
        [Paragraph("<b>Email:</b>", estilo_label), Paragraph(email, estilo_valor)],
        [Paragraph("<b>Estado:</b>", estilo_label),
         Paragraph(f"<b>{estado.upper()}</b> {badge_anon}", estilo_valor)],
        [Paragraph("<b>Creada:</b>", estilo_label), Paragraph(fecha_creacion, estilo_valor)],
        [Paragraph("<b>Última actividad:</b>", estilo_label), Paragraph(fecha_ultima, estilo_valor)],
    ]

    tabla_info = Table(info_data, colWidths=[3.5 * cm, 13 * cm])
    tabla_info.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), FONDO),
        ('BOX', (0, 0), (-1, -1), 1, BORDE),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(tabla_info)
    story.append(Spacer(1, 14))

    # ------------------------------------------------------------
    # RESUMEN
    # ------------------------------------------------------------
    story.append(Paragraph("Resumen", estilo_seccion))

    resumen_data = [
        [
            Paragraph("<b>TOTAL MENSAJES</b>", estilo_label),
            Paragraph("<b>DEL CLIENTE</b>", estilo_label),
            Paragraph("<b>ADMIN / IA</b>", estilo_label),
        ],
        [
            Paragraph(f"<font size='20' color='#e10098'><b>{total_mensajes}</b></font>", estilo_valor),
            Paragraph(f"<font size='20' color='#1a1a2e'><b>{total_cliente}</b></font>", estilo_valor),
            Paragraph(f"<font size='20' color='#6c5ce7'><b>{total_admin} / {total_ia}</b></font>", estilo_valor),
        ]
    ]

    tabla_resumen = Table(resumen_data, colWidths=[5.5 * cm, 5.5 * cm, 5.5 * cm])
    tabla_resumen.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), FONDO),
        ('BOX', (0, 0), (-1, -1), 1, BORDE),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDE),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(tabla_resumen)
    story.append(Spacer(1, 20))

    # ------------------------------------------------------------
    # HISTORIAL DE MENSAJES
    # ------------------------------------------------------------
    story.append(Paragraph("Historial de Mensajes", estilo_seccion))
    story.append(HRFlowable(
        width="100%", thickness=1, color=ROSA_ORION,
        spaceBefore=0, spaceAfter=12
    ))

    if not mensajes:
        story.append(Paragraph("<i>No hay mensajes en esta conversación.</i>", estilo_label))
    else:
        for i, m in enumerate(mensajes, 1):
            texto = _normalizar(m.get('texto', ''))
            es_admin = m.get('es_admin', False)
            es_ia = m.get('es_ia', False)
            fecha_msg = _fmt_fecha(m.get('fecha'))

            if es_ia:
                remitente = "ASISTENTE IA"
                color_rem = MORADO_IA
                bg_color = MORADO_CLARO
            elif es_admin:
                remitente = "ADMIN"
                color_rem = ROSA_ORION
                bg_color = ROSA_CLARO
            else:
                remitente = nombre_cliente.upper()
                color_rem = TEXTO
                bg_color = colors.white

            # Encabezado del mensaje
            encabezado = (
                f'<font color="{color_rem.hexval()}"><b>#{i} · {remitente}</b></font>'
                f'<font color="#888888"> · {fecha_msg}</font>'
            )

            # Contenido: encabezado + texto
            contenido_data = [[
                Paragraph(encabezado, estilo_remitente),
            ], [
                Paragraph(texto.replace('\n', '<br/>'), estilo_mensaje),
            ]]

            tabla_mensaje = Table(contenido_data, colWidths=[16.5 * cm])
            tabla_mensaje.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), bg_color),
                ('LINEBEFORE', (0, 0), (0, -1), 3, color_rem),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(tabla_mensaje)
            story.append(Spacer(1, 6))

    # ------------------------------------------------------------
    # PIE DE PÁGINA
    # ------------------------------------------------------------
    story.append(Spacer(1, 20))
    story.append(HRFlowable(
        width="100%", thickness=1, color=BORDE,
        spaceBefore=0, spaceAfter=8
    ))
    story.append(Paragraph(
        f"Documento generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} · "
        f"ORION - Sistema de Atención al Cliente",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=TEXTO_GRIS)
    ))

    # --- Construir ---
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes