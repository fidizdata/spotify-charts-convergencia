{{ config(
    materialized='table',
    indexes=[
        {'columns': ['region','year']}
    ]
) }}


select 
    date,
    date_part('year', date) as year,
    title,
    rank,
    artist,
    url,
    region,
    chart,
    trend,
    streams 
from {{ref('stg_spotify_charts')}}
where chart ='top200'

