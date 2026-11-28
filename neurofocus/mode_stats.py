"""Read-only aggregates using the same activity boundaries as the learning archive."""
def mode_totals(db,first,last):
    # An activity matches history.activities: successive blocks of the same subject
    # within the same local day/session, including microbreaks between those blocks.
    return list(db.execute("""WITH spans AS (
        SELECT sid,day,block,tag,ms,lag(tag) OVER (PARTITION BY sid,day ORDER BY block,tag) prev
        FROM focus_spans WHERE day BETWEEN ? AND ?),
        sessions_in_range AS (SELECT sid,sum(ms) ms,sum(tag IS NOT prev) activities FROM spans GROUP BY sid),
        scoped AS (SELECT r.*,coalesce(json_extract(p.config,'$.id'), 'legacy') mode,
          coalesce(json_extract(p.config,'$.name'),'旧版记录') name FROM sessions_in_range r LEFT JOIN session_protocol p USING(sid))
        SELECT mode,(SELECT s.name FROM scoped s WHERE s.mode=t.mode ORDER BY sid DESC LIMIT 1),
        sum(ms),sum(activities),count(*) FROM scoped t GROUP BY mode ORDER BY sum(ms) DESC""",(str(first),str(last))))
