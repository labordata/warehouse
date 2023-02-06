with lowered as (
  select
    case_id,
    lower(trade_nm) as trade_nm,
    lower(legal_name) as legal_name,
    lower(street_addr_1_txt) as street_addr_1_txt,
    lower(cty_nm) as cty_nm,
    lower(st_cd) as st_cd,
    naic_cd
  from
    cases
)
select
  *
from
  lowered;
