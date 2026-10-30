import numpy as np
import pandas as pd

def calculate_cosine_similarity_matrix(df_top200, year):
    """
    Computes the pairwise Cosine Similarity matrix between regions for a specific year,
    weighting track relevance by their stream share within each region.
    
    Parameters:
    -----------
    df_top200 : pd.DataFrame
        Cleaned annual Top 200 dataset.
    year : int
        Target year for the network matrix.
        
    Returns:
    --------
    pd.DataFrame
        Square symmetric matrix containing cosine similarities [0, 1] between regions.
    """
    df_year = df_top200[df_top200["year"] == year].copy()
    
    # Calculate stream share per track within each region
    df_year["total_region_streams"] = df_year.groupby("region")["total_streams"].transform("sum")
    df_year["share"] = df_year["total_streams"] / df_year["total_region_streams"]

    # Pivot into a wide matrix (Regions x Tracks)
    pivot_shares = df_year.pivot(index="region", columns="track_id", values="share").fillna(0.0)

    # Vectorized cosine similarity computation
    values = pivot_shares.values
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    normalized_matrix = values / np.where(norms == 0, 1, norms)

    cosine_sim = np.dot(normalized_matrix, normalized_matrix.T)
    np.fill_diagonal(cosine_sim, 0.0)  # Exclude self-similarity for network aggregations

    return pd.DataFrame(cosine_sim, index=pivot_shares.index, columns=pivot_shares.index)


def compute_global_similarity_series(df_top200):
    """
    Computes the Global Similarity Average across all available years in the dataset,
    providing the macro time-series trend of cultural convergence.
    
    Parameters:
    -----------
    df_top200 : pd.DataFrame
        Cleaned annual Top 200 dataset.
        
    Returns:
    --------
    pd.DataFrame
        DataFrame with years and their corresponding mean global cosine similarity.
    """
    years = sorted(df_top200["year"].dropna().unique())
    results = []

    for year in years:
        sim_matrix = calculate_cosine_similarity_matrix(df_top200, year)
        
        # Extract upper/lower triangle values (excluding diagonal) to compute the true mean
        values = sim_matrix.values
        n = values.shape[0]
        if n > 1:
            # Get off-diagonal elements
            off_diagonal_vals = values[np.triu_indices(n, k=1)]
            mean_similarity = np.mean(off_diagonal_vals)
        else:
            mean_similarity = 0.0
            
        results.append({"year": year, "global_similarity": mean_similarity})

    return pd.DataFrame(results)

######### CONVERGENCE ########
def build_convergence_table(df_top200, similarity_func):
    """
    Computes pairwise Cosine Distances (1 - Sim) for all years in tidy format.
    """
    years = sorted(df_top200["year"].dropna().unique())
    records = []
    
    for year in years:
        # Get Similarity Matrix
        sim_matrix = similarity_func(df_top200, year)
        paises = sim_matrix.index.tolist()
        n = len(paises)
        
        # Extract upper triangle
        for i in range(n):
            for j in range(i + 1, n):
                records.append({
                    "year": year,
                    "region_a": paises[i],
                    "region_b": paises[j],
                    "distance": 1.0 - sim_matrix.iloc[i, j]
                })
    return pd.DataFrame(records)

def calculate_sigma_convergence(df_distancias):
    """
    Aggregates distance statistics by year.
    """
    return df_distancias.groupby("year")["distance"].agg(
        mean_distance="mean",
        std_distance="std"
    ).reset_index()
######## SIMILARIDAD Y CONVERGENCIA, ANALISIS PRODFUNDO
######### ROBUSTEZ DE LA MÉTRICA ########
# Pegar al final de network_analysis.py (o importar como módulo aparte).

import numpy as np
import pandas as pd

METRICAS = ("cosine_share", "cosine_log1p", "jaccard")


