import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import networkx as nx
import pathlib

CONTINENTES_NOMBRES = {
    # América Latina
    "Argentina": "América Latina", "Bolivia": "América Latina", "Brazil": "América Latina",
    "Chile": "América Latina", "Colombia": "América Latina", "Costa Rica": "América Latina",
    "Dominican Republic": "América Latina", "Ecuador": "América Latina", "El Salvador": "América Latina",
    "Guatemala": "América Latina", "Honduras": "América Latina", "Mexico": "América Latina",
    "Nicaragua": "América Latina", "Panama": "América Latina", "Peru": "América Latina",
    "Paraguay": "América Latina", "Uruguay": "América Latina",
    # Norteamérica & Oceanía
    "United States": "Norteamérica & Oceanía", "Canada": "Norteamérica & Oceanía",
    "Australia": "Norteamérica & Oceanía", "New Zealand": "Norteamérica & Oceanía",
    # Europa
    "Austria": "Europa", "Belgium": "Europa", "Switzerland": "Europa", "Czech Republic": "Europa",
    "Germany": "Europa", "Denmark": "Europa", "Estonia": "Europa", "Spain": "Europa",
    "Finland": "Europa", "France": "Europa", "United Kingdom": "Europa", "Greece": "Europa",
    "Hungary": "Europa", "Ireland": "Europa", "Iceland": "Europa", "Italy": "Europa",
    "Lithuania": "Europa", "Latvia": "Europa", "Netherlands": "Europa", "Norway": "Europa",
    "Poland": "Europa", "Portugal": "Europa", "Sweden": "Europa", "Slovakia": "Europa", "Turkey": "Europa",
    # Asia
    "Hong Kong": "Asia", "Indonesia": "Asia", "Japan": "Asia", "Malaysia": "Asia",
    "Philippines": "Asia", "Singapore": "Asia", "Thailand": "Asia", "Taiwan": "Asia",
}

COLOR_MAP = {
    "América Latina": "#FF5722",
    "Europa": "#3F51B5",
    "Norteamérica & Oceanía": "#009688",
    "Asia": "#E91E63",
    "Otro/Desconocido": "#9E9E9E",
}

# Coordenadas geográficas iniciales ajustadas para guiar el mapa y el bloque anglo hacia el oeste
POSICIONES_GEO_INICIALES = {
    # América Latina (Izquierda / Oeste)
    "Argentina": (-3.0, -2.5), "Uruguay": (-2.6, -2.2), "Chile": (-3.5, -1.8),
    "Brazil": (-1.5, -1.5), "Colombia": (-2.8, -0.2), "Peru": (-3.0, -0.9),
    "Bolivia": (-2.3, -1.2), "Ecuador": (-3.2, -0.5), "Paraguay": (-2.2, -1.8),
    "Venezuela": (-2.2, 0.2), "Mexico": (-3.2, 1.2), "Costa Rica": (-2.8, -0.5),
    "Panama": (-2.6, -0.4), "Dominican Republic": (-1.8, 0.5), "Guatemala": (-3.0, 0.5),
    "Honduras": (-2.9, 0.3), "Nicaragua": (-2.8, 0.1), "El Salvador": (-2.9, 0.2),

    # Norteamérica & Oceanía (Ajustados hacia la izquierda, cerca de UK/Europa occidental)
    "United States": (-1.5, 2.5), "Canada": (-1.5, 3.2),
    "Australia": (0.5, 2.2), "New Zealand": (0.8, 2.0),

    # Europa (Centro)
    "Spain": (-0.8, 0.8), "Portugal": (-1.2, 0.6), "United Kingdom": (-1.2, 1.8),
    "France": (-0.8, 1.5), "Germany": (0.5, 1.8), "Switzerland": (0.2, 1.1),
    "Italy": (0.6, 0.5), "Austria": (0.8, 1.2), "Belgium": (-0.3, 1.9),
    "Netherlands": (-0.2, 2.3), "Denmark": (0.6, 2.5), "Norway": (0.5, 3.2),
    "Sweden": (1.2, 3.0), "Finland": (1.8, 3.2), "Iceland": (-1.8, 3.5),
    "Ireland": (-1.4, 2.4), "Poland": (1.2, 2.0), "Czech Republic": (0.9, 1.5),
    "Slovakia": (1.3, 1.2), "Hungary": (1.4, 0.9), "Greece": (1.5, -0.2),
    "Turkey": (2.0, 0.2), "Estonia": (1.8, 2.7), "Latvia": (1.8, 2.3),
    "Lithuania": (1.8, 1.9),

    # Asia (Derecha / Este)
    "Japan": (4.0, 1.8), "Hong Kong": (3.0, -0.5), "Taiwan": (3.6, 0.2),
    "Singapore": (2.8, -1.2), "Malaysia": (2.8, -1.6), "Indonesia": (3.2, -2.2),
    "Philippines": (3.8, -0.8), "Thailand": (3.1, -0.9)
}

