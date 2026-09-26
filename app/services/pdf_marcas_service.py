# ================================================================
# app/services/pdf_marcas_service.py
# Ficha de marca estilo MARCANET usando fpdf
# COMPATIBLE con fpdf clásico Y fpdf2
# ================================================================

from fpdf import FPDF
from datetime import datetime


# ================================================================
# COLORES ORION
# ================================================================
ORION_PINK = (225, 0, 152)
ORION_DARK = (26, 26, 46)
ORION_GRAY = (100, 100, 100)
ORION_LIGHT = (245, 246, 248)
ORION_GREEN = (25, 135, 84)
ORION_YELLOW = (255, 193, 7)
ORION_RED = (220, 53, 69)
ORION_WHITE = (255, 255, 255)
ORION_BLACK = (0, 0, 0)


# ================================================================
# HELPER: LIMPIAR TEXTO
# ================================================================

_REEMPLAZOS = {
    '—': '-', '–': '-', '·': '-', '•': '*', '…': '...',
    '“': '"', '”': '"', '‘': "'", '’': "'",
    '«': '"', '»': '"', '‹': '<', '›': '>',
    '™': '(TM)', '©': '(C)', '®': '(R)',
    '°': 'o', '±': '+/-', '×': 'x', '÷': '/',
    'µ': 'u', '€': 'EUR', '£': 'GBP', '¥': 'JPY', '₹': 'INR',
    '\u00a0': ' ', '\t': ' ', '\r': '', '\n': ' ',
}

_ACENTOS = {
    'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
    'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
    'ñ': 'n', 'Ñ': 'N',
    'ü': 'u', 'Ü': 'U',
    'à': 'a', 'è': 'e', 'ì': 'i', 'ò': 'o', 'ù': 'u',
    'â': 'a', 'ê': 'e', 'î': 'i', 'ô': 'o', 'û': 'u',
    'ç': 'c', 'Ç': 'C',
    '¿': '?', '¡': '!',
}


def _limpiar_texto(texto, max_len=None):
    """Convierte cualquier valor a texto seguro para fpdf."""
    if texto is None:
        return '-'

    t = str(texto)

    for viejo, nuevo in _REEMPLAZOS.items():
        t = t.replace(viejo, nuevo)

    for viejo, nuevo in _ACENTOS.items():
        t = t.replace(viejo, nuevo)

    resultado = []
    for c in t:
        try:
            c.encode('latin-1')
            resultado.append(c)
        except UnicodeEncodeError:
            resultado.append('?')

    t = ''.join(resultado).strip()

    if max_len:
        t = t[:max_len]

    return t if t else '-'


def _pdf_to_bytes(pdf):
    """Convierte output del PDF a bytes. Compatible fpdf clásico y fpdf2."""
    try:
        output = pdf.output(dest='S')
    except TypeError:
        output = pdf.output()

    if isinstance(output, (bytes, bytearray)):
        return bytes(output)

    return output.encode('latin-1')


# ================================================================
# CLASE PDF
# ================================================================

class MarcaPDF(FPDF):

    def __init__(self, marca_nombre=""):
        super().__init__()
        self.marca_nombre = _limpiar_texto(marca_nombre)
        self.set_auto_page_break(auto=True, margin=25)

    def header(self):
        self.set_fill_color(*ORION_PINK)
        self.rect(0, 0, 210, 30, 'F')

        self.set_text_color(*ORION_WHITE)
        self.set_font("Arial", 'B', 20)
        self.set_xy(10, 8)
        self.cell(80, 10, 'ORION', 0, 0, 'L')

        self.set_font("Arial", '', 10)
        self.set_xy(90, 9)
        self.cell(110, 10, 'Auditoria de Marcas - MARCANET', 0, 1, 'R')

        self.set_font("Arial", 'I', 9)
        self.set_xy(10, 20)
        self.cell(190, 6, f"Marca: {self.marca_nombre}", 0, 1, 'L')

        self.set_y(38)

    def footer(self):
        self.set_y(-20)
        self.set_draw_color(*ORION_LIGHT)
        self.line(10, self.get_y(), 200, self.get_y())

        self.set_font("Arial", 'I', 8)
        self.set_text_color(*ORION_GRAY)
        self.cell(0, 5,
                  'Documento generado por ORION System - No es un documento oficial del IMPI.',
                  0, 1, 'L')

        fecha = datetime.now().strftime('%d/%m/%Y %H:%M')
        self.set_font("Arial", '', 8)
        self.cell(0, 5, f'Pagina {self.page_no()} - {fecha}', 0, 0, 'R')