def _region_track_matrix(df_year, metric, dedupe_cols=None):
    """
    Matriz Región x Canción para un año, según la métrica.

    - cosine_share : share de streams dentro de cada región (equivale a la métrica actual).
    - cosine_log1p : log1p sobre streams crudos (atenúa la cabeza de la lista).
    - jaccard      : presencia/ausencia (0/1) de la canción en el Top 200.

    dedupe_cols : lista de columnas (p. ej. ["title", "artist"]) que definen una canción.
                  Si se pasa, se suman los streams de versiones duplicadas por región
                  y se usa esa clave en lugar de track_id.
    """
    df = df_year
    track_key = "track_id"

    if dedupe_cols:
        df = df.copy()
        df["_song_key"] = df[dedupe_cols].astype(str).agg("||".join, axis=1)
        track_key = "_song_key"

    # Agregar por si hay duplicados (misma canción en la misma región)
    agg = df.groupby(["region", track_key])["total_streams"].sum().reset_index()
    pivot = agg.pivot(index="region", columns=track_key, values="total_streams").fillna(0.0)

    if metric == "cosine_share":
        return pivot.div(pivot.sum(axis=1), axis=0)
    if metric == "cosine_log1p":
        return np.log1p(pivot)
    if metric == "jaccard":
        return (pivot > 0).astype(float)
    raise ValueError(f"Métrica desconocida: {metric}. Opciones: {METRICAS}")


def _distance_matrix(mat, metric):
    """Matriz de distancias (n x n) a partir de la matriz Región x Canción."""
    X = mat.values

    if metric.startswith("cosine"):
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        Xn = X / np.where(norms == 0, 1, norms)
        sim = Xn @ Xn.T
        return 1.0 - sim

    # Jaccard: |A∩B| / |A∪B|, vectorizado
    inter = X @ X.T
    sizes = X.sum(axis=1)
    union = sizes[:, None] + sizes[None, :] - inter
    sim = np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)
    return 1.0 - sim


def compute_metric_robustness(df_top200, metrics=METRICAS, dedupe_cols=None, base_year=None):
    """
    Distancia media entre pares de regiones por año, con varias definiciones de distancia.

    Returns
    -------
    pd.DataFrame con columnas:
        year, metric, mean_distance, std_distance, n_regions, index_base100
    index_base100 = mean_distance / mean_distance(base_year) * 100, para comparar
    trayectorias entre métricas cuyos niveles no son comparables.
    """
    years = sorted(df_top200["year"].dropna().unique())
    base_year = years[0] if base_year is None else base_year
    rows = []

    for year in years:
        df_year = df_top200[df_top200["year"] == year]
        for metric in metrics:
            mat = _region_track_matrix(df_year, metric, dedupe_cols)
            dist = _distance_matrix(mat, metric)
            n = dist.shape[0]
            vals = dist[np.triu_indices(n, k=1)]
            rows.append({
                "year": int(year),
                "metric": metric,
                "mean_distance": float(np.mean(vals)),
                "std_distance": float(np.std(vals, ddof=1)),
                "n_regions": n,
            })

    out = pd.DataFrame(rows)
    base = out[out["year"] == int(base_year)].set_index("metric")["mean_distance"]
    out["index_base100"] = out.apply(
        lambda r: r["mean_distance"] / base[r["metric"]] * 100, axis=1
    )
    return out


def compute_concentration_diagnostics(df_top200, top_k=10, min_markets=20):
    """
    Diagnóstico complementario: ¿cambió la concentración o el repertorio global?

    Por año devuelve:
      - top_k_share_mean : share acumulado medio de las top_k canciones por región
      - global_hit_share : fracción media del volumen de cada región que corresponde
                           a canciones presentes en >= min_markets regiones
      - global_hit_count : cantidad de canciones presentes en >= min_markets regiones
    """
    rows = []
    for year in sorted(df_top200["year"].dropna().unique()):
        d = df_top200[df_top200["year"] == year].copy()
        d["share"] = d["total_streams"] / d.groupby("region")["total_streams"].transform("sum")

        top_share = (
            d.sort_values("share", ascending=False)
             .groupby("region")["share"].apply(lambda s: s.head(top_k).sum())
        )

        presence = d.groupby("track_id")["region"].nunique()
        global_tracks = presence[presence >= min_markets].index
        hit_share = (
            d[d["track_id"].isin(global_tracks)]
             .groupby("region")["share"].sum()
             .reindex(d["region"].unique()).fillna(0.0)
        )

        rows.append({
            "year": int(year),
            "top_k_share_mean": float(top_share.mean()),
            "global_hit_share": float(hit_share.mean()),
            "global_hit_count": int(len(global_tracks)),
        })
    return pd.DataFrame(rows)


