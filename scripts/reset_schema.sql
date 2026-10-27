-- Xoá sạch để dựng lại theo schema mới. KHÔNG hoàn tác được.
-- Giữ lại bảng users để user id và localStorage của trình duyệt vẫn ổn định.
DROP TABLE IF EXISTS lineage_column_descriptions CASCADE;
DROP TABLE IF EXISTS lineage_node_descriptions   CASCADE;
DROP TABLE IF EXISTS lineage_node_events         CASCADE;
DROP TABLE IF EXISTS lineage_nodes               CASCADE;
DROP TABLE IF EXISTS lineage_edges               CASCADE;
DROP TABLE IF EXISTS breaking_change_alerts      CASCADE;
DROP TABLE IF EXISTS ingest_runs                 CASCADE;
DROP TABLE IF EXISTS database_members            CASCADE;
DROP TABLE IF EXISTS databases                   CASCADE;
DROP TABLE IF EXISTS workspaces                  CASCADE;