# ================================================================
# HELPERS
# ================================================================

def _color_status(status):
    s = (status or 'pendiente').lower()
    if s == 'activo':
        return ORION_GREEN
    if s == 'negado':
        return ORION_RED
    return ORION_YELLOW


# ================================================================
# 1. FICHA COMPLETA DE UNA MARCA
# ================================================================

def generar_pdf_marca(marca):
    """Genera PDF tipo ficha MARCANET de una marca completa. Retorna bytes."""
    nombre = _limpiar_texto(marca.get('nombre_comercial', 'Sin nombre'))

    pdf = MarcaPDF(marca_nombre=nombre)
    pdf.add_page()
    pdf.set_text_color(*ORION_BLACK)

    # TÍTULO
    pdf.set_font("Arial", 'B', 20)
    pdf.set_text_color(*ORION_DARK)
    pdf.cell(0, 12, 'FICHA DE MARCA', 0, 1, 'C')

    pdf.set_font("Arial", '', 10)
    pdf.set_text_color(*ORION_GRAY)
    pdf.cell(0, 6, 'Acervo de Marcas - Datos extraidos del IMPI', 0, 1, 'C')
    pdf.ln(3)

    pdf.set_fill_color(*ORION_PINK)
    pdf.rect(10, pdf.get_y(), 190, 1.5, 'F')
    pdf.ln(6)

    # I. DATOS
    pdf.set_font("Arial", 'B', 13)
    pdf.set_text_color(*ORION_PINK)
    pdf.cell(0, 8, 'I. DATOS DE LA MARCA', 0, 1, 'L')
    pdf.ln(2)

    status_str = (marca.get('status') or 'pendiente').upper()
    fecha_reg = marca.get('created_at')
    fecha_str = fecha_reg.strftime('%d/%m/%Y') if hasattr(fecha_reg, 'strftime') else '-'

    datos = [
        ("Nombre comercial", _limpiar_texto(marca.get('nombre_comercial'))),
        ("RFC", _limpiar_texto(marca.get('rfc') or '-')),
        ("Correo", _limpiar_texto(marca.get('correo') or '-')),
        ("Telefono", _limpiar_texto(marca.get('telefono') or '-')),
        ("Direccion", _limpiar_texto(marca.get('direccion') or '-')),
        ("Fecha de registro", fecha_str),
        ("Estado", status_str),
    ]

    for label, valor in datos:
        pdf.set_fill_color(*ORION_LIGHT)
        pdf.set_text_color(*ORION_DARK)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(45, 8, '  ' + _limpiar_texto(label, 40), 0, 0, 'L', True)

        pdf.set_font("Arial", '', 10)
        if label == "Estado":
            pdf.set_text_color(*_color_status(marca.get('status')))
            pdf.set_font("Arial", 'B', 10)
        else:
            pdf.set_text_color(*ORION_DARK)

        pdf.cell(145, 8, '  ' + _limpiar_texto(valor, 120), 0, 1, 'L', True)

    pdf.ln(6)

    # II. IMPI
    pdf.set_font("Arial", 'B', 13)
    pdf.set_text_color(*ORION_PINK)
    pdf.cell(0, 8, 'II. RESULTADOS DEL ACERVO IMPI', 0, 1, 'L')
    pdf.ln(2)

    datos_impi = marca.get('datos_impi') or []

    if not datos_impi:
        pdf.set_font("Arial", 'I', 10)
        pdf.set_text_color(*ORION_GRAY)
        pdf.cell(0, 8, '  No hay datos extraidos del IMPI para esta marca.', 0, 1, 'L')
    else:
        pdf.set_font("Arial", '', 10)
        pdf.set_text_color(*ORION_DARK)
        pdf.cell(0, 6,
                 f'  Se encontraron {len(datos_impi)} registros en el Acervo de Marcas del IMPI:',
                 0, 1, 'L')
        pdf.ln(2)

        pdf.set_fill_color(*ORION_PINK)
        pdf.set_text_color(*ORION_WHITE)
        pdf.set_font("Arial", 'B', 8)

        headers = [
            ("Solicitud", 28), ("Tipo", 25), ("Expediente", 30),
            ("Registro", 27), ("Denominacion", 50), ("Clase", 20),
        ]

        for titulo, ancho in headers:
            pdf.cell(ancho, 8, titulo, 0, 0, 'C', True)
        pdf.ln()

        pdf.set_font("Arial", '', 8)
        pdf.set_text_color(*ORION_DARK)
        fill = False
        for item in datos_impi:
            if fill:
                pdf.set_fill_color(249, 249, 249)
            else:
                pdf.set_fill_color(*ORION_WHITE)

            valores = [
                (_limpiar_texto(item.get('solicitud', '-'), 20), 28),
                (_limpiar_texto(item.get('tipo', '-'), 18), 25),
                (_limpiar_texto(item.get('expediente', '-'), 22), 30),
                (_limpiar_texto(item.get('registro', '-'), 20), 27),
                (_limpiar_texto(item.get('denominacion', '-'), 40), 50),
                (_limpiar_texto(item.get('clase', '-'), 10), 20),
            ]

            for valor, ancho in valores:
                pdf.cell(ancho, 7, ' ' + valor, 0, 0, 'L', True)
            pdf.ln()
            fill = not fill

    pdf.ln(6)

    # III. NOTAS
    if marca.get('notas_admin'):
        pdf.set_font("Arial", 'B', 13)
        pdf.set_text_color(*ORION_PINK)
        pdf.cell(0, 8, 'III. NOTAS DEL ADMINISTRADOR', 0, 1, 'L')
        pdf.ln(2)

        pdf.set_font("Arial", '', 10)
        pdf.set_text_color(*ORION_DARK)
        pdf.set_fill_color(*ORION_LIGHT)
        pdf.multi_cell(0, 6, '  ' + _limpiar_texto(marca.get('notas_admin'), 500), 0, 'J', True)
        pdf.ln(6)

    # AVISO
    pdf.ln(4)
    pdf.set_fill_color(*ORION_LIGHT)
    pdf.set_text_color(*ORION_GRAY)
    pdf.set_font("Arial", 'I', 8)

    aviso = (
        "AVISO: Este documento es una representacion no oficial generada por ORION System "
        "a partir de datos publicos consultados en el Acervo de Marcas del IMPI. "
        "No tiene validez legal ni sustituye a los documentos oficiales emitidos por el "
        "Instituto Mexicano de la Propiedad Industrial."
    )

    pdf.multi_cell(0, 5, '  ' + _limpiar_texto(aviso, 800), 0, 'J', True)

    return _pdf_to_bytes(pdf)


