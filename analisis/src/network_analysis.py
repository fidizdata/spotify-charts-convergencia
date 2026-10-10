"""
Cosine-distance convergence and network structure of Spotify Top 200 markets.

The module is organised in six sections, one per analytical step of the report:

1. Constants       - region labels and colour palettes.
2. Profiles        - region x track matrices and pairwise similarity primitives.
3. Convergence     - sigma-convergence of the mean pairwise distance.
4. Diagnostics     - robustness of the distance definition and list concentration.
5. MST             - minimum spanning tree: edges, structure, region alignment, figure.
6. Communities     - cluster detection, cohesion, choropleth map and sensitivity.

Expected input
--------------
Every public function that receives ``df_top200`` expects the annual Top 200
table produced by ``preprocessing.load_and_process_spotify``: one row per
(year, region, track_id) with at least the columns ``year``, ``region``,
``track_id`` and ``total_streams``, and exactly 200 tracks per (year, region).

Notes
-----
Plot titles, axis labels, region labels and the column names of the cohesion
and sensitivity tables are kept in Spanish because the report is written in
Spanish. Everything else (code, comments, docstrings) is in English.
"""

from __future__ import annotations

import random
from typing import Callable, Mapping, Sequence

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from networkx.algorithms.community import greedy_modularity_communities, modularity
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

__all__ = [
    "DISTANCE_METRICS",
    "REGION_LABELS",
    "CONTINENTES_NOMBRES",
    "calculate_cosine_similarity_matrix",
    "build_convergence_table",
    "calculate_sigma_convergence",
    "compute_metric_robustness",
    "plot_metric_robustness",
    "compute_concentration_diagnostics",
    "mst_edges",
    "mst_structure",
    "mst_region_alignment",
    "plot_musical_mst_network",
    "detect_musical_clusters",
    "plot_clusters_choropleth",
    "calculate_intracluster_cohesion",
    "cluster_sensitivity",
]


# =============================================================================
# 1. Constants
# =============================================================================

#: Distance definitions supported by :func:`compute_metric_robustness`.
DISTANCE_METRICS = ("cosine_share", "cosine_log1p", "jaccard")

#: A-priori region of every market (used only for colouring and for the
#: region-alignment test; the network itself never uses geography).
REGION_LABELS: dict[str, str] = {
    # Latin America
    "Argentina": "América Latina", "Bolivia": "América Latina", "Brazil": "América Latina",
    "Chile": "América Latina", "Colombia": "América Latina", "Costa Rica": "América Latina",
    "Dominican Republic": "América Latina", "Ecuador": "América Latina",
    "El Salvador": "América Latina", "Guatemala": "América Latina",
    "Honduras": "América Latina", "Mexico": "América Latina", "Nicaragua": "América Latina",
    "Panama": "América Latina", "Peru": "América Latina", "Paraguay": "América Latina",
    "Uruguay": "América Latina",
    # North America & Oceania
    "United States": "Norteamérica & Oceanía", "Canada": "Norteamérica & Oceanía",
    "Australia": "Norteamérica & Oceanía", "New Zealand": "Norteamérica & Oceanía",
    # Europe
    "Austria": "Europa", "Belgium": "Europa", "Switzerland": "Europa",
    "Czech Republic": "Europa", "Germany": "Europa", "Denmark": "Europa",
    "Estonia": "Europa", "Spain": "Europa", "Finland": "Europa", "France": "Europa",
    "United Kingdom": "Europa", "Greece": "Europa", "Hungary": "Europa",
    "Ireland": "Europa", "Iceland": "Europa", "Italy": "Europa", "Lithuania": "Europa",
    "Latvia": "Europa", "Netherlands": "Europa", "Norway": "Europa", "Poland": "Europa",
    "Portugal": "Europa", "Sweden": "Europa", "Slovakia": "Europa", "Turkey": "Europa",
    # Asia
    "Hong Kong": "Asia", "Indonesia": "Asia", "Japan": "Asia", "Malaysia": "Asia",
    "Philippines": "Asia", "Singapore": "Asia", "Thailand": "Asia", "Taiwan": "Asia",
}

#: Backward-compatible alias used by the report notebook.
CONTINENTES_NOMBRES = REGION_LABELS

#: Fixed region order: drives the legend order and the reproducible node order
#: of the permutation test in :func:`mst_region_alignment`.
REGION_ORDER = ("América Latina", "Europa", "Norteamérica & Oceanía", "Asia")
UNKNOWN_REGION = "Otro/Desconocido"

REGION_COLORS = {
    "América Latina": "#FF5722",
    "Europa": "#3F51B5",
    "Norteamérica & Oceanía": "#009688",
    "Asia": "#E91E63",
    UNKNOWN_REGION: "#9E9E9E",
}

