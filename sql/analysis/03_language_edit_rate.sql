-- Of the model's first drafts that were reviewed, the share approved with edits, by language.
create or replace table language_edit_rate as
select
    language,
    count(*) as reviewed,
    avg((first_decision = 'approved_with_edits')::int) as edit_rate
from fct_tickets
where first_drafted_by = 'model' and first_decision is not null
group by language
order by language;