# ================================================================
# 2. NOMBRE DE ARCHIVO PDF
# ================================================================

def nombre_archivo_pdf(marca):
    """Genera nombre limpio para el PDF."""
    nombre = (marca.get('nombre_comercial') or 'marca').strip()
    nombre = ''.join(c if c.isalnum() else '_' for c in nombre)
    fecha = datetime.now().strftime('%Y%m%d')
    return f"Ficha_Marca_{nombre}_{fecha}.pdf"


# ================================================================
# 3. PDF MASIVO (TODAS LAS MARCAS)
# ================================================================

def generar_pdf_todas_marcas(marcas):
    """Genera un PDF con todas las marcas."""
    pdf = MarcaPDF(marca_nombre='Reporte General')
    pdf.add_page()
    pdf.set_text_color(*ORION_BLACK)

    pdf.set_font("Arial", 'B', 20)
    pdf.set_text_color(*ORION_DARK)
    pdf.cell(0, 12, 'REPORTE GENERAL DE MARCAS', 0, 1, 'C')

    pdf.set_font("Arial", '', 10)
    pdf.set_text_color(*ORION_GRAY)
    pdf.cell(0, 6, f'Total: {len(marcas)} marcas - Generado el '
                   f'{datetime.now().strftime("%d/%m/%Y a las %H:%M")}',
             0, 1, 'C')
    pdf.ln(3)

    pdf.set_fill_color(*ORION_PINK)
    pdf.rect(10, pdf.get_y(), 190, 1.5, 'F')
    pdf.ln(6)

    for i, marca in enumerate(marcas, 1):
        nombre = _limpiar_texto(marca.get('nombre_comercial', 'Sin nombre'), 100)

        pdf.set_font("Arial", 'B', 12)
        pdf.set_text_color(*ORION_PINK)
        pdf.cell(0, 8, f'{i}. {nombre}', 0, 1, 'L')

        status_str = (marca.get('status') or 'pendiente').upper()
        datos = [
            ("RFC", _limpiar_texto(marca.get('rfc') or '-')),
            ("Correo", _limpiar_texto(marca.get('correo') or '-')),
            ("Estado", status_str),
            ("Registros IMPI", str(len(marca.get('datos_impi') or []))),
        ]

        for label, valor in datos:
            pdf.set_fill_color(*ORION_LIGHT)
            pdf.set_text_color(*ORION_DARK)
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(40, 7, '  ' + _limpiar_texto(label, 35), 0, 0, 'L', True)

            pdf.set_font("Arial", '', 9)
            if label == "Estado":
                pdf.set_text_color(*_color_status(marca.get('status')))
                pdf.set_font("Arial", 'B', 9)
            pdf.cell(150, 7, '  ' + _limpiar_texto(valor, 120), 0, 1, 'L', True)

        pdf.ln(4)

    pdf.ln(4)
    pdf.set_fill_color(*ORION_LIGHT)
    pdf.set_text_color(*ORION_GRAY)
    pdf.set_font("Arial", 'I', 8)
    pdf.multi_cell(0, 5,
                   '  AVISO: Documento generado por ORION System. '
                   'No es un documento oficial del IMPI.',
                   0, 'J', True)

    return _pdf_to_bytes(pdf)


