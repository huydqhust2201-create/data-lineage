WITH actor_revenue AS (
    SELECT 
        a.actor_id,
        a.first_name || ' ' || a.last_name AS actor_fullname,
        f.film_id,
        f.title AS film_title,
        COALESCE(SUM(p.amount), 0) AS total_film_revenue
    FROM {{ ref('actor') }} a
    JOIN {{ ref('film_actor') }} fa ON a.actor_id = fa.actor_id
    JOIN {{ ref('film') }} f ON fa.film_id = f.film_id
    JOIN {{ ref('inventory') }} i ON f.film_id = i.film_id
    JOIN {{ ref('rental') }} r ON i.inventory_id = r.inventory_id
    JOIN {{ ref('payment') }} p ON r.rental_id = p.rental_id
    GROUP BY a.actor_id, a.first_name, a.last_name, f.film_id, f.title
),
actor_rankings AS (
    SELECT 
        ar.actor_id,
        ar.actor_fullname,
        ar.film_title,
        ar.total_film_revenue,
        DENSE_RANK() OVER (
            PARTITION BY ar.actor_id 
            ORDER BY ar.total_film_revenue DESC
        ) AS film_revenue_rank
    FROM actor_revenue ar
),
top_actor_films AS (
    SELECT 
        ark.actor_fullname,
        ark.film_title,
        ark.total_film_revenue
    FROM actor_rankings ark
    WHERE ark.film_revenue_rank <= 2
),
store_customer_demographics AS (
    SELECT 
        c.customer_id,
        c.first_name || ' ' || c.last_name AS customer_fullname,
        ct.city,
        co.country,
        c.store_id
    FROM {{ ref('customer') }} c
    JOIN {{ ref('address') }} ad ON c.address_id = ad.address_id
    JOIN {{ ref('city') }} ct ON ad.city_id = ct.city_id
    JOIN {{ ref('country') }} co ON ct.country_id = co.country_id
),
customer_rental_summary AS (
    SELECT 
        scd.customer_fullname,
        scd.city,
        scd.country,
        scd.store_id,
        f.title AS film_title,
        COUNT(r.rental_id) AS rental_count
    FROM store_customer_demographics scd
    JOIN {{ ref('rental') }} r ON scd.customer_id = r.customer_id
    JOIN {{ ref('inventory') }} i ON r.inventory_id = i.inventory_id
    JOIN {{ ref('film') }} f ON i.film_id = f.film_id
    GROUP BY scd.customer_fullname, scd.city, scd.country, scd.store_id, f.title
)
SELECT 
    taf.actor_fullname,
    crs.customer_fullname,
    crs.city,
    crs.country,
    crs.store_id,
    taf.film_title,
    taf.total_film_revenue,
    crs.rental_count
FROM top_actor_films taf
JOIN customer_rental_summary crs ON taf.film_title = crs.film_title
ORDER BY taf.total_film_revenue DESC, crs.rental_count DESC;