def plot_metric_robustness(df_rob, ax=None):
    """Trayectorias de las métricas como índice base 100 (año inicial = 100)."""
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(9, 5), dpi=120)
    for metric, g in df_rob.groupby("metric"):
        ax.plot(g["year"], g["index_base100"], marker="o", linewidth=2.2, label=metric)
    ax.axhline(100, color="gray", linestyle="--", linewidth=1)
    ax.set_xticks(sorted(df_rob["year"].unique()))
    ax.set_xlabel("Año")
    ax.set_ylabel("Distancia media (índice, año inicial = 100)")
    ax.set_title("Robustez de la divergencia a la definición de distancia")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(title="Métrica")
    return ax





######## NETWORKS ########

import networkx as nx
import plotly.graph_objects as go
import pandas as pd

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

def plot_musical_mst_network(df_top200, calculate_distance_func, year=2021):
    # Filtrar datos para el año objetivo
    df_year = df_top200[df_top200["year"] == year].copy()
    
    # Calcular streams totales por región para dimensionar los nodos
    region_streams = df_year.groupby("region")["total_streams"].sum().to_dict()
    
    # Normalizar tamaños de nodos para Plotly (ej: entre 10 y 45)
    min_size, max_size = 10, 45
    min_streams = min(region_streams.values()) if region_streams else 1
    max_streams = max(region_streams.values()) if region_streams else 1
    
    def get_node_size(region_name):
        val = region_streams.get(region_name, min_streams)
        if max_streams == min_streams:
            return 20
        # Escala logarítmica o lineal (la lineal va bien si las diferencias no son extremas)
        norm = (val - min_streams) / (max_streams - min_streams)
        return min_size + norm * (max_size - min_size)

    matriz_distancia_cos = calculate_distance_func(df_top200, year)

    G_full = nx.Graph()
    paises = matriz_distancia_cos.index.tolist()

    for p in paises:
        region = CONTINENTES_NOMBRES.get(p, "Otro/Desconocido")
        streams_val = region_streams.get(p, 0)
        G_full.add_node(p, continente=region, streams=streams_val)

    for i in range(len(paises)):
        for j in range(i + 1, len(paises)):
            p1, p2 = paises[i], paises[j]
            dist = matriz_distancia_cos.loc[p1, p2]
            if pd.notna(dist):
                G_full.add_edge(p1, p2, weight=float(dist))

    G_mst = nx.minimum_spanning_tree(G_full, weight="weight")
    pos = nx.kamada_kawai_layout(G_mst, weight="weight", scale=2.0)

    edge_x, edge_y = [], []
    for edge in G_mst.edges():
        if edge[0] in pos and edge[1] in pos:
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        line=dict(width=1.2, color="#888888"),
        hoverinfo="none",
        mode="lines",
        showlegend=False
    )

    fig = go.Figure(data=[edge_trace])

    for continente in [
        "América Latina",
        "Europa",
        "Norteamérica & Oceanía",
        "Asia",
        "Otro/Desconocido",
    ]:
        nodos_cont = [
            n for n, d in G_mst.nodes(data=True) if d.get("continente") == continente and n in pos
        ]
        if not nodos_cont:
            continue

        node_x = [pos[n][0] for n in nodos_cont]
        node_y = [pos[n][1] for n in nodos_cont]
        node_sizes = [get_node_size(n) for n in nodos_cont]

        textos = [
            f"País: {n}<br>Región: {continente}<br>Streams Totales: {region_streams.get(n, 0):,}" 
            for n in nodos_cont
        ]

        fig.add_trace(
            go.Scatter(
                x=node_x,
                y=node_y,
                mode="markers+text",
                name=continente,
                text=nodos_cont,
                textposition="top center",
                textfont=dict(size=10, color="black"),
                hovertext=textos,
                hoverinfo="text",
                marker=dict(
                    size=node_sizes,
                    color=COLOR_MAP[continente],
                    line=dict(width=1.5, color="white"),
                ),
            )
        )

    fig.update_layout(
        title=dict(
            text=f"Árbol de Similitud Musical por Continente (MST Coseno - {year})",
            font=dict(size=14),
        ),
        showlegend=True,
        legend=dict(title="Regiones", x=1.02, y=1),
        hovermode="closest",
        margin=dict(b=20, l=20, r=160, t=50),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        template="plotly_white",
        width=1000,
        height=700,
    )

    return fig


