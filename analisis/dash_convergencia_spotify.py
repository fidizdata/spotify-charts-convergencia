#################### ESQUELETO INICIAL ########################################

#  Importamos los componentes necesarios de Dash y Plotly
from dash import Dash, html, dcc, Input, Output
import plotly.express as px
import pandas as pd

# 1. PREPARACIÓN DE DATOS (Simulando lo que ya tenés procesado)
# En tu proyecto real, acá cargarías tus DataFrames con los clústeres y años
df = pd.DataFrame({
    "Año": [2020, 2020, 2021, 2021, 2022, 2022],
    "Cluster": ["Anglosphere", "Iberoamerican", "Anglosphere", "Iberoamerican", "Anglosphere", "Iberoamerican"],
    "Similitud_Promedio": [0.85, 0.72, 0.88, 0.75, 0.90, 0.78],
    "Top_Artista": ["Drake", "Bad Bunny", "Taylor Swift", "Karol G", "The Weeknd", "Rosalía"]
})

# Inicializamos la aplicación de Dash
app = Dash(__name__)

# 2. DEFINICIÓN DEL LAYOUT (La estructura visual que ve el usuario)
app.layout = html.Div([
    html.H1("Explorador de Similitud Musical por Clústeres", style={"textAlign": "center"}),
    
    html.Div([
        html.P("Seleccioná el año de análisis:"),
        # Componente deslizador (Slider) para filtrar por año
        dcc.Slider(
            id='slider-anio',
            min=df['Año'].min(),
            max=df['Año'].max(),
            step=1,
            value=df['Año'].min(),
            marks={str(anio): str(anio) for anio in df['Año'].unique()}
        )
    ], style={"width": "50%", "margin": "auto", "padding": "20px"}),

    # Contenedor para mostrar el gráfico de dispersión / nodos
    dcc.Graph(id='grafico-red'),

    # Contenedor para mostrar el desglose de datos al interactuar
    html.Div(id='panel-desglose', style={"textAlign": "center", "marginTop": "20px", "fontSize": "18px"})
])

# 3. LOS CALLBACKS (El motor interactivo que conecta entradas y salidas)
@app.callback(
    [Output('grafico-red', 'figure'),
     Output('panel-desglose', 'children')],
    [Input('slider-anio', 'value')]
)
def actualizar_dashboard(anio_seleccionado):
    # Filtramos los datos según el año que eligió el usuario en el slider
    df_filtrado = df[df['Año'] == anio_seleccionado]
    
    # Creamos un gráfico interactivo con Plotly Express
    fig = px.scatter(
        df_filtrado,
        x="Cluster",
        y="Similitud_Promedio",
        size="Similitud_Promedio",
        color="Cluster",
        hover_data=["Top_Artista"],
        title=f"Estructura de Clústeres en el año {anio_seleccionado}"
    )
    
    # Actualizamos el diseño del gráfico para que se vea limpio
    fig.update_layout(transition_duration=500)
    
    # Texto dinámico para el panel de desglose inferior
    artistas_destacados = ", ".join(df_filtrado['Top_Artista'].unique())
    texto_desglose = f"Artistas principales para el año {anio_seleccionado}: {artistas_destacados}"
    
    return fig, texto_desglose

# 4. EJECUCIÓN DEL SERVIDOR LOCAL
if __name__ == '__main__':
    app.run(debug=True)