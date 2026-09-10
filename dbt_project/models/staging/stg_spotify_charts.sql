with source as (

    select * from {{ source('raw', 'spotify_charts') }}

),

renamed as (

    select
        title       as titulo,
        rank        as posicion,
        artist      as artista,
        url         as url,
        region      as region,
        chart       as tipo_chart,
        trend       as tendencia,
        streams     as reproducciones,
        date        as fecha

    from source

)

select * from renamed