def plot_musical_mst_network_uniform(df_top200, calculate_distance_func, year=2021):

    matriz_distancia_cos = calculate_distance_func(df_top200, year)



    G_full = nx.Graph()

    paises = matriz_distancia_cos.index.tolist()



    for p in paises:

        region = CONTINENTES_NOMBRES.get(p, "Otro/Desconocido")

        G_full.add_node(p, continente=region)



    for i in range(len(paises)):

        for j in range(i + 1, len(paises)):

            p1, p2 = paises[i], paises[j]

            dist = matriz_distancia_cos.loc[p1, p2]

            if pd.notna(dist):

                G_full.add_edge(p1, p2, weight=float(dist))



    # Remove isolated nodes if any exist to prevent layout collapse

    G_mst = nx.minimum_spanning_tree(G_full, weight="weight")

   

    # Compute Kamada-Kawai layout explicitly matching original scale

    pos = nx.kamada_kawai_layout(G_mst, weight="weight", scale=2.0)



    edge_x, edge_y = [], []

    for edge in G_mst.edges():

        if edge[0] in pos and edge[1] in pos:

            x0, y0 = pos[edge[0]]

            x1, y1 = pos[edge[1]]

            edge_x.extend([x0, x1, None])

            edge_y.extend([y0, y1, None])



    edge_trace = go.Scatter(

        x=edge_x,

        y=edge_y,

        line=dict(width=1.2, color="#888888"),

        hoverinfo="none",

        mode="lines",

        showlegend=False

    )



    fig = go.Figure(data=[edge_trace])



    for continente in [

        "América Latina",

        "Europa",

        "Norteamérica & Oceanía",

        "Asia",

        "Otro/Desconocido",

    ]:

        nodos_cont = [

            n for n, d in G_mst.nodes(data=True) if d.get("continente") == continente and n in pos

        ]

        if not nodos_cont:

            continue



        node_x = [pos[n][0] for n in nodos_cont]

        node_y = [pos[n][1] for n in nodos_cont]



        textos = [f"País: {n}<br>Región: {continente}" for n in nodos_cont]



        fig.add_trace(

            go.Scatter(

                x=node_x,

                y=node_y,

                mode="markers+text",

                name=continente,

                text=nodos_cont,

                textposition="top center",

                textfont=dict(size=10, color="black"),

                hovertext=textos,

                hoverinfo="text",

                marker=dict(

                    size=14,

                    color=COLOR_MAP[continente],

                    line=dict(width=1.5, color="white"),

                ),

            )

        )



    fig.update_layout(

        title=dict(

            text=f"Árbol de Similitud Musical por Continente (MST Coseno - {year})",

            font=dict(size=14),

        ),

        showlegend=True,

        legend=dict(title="Regiones", x=1.02, y=1),

        hovermode="closest",

        margin=dict(b=20, l=20, r=160, t=50),

        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, scaleanchor="y", scaleratio=1),

        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),

        template="plotly_white",

        width=1000,

        height=700,

    )



    return fig

######### CLUSTERS ########

import pandas as pd
import numpy as np
import networkx as nx
from networkx.algorithms.community import greedy_modularity_communities
from scipy.spatial.distance import pdist, squareform

