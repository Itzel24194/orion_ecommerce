from fpdf import FPDF
from datetime import datetime

class FacturaPDF(FPDF):
    def header(self):
        # Color primario ORION (Rosa intenso)
        self.set_fill_color(225, 0, 152)
        self.rect(0, 0, 210, 30, 'F')
        
        # Título principal
        self.set_text_color(255, 255, 255)
        self.set_font("Arial", 'B', 24)
        self.cell(0, 20, 'ORION FACTURA', 0, 1, 'R')
        
        # Info empresa
        self.set_font("Arial", '', 10)
        self.cell(0, 5, 'www.orion-store.com', 0, 1, 'R')
        self.ln(15)

    def footer(self):
        self.set_y(-25)
        self.set_font("Arial", 'I', 9)
        self.set_text_color(100)
        self.cell(0, 5, 'Gracias por elegir la calidad de ORION.', 0, 1, 'C')
        self.cell(0, 5, 'Documento generado digitalmente.', 0, 0, 'C')

def generar_pdf_factura(carrito, total):
    pdf = FacturaPDF()
    pdf.add_page()
    
    # Datos de usuario y fecha
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 10, f"Fecha de emisión: {datetime.now().strftime('%d de %B de %Y')}", 0, 1, 'L')
    pdf.ln(5)

    # Cabecera de tabla con estilo moderno
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Arial", 'B', 10)
    
    # Línea superior
    pdf.cell(80, 8, "Producto", 0, 0, 'L', True)
    pdf.cell(30, 8, "Cant.", 0, 0, 'C', True)
    pdf.cell(40, 8, "Precio Unit.", 0, 0, 'C', True)
    pdf.cell(40, 8, "Subtotal", 0, 1, 'C', True)
    
    # Filas de productos
    pdf.set_font("Arial", '', 10)
    for item in carrito:
        pdf.cell(80, 10, item.get('nombre', '-'), 'B')
        pdf.cell(30, 10, str(item.get('cantidad', 0)), 'B', 0, 'C')
        pdf.cell(40, 10, f"$ {float(item.get('precio', 0)):,.2f}", 'B', 0, 'C')
        pdf.cell(40, 10, f"$ {float(item.get('precio', 0)) * int(item.get('cantidad', 0)):,.2f}", 'B', 1, 'C')

    # Total destacado con fondo rosa
    pdf.ln(10)
    pdf.set_fill_color(225, 0, 152)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(150, 12, "TOTAL A PAGAR", 0, 0, 'R', True)
    pdf.cell(40, 12, f"$ {total:,.2f}", 0, 1, 'C', True)
    
    return pdf.output(dest='S').encode('latin-1')