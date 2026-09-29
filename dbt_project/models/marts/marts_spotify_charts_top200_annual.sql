{{ config(materialized='table') }}

with top200_processed as (

    select
        year,
        title,
        artist,
        region,
        streams
    from {{ ref('int_spotify_charts_top200_processed') }}

),

aggregation as (

    select
        year,
        region,
        artist,
        title,
        sum(streams) as total_streams
    from top200_processed
    group by
        year,
        region,
        artist,
        title

),

ranked as (

    select
        *,
        row_number() over (
            partition by year, region
            order by total_streams desc
        ) as ranking
    from aggregation

)

select
    year,
    region,
    artist,
    title,
    total_streams
from ranked
where ranking <= 200