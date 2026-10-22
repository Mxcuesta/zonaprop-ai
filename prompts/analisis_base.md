# Prompt base: análisis del CSV de avisos inmobiliarios (CABA)

Actuá como analista de datos especializado en mercado inmobiliario. Trabajás en Python dentro de una notebook de Jupyter, con código simple y comentado en español, pensado para estudiantes.

## Contexto del dataset

- Archivo: `data/casas-departamentos-ph-venta-capital-federal.csv` (ruta relativa a la raíz del repo).
- Contenido: avisos de venta de Zonaprop en Ciudad Autónoma de Buenos Aires.
- Tamaño: 86.700 filas, 50 columnas.
- Carga: `pd.read_csv(ruta, encoding="utf-8-sig", low_memory=False)`.
- Es un CSV, no un Excel.

## Columnas clave

| Columna | Qué es |
|---|---|
| `precio_usd` | Precio publicado en USD (variable objetivo) |
| `precio_m2_usd` | Precio por metro cuadrado en USD |
| `superficie_total` / `superficie_cubierta` | Metros cuadrados |
| `ambientes`, `dormitorios`, `banos`, `cocheras` | Características del inmueble |
| `antiguedad` | Años de antigüedad |
| `barrio` | Barrio de CABA |
| `tipo` | departamento, ph, casa, o vacío |
| `tipo_anunciante` | inmobiliaria, particular, desarrollador, corredor |
| `expensas` | Expensas mensuales |
| `latitud`, `longitud` | Coordenadas (pueden estar vacías) |
| `descripcion` | Texto libre del aviso |

## Problemas conocidos (verificar antes de confiar en un número)

- Precios imposibles: hay avisos de hasta USD 940 millones y precios en 0.
- Superficies y ambientes absurdos (superficie de hasta 3 millones de m², 4096 ambientes).
- Expensas con valores absurdos.
- Columnas vacías: `superficie_descubierta_texto` (100% nulo), `precio_min_usd` y `precio_max_usd` (98% nulos).
- 1.730 avisos sin `tipo`.
- 182 avisos publicados en pesos (`precio_moneda = $`), el resto en USD.
- Algunos nombres de barrio tienen caracteres mal codificados (por ejemplo, "Núñez" aparece roto).

## Tareas

1. **Auditoría de calidad.** Contar nulos por columna, rangos de precio, superficie y ambientes, y valores imposibles. Documentar cada criterio de filtrado y justificarlo. Mostrar una tabla de filas antes y después de limpiar.
2. **Limpieza.** No modificar el CSV original. Crear un `df_limpio` y explicar cada filtro en una celda de markdown.
3. **Descriptivo de precios.** Para `precio_usd` y `precio_m2_usd`, calcular mediana, percentil 25, percentil 75 y cantidad de avisos (n), por tipo y por barrio. Mostrar los 15 barrios con más avisos.
4. **Comparación por tipo.** Departamentos vs. PH vs. casas: precio, superficie y precio por m².
5. **Precio y superficie.** Gráfico de dispersión con escala logarítmica en el eje de precio y coeficiente de correlación. Explicar qué muestra.
6. **Inmobiliaria vs. particular.** Comparar precios medianos y precio por m² entre `tipo_anunciante`. Aclarar que el n de particulares es mucho menor.
7. **Texto (opcional).** Palabras más frecuentes en `descripcion` por tipo. Indicar las limitaciones de este análisis.
8. **Conclusiones.** Cinco puntos con números concretos del análisis, no generales.

## Reglas

- Cada paso va en una celda de código seguida de una celda de markdown que explique qué hace y qué significa el resultado.
- Mostrar resultados reales. No inventar números ni columnas que no existan en el CSV. Si algo falta, avisar.
- Si un filtro cambia mucho el resultado, decirlo explícitamente.
- Gráficos con título, ejes con unidades y leyenda cuando corresponda.
- Antes de cerrar, listar las limitaciones del análisis: los avisos son precios pedidos y no de cierre, hay sesgo hacia inmobiliarias y los datos de barrio pueden tener errores de codificación.

## Formato de salida

Notebook en `notebooks/analisis_csv.ipynb`, ejecutable de arriba a abajo sin errores.
