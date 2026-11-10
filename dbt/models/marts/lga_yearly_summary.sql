select
    lga_name,
    accident_year,
    is_complete_year,
    count(*) as crashes,
    sum(case when is_fatal then 1 else 0 end) as fatal_crashes,
    sum(case when severity = 'Serious injury accident' then 1 else 0 end) as serious_injury_crashes,
    sum(persons_killed) as persons_killed,
    sum(persons_seriously_injured) as persons_seriously_injured,
    sum(pedestrians) as pedestrians_involved,
    sum(bicyclists) as bicyclists_involved,
    sum(motorcyclists) as motorcyclists_involved
from {{ ref('crashes') }}
where lga_name is not null
group by lga_name, accident_year, is_complete_year