def cargar_datos_completos():
    base_path = pathlib.Path(__file__).parent.resolve().parent
    processed_path = base_path / "data" / "processed" / "df_top200_annual.csv"
    if not processed_path.exists():
        processed_path = pathlib.Path("data/processed/df_top200_annual.csv")

    if not processed_path.exists():
        print(f"Aviso: No se encontró el archivo procesado en {processed_path}.")
        return None, []

    print("Cargando dataset preprocesado completo...")
    df_top200_annual = pd.read_csv(processed_path)
    anios_disponibles = sorted(df_top200_annual["year"].unique())
    return df_top200_annual, anios_disponibles

df_global, lista_anios = cargar_datos_completos()

def calcular_grafo_para_anio(df_top200_annual, anio):
    df_anio = df_top200_annual[df_top200_annual["year"] == anio].copy()
    if df_anio.empty:
        return None, {}, [], df_anio

    df_anio["total_region_streams"] = df_anio.groupby("region")["total_streams"].transform("sum")
    df_anio["share"] = df_anio["total_streams"] / df_anio["total_region_streams"]
    matriz_shares = df_anio.pivot(index="region", columns="url", values="share").fillna(0.0)
    
    valores = matriz_shares.values
    normas = np.linalg.norm(valores, axis=1, keepdims=True)
    matriz_norm = valores / np.where(normas == 0, 1, normas)
    cos_sim = np.dot(matriz_norm, matriz_norm.T)
    dist_array = 1.0 - cos_sim
    np.fill_diagonal(dist_array, 0.0)
    matriz_dist = pd.DataFrame(dist_array, index=matriz_shares.index, columns=matriz_shares.index)

    G_full = nx.Graph()
    paises = matriz_dist.index.tolist()

    for p in paises:
        region = CONTINENTES_NOMBRES.get(p, "Otro/Desconocido")
        G_full.add_node(p, continente=region)

    for i in range(len(paises)):
        for j in range(i + 1, len(paises)):
            p1, p2 = paises[i], paises[j]
            dist = matriz_dist.loc[p1, p2]
            G_full.add_edge(p1, p2, weight=dist)

    G_mst = nx.minimum_spanning_tree(G_full, weight="weight")
    
    pos_inicial_filtrada = {p: POSICIONES_GEO_INICIALES[p] for p in paises if p in POSICIONES_GEO_INICIALES}

    print(f"Calculando layout geográfico guiado para el año {anio}...")
    try:
        pos_nx = nx.kamada_kawai_layout(G_mst, weight="weight", pos=pos_inicial_filtrada if pos_inicial_filtrada else None)
    except Exception as e:
        print(f"Aviso en Kamada-Kawai con semilla geo: {e}. Usando layout estándar.")
        pos_nx = nx.kamada_kawai_layout(G_mst, weight="weight")

    paises_disponibles = sorted(paises)
    return G_mst, pos_nx, paises_disponibles, df_anio

