with lowered as (
  select
    activity_nr,
    lower(estab_name) as trade_nm,
    lower(estab_name) as legal_name,
    lower(site_address) as street_addr_1_txt,
    lower(site_city) as cty_nm,
    lower(site_state) as st_cd,
    naics_code as naic_cd
  from
    inspection
)
select
  *
from
  lowered
