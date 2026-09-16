WITH 
table_stg as (

    select 
    * 
    from {{ref('stg_spotify_charts')}}
),
viral as (

    Select 
    * 
    from table_stg
    where chart ='viral50'

)
select * from viral
