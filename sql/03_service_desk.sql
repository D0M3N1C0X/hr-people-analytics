-- HR service-desk operations: volume, SLA, quality, and the link back to attrition.

-- name: monthly_volume_and_sla
-- ? Does SLA attainment fall when volume rises?
WITH monthly AS (
    SELECT strftime('%Y-%m', created_date)                                 AS month,
           COUNT(*)                                                        AS cases,
           ROUND(100.0 * AVG(sla_met), 1)                                  AS sla_pct,
           ROUND(AVG(resolution_hours), 1)                                 AS avg_hours
    FROM hr_cases
    GROUP BY month
)
SELECT month,
       cases,
       sla_pct,
       avg_hours,
       ROUND(AVG(cases) OVER (ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 0)
                                                                           AS cases_3m_avg,
       ROUND(100.0 * cases / AVG(cases) OVER () - 100, 1)                  AS vs_avg_pct
FROM monthly
ORDER BY month;

-- name: category_pareto
-- ? How concentrated is the volume, and where is SLA weakest?
SELECT category,
       COUNT(*)                                                            AS cases,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)                  AS pct_of_volume,
       ROUND(100.0 * SUM(COUNT(*)) OVER (ORDER BY COUNT(*) DESC
                                         ROWS UNBOUNDED PRECEDING)
             / SUM(COUNT(*)) OVER (), 1)                                   AS cumulative_pct,
       ROUND(100.0 * AVG(sla_met), 1)                                      AS sla_pct,
       ROUND(AVG(csat), 2)                                                 AS avg_csat
FROM hr_cases
GROUP BY category
ORDER BY cases DESC;

-- name: quality_drivers
-- ? What does a missed SLA or a reopened case do to satisfaction?
SELECT CASE WHEN sla_met = 0 AND reopened = 1 THEN 'missed SLA and reopened'
            WHEN sla_met = 0                  THEN 'missed SLA'
            WHEN reopened = 1                 THEN 'reopened'
            ELSE                                   'clean resolution' END  AS case_experience,
       COUNT(*)                                                            AS cases,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)                  AS pct_of_cases,
       ROUND(AVG(csat), 2)                                                 AS avg_csat,
       ROUND(AVG(resolution_hours), 1)                                     AS avg_hours
FROM hr_cases
GROUP BY case_experience
ORDER BY avg_csat DESC;

-- name: agent_ramp_up
-- ? Do new agents resolve differently from experienced ones?
SELECT CASE WHEN agent_tenure_months < 6  THEN '1. under 6 months'
            WHEN agent_tenure_months < 24 THEN '2. 6-23 months'
            ELSE                               '3. 2 years +' END          AS agent_experience,
       COUNT(DISTINCT agent_id)                                            AS agents,
       COUNT(*)                                                            AS cases,
       ROUND(100.0 * AVG(first_contact_resolution), 1)                     AS fcr_pct,
       ROUND(100.0 * AVG(sla_met), 1)                                      AS sla_pct,
       ROUND(AVG(csat), 2)                                                 AS avg_csat
FROM hr_cases
GROUP BY agent_experience
ORDER BY agent_experience;

-- name: service_experience_and_attrition
-- ? The cross-dataset question: do people whose cases get reopened leave more often?
WITH case_history AS (
    SELECT employee_id,
           COUNT(*)                                                        AS cases,
           SUM(reopened)                                                   AS reopened_cases,
           SUM(CASE WHEN sla_met = 0 THEN 1 ELSE 0 END)                    AS breached_cases
    FROM hr_cases
    WHERE created_date < '2025-10-01'          -- feature window only, no look-ahead
    GROUP BY employee_id
)
SELECT CASE WHEN COALESCE(h.reopened_cases, 0) = 0 THEN 'no reopened case'
            WHEN h.reopened_cases = 1             THEN '1 reopened case'
            ELSE                                       '2+ reopened cases' END
                                                                           AS service_experience,
       COUNT(*)                                                            AS employees,
       SUM(CASE WHEN e.exit_type = 'Voluntary' AND e.exit_date >= '2025-10-01'
                THEN 1 ELSE 0 END)                                         AS exits_next_9_months,
       ROUND(100.0 * SUM(CASE WHEN e.exit_type = 'Voluntary' AND e.exit_date >= '2025-10-01'
                              THEN 1 ELSE 0 END) / COUNT(*), 1)            AS exit_pct,
       ROUND(AVG(e.engagement_score), 1)                                   AS avg_engagement
FROM employees e
LEFT JOIN case_history h ON h.employee_id = e.employee_id
WHERE e.hire_date < '2025-10-01'
  AND (e.exit_date IS NULL OR e.exit_date >= '2025-10-01')
GROUP BY service_experience
ORDER BY exit_pct;
