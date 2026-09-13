import pathlib
import pandas as pd

def generar_dataset_anual():
    # Definir rutas relativas
    base_path = pathlib.Path(__file__).parent.resolve().parent
    raw_path = base_path / "data" / "raw" / "spotify_charts.csv"
    processed_path = base_path / "data" / "processed" / "df_top200_annual.csv"

    if not raw_path.exists():
        raw_path = pathlib.Path("data/raw/spotify_charts.csv")
        processed_path = pathlib.Path("data/processed/df_top200_annual.csv")

    if not raw_path.exists():
        print(f"Error crítico: No se encontró el archivo crudo en {raw_path}")
        return

    print("Leyendo archivo crudo de Spotify (esto puede demorar)...")
    df = pd.read_csv(raw_path)
    
    df_clean = df[df['chart'] == 'top200'].copy()
    df_clean['date'] = pd.to_datetime(df_clean['date'], errors='coerce')
    df_clean['year'] = df_clean['date'].dt.year
    df_clean['rank'] = pd.to_numeric(df_clean['rank'], errors='coerce').astype('Int64')
    df_clean['streams'] = pd.to_numeric(df_clean['streams'], errors='coerce')

    total_anios = df_clean['year'].nunique()
    paises_anios = df_clean.groupby('region')['year'].nunique()
    paises_constantes = paises_anios[paises_anios == total_anios].index.tolist()
    
    df_clean = df_clean[df_clean['region'].isin(paises_constantes)]
    df_clean = df_clean[df_clean['region'] != 'Global'].copy()

    df_annual = (
        df_clean.groupby(["year", "region", "url"])
        .agg(
            total_streams=("streams", "sum"),
            title=("title", "first"),
            artist=("artist", "first"),
        )
        .reset_index()
    )

    df_top200_annual = (
        df_annual.sort_values(by=["year", "region", "total_streams"], ascending=[True, True, False])
        .groupby(["year", "region"])
        .head(200)
        .reset_index(drop=True)
    )

    df_top200_annual = df_top200_annual[
        ~df_top200_annual["region"].isin(["Bulgaria", "Luxembourg", "Nicaragua"])
    ].copy()

    # Crear carpeta processed si no existe y exportar
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    df_top200_annual.to_csv(processed_path, index=False)
    print(f"¡Éxito! Dataset multi-año guardado en: {processed_path}")

if __name__ == "__main__":
    generar_dataset_anual()