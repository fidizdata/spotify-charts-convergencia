import pandas as pd

def load_and_process_spotify(filepath="../data/raw/spotify_charts.csv", excluded_countries=None):
    """
    Loads, cleans, filters, and structures the historical Spotify Charts dataset.
    
    Parameters:
    -----------
    filepath : str
        Path to the original raw CSV file.
    excluded_countries : list, optional
        List of regions or countries with incomplete data detected in previous audits.
        
    Returns:
    --------
    pd.DataFrame
        Processed and filtered DataFrame with the annual Top 200 per region, ready for analysis.
    """
    if excluded_countries is None:
        excluded_countries = ["Bulgaria", "Luxembourg", "Nicaragua"]

    print("[1/6] Loading the original CSV file...")
    df = pd.read_csv(filepath)
    
    print("[2/6] Filtering charts (discarding 'Viral 50' and keeping only 'Top 200')...")
    df_clean = df[df['chart'] == 'top200'].copy()
    
    print("[3/6] Normalizing data types, dates, and creating unique track identifier...")
    df_clean['date'] = pd.to_datetime(df_clean['date'], errors='coerce')
    df_clean['year'] = df_clean['date'].dt.year
    
    string_columns = ['title', 'artist', 'url', 'region', 'chart', 'trend']
    for col in string_columns:
        if col in df_clean.columns:
            df_clean[col] = df_clean[col].astype(str)
            
    df_clean['rank'] = pd.to_numeric(df_clean['rank'], errors='coerce').astype('Int64')
    df_clean['streams'] = pd.to_numeric(df_clean['streams'], errors='coerce')
    
    df_clean['track_id'] = (
        df_clean['title'].str.lower().str.strip() + "_" + df_clean['artist'].str.lower().str.strip()
    )
    
    print("[4/6] Filtering countries with constant presence across the entire time series...")
    total_years = df_clean['year'].nunique()
    country_years = df_clean.groupby('region')['year'].nunique()
    constant_countries = country_years[country_years == total_years].index.tolist()
    
    df_clean = df_clean[df_clean['region'].isin(constant_countries)]
    df_clean = df_clean[df_clean['region'] != 'Global'].copy()
    
    print("[5/6] Aggregating annual metrics by region and selecting Top 200...")
    df_annual = (
        df_clean.groupby(["year", "region", "track_id"])
        .agg(
            total_streams=("streams", "sum"),
            best_rank=("rank", "min"),
            appearances=("rank", "count"),
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
    
    print("[6/6] Removing regions with incomplete data and validating final integrity...")
    if excluded_countries:
        df_top200_annual = df_top200_annual[
            ~df_top200_annual["region"].isin(excluded_countries)
        ].copy()
        
    counts = df_top200_annual.groupby(["year", "region"]).size()
    all_complete = (counts == 200).all()
    
    print(f" -> Do all countries/years have exactly 200 tracks?: {all_complete}")
    print(f" -> Total final clean records: {len(df_top200_annual)}")
    
    return df_top200_annual