def construir_figura_grafo(G_mst, pos_nx, df_anio, pais_destacado=None, region_destacada=None):
    edge_x = []
    edge_y = []
    for edge in G_mst.edges():
        x0, y0 = pos_nx[edge[0]]
        x1, y1 = pos_nx[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=1.5, color='#555555'),
        hoverinfo='none',
        mode='lines'
    )

    node_x = []
    node_y = []
    node_text = []
    node_hover_text = []
    node_color = []
    node_customdata = []
    node_size = []

    # Calcular streams totales por país para definir tamaños proporcionales
    streams_por_pais = df_anio.groupby("region")["total_streams"].sum().to_dict() if not df_anio.empty else {}
    max_streams = max(streams_por_pais.values()) if streams_por_pais else 1

    for node in G_mst.nodes():
        x, y = pos_nx[node]
        node_x.append(x)
        node_y.append(y)
        node_text.append(node)
        
        region = G_mst.nodes[node].get('continente', 'Otro/Desconocido')
        node_color.append(COLOR_MAP.get(region, '#9E9E9E'))
        node_customdata.append(node)

        # Tamaño proporcional al mercado (normalizado entre 10 y 34 píxeles)
        streams_nodo = streams_por_pais.get(node, 0)
        proporcion = np.sqrt(streams_nodo / max_streams) if max_streams > 0 else 0.1
        tamanio_base = 10 + (proporcion * 24)

        # Texto personalizado para el hover incluyendo reproducciones formateadas
        streams_fmt = f"{int(streams_nodo):,}".replace(",", ".") if streams_nodo > 0 else "N/D"
        node_hover_text.append(f"<b>{node}</b><br>Región: {region}<br>Streams: {streams_fmt}")

        if pais_destacado and node == pais_destacado:
            node_size.append(tamanio_base + 10)
        elif region_destacada and region == region_destacada and not pais_destacado:
            node_size.append(tamanio_base + 5)
        else:
            node_size.append(tamanio_base)

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        text=node_text,
        textposition="top center",
        textfont=dict(color='#ffffff', size=11, family='Montserrat'),
        hoverinfo='text',
        hovertext=node_hover_text,
        customdata=node_customdata,
        marker=dict(
            showscale=False,
            color=node_color,
            size=node_size,
            line=dict(color='#ffffff', width=1.5)
        )
    )

    fig = go.Figure(data=[edge_trace, node_trace],
                    layout=go.Layout(
                        showlegend=False,
                        hovermode='closest',
                        margin=dict(b=20, l=20, r=20, t=20),
                        plot_bgcolor='#121212',
                        paper_bgcolor='#121212',
                        font=dict(family='Montserrat', color='#ffffff'),
                        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
                    ))
    return fig

# Importar stylesheet externo para cargar Google Font Montserrat
external_stylesheets = ['https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap']
app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

min_anio = min(lista_anios) if lista_anios else 2017
max_anio = max(lista_anios) if lista_anios else 2021
val_inicial = 2021 if 2021 in lista_anios else min_anio
slider_marks = {str(anio): {'label': str(anio), 'style': {'color': '#ccc', 'fontSize': '11px', 'fontFamily': 'Montserrat'}} for anio in lista_anios}

