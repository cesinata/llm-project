-- A crash is fatal if and only if at least one person was killed.
select accident_no, severity, persons_killed
from {{ ref('crashes') }}
where is_fatal <> (persons_killed > 0)
