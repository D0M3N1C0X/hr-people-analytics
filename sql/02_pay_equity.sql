-- Pay equity reporting items, EU Pay Transparency Directive (2023/970).
-- Population: active employees only, as in a statutory snapshot.

-- name: headline_gap
-- ? Mean and median gender pay gap, the two Article 9 headline numbers.
WITH ranked AS (
    SELECT gender,
           base_salary_eur,
           ROW_NUMBER() OVER (PARTITION BY gender ORDER BY base_salary_eur) AS rn,
           COUNT(*)     OVER (PARTITION BY gender)                          AS n
    FROM v_active_employees
),
medians AS (
    SELECT gender, AVG(base_salary_eur) AS median_salary
    FROM ranked
    WHERE rn IN ((n + 1) / 2, (n + 2) / 2)      -- works for odd and even n
    GROUP BY gender
),
means AS (
    SELECT gender, AVG(base_salary_eur) AS mean_salary, COUNT(*) AS employees
    FROM v_active_employees GROUP BY gender
)
SELECT ROUND(MAX(CASE WHEN m.gender = 'F' THEN m.mean_salary END), 0)       AS mean_women,
       ROUND(MAX(CASE WHEN m.gender = 'M' THEN m.mean_salary END), 0)       AS mean_men,
       ROUND(100.0 * (MAX(CASE WHEN m.gender = 'M' THEN m.mean_salary END)
                    - MAX(CASE WHEN m.gender = 'F' THEN m.mean_salary END))
             / MAX(CASE WHEN m.gender = 'M' THEN m.mean_salary END), 1)     AS mean_gap_pct,
       ROUND(100.0 * (MAX(CASE WHEN d.gender = 'M' THEN d.median_salary END)
                    - MAX(CASE WHEN d.gender = 'F' THEN d.median_salary END))
             / MAX(CASE WHEN d.gender = 'M' THEN d.median_salary END), 1)   AS median_gap_pct
FROM means m JOIN medians d ON d.gender = m.gender;

-- name: pay_quartiles
-- ? Share of each gender in each pay quartile - Article 9(1)(f).
WITH banded AS (
    SELECT gender,
           NTILE(4) OVER (ORDER BY base_salary_eur) AS quartile
    FROM v_active_employees
)
SELECT CASE quartile WHEN 1 THEN 'Q1 (lowest)' WHEN 4 THEN 'Q4 (highest)'
                     ELSE 'Q' || quartile END                              AS pay_quartile,
       SUM(CASE WHEN gender = 'F' THEN 1 ELSE 0 END)                       AS women,
       SUM(CASE WHEN gender = 'M' THEN 1 ELSE 0 END)                       AS men,
       ROUND(100.0 * SUM(CASE WHEN gender = 'F' THEN 1 ELSE 0 END)
             / COUNT(*), 1)                                                AS pct_women
FROM banded
GROUP BY quartile
ORDER BY quartile;

-- name: categories_over_article_10_threshold
-- ? Which categories of workers show a gap of 5%+ and would need a joint pay assessment?
WITH category AS (
    SELECT department,
           job_level,
           COUNT(*)                                                        AS employees,
           SUM(CASE WHEN gender = 'F' THEN 1 ELSE 0 END)                   AS women,
           AVG(CASE WHEN gender = 'F' THEN base_salary_eur END)            AS avg_women,
           AVG(CASE WHEN gender = 'M' THEN base_salary_eur END)            AS avg_men
    FROM v_active_employees
    GROUP BY department, job_level
    HAVING COUNT(*) >= 30
       AND SUM(CASE WHEN gender = 'F' THEN 1 ELSE 0 END) >= 8
       AND SUM(CASE WHEN gender = 'M' THEN 1 ELSE 0 END) >= 8
)
SELECT department || ' - ' || job_level                                    AS worker_category,
       employees,
       ROUND(100.0 * women / employees, 0)                                 AS pct_women,
       ROUND(avg_women, 0)                                                 AS avg_women,
       ROUND(avg_men, 0)                                                   AS avg_men,
       ROUND(100.0 * (avg_men - avg_women) / avg_men, 1)                   AS gap_pct,
       CASE WHEN 100.0 * (avg_men - avg_women) / avg_men >= 5
            THEN 'JOINT PAY ASSESSMENT' ELSE 'within tolerance' END        AS article_10_status
FROM category
ORDER BY gap_pct DESC;

-- name: gap_by_level
-- ? Is the gap coming from pay for the same job, or from who holds which job?
SELECT job_level,
       COUNT(*)                                                            AS employees,
       ROUND(100.0 * SUM(CASE WHEN gender = 'F' THEN 1 ELSE 0 END)
             / COUNT(*), 1)                                                AS pct_women,
       ROUND(100.0 * (AVG(CASE WHEN gender = 'M' THEN base_salary_eur END)
                    - AVG(CASE WHEN gender = 'F' THEN base_salary_eur END))
             / AVG(CASE WHEN gender = 'M' THEN base_salary_eur END), 1)    AS gap_within_level_pct
FROM v_active_employees
GROUP BY job_level
ORDER BY job_level;
