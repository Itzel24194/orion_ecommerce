# EJERCICIO BÁSICO
# MercaRed - Generación de clientes simulados
#
# Objetivo:
# Aprender a utilizar:
#
# - Pandas
# - Numpy
# - Random
# - Datetime
#
# Crearemos un pequeño conjunto de clientes
# y lo guardaremos en un archivo CSV

# IMPORTAR LIBRERÍAS

# Pandas permite trabajar con tablas
import pandas as pd

# Numpy sirve para generar números aleatorios
import numpy as np

# Random selecciona elementos aleatorios
import random

# datetime maneja fechas
# timedelta permite sumar o restar días
from datetime import datetime, timedelta

# PASO 1:
# CREAR LISTAS CON INFORMACIÓN

# Lista de estados

estados=[

    "Estado de México",
    "CDMX",
    "Jalisco",
    "Puebla",
    "Nuevo León"

]

# Lista de categorías favoritas

categorias=[

    "Electrónica",
    "Moda",
    "Hogar",
    "Videojuegos",
    "Deportes"

]

# PASO 2:
# CREAR LISTAS VACÍAS

# Aquí almacenaremos la información

lista_cliente=[]

lista_edad=[]

lista_compras=[]

lista_ticket=[]

lista_estado=[]

lista_categoria=[]

lista_fecha=[]

# PASO 3:
# OBTENER FECHA ACTUAL

# Obtiene fecha actual del sistema

fecha_actual=datetime.now()

print("Fecha actual")

print(fecha_actual)

# PASO 4: GENERAR DATOS

# El ciclo se repetirá 20 veces

for i in range(20): #solo se cambia el limite del ciclo para x cantidad de registros

    # Crear ID del cliente
    
    cliente="C"+str(i+1)

    # Edad aleatoria entre 18 y 65
    
    edad=np.random.randint(

        18,
        66

    )

    # Número de compras
    
    compras=np.random.randint(

        1,
        15

    )

    # Ticket promedio
    # uniform genera valores decimales
    # round limita a 2 decimales
    
    ticket=round(

        np.random.uniform(

            100,
            3000

        ),

        2

    )

    # Seleccionar estado aleatoriamente
    
    estado=random.choice(

        estados

    )

    # Seleccionar categoría favorita
    
    categoria=random.choice(

        categorias

    )

    # Crear fecha de compra Restar entre 1 y 30 días
    
    fecha_compra=fecha_actual-timedelta(

        days=random.randint(

            1,
            30

        )

    )

    # Guardar datos en listas
    
    lista_cliente.append(cliente)

    lista_edad.append(edad)

    lista_compras.append(compras)

    lista_ticket.append(ticket)

    lista_estado.append(estado)

    lista_categoria.append(categoria)

    lista_fecha.append(fecha_compra)

# PASO 5: CREAR DATAFRAME

clientes=pd.DataFrame({

    'ID_Cliente':lista_cliente,

    'Edad':lista_edad,

    'Numero_Compras':lista_compras,

    'Promedio_Ticket':lista_ticket,

    'Estado':lista_estado,

    'Categoria_Favorita':lista_categoria,

    'Fecha_Ultima_Compra':lista_fecha

})

# PASO 6: CREAR NUEVA COLUMNA
#
# Valor cliente = compras × ticket promedio

clientes['Valor_Cliente']= (

clientes['Numero_Compras']

*

clientes['Promedio_Ticket']

)

# PASO 7: MOSTRAR TABLA

print("\nTABLA DE CLIENTES")

print(clientes)

# PASO 8: OBTENER ESTADÍSTICAS

print("\nESTADÍSTICAS")

print(

clientes.describe()

)

# PASO 9: GUARDAR CSV

clientes.to_csv(

'clientes_mercared.csv',

index=False

)


print("\nArchivo generado correctamente")