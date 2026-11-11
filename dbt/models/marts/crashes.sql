with crashes as (
    select * from {{ ref('stg_crashes') }}
),

coverage as (
    select max(accident_date) as latest_date from crashes
)

select
    c.accident_no as accident_no,
    c.accident_date as accident_date,
    extract(year from c.accident_date) as accident_year,
    extract(month from c.accident_date) as accident_month,
    extract(hour from c.accident_time) as accident_hour,
    c.day_of_week as day_of_week,
    c.day_of_week in ('Saturday', 'Sunday') as is_weekend,
    extract(year from c.accident_date) < extract(year from coverage.latest_date) as is_complete_year,

    c.severity as severity,
    c.severity = 'Fatal accident' as is_fatal,
    c.accident_type as accident_type,
    c.dca_code as dca_code,
    c.dca_code_description as dca_description,
    c.light_condition as light_condition,
    c.police_attended as police_attended,
    c.ran_off_road as ran_off_road,

    c.road_name as road_name,
    c.road_type as road_type,
    c.road_geometry as road_geometry,
    c.rma as road_class,
    c.divided as road_divided,
    c.speed_zone as speed_zone,
    c.speed_limit_kmh as speed_limit_kmh,

    c.lga_name as lga_name,
    c.dtp_region as region,
    c.deg_urban_name as urban_area_type,
    c.stat_div_name as metro_or_country,
    c.latitude as latitude,
    c.longitude as longitude,

    c.total_persons as persons_involved,
    c.fatality as persons_killed,
    c.seriousinjury as persons_seriously_injured,
    c.otherinjury as persons_other_injured,
    c.noninjured as persons_uninjured,
    c.pedestrian as pedestrians,
    c.bicyclist as bicyclists,
    c.motorcyclist as motorcyclists,
    c.driver as drivers,
    c.passenger as passengers,
    c.old_ped_65_and_over as pedestrians_65_plus,
    c.old_driver_75_and_over as drivers_75_plus,
    c.young_driver_18_25 as drivers_18_to_25,
    c.no_of_vehicles as vehicles_involved,
    c.heavyvehicle as heavy_vehicles,
    c.motorcycle as motorcycles,
    c.pt_vehicle as public_transport_vehicles
from crashes as c
cross join coverage