def detect_musical_clusters(df_top200, year, calculate_similarity_func=None, percentile_cutoff=90, include_mst=True, col_track='track_id'):
    """
    Detects community clusters of music convergence across regions using the exact
    original validated logic (MST backbone + percentile thresholding on cosine similarity).
    """
    # 1. Filter by year
    df_anio = df_top200[df_top200['year'] == year]
    
    if df_anio.empty:
        raise ValueError(f"No hay registros para el año {year} en el dataset.")
        
    # Pivot (Region x Track using 'track_id')
    matriz_pivot = df_anio.pivot_table(
        index='region', 
        columns=col_track, 
        values='total_streams', 
        aggfunc='sum', 
        fill_value=0
    )
    
    # 2. Cosine Distance and Similarity Matrices
    distancias = pdist(matriz_pivot.values, metric='cosine')
    matriz_distancia = pd.DataFrame(
        squareform(distancias),
        index=matriz_pivot.index,
        columns=matriz_pivot.index
    )
    
    matriz_similitud = 1.0 - matriz_distancia.copy()
    for idx in matriz_similitud.index:
        matriz_similitud.loc[idx, idx] = 0.0

    # 3. NetworkX Graph Construction
    paises = matriz_distancia.index
    n = len(paises)
    G = nx.Graph()
    G.add_nodes_from(paises)

    # MST Backbone
    if include_mst:
        G_dist = nx.from_pandas_adjacency(matriz_distancia)
        mst_dist = nx.minimum_spanning_tree(G_dist)
        for u, v in mst_dist.edges():
            dist_val = matriz_distancia.loc[u, v]
            G.add_edge(u, v, weight=1.0 - dist_val, distance=dist_val)

    # Percentile edges over unique pairs
    triu_indices = np.triu_indices(n, k=1)
    umbral_sim = np.percentile(matriz_similitud.values[triu_indices], percentile_cutoff)

    sim_values = matriz_similitud.values
    for i in range(n):
        for j in range(i + 1, n):
            sim_val = sim_values[i, j]
            if sim_val >= umbral_sim:
                p1, p2 = paises[i], paises[j]
                if not G.has_edge(p1, p2):
                    G.add_edge(p1, p2, weight=sim_val, distance=1.0 - sim_val)

    # 4. Community Detection Algorithm (Greedy Modularity)
    comunidades_raw = list(greedy_modularity_communities(G, weight='weight'))

    registro_clusters = []
    for idx, comm in enumerate(comunidades_raw, 1):
        for pais in comm:
            registro_clusters.append({
                "region": pais,
                "cluster_id": f"Cluster_{idx}",
                "cluster_size": len(comm),
                "year": year,
                "percentile_cutoff": percentile_cutoff
            })

    df_clusters = pd.DataFrame(registro_clusters).sort_values(by=["cluster_id", "region"]).reset_index(drop=True)
    return df_clusters, G



def detectar_clusters_musicales(df_top200, anio, percentil_corte=90, incluir_mst=True, col_track='track_id'):
    """
    Filtra los datos por año, calcula la matriz de distancia Coseno,
    construye el grafo de red y detecta los clusters comunitarios.
    """
    # 1. Filtrar año
    df_anio = df_top200[df_top200['year'] == anio]
    
    if df_anio.empty:
        raise ValueError(f"No hay registros para el año {anio} en el dataset.")
        
    # Pivotear (Región/País x Canción usando 'track_id' o ['title', 'artist'])
    matriz_pivot = df_anio.pivot_table(
        index='region', 
        columns=col_track, 
        values='total_streams', 
        aggfunc='sum', 
        fill_value=0
    )
    
    # 2. Matriz de Distancia Coseno y Matriz de Similitud
    distancias = pdist(matriz_pivot.values, metric='cosine')
    matriz_distancia = pd.DataFrame(
        squareform(distancias),
        index=matriz_pivot.index,
        columns=matriz_pivot.index
    )
    
    matriz_similitud = 1.0 - matriz_distancia.copy()
    for idx in matriz_similitud.index:
        matriz_similitud.loc[idx, idx] = 0.0

    # 3. Construcción del Grafo NetworkX
    paises = matriz_distancia.index
    n = len(paises)
    G = nx.Graph()
    G.add_nodes_from(paises)

    # Esqueleto MST
    if incluir_mst:
        G_dist = nx.from_pandas_adjacency(matriz_distancia)
        mst_dist = nx.minimum_spanning_tree(G_dist)
        for u, v in mst_dist.edges():
            dist_val = matriz_distancia.loc[u, v]
            G.add_edge(u, v, weight=1.0 - dist_val, distance=dist_val)

    # Aristas por percentil sobre pares únicos
    triu_indices = np.triu_indices(n, k=1)
    umbral_sim = np.percentile(matriz_similitud.values[triu_indices], percentil_corte)

    sim_values = matriz_similitud.values
    for i in range(n):
        for j in range(i + 1, n):
            sim_val = sim_values[i, j]
            if sim_val >= umbral_sim:
                p1, p2 = paises[i], paises[j]
                G.add_edge(p1, p2, weight=sim_val, distance=1.0 - sim_val)

    # 4. Algoritmo de Detección de Comunidades
    comunidades_raw = list(greedy_modularity_communities(G, weight='weight'))

    registro_clusters = []
    for idx, comm in enumerate(comunidades_raw, 1):
        for pais in comm:
            registro_clusters.append({
                "pais": pais,
                "cluster_id": f"Cluster_{idx}",
                "integrantes_cluster": len(comm),
                "anio": anio,
                "percentil": percentil_corte
            })

    df_clusters = pd.DataFrame(registro_clusters).sort_values(by=["cluster_id", "pais"]).reset_index(drop=True)
    return df_clusters, G




