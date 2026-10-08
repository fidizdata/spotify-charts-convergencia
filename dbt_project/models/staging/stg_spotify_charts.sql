with source as (

    select * from {{ source('raw', 'spotify_charts') }}

),

renamed as (

    select
        title,
        rank,
        artist,      
        url,         
        region,      
        chart,     
        trend,      
        streams,     
        date        

    from source

)

select * from renamed