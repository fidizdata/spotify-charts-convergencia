{{ config(materialized='view') }}

with 
top200_processed as (

    select
    year,
    title,
    rank,
    artist,
    url,
    region,
    chart,
    trend,
    streams
    from
    {{ref('int_spotify_charts_top200_processed')}}

),
agregation as (
    select
    year,
    region,
    artist,
    title,
    SUM(streams) total_streams
    from top200_processed
    group by year, region, title, artist
)
select * from agregation