def plot_clusters_choropleth(df_clusters):
    """
    Genera un mapa coroplético a partir del DataFrame de clústeres detectados.
    """
    import plotly.express as px

    df_plot = df_clusters.copy()
    
    # Manejar nombres de columnas (detect_musical_clusters usa 'region', detectar_clusters_musicales usa 'pais')
    pais_col = "region" if "region" in df_plot.columns else "pais"
    size_col = "cluster_size" if "cluster_size" in df_plot.columns else "integrantes_cluster"
    year_val = df_plot["year"].iloc[0] if "year" in df_plot.columns else df_plot["anio"].iloc[0]
    percentile_val = df_plot["percentile_cutoff"].iloc[0] if "percentile_cutoff" in df_plot.columns else df_plot["percentil"].iloc[0]
    
    df_plot = df_plot.rename(columns={pais_col: "pais", size_col: "integrantes_cluster"})
    df_plot["cluster_id"] = df_plot["cluster_id"].astype(str)
    if not df_plot["cluster_id"].iloc[0].startswith("Cluster_"):
        df_plot["cluster_id"] = "Cluster_" + df_plot["cluster_id"]

    colores_clusters = {
        "Cluster_1": "#1f77b4",  # Azul
        "Cluster_2": "#2ca02c",  # Verde
        "Cluster_3": "#9467bd",  # Violeta
        "Cluster_4": "#d62728",  # Rojo
        "Cluster_5": "#ff7f0e",  # Naranja
    }

    n_clusters = df_plot["cluster_id"].nunique()

    fig = px.choropleth(
        df_plot,
        locations="pais",
        locationmode="country names",
        color="cluster_id",
        hover_name="pais",
        hover_data={"integrantes_cluster": True, "cluster_id": True},
        title=f"Clústeres de Consumo Musical — Año {year_val} (Percentil {percentile_val}%) — Total: {n_clusters} Clústeres",
        color_discrete_map=colores_clusters
    )

    fig.update_layout(
        geo=dict(
            showframe=False,
            showcoastlines=True,
            projection_type="natural earth",
            center=dict(lat=25, lon=20),
            projection_rotation=dict(lon=20)
        ),
        dragmode=False,
        legend_title_text="ID de Clúster",
        margin={"r": 0, "t": 50, "l": 0, "b": 0}
    )

    return fig

def calculate_intracluster_cohesion(df_clusters, df_top200, year):

    """
    Calcula la cohesión interna (similitud y distancia media) de cada clúster
    para un año determinado.

    Parameters:
    -----------
    df_clusters : pd.DataFrame
        DataFrame con columnas ['region', 'cluster_id'] o ['pais', 'cluster_id'].
    df_top200 : pd.DataFrame
        Dataset anual limpio.
    year : int
        Año de referencia.

    Returns:
    --------
    pd.DataFrame
        Métricas de cohesión intra-clúster (similitud media y distancia media).
    """
    sim_matrix = calculate_cosine_similarity_matrix(df_top200, year)
    pais_col = "region" if "region" in df_clusters.columns else "pais"

    metricas = []
    for cluster_id, group in df_clusters.groupby("cluster_id"):
        paises_cluster = [p for p in group[pais_col].unique() if p in sim_matrix.index]
        n_paises = len(paises_cluster)

        if n_paises < 2:
            metricas.append({
                "cluster_id": cluster_id,
                "n_paises": n_paises,
                "similitud_media": 1.0,
                "distancia_media": 0.0,
                "std_distancia": 0.0
            })
            continue

        # Extraer submatriz del clúster
        sub_sim = sim_matrix.loc[paises_cluster, paises_cluster].values
        # Extraer triángulo superior (pares únicos intra-clúster)
        triu_idx = np.triu_indices(n_paises, k=1)
        similitudes_intra = sub_sim[triu_idx]
        distancias_intra = 1.0 - similitudes_intra

        metricas.append({
            "cluster_id": cluster_id,
            "n_paises": n_paises,
            "similitud_media": round(float(np.mean(similitudes_intra)), 4),
            "distancia_media": round(float(np.mean(distancias_intra)), 4),
            "std_distancia": round(float(np.std(distancias_intra)), 4)
        })

    df_cohesion = pd.DataFrame(metricas).sort_values("cluster_id").reset_index(drop=True)
    return df_cohesion