app.layout = html.Div([
    html.H1("Mapa de Proximidad de Gustos Musicales (Spotify)", style={'textAlign': 'center', 'color': '#ffffff', 'paddingTop': '20px'}),
    
    html.Div([
        html.Div([
            # Barra superior: Leyendas + Deslizador de Años
            html.Div([
                html.Div([
                    html.Span("Regiones:", style={'color': '#aaa', 'fontWeight': 'bold', 'fontSize': '12px', 'marginRight': '12px'}),
                    html.Button([
                        html.Span(style={'height': '10px', 'width': '10px', 'backgroundColor': '#FF5722', 'borderRadius': '50%', 'display': 'inline-block', 'marginRight': '6px'}),
                        html.Span("América Latina", style={'color': '#ccc', 'fontSize': '12px'})
                    ], id='btn-leyenda-america-latina', n_clicks=0, style={'background': 'none', 'border': 'none', 'cursor': 'pointer', 'display': 'inline-block', 'marginRight': '15px', 'padding': '0'}),
                    
                    html.Button([
                        html.Span(style={'height': '10px', 'width': '10px', 'backgroundColor': '#3F51B5', 'borderRadius': '50%', 'display': 'inline-block', 'marginRight': '6px'}),
                        html.Span("Europa", style={'color': '#ccc', 'fontSize': '12px'})
                    ], id='btn-leyenda-europa', n_clicks=0, style={'background': 'none', 'border': 'none', 'cursor': 'pointer', 'display': 'inline-block', 'marginRight': '15px', 'padding': '0'}),
                    
                    html.Button([
                        html.Span(style={'height': '10px', 'width': '10px', 'backgroundColor': '#009688', 'borderRadius': '50%', 'display': 'inline-block', 'marginRight': '6px'}),
                        html.Span("Norteamérica & Oceanía", style={'color': '#ccc', 'fontSize': '12px'})
                    ], id='btn-leyenda-norteamerica', n_clicks=0, style={'background': 'none', 'border': 'none', 'cursor': 'pointer', 'display': 'inline-block', 'marginRight': '15px', 'padding': '0'}),
                    
                    html.Button([
                        html.Span(style={'height': '10px', 'width': '10px', 'backgroundColor': '#E91E63', 'borderRadius': '50%', 'display': 'inline-block', 'marginRight': '6px'}),
                        html.Span("Asia", style={'color': '#ccc', 'fontSize': '12px'})
                    ], id='btn-leyenda-asia', n_clicks=0, style={'background': 'none', 'border': 'none', 'cursor': 'pointer', 'display': 'inline-block', 'padding': '0'}),
                ], style={'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap', 'flex': '1'}),

                # Deslizador de Años (Slider)
                html.Div([
                    html.Span("Año:", style={'color': '#aaa', 'fontWeight': 'bold', 'fontSize': '12px', 'marginRight': '12px'}),
                    html.Div([
                        dcc.Slider(
                            id='slider-anio',
                            min=min_anio,
                            max=max_anio,
                            step=1,
                            value=val_inicial,
                            marks=slider_marks,
                            tooltip={"placement": "bottom", "always_visible": False}
                        )
                    ], style={'width': '160px'})
                ], style={'display': 'flex', 'alignItems': 'center', 'marginLeft': '15px'})
            ], style={'backgroundColor': '#252525', 'padding': '8px 15px', 'borderRadius': '4px', 'marginBottom': '10px', 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between', 'flexWrap': 'wrap'}),

            dcc.Graph(
                id='mst-plotly-graph',
                style={'width': '100%', 'height': '80vh'}
            )
        ], style={'width': '68%', 'display': 'inline-block', 'verticalAlign': 'top'}),
        
        html.Div([
            html.H3("Panel de Análisis", style={'color': '#ffffff', 'marginBottom': '15px'}),

            html.Button("Restablecer Vista Global", id='btn-reset', n_clicks=0, style={
                'width': '100%', 'backgroundColor': '#333', 'color': 'white', 
                'border': '1px solid #555', 'padding': '8px', 'borderRadius': '4px',
                'cursor': 'pointer', 'marginBottom': '15px', 'fontWeight': 'bold', 'fontFamily': 'Montserrat'
            }),

            html.Div(id='mst-detail-content', children=[
                html.P("Hacé clic en cualquier país del árbol o en las regiones superiores.", style={'color': '#888'})
            ]),
            
            html.Hr(style={'borderColor': '#444', 'margin': '15px 0'}),
            html.H4("Top Artistas", style={'color': '#aaa', 'marginBottom': '10px', 'fontSize': '16px', 'fontWeight': 'bold'}),
            html.Div(id='top-artists-table-container'),

            html.Hr(style={'borderColor': '#444', 'margin': '20px 0 15px 0'}),
            html.H4("Top Canciones", style={'color': '#aaa', 'marginBottom': '10px', 'fontSize': '16px', 'fontWeight': 'bold'}),
            html.Div(id='top-tracks-table-container')
        ], style={
            'width': '28%', 'display': 'inline-block', 'verticalAlign': 'top', 
            'padding': '20px', 'backgroundColor': '#1e1e1e', 'borderRadius': '5px', 
            'height': '85vh', 'boxSizing': 'border-box', 'marginLeft': '2%', 'overflowY': 'auto'
        })
    ], style={'width': '95%', 'margin': '0 auto'})
], style={'minHeight': '100vh', 'backgroundColor': '#121212', 'paddingBottom': '20px', 'fontFamily': 'Montserrat'})

@app.callback(
    [Output('mst-detail-content', 'children'),
     Output('top-artists-table-container', 'children'),
     Output('top-tracks-table-container', 'children'),
     Output('mst-plotly-graph', 'figure')],
    [Input('slider-anio', 'value'),
     Input('mst-plotly-graph', 'clickData'),
     Input('btn-reset', 'n_clicks'),
     Input('btn-leyenda-america-latina', 'n_clicks'),
     Input('btn-leyenda-europa', 'n_clicks'),
     Input('btn-leyenda-norteamerica', 'n_clicks'),
     Input('btn-leyenda-asia', 'n_clicks')]
)
def actualizar_dashboard(anio_seleccionado, click_data, n_clicks_reset, n_latina, n_europa, n_norteamerica, n_asia):
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else ''

    pais_seleccionado = None
    region_seleccionada = None

    if trigger_id != 'slider-anio':
        if trigger_id == 'btn-reset':
            pais_seleccionado = None
            region_seleccionada = None
        elif trigger_id == 'btn-leyenda-america-latina':
            region_seleccionada = "América Latina"
        elif trigger_id == 'btn-leyenda-europa':
            region_seleccionada = "Europa"
        elif trigger_id == 'btn-leyenda-norteamerica':
            region_seleccionada = "Norteamérica & Oceanía"
        elif trigger_id == 'btn-leyenda-asia':
            region_seleccionada = "Asia"
        elif trigger_id == 'mst-plotly-graph' and click_data:
            punto = click_data['points'][0]
            if 'customdata' in punto:
                pais_seleccionado = punto['customdata']
                region_seleccionada = CONTINENTES_NOMBRES.get(pais_seleccionado)

    anio_actual = anio_seleccionado if anio_seleccionado else 2021
    G_mst, pos_nx, lista_paises, df_anio = calcular_grafo_para_anio(df_global, anio_actual)

    fig_actualizada = construir_figura_grafo(G_mst, pos_nx, df_anio, pais_destacado=pais_seleccionado, region_destacada=region_seleccionada)

    detail_content = [
        html.P(f"Año seleccionado: {anio_actual}", style={'color': '#aaa', 'margin': '0 0 5px 0'}),
        html.P("Mapa de proximidad basado en similitud de coseno.", style={'color': '#aaa', 'fontSize': '12px', 'margin': '0 0 10px 0'})
    ]

    if pais_seleccionado and pais_seleccionado in lista_paises:
        cont_val = CONTINENTES_NOMBRES.get(pais_seleccionado, "Otro/Desconocido")
        detail_content.extend([
            html.H4(f"País: {pais_seleccionado}", style={'color': '#aaa', 'marginTop': '10px', 'marginBottom': '5px', 'fontSize': '16px', 'fontWeight': 'bold'}),
            html.P(f"Continente: {cont_val}", style={'color': '#aaa', 'margin': '2px 0'})
        ])
    elif region_seleccionada:
        detail_content.extend([
            html.H4(f"Región: {region_seleccionada}", style={'color': '#aaa', 'marginTop': '10px', 'marginBottom': '5px', 'fontSize': '16px', 'fontWeight': 'bold'}),
            html.P("Visualizando top consolidado para todo el cluster regional.", style={'color': '#aaa', 'margin': '2px 0', 'fontSize': '13px'})
        ])
    else:
        detail_content.append(html.P("Vista Global / Sin filtros activos.", style={'fontStyle': 'italic', 'color': '#888', 'marginTop': '10px'}))

    if not df_anio.empty:
        if pais_seleccionado and pais_seleccionado in lista_paises:
            df_filtrado = df_anio[df_anio["region"] == pais_seleccionado]
        elif region_seleccionada:
            paises_en_region = [p for p, r in CONTINENTES_NOMBRES.items() if r == region_seleccionada]
            df_filtrado = df_anio[df_anio["region"].isin(paises_en_region)]
        else:
            df_filtrado = df_anio

        df_artistas = (
            df_filtrado.groupby("artist")["total_streams"]
            .sum()
            .reset_index()
            .sort_values(by="total_streams", ascending=False)
            .head(10)
        )
        df_artistas["Reproducciones"] = df_artistas["total_streams"].apply(lambda x: f"{int(x):,}".replace(",", "."))
        df_artistas = df_artistas.rename(columns={"artist": "Artista"})
        
        tabla_artistas = dash_table.DataTable(
            data=df_artistas[["Artista", "Reproducciones"]].to_dict('records'),
            columns=[{"name": i, "id": i} for i in ["Artista", "Reproducciones"]],
            style_table={'overflowX': 'auto'},
            style_header={'backgroundColor': '#2a2a2a', 'color': 'white', 'fontWeight': 'bold', 'border': 'none', 'fontFamily': 'Montserrat'},
            style_cell={'backgroundColor': '#1e1e1e', 'color': '#ddd', 'textAlign': 'left', 'padding': '8px', 'fontSize': '13px', 'border': 'none', 'borderBottom': '1px solid #333', 'fontFamily': 'Montserrat'},
            page_size=10
        )

        df_canciones = (
            df_filtrado.groupby(["title", "artist"])["total_streams"]
            .sum()
            .reset_index()
            .sort_values(by="total_streams", ascending=False)
            .head(10)
        )
        df_canciones["Canción - Artista"] = df_canciones["title"] + " - " + df_canciones["artist"]
        df_canciones["Reproducciones"] = df_canciones["total_streams"].apply(lambda x: f"{int(x):,}".replace(",", "."))

        tabla_canciones = dash_table.DataTable(
            data=df_canciones[["Canción - Artista", "Reproducciones"]].to_dict('records'),
            columns=[{"name": i, "id": i} for i in ["Canción - Artista", "Reproducciones"]],
            style_table={'overflowX': 'auto'},
            style_header={'backgroundColor': '#2a2a2a', 'color': 'white', 'fontWeight': 'bold', 'border': 'none', 'fontFamily': 'Montserrat'},
            style_cell={'backgroundColor': '#1e1e1e', 'color': '#ddd', 'textAlign': 'left', 'padding': '8px', 'fontSize': '13px', 'border': 'none', 'borderBottom': '1px solid #333', 'fontFamily': 'Montserrat'},
            page_size=10
        )
    else:
        tabla_artistas = html.P("No hay datos disponibles para este año.", style={'color': '#888'})
        tabla_canciones = html.P("No hay datos disponibles para este año.", style={'color': '#888'})

    return detail_content, tabla_artistas, tabla_canciones, fig_actualizada

if __name__ == '__main__':
    app.run(debug=True, port=8050)