CLUSTER_COLORS = {
    "Cluster_1": "#1f77b4",  # blue
    "Cluster_2": "#2ca02c",  # green
    "Cluster_3": "#9467bd",  # violet
    "Cluster_4": "#d62728",  # red
    "Cluster_5": "#ff7f0e",  # orange
}

_NODE_SIZE_RANGE = (10, 45)  # marker size range of the MST figure
_NODE_SIZE_FALLBACK = 20     # marker size when all markets have the same volume


# =============================================================================
# 2. Profiles and similarity primitives
# =============================================================================

def _years(df_top200: pd.DataFrame) -> list:
    """Return the sorted list of distinct, non-null years in the dataset."""
    return sorted(df_top200["year"].dropna().unique())


def _year_slice(df_top200: pd.DataFrame, year: int) -> pd.DataFrame:
    """Return the rows of one year, raising ``ValueError`` if there are none."""
    df_year = df_top200[df_top200["year"] == year]
    if df_year.empty:
        raise ValueError(f"No records found for year {year}.")
    return df_year


def _stream_matrix(df_year: pd.DataFrame) -> pd.DataFrame:
    """
    Build the raw region x track matrix of total streams for one year.

    Parameters
    ----------
    df_year : pd.DataFrame
        Top 200 rows of a single year.

    Returns
    -------
    pd.DataFrame
        Rows are regions, columns are tracks; missing tracks are filled with 0.
    """
    return (
        df_year.groupby(["region", "track_id"])["total_streams"]
        .sum()
        .unstack(fill_value=0.0)
    )


def _apply_metric(streams: pd.DataFrame, metric: str) -> pd.DataFrame:
    """
    Transform a raw stream matrix into the profile used by a distance definition.

    Parameters
    ----------
    streams : pd.DataFrame
        Region x track matrix of raw streams (see :func:`_stream_matrix`).
    metric : {"cosine_share", "cosine_log1p", "jaccard"}
        ``cosine_share``: stream share of each track within its region.
        ``cosine_log1p``: ``log(1 + streams)``, which damps the head of the list.
        ``jaccard``: presence (1) or absence (0) of each track, ignoring volume.

    Returns
    -------
    pd.DataFrame
        Matrix with the same shape as ``streams``.
    """
    if metric == "cosine_share":
        return streams.div(streams.sum(axis=1), axis=0)
    if metric == "cosine_log1p":
        return np.log1p(streams)
    if metric == "jaccard":
        return (streams > 0).astype(float)
    raise ValueError(f"Unknown metric: {metric!r}. Options: {DISTANCE_METRICS}")


def _similarity_values(profiles: np.ndarray, metric: str) -> np.ndarray:
    """
    Compute the pairwise similarity matrix of the rows of ``profiles``.

    Parameters
    ----------
    profiles : np.ndarray
        Region x track matrix returned by :func:`_apply_metric`.
    metric : str
        Cosine similarity for ``cosine_*`` metrics, set-based Jaccard similarity
        (|A ∩ B| / |A ∪ B|) for ``jaccard``.

    Returns
    -------
    np.ndarray
        Square matrix of shape (n_regions, n_regions).
    """
    if metric.startswith("cosine"):
        norms = np.linalg.norm(profiles, axis=1, keepdims=True)
        unit = profiles / np.where(norms == 0, 1.0, norms)
        return unit @ unit.T

    intersection = profiles @ profiles.T
    sizes = profiles.sum(axis=1)
    union = sizes[:, None] + sizes[None, :] - intersection
    return np.divide(
        intersection, union, out=np.zeros_like(intersection), where=union > 0
    )


def _upper_triangle(matrix: np.ndarray) -> np.ndarray:
    """Return the values above the diagonal, i.e. each unordered pair once."""
    return matrix[np.triu_indices(matrix.shape[0], k=1)]


def calculate_cosine_similarity_matrix(df_top200: pd.DataFrame, year: int) -> pd.DataFrame:
    """
    Pairwise cosine similarity between regions for one year, on stream shares.

    Each region is represented by the share of its streams that every track
    accounts for. The diagonal is set to 0 so that self-similarity does not
    contaminate network aggregations.

    Parameters
    ----------
    df_top200 : pd.DataFrame
        Annual Top 200 dataset.
    year : int
        Target year.

    Returns
    -------
    pd.DataFrame
        Symmetric region x region matrix of cosine similarities in [0, 1],
        with a zero diagonal.
    """
    streams = _stream_matrix(_year_slice(df_top200, year))
    profiles = _apply_metric(streams, "cosine_share").to_numpy(dtype=float)

    similarity = _similarity_values(profiles, "cosine_share")
    np.fill_diagonal(similarity, 0.0)
    return pd.DataFrame(similarity, index=streams.index, columns=streams.index)


