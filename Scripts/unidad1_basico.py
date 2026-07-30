import streamlit as st
import pandas as pd
import numpy as np

# Configuración de diseño amplio
st.set_page_config(page_title="Eco Mart Dashboard", layout="wide")

# CSS para un diseño limpio, moderno y con mucho contraste
st.markdown("""
    <style>
    /* Fondo global */
    .stApp { background-color: #f8f9fa; }
    
    /* Encabezado elegante */
    .header { 
        background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
        color: white; 
        padding: 2rem; 
        border-radius: 15px; 
        text-align: center;
        margin-bottom: 2rem;
    }
    
    /* Tarjetas de datos */
    .metric-card {
        background-color: white;
        padding: 20px;
        border-radius: 15px;
        border-bottom: 5px solid #2a5298;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    </style>
""", unsafe_allow_html=True)

# Encabezado personalizado
st.markdown('<div class="header"><h1>ECO MART | PANEL DE CONTROL DE INVENTARIO</h1></div>', unsafe_allow_html=True)

# 1. DATOS
datos = {
    'Producto': ['Leche', 'Carne Res', 'Yogurt', 'Pollo', 'Queso', 'Pan', 'Carne Cerdo', 'Mantequilla'],
    'Categoria': ['Lácteos', 'Carnes', 'Lácteos', 'Carnes', 'Lácteos', 'Panadería', 'Carnes', 'Lácteos'],
    'Ventas_Totales': [120, 85, 90, 60, 150, 200, 90, 90],
    'Stock_Disponible': [10, 8, 20, 12, 5, 40, 14, 9]
}
df = pd.DataFrame(datos)

# 2. PROCESAMIENTO
filtro = df[((df['Categoria'] == 'Carnes') | (df['Categoria'] == 'Lácteos')) & (df['Stock_Disponible'] < 15)]

# 3. MÉTRICAS VISUALES
c1, c2, c3 = st.columns(3)
c1.metric("Total Productos", len(df))
c2.metric("Productos en Riesgo", len(filtro))
c3.metric("Stock Mínimo", df['Stock_Disponible'].min())

st.write("###") # Espacio

# 4. TABLAS CON ESTILO
col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("Inventario General")
    st.dataframe(df, use_container_width=True, hide_index=True)

with col2:
    st.subheader("Reporte de Productos Críticos")
    # Aplicamos un estilo de degradado de color al stock para que sea más visual
    st.dataframe(
        filtro.style.background_gradient(subset=['Stock_Disponible'], cmap='Reds'),
        use_container_width=True,
        hide_index=True
    )
    
    # Botón de descarga con color principal
    csv = filtro.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="DESCARGAR REPORTE",
        data=csv,
        file_name='alerta_desabasto.csv',
        mime='text/csv',
        use_container_width=True
    )