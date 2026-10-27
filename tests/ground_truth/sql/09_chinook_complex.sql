WITH customer_spending AS (
    SELECT 
        c.customer_id,
        c.support_rep_id,
        c.first_name || ' ' || c.last_name AS customer_fullname,
        SUM(i.total) AS total_customer_spent
    FROM customer c
    JOIN invoice i ON c.customer_id = i.customer_id
    GROUP BY c.customer_id, c.support_rep_id, c.first_name, c.last_name
),
rep_top_customers AS (
    SELECT 
        cs.customer_id,
        cs.support_rep_id,
        cs.customer_fullname,
        cs.total_customer_spent,
        ROW_NUMBER() OVER (
            PARTITION BY cs.support_rep_id 
            ORDER BY cs.total_customer_spent DESC
        ) AS rank_in_rep
    FROM customer_spending cs
),
target_vip_customers AS (
    SELECT 
        rtc.customer_id,
        rtc.support_rep_id,
        rtc.customer_fullname
    FROM rep_top_customers rtc
    WHERE rtc.rank_in_rep <= 3
),
track_album_genre AS (
    SELECT 
        t.track_id,
        t.name AS track_name,
        al.title AS album_title,
        g.name AS genre_name
    FROM track t
    JOIN album al ON t.album_id = al.album_id
    JOIN genre g ON t.genre_id = g.genre_id
),
invoice_items AS (
    SELECT 
        il.invoice_line_id,
        i.customer_id,
        il.track_id,
        il.unit_price * il.quantity AS item_revenue
    FROM invoice_line il
    JOIN invoice i ON il.invoice_id = i.invoice_id
)
SELECT 
    e.first_name || ' ' || e.last_name AS sales_agent,
    tvc.customer_fullname,
    tag.album_title,
    tag.genre_name,
    SUM(ii.item_revenue) AS total_revenue
FROM target_vip_customers tvc
JOIN employee e ON tvc.support_rep_id = e.employee_id
JOIN invoice_items ii ON tvc.customer_id = ii.customer_id
JOIN track_album_genre tag ON ii.track_id = tag.track_id
GROUP BY e.first_name, e.last_name, tvc.customer_fullname, tag.album_title, tag.genre_name
ORDER BY sales_agent ASC, total_revenue DESC;
