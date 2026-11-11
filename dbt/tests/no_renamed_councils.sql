-- Councils that were renamed must appear under their current name only.
select lga_name, count(*) as crashes
from {{ ref('crashes') }}
where lga_name in ('MORELAND')
group by lga_name
