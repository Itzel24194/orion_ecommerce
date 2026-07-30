import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression

# 1. Dataset ampliado con múltiples variables
data = {
    'Horas': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    'Asistencia': [80, 82, 85, 88, 90, 92, 94, 96, 98, 100],
    'Participacion': [2, 3, 3, 4, 5, 6, 7, 8, 8, 9],
    'Tareas': [5, 6, 6, 7, 7, 8, 9, 9, 10, 10],
    'Examenes': [50, 55, 62, 68, 72, 76, 82, 86, 91, 96],
    'Calificacion': [50, 55, 60, 65, 70, 75, 80, 85, 90, 95]
}
df = pd.DataFrame(data)

# 2. Definir variables independientes (X) y dependiente (y)
# Ahora X es una matriz con múltiples columnas
X = df[['Horas', 'Asistencia', 'Participacion', 'Tareas', 'Examenes']]
y = df['Calificacion']

# 3. Entrenar el modelo de Regresión Lineal Múltiple
modelo = LinearRegression()
modelo.fit(X, y)

# 4. Predicción
y_pred = modelo.predict(X)

# 5. Graficar resultados (Calificaciones Reales vs las que se habian comentado)
plt.figure(figsize=(10, 6))
plt.scatter(y, y_pred, color='purple')
plt.plot([y.min(), y.max()], [y.min(), y.max()], 'k--', lw=2)
plt.title('Regresión Lineal Múltiple: Predicción de Calificaciones')
plt.xlabel('Calificaciones Reales')
plt.ylabel('Calificaciones Predichas')
plt.grid(True)
plt.show()

# Mostrar la importancia de cada variable (coeficientes)
for col, coef in zip(X.columns, modelo.coef_):
    print(f"Impacto de {col}: {coef:.4f}")