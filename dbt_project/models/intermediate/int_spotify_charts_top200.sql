{{ config(
    materialized='table',
    indexes=[
        {'columns': ['region','year']}
    ]
) }}


select 
    date,
    date_part('year', date) as year,
    lower(trim(title)) || '_' || lower(trim(artist)) as track_id,
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

