with top200 as (

    select
        date,
        year,
        track_id,
        title,
        rank,
        artist,
        url,
        region,
        chart,
        trend,
        streams
    from {{ ref('int_spotify_charts_top200') }}

),

total_anios as (

    select count(distinct year) as total
    from top200

),

paises_distintos_anio as (

    select distinct
        year,
        region
    from top200

),

cantidad_paises_anio as (

    select
        region,
        count(1) as cantidad
    from paises_distintos_anio
    group by region

),

menos_200 as (

    select region
    from (
        select distinct
            year,
            region,
            artist,
            title
        from top200
    ) p
    group by year, region
    having count(*) < 200

)

select
    t.date,
    t.year,
    t.track_id,
    t.title,
    t.rank,
    t.artist,
    t.url,
    t.region,
    t.chart,
    t.trend,
    t.streams
from top200 t
inner join cantidad_paises_anio c
    on c.region = t.region
cross join total_anios ta
where c.cantidad = ta.total
  and t.region not in (select region from menos_200)