## EXTRAS CAP 3

import random
from networkx.algorithms.community import modularity
from scipy.cluster.hierarchy import linkage, fcluster
_REGION_ORDER = ["América Latina", "Europa", "Norteamérica & Oceanía", "Asia"]


def mst_edges(df_top200, year):
    """
    Aristas del Árbol de Expansión Mínima (distancia coseno) para un año.

    Returns
    -------
    pd.DataFrame con region_a, region_b, distance (52 filas para 53 mercados),
    ordenado de menor a mayor distancia.
    """
    sim = calculate_cosine_similarity_matrix(df_top200, year)
    paises = sim.index.tolist()

    G = nx.Graph()
    G.add_nodes_from(paises)
    for i in range(len(paises)):
        for j in range(i + 1, len(paises)):
            G.add_edge(paises[i], paises[j], weight=float(1.0 - sim.iloc[i, j]))

    T = nx.minimum_spanning_tree(G, weight="weight")
    rows = [{"region_a": a, "region_b": b, "distance": d["weight"]}
            for a, b, d in T.edges(data=True)]
    return pd.DataFrame(rows).sort_values("distance").reset_index(drop=True)


def mst_structure(edges):
    """
    Grado de cada mercado en el MST y listado de hojas con su vecino
    (en un MST, la arista de menor distancia de cada nodo siempre está en el árbol,
    de modo que el vecino de una hoja es su mercado más cercano).
    """
    G = nx.Graph()
    G.add_edges_from(zip(edges["region_a"], edges["region_b"]))

    grados = pd.Series(dict(G.degree())).sort_values(ascending=False)
    hojas = {n: next(iter(G[n])) for n in G.nodes if G.degree(n) == 1}
    return grados, hojas


def mst_region_alignment(edges, labels=None, n_perm=20000, seed=0):
    """
    ¿Cuántas aristas del MST unen mercados de la misma región (etiquetas a priori)?
    Se compara con el resultado de asignar las mismas etiquetas al azar (permutación).

    Returns
    -------
    dict con: observadas, total, perm_media, perm_p95, perm_max, cruces (DataFrame)
    """
    labels = CONTINENTES_NOMBRES if labels is None else labels

    nodos = sorted(set(edges["region_a"]) | set(edges["region_b"]))
    # Orden fijo (región y luego alfabético) para que la permutación sea reproducible
    nodos = [n for r in _REGION_ORDER for n in nodos if labels.get(n) == r] + \
            [n for n in nodos if labels.get(n) not in _REGION_ORDER]

    pares = list(zip(edges["region_a"], edges["region_b"]))
    observadas = sum(labels[a] == labels[b] for a, b in pares)

    rng = random.Random(seed)
    base = [labels[n] for n in nodos]
    sims = []
    for _ in range(n_perm):
        vals = base[:]
        rng.shuffle(vals)
        lab = dict(zip(nodos, vals))
        sims.append(sum(lab[a] == lab[b] for a, b in pares))
    sims = np.array(sims)

    cruces = edges[[labels[a] != labels[b] for a, b in pares]].copy()
    cruces["region_label_a"] = cruces["region_a"].map(labels)
    cruces["region_label_b"] = cruces["region_b"].map(labels)

    return {
        "observadas": int(observadas),
        "total": len(pares),
        "perm_media": float(sims.mean()),
        "perm_p95": float(np.percentile(sims, 95)),
        "perm_max": int(sims.max()),
        "cruces": cruces.reset_index(drop=True),
    }