def _cosine_distance_matrix(df_top200: pd.DataFrame, year: int) -> pd.DataFrame:
    """
    Pairwise cosine distance (1 - similarity) between regions for one year.

    Unlike :func:`calculate_cosine_similarity_matrix`, the diagonal is a true 0.
    """
    similarity = calculate_cosine_similarity_matrix(df_top200, year)
    distance = 1.0 - similarity.to_numpy()
    np.fill_diagonal(distance, 0.0)
    return pd.DataFrame(distance, index=similarity.index, columns=similarity.index)


# =============================================================================
# 3. Convergence
# =============================================================================

def build_convergence_table(
    df_top200: pd.DataFrame,
    similarity_func: Callable[[pd.DataFrame, int], pd.DataFrame],
) -> pd.DataFrame:
    """
    Pairwise distances (1 - similarity) between all regions, for every year.

    Parameters
    ----------
    df_top200 : pd.DataFrame
        Annual Top 200 dataset.
    similarity_func : callable
        Function ``(df_top200, year) -> similarity matrix`` such as
        :func:`calculate_cosine_similarity_matrix`.

    Returns
    -------
    pd.DataFrame
        Tidy table with columns ``year``, ``region_a``, ``region_b`` and
        ``distance``; each unordered pair of regions appears once per year.
    """
    frames = []
    for year in _years(df_top200):
        similarity = similarity_func(df_top200, year)
        regions = similarity.index.to_numpy()
        row_idx, col_idx = np.triu_indices(len(regions), k=1)
        frames.append(
            pd.DataFrame(
                {
                    "year": year,
                    "region_a": regions[row_idx],
                    "region_b": regions[col_idx],
                    "distance": 1.0 - similarity.to_numpy()[row_idx, col_idx],
                }
            )
        )

    if not frames:
        return pd.DataFrame(columns=["year", "region_a", "region_b", "distance"])
    return pd.concat(frames, ignore_index=True)


def calculate_sigma_convergence(df_distances: pd.DataFrame) -> pd.DataFrame:
    """
    Sigma-convergence statistics: dispersion of pairwise distances by year.

    Parameters
    ----------
    df_distances : pd.DataFrame
        Output of :func:`build_convergence_table`.

    Returns
    -------
    pd.DataFrame
        One row per year with ``mean_distance`` and ``std_distance``. A
        falling ``mean_distance`` over time would indicate convergence.
    """
    return (
        df_distances.groupby("year")["distance"]
        .agg(mean_distance="mean", std_distance="std")
        .reset_index()
    )


# =============================================================================
# 4. Diagnostics: robustness of the metric and concentration of the lists
# =============================================================================

def compute_metric_robustness(
    df_top200: pd.DataFrame,
    metrics: Sequence[str] = DISTANCE_METRICS,
    base_year: int | None = None,
) -> pd.DataFrame:
    """
    Mean pairwise distance by year under several distance definitions.

    Parameters
    ----------
    df_top200 : pd.DataFrame
        Annual Top 200 dataset.
    metrics : sequence of str, default ``DISTANCE_METRICS``
        Distance definitions to compare (see :func:`_apply_metric`).
    base_year : int, optional
        Year used as 100 in the index column. Defaults to the first year.

    Returns
    -------
    pd.DataFrame
        Columns ``year``, ``metric``, ``mean_distance``, ``std_distance``,
        ``n_regions`` and ``index_base100`` (mean distance relative to
        ``base_year``), which makes trajectories comparable across metrics
        whose levels are not.
    """
    years = _years(df_top200)
    base_year = years[0] if base_year is None else base_year

    rows = []
    for year in years:
        streams = _stream_matrix(df_top200[df_top200["year"] == year])
        for metric in metrics:
            profiles = _apply_metric(streams, metric).to_numpy(dtype=float)
            distances = _upper_triangle(1.0 - _similarity_values(profiles, metric))
            rows.append(
                {
                    "year": int(year),
                    "metric": metric,
                    "mean_distance": float(np.mean(distances)),
                    "std_distance": float(np.std(distances, ddof=1)),
                    "n_regions": profiles.shape[0],
                }
            )

    out = pd.DataFrame(rows)
    base = out.loc[out["year"] == int(base_year)].set_index("metric")["mean_distance"]
    out["index_base100"] = out["mean_distance"] / out["metric"].map(base) * 100
    return out


