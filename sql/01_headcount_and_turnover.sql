-- Headcount, turnover and exit patterns.
-- Dialect: SQLite. Every query is standalone and read-only.

-- name: monthly_headcount
-- ? How did active headcount and exits move month by month over the window?
WITH RECURSIVE months(month_start) AS (
    SELECT '2025-07-01'
    UNION ALL
    SELECT date(month_start, '+1 month') FROM months WHERE month_start < '2026-06-01'
),
snapshot AS (
    SELECT m.month_start,
           SUM(CASE WHEN e.hire_date <= date(m.month_start, '+1 month', '-1 day')
                     AND (e.exit_date IS NULL
                          OR e.exit_date > date(m.month_start, '+1 month', '-1 day'))
                    THEN 1 ELSE 0 END)                                    AS headcount,
           SUM(CASE WHEN strftime('%Y-%m', e.exit_date) = strftime('%Y-%m', m.month_start)
                     AND e.exit_type = 'Voluntary' THEN 1 ELSE 0 END)     AS voluntary_exits
    FROM months m CROSS JOIN employees e
    GROUP BY m.month_start
)
SELECT strftime('%Y-%m', month_start)                                     AS month,
       headcount,
       voluntary_exits,
       headcount - LAG(headcount) OVER (ORDER BY month_start)             AS net_change,
       ROUND(AVG(headcount) OVER (ORDER BY month_start
                                  ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 0)
                                                                          AS headcount_3m_avg
FROM snapshot
ORDER BY month_start;

-- name: turnover_by_department
-- ? Which departments lose the most people, and how do they rank?
WITH stats AS (
    SELECT department,
           COUNT(*)                                                       AS employees,
           SUM(CASE WHEN exit_type = 'Voluntary' THEN 1 ELSE 0 END)       AS voluntary_exits,
           SUM(CASE WHEN exit_date IS NOT NULL THEN 1 ELSE 0 END)         AS all_exits
    FROM employees
    GROUP BY department
)
SELECT department,
       employees,
       voluntary_exits,
       ROUND(100.0 * voluntary_exits / employees, 1)                      AS voluntary_pct,
       ROUND(100.0 * all_exits / employees, 1)                            AS total_pct,
       RANK() OVER (ORDER BY 1.0 * voluntary_exits / employees DESC)      AS risk_rank,
       ROUND(100.0 * voluntary_exits
             / SUM(voluntary_exits) OVER (), 1)                           AS share_of_all_exits
FROM stats
ORDER BY risk_rank;

-- name: exit_risk_by_pay_position
-- ? Does position in the salary band track with leaving?
SELECT CASE WHEN compa_ratio < 0.92 THEN '1. below band (<0.92)'
            WHEN compa_ratio < 1.00 THEN '2. lower half (0.92-1.00)'
            WHEN compa_ratio < 1.08 THEN '3. upper half (1.00-1.08)'
            ELSE                        '4. top of band (1.08+)' END      AS pay_position,
       COUNT(*)                                                           AS employees,
       SUM(CASE WHEN exit_type = 'Voluntary' THEN 1 ELSE 0 END)           AS voluntary_exits,
       ROUND(100.0 * SUM(CASE WHEN exit_type = 'Voluntary' THEN 1 ELSE 0 END)
             / COUNT(*), 1)                                               AS voluntary_pct,
       ROUND(AVG(engagement_score), 1)                                    AS avg_engagement
FROM employees
GROUP BY pay_position
ORDER BY pay_position;

-- name: exit_reasons
-- ? What do leavers say, and how concentrated are the reasons?
SELECT exit_reason,
       COUNT(*)                                                           AS leavers,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)                 AS pct_of_exits,
       ROUND(100.0 * SUM(COUNT(*)) OVER (ORDER BY COUNT(*) DESC
                                         ROWS UNBOUNDED PRECEDING)
             / SUM(COUNT(*)) OVER (), 1)                                  AS cumulative_pct
FROM employees
WHERE exit_type = 'Voluntary'
GROUP BY exit_reason
ORDER BY leavers DESC;
