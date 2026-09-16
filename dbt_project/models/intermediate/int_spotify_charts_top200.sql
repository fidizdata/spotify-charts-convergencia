{{ config(materialized='table') }}
WITH 
table_stg as (

    select 
    * 
    from {{ref('stg_spotify_charts')}}
),
top as (

    Select 
    * 
    from table_stg
    where chart ='top200'

)
select * from top