def plot_metric_robustness(df_rob: pd.DataFrame, ax: plt.Axes | None = None) -> plt.Axes:
    """
    Plot the base-100 trajectories of the mean distance for each metric.

    Parameters
    ----------
    df_rob : pd.DataFrame
        Output of :func:`compute_metric_robustness`.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on; a new figure is created if omitted.

    Returns
    -------
    matplotlib.axes.Axes
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(9, 5), dpi=120)

    for metric, group in df_rob.groupby("metric"):
        ax.plot(group["year"], group["index_base100"], marker="o", linewidth=2.2, label=metric)

    ax.axhline(100, color="gray", linestyle="--", linewidth=1)
    ax.set_xticks(sorted(df_rob["year"].unique()))
    ax.set_xlabel("Año")
    ax.set_ylabel("Distancia media (índice, año inicial = 100)")
    ax.set_title("Robustez de la divergencia a la definición de distancia")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(title="Métrica")
    return ax


def compute_concentration_diagnostics(
    df_top200: pd.DataFrame, top_k: int = 10, min_markets: int = 20
) -> pd.DataFrame:
    """
    Distinguish a change in list concentration from a change in shared repertoire.

    Parameters
    ----------
    df_top200 : pd.DataFrame
        Annual Top 200 dataset.
    top_k : int, default 10
        Number of leading tracks per region used for the concentration measure.
    min_markets : int, default 20
        A track is "global" in a year if it appears in the Top 200 of at least
        this many regions.

    Returns
    -------
    pd.DataFrame
        One row per year with:

        - ``top_k_share_mean``: mean share of streams held by each region's
          ``top_k`` tracks.
        - ``global_hit_share``: mean share of each region's streams that comes
          from global tracks.
        - ``global_hit_count``: number of global tracks.
    """
    rows = []
    for year in _years(df_top200):
        d = df_top200.loc[
            df_top200["year"] == year, ["region", "track_id", "total_streams"]
        ].copy()
        d["share"] = d["total_streams"] / d.groupby("region")["total_streams"].transform("sum")

        top_share = (
            d.sort_values("share", ascending=False)
            .groupby("region")
            .head(top_k)
            .groupby("region")["share"]
            .sum()
        )

        presence = d.groupby("track_id")["region"].nunique()
        global_tracks = presence.index[presence >= min_markets]
        global_share = (
            d.loc[d["track_id"].isin(global_tracks)]
            .groupby("region")["share"]
            .sum()
            .reindex(top_share.index, fill_value=0.0)
        )

        rows.append(
            {
                "year": int(year),
                "top_k_share_mean": float(top_share.mean()),
                "global_hit_share": float(global_share.mean()),
                "global_hit_count": int(len(global_tracks)),
            }
        )
    return pd.DataFrame(rows)


# =============================================================================
# 5. Minimum spanning tree (MST)
# =============================================================================

def _build_mst(distance: pd.DataFrame) -> nx.Graph:
    """
    Minimum spanning tree of the complete graph defined by a distance matrix.

    Nodes keep the order of ``distance.index``; only the upper triangle of the
    matrix is read and NaN distances are skipped.

    Parameters
    ----------
    distance : pd.DataFrame
        Square region x region distance matrix.

    Returns
    -------
    nx.Graph
        Tree with ``len(distance) - 1`` edges and a ``weight`` attribute
        holding the distance.
    """
    regions = distance.index.tolist()
    values = distance.to_numpy(dtype=float)

    complete = nx.Graph()
    complete.add_nodes_from(regions)
    row_idx, col_idx = np.triu_indices(len(regions), k=1)
    complete.add_weighted_edges_from(
        (regions[i], regions[j], float(values[i, j]))
        for i, j in zip(row_idx, col_idx)
        if not np.isnan(values[i, j])
    )
    return nx.minimum_spanning_tree(complete, weight="weight")


def mst_edges(df_top200: pd.DataFrame, year: int) -> pd.DataFrame:
    """
    Edges of the cosine-distance MST for one year.

    Parameters
    ----------
    df_top200 : pd.DataFrame
        Annual Top 200 dataset.
    year : int
        Target year.

    Returns
    -------
    pd.DataFrame
        Columns ``region_a``, ``region_b`` and ``distance`` (n_regions - 1
        rows), sorted from the shortest to the longest edge.
    """
    tree = _build_mst(_cosine_distance_matrix(df_top200, year))
    rows = [
        {"region_a": a, "region_b": b, "distance": data["weight"]}
        for a, b, data in tree.edges(data=True)
    ]
    return pd.DataFrame(rows).sort_values("distance").reset_index(drop=True)


def mst_structure(edges: pd.DataFrame) -> tuple[pd.Series, dict[str, str]]:
    """
    Degree of every node and nearest neighbour of every leaf of the MST.

    In an MST the lightest edge incident to a node always belongs to the tree,
    so the single neighbour of a leaf is its closest region.

    Parameters
    ----------
    edges : pd.DataFrame
        Output of :func:`mst_edges`.

    Returns
    -------
    degrees : pd.Series
        Number of connections per region, sorted in descending order.
    leaves : dict
        Maps each leaf region to its only neighbour.
    """
    graph = nx.Graph()
    graph.add_edges_from(zip(edges["region_a"], edges["region_b"]))

    degrees = pd.Series(dict(graph.degree())).sort_values(ascending=False)
    leaves = {n: next(iter(graph[n])) for n in graph.nodes if graph.degree(n) == 1}
    return degrees, leaves


def mst_region_alignment(
    edges: pd.DataFrame,
    labels: Mapping[str, str] | None = None,
    n_perm: int = 20_000,
    seed: int = 0,
) -> dict:
    """
    Test whether MST edges join regions of the same a-priori group more often than chance.

    The observed number of same-group edges is compared with the distribution
    obtained by randomly reassigning the same labels to the nodes (permutation
    test). The node order is fixed (group order, then alphabetical) so the
    result is reproducible for a given ``seed``.

    Parameters
    ----------
    edges : pd.DataFrame
        Output of :func:`mst_edges`.
    labels : mapping, optional
        Region label of every market. Defaults to :data:`REGION_LABELS`.
    n_perm : int, default 20000
        Number of random label assignments.
    seed : int, default 0
        Seed of the random generator.

    Returns
    -------
    dict
        ``observadas`` (same-group edges), ``total`` (edges), ``perm_media``,
        ``perm_p95`` and ``perm_max`` (mean, 95th percentile and maximum of the
        permuted counts) and ``cruces`` (DataFrame of edges joining different
        groups, with both labels).
    """
    labels = REGION_LABELS if labels is None else labels

    group_rank = {group: k for k, group in enumerate(REGION_ORDER)}
    nodes = sorted(set(edges["region_a"]) | set(edges["region_b"]))
    nodes.sort(key=lambda n: group_rank.get(labels.get(n), len(group_rank)))  # stable

    node_pos = {n: k for k, n in enumerate(nodes)}
    end_a = np.array([node_pos[a] for a in edges["region_a"]])
    end_b = np.array([node_pos[b] for b in edges["region_b"]])

    group_codes = pd.factorize(pd.Series([labels[n] for n in nodes]))[0]
    observed = int(np.sum(group_codes[end_a] == group_codes[end_b]))

    # Shuffling a list of positions is equivalent to shuffling the labels
    # themselves, but lets the comparison be vectorised.
    rng = random.Random(seed)
    permutations = np.empty((n_perm, len(nodes)), dtype=np.int64)
    positions = list(range(len(nodes)))
    for k in range(n_perm):
        shuffled = positions[:]
        rng.shuffle(shuffled)
        permutations[k] = shuffled
    permuted_codes = group_codes[permutations]
    counts = (permuted_codes[:, end_a] == permuted_codes[:, end_b]).sum(axis=1)

    crossing_mask = group_codes[end_a] != group_codes[end_b]
    crossings = edges.loc[crossing_mask].copy()
    crossings["region_label_a"] = crossings["region_a"].map(labels)
    crossings["region_label_b"] = crossings["region_b"].map(labels)

    return {
        "observadas": observed,
        "total": len(edges),
        "perm_media": float(counts.mean()),
        "perm_p95": float(np.percentile(counts, 95)),
        "perm_max": int(counts.max()),
        "cruces": crossings.reset_index(drop=True),
    }


def _scaled_size(value: float, low: float, high: float) -> float:
    """Linearly map ``value`` from [low, high] to the marker size range."""
    if high == low:
        return _NODE_SIZE_FALLBACK
    smallest, largest = _NODE_SIZE_RANGE
    return smallest + (value - low) / (high - low) * (largest - smallest)


def plot_musical_mst_network(
    df_top200: pd.DataFrame,
    calculate_distance_func: Callable[[pd.DataFrame, int], pd.DataFrame],
    year: int = 2021,
) -> go.Figure:
    """
    Interactive figure of the MST, coloured by region and sized by stream volume.

    The node positions come from a Kamada-Kawai layout and are only a drawing
    aid: the information is in the connections, not in the distances on screen.

    Parameters
    ----------
    df_top200 : pd.DataFrame
        Annual Top 200 dataset.
    calculate_distance_func : callable
        Function ``(df_top200, year) -> distance matrix`` (regions x regions).
    year : int, default 2021
        Target year.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    region_streams = (
        df_top200.loc[df_top200["year"] == year]
        .groupby("region")["total_streams"]
        .sum()
        .to_dict()
    )
    lowest = min(region_streams.values()) if region_streams else 1
    highest = max(region_streams.values()) if region_streams else 1

    tree = _build_mst(calculate_distance_func(df_top200, year))
    position = nx.kamada_kawai_layout(tree, weight="weight", scale=2.0)

    edge_x, edge_y = [], []
    for u, v in tree.edges():
        (x0, y0), (x1, y1) = position[u], position[v]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    fig = go.Figure(
        data=[
            go.Scatter(
                x=edge_x,
                y=edge_y,
                line=dict(width=1.2, color="#888888"),
                hoverinfo="none",
                mode="lines",
                showlegend=False,
            )
        ]
    )

    region_of = {n: REGION_LABELS.get(n, UNKNOWN_REGION) for n in tree.nodes}
    for region in (*REGION_ORDER, UNKNOWN_REGION):
        members = [n for n in tree.nodes if region_of[n] == region]
        if not members:
            continue

        fig.add_trace(
            go.Scatter(
                x=[position[n][0] for n in members],
                y=[position[n][1] for n in members],
                mode="markers+text",
                name=region,
                text=members,
                textposition="top center",
                textfont=dict(size=10, color="black"),
                hovertext=[
                    f"País: {n}<br>Región: {region}<br>"
                    f"Streams Totales: {region_streams.get(n, 0):,}"
                    for n in members
                ],
                hoverinfo="text",
                marker=dict(
                    size=[
                        _scaled_size(region_streams.get(n, lowest), lowest, highest)
                        for n in members
                    ],
                    color=REGION_COLORS[region],
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
        xaxis=dict(
            showgrid=False, zeroline=False, showticklabels=False, scaleanchor="y", scaleratio=1
        ),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        template="plotly_white",
        width=1000,
        height=700,
    )
    return fig


# =============================================================================
# 6. Community detection
# =============================================================================

def _cluster_graph(
    distance: pd.DataFrame, percentile_cutoff: float, include_mst: bool
) -> nx.Graph:
    """
    Similarity graph on which communities are detected.

    The graph contains (i) the MST edges, which guarantee connectivity, and
    (ii) every pair whose similarity reaches the ``percentile_cutoff``-th
    percentile of all pairwise similarities. Edge weights are similarities.

    Parameters
    ----------
    distance : pd.DataFrame
        Region x region distance matrix with a zero diagonal.
    percentile_cutoff : float
        Percentile (0-100) of the pairwise similarities used as threshold.
    include_mst : bool
        Whether to add the MST backbone.

    Returns
    -------
    nx.Graph
        Edges carry ``weight`` (similarity) and ``distance`` attributes.
    """
    regions = distance.index.tolist()
    position = {r: k for k, r in enumerate(regions)}
    dist = distance.to_numpy(dtype=float)
    similarity = 1.0 - dist
    np.fill_diagonal(similarity, 0.0)

    graph = nx.Graph()
    graph.add_nodes_from(regions)

    if include_mst:
        for u, v in _build_mst(distance).edges():
            d = dist[position[u], position[v]]
            graph.add_edge(u, v, weight=1.0 - d, distance=d)

    row_idx, col_idx = np.triu_indices(len(regions), k=1)
    pair_similarity = similarity[row_idx, col_idx]
    keep = pair_similarity >= np.percentile(pair_similarity, percentile_cutoff)
    for i, j in zip(row_idx[keep], col_idx[keep]):
        u, v = regions[i], regions[j]
        if not graph.has_edge(u, v):
            graph.add_edge(u, v, weight=similarity[i, j], distance=1.0 - similarity[i, j])
    return graph


def _communities_table(graph: nx.Graph, year: int, percentile_cutoff: float) -> pd.DataFrame:
    """Run Greedy Modularity on ``graph`` and return the membership table."""
    records = []
    for cluster_number, community in enumerate(
        greedy_modularity_communities(graph, weight="weight"), start=1
    ):
        for region in community:
            records.append(
                {
                    "region": region,
                    "cluster_id": f"Cluster_{cluster_number}",
                    "cluster_size": len(community),
                    "year": year,
                    "percentile_cutoff": percentile_cutoff,
                }
            )
    return (
        pd.DataFrame(records)
        .sort_values(by=["cluster_id", "region"])
        .reset_index(drop=True)
    )


def detect_musical_clusters(
    df_top200: pd.DataFrame,
    year: int,
    percentile_cutoff: float = 90,
    include_mst: bool = True,
) -> tuple[pd.DataFrame, nx.Graph]:
    """
    Detect groups of markets with similar listening profiles in one year.

    Communities are found with Greedy Modularity on a similarity graph built
    from the MST backbone plus all pairs above a similarity percentile (see
    :func:`_cluster_graph`).

    Parameters
    ----------
    df_top200 : pd.DataFrame
        Annual Top 200 dataset.
    year : int
        Target year.
    percentile_cutoff : float, default 90
        Percentile of pairwise similarities above which a pair becomes an edge.
    include_mst : bool, default True
        Whether to include the MST backbone.

    Returns
    -------
    df_clusters : pd.DataFrame
        Columns ``region``, ``cluster_id``, ``cluster_size``, ``year`` and
        ``percentile_cutoff``; ``Cluster_1`` is the largest community.
    graph : nx.Graph
        The graph on which the communities were detected.
    """
    distance = _cosine_distance_matrix(df_top200, year)
    graph = _cluster_graph(distance, percentile_cutoff, include_mst)
    return _communities_table(graph, year, percentile_cutoff), graph


def plot_clusters_choropleth(df_clusters: pd.DataFrame) -> go.Figure:
    """
    World map coloured by cluster membership.

    Parameters
    ----------
    df_clusters : pd.DataFrame
        First output of :func:`detect_musical_clusters`.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    df_plot = df_clusters.rename(
        columns={"region": "pais", "cluster_size": "integrantes_cluster"}
    )
    year = df_plot["year"].iloc[0]
    percentile = df_plot["percentile_cutoff"].iloc[0]
    n_clusters = df_plot["cluster_id"].nunique()

    fig = px.choropleth(
        df_plot,
        locations="pais",
        locationmode="country names",
        color="cluster_id",
        hover_name="pais",
        hover_data={"integrantes_cluster": True, "cluster_id": True},
        title=(
            f"Clústeres de Consumo Musical — Año {year} "
            f"(Percentil {percentile}%) — Total: {n_clusters} Clústeres"
        ),
        color_discrete_map=CLUSTER_COLORS,
    )
    fig.update_layout(
        geo=dict(
            showframe=False,
            showcoastlines=True,
            projection_type="natural earth",
            center=dict(lat=25, lon=20),
            projection_rotation=dict(lon=20),
        ),
        dragmode=False,
        legend_title_text="ID de Clúster",
        margin={"r": 0, "t": 50, "l": 0, "b": 0},
    )
    return fig


def calculate_intracluster_cohesion(
    df_clusters: pd.DataFrame, df_top200: pd.DataFrame, year: int
) -> pd.DataFrame:
    """
    Mean similarity and distance among the members of each cluster.

    Parameters
    ----------
    df_clusters : pd.DataFrame
        First output of :func:`detect_musical_clusters`.
    df_top200 : pd.DataFrame
        Annual Top 200 dataset.
    year : int
        Year used to compute the similarities.

    Returns
    -------
    pd.DataFrame
        One row per cluster with ``n_paises``, ``similitud_media``,
        ``distancia_media`` and ``std_distancia`` (rounded to 4 decimals).
        A single-member cluster has similarity 1 and distance 0 by convention.
    """
    similarity = calculate_cosine_similarity_matrix(df_top200, year)

    rows = []
    for cluster_id, group in df_clusters.groupby("cluster_id"):
        members = [r for r in group["region"].unique() if r in similarity.index]
        if len(members) < 2:
            rows.append(
                {
                    "cluster_id": cluster_id,
                    "n_paises": len(members),
                    "similitud_media": 1.0,
                    "distancia_media": 0.0,
                    "std_distancia": 0.0,
                }
            )
            continue

        pair_similarity = _upper_triangle(similarity.loc[members, members].to_numpy())
        pair_distance = 1.0 - pair_similarity
        rows.append(
            {
                "cluster_id": cluster_id,
                "n_paises": len(members),
                "similitud_media": round(float(np.mean(pair_similarity)), 4),
                "distancia_media": round(float(np.mean(pair_distance)), 4),
                "std_distancia": round(float(np.std(pair_distance)), 4),
            }
        )
    return pd.DataFrame(rows).sort_values("cluster_id").reset_index(drop=True)


# ---- Sensitivity of the partition -------------------------------------------

def _adjusted_rand_index(labels_a: pd.Series, labels_b: pd.Series) -> float:
    """
    Adjusted Rand Index between two partitions of the same elements.

    Parameters
    ----------
    labels_a, labels_b : pd.Series
        Cluster label of each region; ``labels_b`` defines the common index.

    Returns
    -------
    float
        1 for identical partitions, about 0 for chance-level agreement.
    """
    table = pd.crosstab(labels_a.loc[labels_b.index].to_numpy(), labels_b.to_numpy()).to_numpy()

    def pairs(x):
        """Number of unordered pairs that can be formed from each count in ``x``."""
        return x * (x - 1) / 2

    sum_cells = pairs(table).sum()
    sum_rows = pairs(table.sum(axis=1)).sum()
    sum_cols = pairs(table.sum(axis=0)).sum()
    expected = sum_rows * sum_cols / pairs(table.sum())
    maximum = (sum_rows + sum_cols) / 2

    if maximum == expected:
        return 1.0
    return float((sum_cells - expected) / (maximum - expected))


def _members(labels: pd.Series) -> dict:
    """Map each cluster label to the set of regions it contains."""
    return {k: set(v) for k, v in labels.groupby(labels).groups.items()}


def _best_match_jaccard(reference: pd.Series, alternative: pd.Series) -> dict[str, float]:
    """
    For every reference cluster, the highest Jaccard index with any alternative cluster.

    Returns
    -------
    dict
        ``{"J_<cluster_id>": value}`` rounded to 3 decimals.
    """
    alternative_groups = _members(alternative)
    return {
        f"J_{cluster_id}": round(
            max(len(a & b) / len(a | b) for b in alternative_groups.values()), 3
        )
        for cluster_id, a in _members(reference).items()
    }


def _partition_sizes(labels: pd.Series) -> str:
    """Cluster sizes in descending order as a string such as ``'29/16/8'``."""
    return "/".join(str(s) for s in sorted(labels.value_counts().tolist(), reverse=True))


def cluster_sensitivity(
    df_top200: pd.DataFrame,
    year: int = 2021,
    percentiles: Sequence[float] = (80, 85, 90, 95),
    reference_percentile: float = 90,
    linkages: Sequence[str] = ("average", "complete"),
) -> pd.DataFrame:
    """
    Compare the reference partition with alternative constructions and methods.

    The reference is Greedy Modularity on the MST + ``reference_percentile``
    graph. It is compared with (a) the same construction at other percentiles
    and (b) hierarchical clustering on the cosine distance, cut into the same
    number of groups as the reference.

    Parameters
    ----------
    df_top200 : pd.DataFrame
        Annual Top 200 dataset.
    year : int, default 2021
        Target year.
    percentiles : sequence of float
        Percentiles to evaluate for the graph construction.
    reference_percentile : float, default 90
        Percentile that defines the reference partition.
    linkages : sequence of str
        Linkage methods for the hierarchical baselines.

    Returns
    -------
    pd.DataFrame
        One row per method with ``metodo``, ``n_aristas`` (graph edges),
        ``n_grupos``, ``tamanos``, ``ARI_vs_ref`` (agreement with the
        reference), ``Q_grafo_ref`` (modularity measured on the reference
        graph) and one ``J_Cluster_k`` column per reference cluster (best
        Jaccard match of that cluster).
    """
    distance = _cosine_distance_matrix(df_top200, year)

    partitions: dict[float, tuple[pd.Series, nx.Graph]] = {}

    def partition(percentile):
        """Cluster labels and graph for one percentile, computed once and cached."""
        if percentile not in partitions:
            graph = _cluster_graph(distance, percentile, include_mst=True)
            table = _communities_table(graph, year, percentile)
            partitions[percentile] = (table.set_index("region")["cluster_id"], graph)
        return partitions[percentile]

    reference, reference_graph = partition(reference_percentile)

    def summary(method, n_edges, labels):
        """One output row: size, agreement and modularity of a partition vs the reference."""
        communities = [set(m) for m in _members(labels).values()]
        row = {
            "metodo": method,
            "n_aristas": n_edges,
            "n_grupos": labels.nunique(),
            "tamanos": _partition_sizes(labels),
            "ARI_vs_ref": round(_adjusted_rand_index(reference, labels), 3),
            "Q_grafo_ref": round(
                float(modularity(reference_graph, communities, weight="weight")), 3
            ),
        }
        row.update(_best_match_jaccard(reference, labels))
        return row

    rows = []
    for p in percentiles:
        labels, graph = partition(p)
        suffix = " (referencia)" if p == reference_percentile else ""
        rows.append(
            summary(f"Greedy modularity, percentil {p}{suffix}", graph.number_of_edges(), labels)
        )

    n_reference = reference.nunique()
    condensed = squareform(distance.to_numpy(), checks=False)
    for method in linkages:
        tree = linkage(condensed, method=method)
        labels = pd.Series(
            fcluster(tree, t=n_reference, criterion="maxclust"), index=distance.index
        ).astype(str)
        rows.append(summary(f"Jerárquico ({method}), k={n_reference}", np.nan, labels))

    return pd.DataFrame(rows)
