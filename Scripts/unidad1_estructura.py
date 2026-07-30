import streamlit as st
import pandas as pd
import numpy as np

# Configuración de página
st.set_page_config(page_title="Eco Mart Inventory", layout="wide")

# Estilos CSS personalizados para un look moderno y elegante
st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    .header-box { 
        background: linear-gradient(135deg, #2c3e50 0%, #4ca1af 100%);
        padding: 2rem; 
        border-radius: 15px; 
        color: white; 
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card { background: white; padding: 1rem; border-radius: 10px; border-left: 5px solid #4ca1af; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    </style>
""", unsafe_allow_html=True)

# --- LÓGICA DE NEGOCIO ---
def cargar_datos():
    datos = {
        "Producto": ["Leche", "Yogurt", "Queso", "Carne Res", "Carne Cerdo", "Pollo", "Pan Integral", "Mantequilla", "Crema"],
        "Categoria": ["Lácteos", "Lácteos", "Lácteos", "Carnes", "Carnes", "Carnes", "Panadería", "Lácteos", "Lácteos"],
        "Ventas_Totales": [250, np.nan, 180, 95, np.nan, 120, 300, 90, 110],
        "Stock_Disponible": [12, 8, 4, 10, 7, 20, 50, 5, 13]
    }
    return pd.DataFrame(datos)

# --- INTERFAZ ---
st.markdown('<div class="header-box"><h1>ECO MART | PANEL DE CONTROL DE INVENTARIO</h1></div>', unsafe_allow_html=True)

df = cargar_datos()

# Limpieza (automática)
df["Ventas_Totales"] = df["Ventas_Totales"].fillna(df["Ventas_Totales"].median())

# Filtrado
alerta = df[(df["Categoria"].isin(["Carnes", "Lácteos"])) & (df["Stock_Disponible"] < 15)]

# Métricas rápidas
c1, c2, c3 = st.columns(3)
c1.metric("Total Productos", len(df))
c2.metric("En Riesgo", len(alerta))
c3.metric("Stock Promedio", f"{df['Stock_Disponible'].mean():.1f}")

st.markdown("---")

# Visualización en columnas
col_tablas1, col_tablas2 = st.columns([1, 1])

with col_tablas1:
    st.subheader("Inventario Completo")
    st.dataframe(df, use_container_width=True, hide_index=True)

with col_tablas2:
    st.subheader("Productos Críticos (Alerta)")
    # Estilo visual en la tabla de alerta
    st.dataframe(
        alerta.style.background_gradient(subset=['Stock_Disponible'], cmap='Blues'),
        use_container_width=True, 
        hide_index=True
    )
    
    # Exportación
    csv = alerta.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="DESCARGAR REPORTE CSV",
        data=csv,
        file_name='alerta_desabasto_ecomart.csv',
        mime='text/csv',
        use_container_width=True
    )