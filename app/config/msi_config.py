# app/config/msi_config.py
# ================================================================
# CONFIGURACIÓN DE MESES SIN INTERESES (MSI) — México
# ================================================================
# Cada opción tiene:
#   - meses: número de meses
#   - min: monto mínimo de compra para aplicar
#   - tasa_interes: porcentaje ANUAL de interés (0 = MSI puro)
#   - etiqueta: texto a mostrar
#   - tipo: "sin_interes" o "con_interes"
#   - bancos: lista de bancos participantes (se muestra en el modal)
# ================================================================

MSI_OPCIONES = [
    {
        "meses": 3,
        "min": 300,
        "tasa_interes": 0,
        "etiqueta": "3 MSI",
        "tipo": "sin_interes",
        "bancos": ["BBVA", "Banorte", "Santander", "HSBC", "Citibanamex", "Scotiabank", "Inbursa", "BanCoppel"],
    },
    {
        "meses": 6,
        "min": 600,
        "tasa_interes": 0,
        "etiqueta": "6 MSI",
        "tipo": "sin_interes",
        "bancos": ["BBVA", "Banorte", "Santander", "HSBC", "Citibanamex", "Scotiabank", "Inbursa", "BanCoppel"],
    },
    {
        "meses": 9,
        "min": 1000,
        "tasa_interes": 0,
        "etiqueta": "9 MSI",
        "tipo": "sin_interes",
        "bancos": ["BBVA", "Banorte", "Santander", "Citibanamex"],
    },
    {
        "meses": 12,
        "min": 2000,
        "tasa_interes": 0,
        "etiqueta": "12 MSI",
        "tipo": "sin_interes",
        "bancos": ["BBVA", "Banorte", "Citibanamex"],
    },
    {
        "meses": 18,
        "min": 3000,
        "tasa_interes": 0,
        "etiqueta": "18 MSI",
        "tipo": "sin_interes",
        "bancos": ["BBVA", "Banorte"],
    },
    {
        "meses": 24,
        "min": 5000,
        "tasa_interes": 15.9,
        "etiqueta": "24 meses",
        "tipo": "con_interes",
        "bancos": ["BBVA", "Banorte", "Santander"],
    },
]

# Tarjetas de tienda (aplican MSI propios sin importar monto)
TARJETAS_TIENDA = [
    {
        "nombre": "Tarjeta ORION",
        "meses_max": 12,
        "tasa_interes": 0,
    },
]

# Texto legal que se muestra en el modal
MSI_LEGAL = (
    "Los Meses Sin Intereses aplican únicamente con tarjetas de crédito participantes. "
    "El monto mínimo para cada plan depende del banco emisor. "
    "Consulta términos y condiciones con tu banco. "
    "ORION no se hace responsable por cambios en las políticas de los bancos."
)