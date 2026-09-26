# app/config/payment_config.py
import os

# ================================================================
# CONEKTA — Configuración de pagos con MSI
# ================================================================
CONEKTA_PUBLIC_KEY = os.getenv('CONEKTA_PUBLIC_KEY', 'key_xxxxxxxxxxxxx')
CONEKTA_PRIVATE_KEY = os.getenv('CONEKTA_PRIVATE_KEY', 'key_xxxxxxxxxxxxx')

CONEKTA_API_URL = 'https://api.conekta.io'

# Plazos habilitados (deben coincidir con los activados en tu panel de Conekta)
CONEKTA_MSI_PLAZOS = [3, 6, 9, 12, 18, 24]

# Bancos aceptados por Conekta para MSI (referencia)
CONEKTA_BANCOS_MSI = [
    'bbva', 'banorte', 'santander', 'hsbc', 'citibanamex',
    'scotiabank', 'inbursa', 'bancoppel', 'banregio',
    'banco_del_bajio', 'afirme', 'banca_afirme'
]