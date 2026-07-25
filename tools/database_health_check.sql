-- ============================================================
-- CarHunter Enterprise Database Health Check
-- Version : 2.9-dev
-- Purpose : Validate database integrity after pipeline changes
-- ============================================================

.headers on
.mode column

.print ""
.print "=============================================="
.print " CarHunter Database Health Check"
.print "=============================================="
.print ""

---------------------------------------------------------------
-- Total cars
---------------------------------------------------------------

.print "Total vehicles"

SELECT COUNT(*) AS total_cars
FROM cars;

---------------------------------------------------------------
-- NULL score validation
---------------------------------------------------------------

.print ""
.print "NULL score validation"

SELECT
    SUM(CASE WHEN car_score IS NULL THEN 1 ELSE 0 END)       AS car_score_null,
    SUM(CASE WHEN value_score IS NULL THEN 1 ELSE 0 END)     AS value_score_null,
    SUM(CASE WHEN premium_score IS NULL THEN 1 ELSE 0 END)   AS premium_score_null,
    SUM(CASE WHEN options_score IS NULL THEN 1 ELSE 0 END)   AS options_score_null,
    SUM(CASE WHEN personal_score IS NULL THEN 1 ELSE 0 END)  AS personal_score_null,
    SUM(CASE WHEN deal_score IS NULL THEN 1 ELSE 0 END)      AS deal_score_null,
    SUM(CASE WHEN final_score IS NULL THEN 1 ELSE 0 END)     AS final_score_null
FROM cars;

---------------------------------------------------------------
-- Watchlist
---------------------------------------------------------------

.print ""
.print "Watchlist statistics"

SELECT
    COUNT(*) AS watchlist_matches
FROM cars
WHERE watchlist_match = 1;

SELECT
    COUNT(*) AS personal_scores
FROM cars
WHERE personal_score > 0;

---------------------------------------------------------------
-- Recommendations
---------------------------------------------------------------

.print ""
.print "Recommendations"

SELECT
    COUNT(*) AS recommendations
FROM cars
WHERE recommendation IS NOT NULL
AND recommendation <> '';

---------------------------------------------------------------
-- Options
---------------------------------------------------------------

.print ""
.print "Options"

SELECT
    COUNT(*) AS missing_options
FROM cars
WHERE options_found IS NULL
   OR TRIM(options_found) = '';

SELECT
    COUNT(*) AS options_checked
FROM cars
WHERE options_checked = 1;

---------------------------------------------------------------
-- Descriptions
---------------------------------------------------------------

.print ""
.print "Descriptions"

SELECT
    COUNT(*) AS descriptions_available
FROM cars
WHERE description IS NOT NULL
AND TRIM(description) <> '';

SELECT
    COUNT(*) AS descriptions_missing
FROM cars
WHERE description IS NULL
OR TRIM(description) = '';

---------------------------------------------------------------
-- Deal score distribution
---------------------------------------------------------------

.print ""
.print "Deal score"

SELECT
    MIN(deal_score) AS min_deal,
    AVG(deal_score) AS avg_deal,
    MAX(deal_score) AS max_deal
FROM cars;

---------------------------------------------------------------
-- Final score distribution
---------------------------------------------------------------

.print ""
.print "Final score"

SELECT
    MIN(final_score) AS min_final,
    AVG(final_score) AS avg_final,
    MAX(final_score) AS max_final
FROM cars;

---------------------------------------------------------------
-- Top 10 cars
---------------------------------------------------------------

.print ""
.print "Top 10 vehicles"

SELECT
    id,
    title,
    price,
    year,
    km,
    final_score,
    deal_score,
    personal_score,
    recommendation
FROM cars
ORDER BY final_score DESC
LIMIT 10;

---------------------------------------------------------------
-- Price sanity
---------------------------------------------------------------

.print ""
.print "Invalid prices"

SELECT COUNT(*) AS invalid_prices
FROM cars
WHERE price <= 0;

---------------------------------------------------------------
-- Year sanity
---------------------------------------------------------------

.print ""
.print "Invalid years"

SELECT COUNT(*) AS invalid_years
FROM cars
WHERE year < 1990
   OR year > strftime('%Y','now') + 1;

---------------------------------------------------------------
-- Duplicate AutoScout IDs
---------------------------------------------------------------

.print ""
.print "Duplicate AutoScout IDs"

SELECT
    autoscout_id,
    COUNT(*) AS duplicates
FROM cars
GROUP BY autoscout_id
HAVING COUNT(*) > 1;

---------------------------------------------------------------
-- Finished
---------------------------------------------------------------

.print ""
.print "=============================================="
.print " Database Health Check Finished"
.print "=============================================="
