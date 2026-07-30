# EJERCICIO BÁSICO:
# Objetivo:
# Crear un pequeño dataset con ventas simuladas
# utilizando Pandas, Numpy, Random y Datetime

# IMPORTAR LIBRERÍAS

# Pandas se utiliza para trabajar con tablas (DataFrames)
import pandas as pd

# Numpy se utiliza para cálculos y generación de números
import numpy as np

# Random permite elegir elementos aleatorios
import random

# Importamos manejo de fechas
from datetime import datetime, timedelta


# PASO 1: CREAR LISTA DE PRODUCTOS

# Lista simple con productos de una tienda

productos=[
    "Laptop",
    "Mouse",
    "Teclado",
    "Monitor",
    "Audífonos"

]

# PASO 2: CREAR LISTAS VACÍAS

# Aquí guardaremos la información generada

lista_productos=[]

lista_cantidades=[]

lista_precios=[]

lista_fechas=[]

# PASO 3: GENERAR FECHA ACTUAL

# Obtiene la fecha y hora actual del sistema

fecha_actual=datetime.now()


# Mostrar fecha actual

print("Fecha actual:")

print(fecha_actual)

# PASO 4: CREAR DATOS ALEATORIOS

# El ciclo se ejecutará 10 veces
# Cada repetición será una venta

for i in range(10):

    # Elegir producto aleatoriamente
    
    producto=random.choice(productos)

    # Generar cantidad entre 1 y 10
    
    cantidad=np.random.randint(1,11)

    # Generar precio aleatorio
    # uniform genera números decimales
    # round limita a dos decimales
    
    precio=round(

        np.random.uniform(100, 1000),2)

    # Crear fecha aleatoria Restamos entre 1 y 7 días
    
    fecha=fecha_actual-timedelta(

        days=random.randint(1,7)

    )



    # Guardar datos en listas
    
    lista_productos.append(producto)

    lista_cantidades.append(cantidad)

    lista_precios.append(precio)

    lista_fechas.append(fecha)

# PASO 5: CREAR DATAFRAME

# Crear tabla con los datos generados

ventas=pd.DataFrame({

    'Producto':lista_productos,

    'Cantidad':lista_cantidades,

    'Precio':lista_precios,

    'Fecha':lista_fechas

})

# PASO 6: CREAR NUEVA COLUMNA

# Multiplicar cantidad por precio

ventas['Total']=(

ventas['Cantidad']

*

ventas['Precio']

)

# PASO 7: MOSTRAR RESULTADOS

print("\nTABLA DE VENTAS")

print(ventas)

# PASO 8: OBTENER ESTADÍSTICAS

print("\nESTADÍSTICAS")

print(

ventas.describe()

)

# PASO 9: GUARDAR ARCHIVO CSV

ventas.to_csv('ventas_simuladas.csv',index=False)

print("\nArchivo guardado correctamente")

# JOVENES LES DEJE LA COODIFICACION MEZCLADA PARA QUE IDENTIFIQUEN QUE EN ALGUNAS OCASIONES NO IMPORTA COMO ESCRIBAS 
# EL CODIGO MIENTRAS LA LOGICA ESTE BIEN ESTE SE EJECUTARA.