def adjusted_rand_index(labels_a, labels_b):
    """
    Índice de Rand ajustado entre dos particiones de los mismos elementos.
    1 = particiones idénticas; 0 = acuerdo equivalente al azar.
    labels_a / labels_b: pd.Series con el mismo índice (mercados).
    """
    a = labels_a.loc[labels_b.index]
    tabla = pd.crosstab(a.values, labels_b.values).values
    n = tabla.sum()

    def comb2(x):
        return x * (x - 1) / 2

    suma_celdas = comb2(tabla).sum()
    suma_filas = comb2(tabla.sum(axis=1)).sum()
    suma_cols = comb2(tabla.sum(axis=0)).sum()
    esperado = suma_filas * suma_cols / comb2(n)
    maximo = (suma_filas + suma_cols) / 2

    if maximo == esperado:
        return 1.0
    return float((suma_celdas - esperado) / (maximo - esperado))


def _best_match_jaccard(ref_labels, alt_labels):
    """Para cada grupo de referencia, mayor Jaccard con algún grupo de la partición alternativa."""
    out = {}
    for cid, miembros in ref_labels.groupby(ref_labels).groups.items():
        A = set(miembros)
        mejor = 0.0
        for _, miembros_alt in alt_labels.groupby(alt_labels).groups.items():
            B = set(miembros_alt)
            mejor = max(mejor, len(A & B) / len(A | B))
        out[f"J_{cid}"] = round(mejor, 3)
    return out


def _sizes(labels):
    return "/".join(str(s) for s in sorted(labels.value_counts().tolist(), reverse=True))


def cluster_sensitivity(df_top200, year=2021, percentiles=(80, 85, 90, 95),
                        reference_percentile=90, linkages=("average", "complete")):
    """
    Compara la partición de referencia (MST + percentil `reference_percentile`, Greedy Modularity)
    con (a) la misma construcción con otros percentiles y (b) clustering jerárquico sobre la
    distancia coseno, cortado en el mismo número de grupos que la referencia.

    Columnas del resultado:
      n_grupos, tamanos, ARI_vs_ref (acuerdo con la referencia),
      J_Cluster_k (mayor Jaccard del grupo k de referencia con algún grupo de la alternativa),
      Q_grafo_ref (modularidad de la partición medida sobre el grafo de referencia).
    """
    df_ref, G_ref = detect_musical_clusters(
        df_top200, year, percentile_cutoff=reference_percentile)
    ref = df_ref.set_index("region")["cluster_id"]
    k_ref = ref.nunique()

    def q_sobre_ref(labels):
        comunidades = [set(m) for m in labels.groupby(labels).groups.values()]
        return round(float(modularity(G_ref, comunidades, weight="weight")), 3)

    filas = []

    for p in percentiles:
        df_p, G_p = detect_musical_clusters(df_top200, year, percentile_cutoff=p)
        lab = df_p.set_index("region")["cluster_id"]
        fila = {
            "metodo": f"Greedy modularity, percentil {p}" + (" (referencia)" if p == reference_percentile else ""),
            "n_aristas": G_p.number_of_edges(),
            "n_grupos": lab.nunique(),
            "tamanos": _sizes(lab),
            "ARI_vs_ref": round(adjusted_rand_index(ref, lab), 3),
            "Q_grafo_ref": q_sobre_ref(lab),
        }
        fila.update(_best_match_jaccard(ref, lab))
        filas.append(fila)

    # Línea base jerárquica sobre la distancia coseno
    dist = 1.0 - calculate_cosine_similarity_matrix(df_top200, year)
    paises = dist.index
    D = dist.values.copy()
    np.fill_diagonal(D, 0.0)
    condensada = squareform(D, checks=False)

    for metodo in linkages:
        Z = linkage(condensada, method=metodo)
        lab = pd.Series(fcluster(Z, t=k_ref, criterion="maxclust"), index=paises).astype(str)
        fila = {
            "metodo": f"Jerárquico ({metodo}), k={k_ref}",
            "n_aristas": np.nan,
            "n_grupos": lab.nunique(),
            "tamanos": _sizes(lab),
            "ARI_vs_ref": round(adjusted_rand_index(ref, lab), 3),
            "Q_grafo_ref": q_sobre_ref(lab),
        }
        fila.update(_best_match_jaccard(ref, lab))
        filas.append(fila)

    return pd.DataFrame(filas)