# ================================================================
# 4. PDF DE UN SOLO RESULTADO DEL ACERVO IMPI
# ================================================================

def generar_pdf_resultado_impi(marca, item, index=0):
    """Genera un PDF para UN resultado específico del Acervo IMPI con links a MARCANET."""
    nombre_marca = _limpiar_texto(marca.get('nombre_comercial', 'Sin nombre'))

    pdf = MarcaPDF(marca_nombre=nombre_marca)
    pdf.add_page()
    pdf.set_text_color(*ORION_BLACK)

    # TÍTULO
    pdf.set_font("Arial", 'B', 20)
    pdf.set_text_color(*ORION_DARK)
    pdf.cell(0, 12, 'FICHA DE RESULTADO IMPI', 0, 1, 'C')

    pdf.set_font("Arial", '', 10)
    pdf.set_text_color(*ORION_GRAY)
    pdf.cell(0, 6, f'Registro #{index + 1} del Acervo de Marcas - MARCANET', 0, 1, 'C')
    pdf.ln(3)

    pdf.set_fill_color(*ORION_PINK)
    pdf.rect(10, pdf.get_y(), 190, 1.5, 'F')
    pdf.ln(6)

    # I. MARCA
    pdf.set_font("Arial", 'B', 13)
    pdf.set_text_color(*ORION_PINK)
    pdf.cell(0, 8, 'I. MARCA RELACIONADA', 0, 1, 'L')
    pdf.ln(2)

    datos_marca = [
        ("Nombre comercial", _limpiar_texto(marca.get('nombre_comercial'))),
        ("RFC", _limpiar_texto(marca.get('rfc') or '-')),
    ]

    for label, valor in datos_marca:
        pdf.set_fill_color(*ORION_LIGHT)
        pdf.set_text_color(*ORION_DARK)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(45, 8, '  ' + _limpiar_texto(label, 40), 0, 0, 'L', True)

        pdf.set_font("Arial", '', 10)
        pdf.set_text_color(*ORION_DARK)
        pdf.cell(145, 8, '  ' + _limpiar_texto(valor, 120), 0, 1, 'L', True)

    pdf.ln(6)

    # II. DATOS DEL EXPEDIENTE
    pdf.set_font("Arial", 'B', 13)
    pdf.set_text_color(*ORION_PINK)
    pdf.cell(0, 8, 'II. DATOS DEL EXPEDIENTE', 0, 1, 'L')
    pdf.ln(2)

    datos_impi = [
        ("Solicitud", _limpiar_texto(item.get('solicitud', '-'))),
        ("Tipo de marca", _limpiar_texto(item.get('tipo', '-'))),
        ("Expediente", _limpiar_texto(item.get('expediente', '-'))),
        ("Registro", _limpiar_texto(item.get('registro', '-'))),
        ("Denominación", _limpiar_texto(item.get('denominacion', '-'))),
        ("Clase Niza", _limpiar_texto(item.get('clase', '-'))),
    ]

    for label, valor in datos_impi:
        pdf.set_fill_color(*ORION_LIGHT)
        pdf.set_text_color(*ORION_DARK)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(45, 8, '  ' + _limpiar_texto(label, 40), 0, 0, 'L', True)

        pdf.set_font("Arial", '', 10)
        pdf.set_text_color(*ORION_DARK)
        pdf.cell(145, 8, '  ' + _limpiar_texto(valor, 120), 0, 1, 'L', True)

    pdf.ln(6)

    # III. ENLACES A MARCANET
    pdf.set_font("Arial", 'B', 13)
    pdf.set_text_color(*ORION_PINK)
    pdf.cell(0, 8, 'III. ENLACES AL ACERVO OFICIAL', 0, 1, 'L')
    pdf.ln(2)

    exp = item.get('expediente', '')
    sol = item.get('solicitud', '')

    url_exp = f"https://acervomarcas.impi.gob.mx:8181/marcanet/vistas/common/datos/bsqExpedienteCompleto.pgi?expediente={exp}"
    url_sol = f"https://acervomarcas.impi.gob.mx:8181/marcanet/vistas/common/datos/bsqSolicitudCompleta.pgi?solicitud={sol}"
    url_home = "https://acervomarcas.impi.gob.mx:8181/marcanet/vistas/common/home.pgi"

    # Link expediente
    pdf.set_font("Arial", 'B', 10)
    pdf.set_text_color(*ORION_DARK)
    pdf.cell(0, 6, '  Ver expediente completo en MARCANET:', 0, 1, 'L')

    pdf.set_font("Arial", 'U', 9)
    pdf.set_text_color(13, 110, 253)
    pdf.cell(0, 6, f'  {url_exp}', 0, 1, 'L', link=url_exp)
    pdf.ln(3)

    # Link solicitud
    if sol:
        pdf.set_font("Arial", 'B', 10)
        pdf.set_text_color(*ORION_DARK)
        pdf.cell(0, 6, '  Ver solicitud completa en MARCANET:', 0, 1, 'L')

        pdf.set_font("Arial", 'U', 9)
        pdf.set_text_color(13, 110, 253)
        pdf.cell(0, 6, f'  {url_sol}', 0, 1, 'L', link=url_sol)
        pdf.ln(3)

    # Link home
    pdf.set_font("Arial", 'B', 10)
    pdf.set_text_color(*ORION_DARK)
    pdf.cell(0, 6, '  Portal principal de MARCANET:', 0, 1, 'L')

    pdf.set_font("Arial", 'U', 9)
    pdf.set_text_color(13, 110, 253)
    pdf.cell(0, 6, f'  {url_home}', 0, 1, 'L', link=url_home)
    pdf.ln(4)

    # Nota
    pdf.set_font("Arial", 'I', 8)
    pdf.set_text_color(*ORION_GRAY)
    pdf.set_fill_color(*ORION_LIGHT)
    pdf.multi_cell(0, 5,
                   '  Nota: Los enlaces abren el Acervo Oficial del IMPI en tu navegador. '
                   'Ahi podras descargar el expediente oficial en PDF directamente desde MARCANET.',
                   0, 'J', True)

    pdf.ln(6)

    # IV. CLASE NIZA
    clase = _limpiar_texto(item.get('clase', '-'))

    clases_niza = {
        '1': 'Productos quimicos para la industria, ciencia y fotografia',
        '2': 'Pinturas, barnices, lacas',
        '3': 'Preparaciones para blanquear y otras sustancias detergentes',
        '4': 'Aceites y grasas industriales, lubricantes',
        '5': 'Productos farmaceuticos, veterinarios e higienicos',
        '6': 'Metales comunes y sus aleaciones',
        '7': 'Maquinas y maquinas herramientas',
        '8': 'Herramientas y cuchilleria',
        '9': 'Aparatos e instrumentos cientificos, nauticos, electricos',
        '10': 'Aparatos e instrumentos medicos, dentales y veterinarios',
        '11': 'Aparatos de alumbrado, calefaccion, produccion de vapor',
        '12': 'Vehiculos y aparatos de locomocion',
        '13': 'Armas de fuego, municiones y proyectiles',
        '14': 'Metales preciosos y sus aleaciones',
        '15': 'Instrumentos musicales',
        '16': 'Papel, carton y articulos de papelería',
        '17': 'Caucho, gutapercha, goma y articulos de estas materias',
        '18': 'Cuero e imitaciones de cuero, articulos de cuero',
        '19': 'Materiales de construccion no metalicos',
        '20': 'Muebles, espejos, marcos',
        '21': 'Utensilios y recipientes para el menaje o la cocina',
        '22': 'Cuerdas, cordeles, redes, tiendas de campaña',
        '23': 'Hilos para uso textil',
        '24': 'Tejidos y productos textiles no comprendidos en otras clases',
        '25': 'Vestidos, calzados, sombrereria',
        '26': 'Encajes, bordados, cintas y lazos',
        '27': 'Alfombras, felpudos, esteras, linoleo',
        '28': 'Juegos, juguetes, articulos de gimnasia y deporte',
        '29': 'Carne, pescado, aves y caza, extractos de carne',
        '30': 'Cafe, te, cacao, azucar, arroz, tapioca, sagu',
        '31': 'Productos agricolas, horticolas, forestales y granos',
        '32': 'Cervezas, aguas minerales y otras bebidas sin alcohol',
        '33': 'Bebidas alcoholicas (excepto cervezas)',
        '34': 'Tabaco, articulos para fumadores',
        '35': 'Publicidad, gestion de negocios comerciales',
        '36': 'Seguros, operaciones financieras, monetarias',
        '37': 'Construccion, reparacion, instalacion',
        '38': 'Telecomunicaciones',
        '39': 'Transporte, embalaje, almacenamiento',
        '40': 'Tratamiento de materiales',
        '41': 'Educacion, formacion, entretenimiento, deportes',
        '42': 'Servicios cientificos, tecnologicos, juridicos',
        '43': 'Servicios de restauracion, hospedaje',
        '44': 'Servicios medicos, veterinarios, higienicos',
        '45': 'Servicios juridicos, de seguridad, proteccion',
    }

    clase_desc = clases_niza.get(clase, 'Sin descripcion registrada')

    pdf.set_font("Arial", 'B', 13)
    pdf.set_text_color(*ORION_PINK)
    pdf.cell(0, 8, 'IV. CLASE NIZA', 0, 1, 'L')
    pdf.ln(2)

    pdf.set_font("Arial", '', 10)
    pdf.set_text_color(*ORION_DARK)
    pdf.set_fill_color(*ORION_LIGHT)
    pdf.multi_cell(0, 6, f'  Clase {clase}: {clase_desc}', 0, 'J', True)
    pdf.ln(6)

    # AVISO
    pdf.ln(4)
    pdf.set_fill_color(*ORION_LIGHT)
    pdf.set_text_color(*ORION_GRAY)
    pdf.set_font("Arial", 'I', 8)

    aviso = (
        "AVISO: Este documento es una representacion no oficial generada por ORION System "
        "a partir de datos publicos consultados en el Acervo de Marcas del IMPI. "
        "Para obtener el expediente oficial en PDF, utiliza los enlaces a MARCANET de arriba."
    )

    pdf.multi_cell(0, 5, '  ' + _limpiar_texto(aviso, 800), 0, 'J', True)

    return _pdf_to_bytes(pdf)


# ================================================================
# 5. NOMBRE DE ARCHIVO PARA PDF DE RESULTADO IMPI
# ================================================================

def nombre_archivo_pdf_resultado(marca, item, index=0):
    """Genera nombre limpio para el PDF de un resultado."""
    nombre = (marca.get('nombre_comercial') or 'marca').strip()
    nombre = ''.join(c if c.isalnum() else '_' for c in nombre)
    expediente = (item.get('expediente') or f'resultado_{index + 1}').strip()
    expediente = ''.join(c if c.isalnum() or c in '-_' else '_' for c in expediente)
    return f"Resultado_IMPI_{nombre}_{expediente}.pdf"