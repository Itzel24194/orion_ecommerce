# 1. IMPORTACIÓN DE LIBRERÍAS
import os
import sys
import numpy as np # Necesario para la mediana local
from pyspark.sql import SparkSession
from pyspark.sql.functions import col
from pyspark.sql.types import StructType, StructField, StringType, IntegerType
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.regression import LinearRegression
from pyspark import SparkConf

# Configuración de entorno
os.environ['PYSPARK_PYTHON'] = sys.executable
os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable

# 2. CREACIÓN DE SESIÓN (Optimizada para evitar conflictos de comunicación)
conf = SparkConf().setAppName("EcoMart Big Data") \
    .set("spark.master", "local[*]") \
    .set("spark.driver.host", "127.0.0.1") \
    .set("spark.sql.execution.pyspark.udf.faulthandler.enabled", "true") \
    .set("spark.python.worker.reuse", "false")

spark = SparkSession.builder.config(conf=conf).getOrCreate()
print("Spark iniciado correctamente")

# 3. CREACIÓN DEL CONJUNTO DE DATOS
datos = [
    ("Leche", "Lácteos", 250, 12),
    ("Yogurt", "Lácteos", None, 8),
    ("Queso", "Lácteos", 180, 4),
    ("Carne Res", "Carnes", 95, 10),
    ("Carne Cerdo", "Carnes", None, 7),
    ("Pollo", "Carnes", 120, 20),
    ("Pan Integral", "Panadería", 300, 50),
    ("Mantequilla", "Lácteos", 90, 5),
    ("Crema", "Lácteos", 110, 13)
]

schema = StructType([
    StructField("Producto", StringType(), True),
    StructField("Categoria", StringType(), True),
    StructField("Ventas_Totales", IntegerType(), True),
    StructField("Stock_Disponible", IntegerType(), True)
])

df = spark.createDataFrame(datos, schema)
print("\nDATAFRAME CREADO")

# 4. LIMPIEZA (Alternativa robusta a approxQuantile)
# Usamos collect() para traer los datos y calcular la mediana localmente en Python
# Esto evita el error de "Python worker exited" causado por procesos distribuidos en Windows
ventas_no_nulas = [row.Ventas_Totales for row in df.filter(col("Ventas_Totales").isNotNull()).collect()]
mediana = float(np.median(ventas_no_nulas))
print(f"Mediana calculada localmente: {mediana}")

df_limpio = df.fillna({"Ventas_Totales": int(mediana)})

# 5. FILTRADO
alerta_desabasto = df_limpio.filter(
    ((col("Categoria") == "Carnes") | (col("Categoria") == "Lácteos"))
    & (col("Stock_Disponible") < 15)
)

print("\nPRODUCTOS CRÍTICOS:")
alerta_desabasto.show()

# 6. EXPORTAR
alerta_desabasto.coalesce(1).write.mode("overwrite").option("header", True).csv("alerta_desabasto_ecomart_final")

# 7. MACHINE LEARNING
assembler = VectorAssembler(inputCols=["Stock_Disponible"], outputCol="features")
datos_ml = assembler.transform(df_limpio)

modelo = LinearRegression(featuresCol="features", labelCol="Ventas_Totales", regParam=0.1)
modelo_entrenado = modelo.fit(datos_ml)
predicciones = modelo_entrenado.transform(datos_ml)

print("\nPredicciones:")
predicciones.select("Producto", "Stock_Disponible", "Ventas_Totales", "prediction").show()

# Finalización
spark.stop()
print("\nProceso finalizado correctamente")