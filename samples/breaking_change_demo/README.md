# breaking_change_demo — ingest có chủ đích, hai lượt

Thư mục này **không** phải dữ liệu mẫu và **không** được đặt dưới
`samples/hospital/`. Lý do giống `samples/_fixtures/`: file DDL nằm trong đường
ingest mặc định sẽ đổ dữ liệu giả vào đồ thị thật mỗi lần chạy.

## Cách dùng

```
1. ingest samples/hospital            → graph có department_revenue + downstream
2. ingest samples/breaking_change_demo → alert xuất hiện
```

Đảo thứ tự hoặc bỏ bước 1 thì **không có alert nào** — phát hiện drop cần graph
của lần ingest trước (`lineage_nodes.py`, `nx.descendants(working, event.table)`).

## Biết trước: ingest lại sẽ NHÂN alert

`record_breaking_change_alert` không dedupe (`storage_service.py`, `INSERT`
thuần, không `ON CONFLICT`). Mỗi lần chạy lại bước 2 là thêm một alert trùng.

Đây là hành vi **đã biết**, thuộc họ D-3 mà con người đã chốt bỏ khỏi phạm vi.
Đừng nghiệm thu bằng con số alert tuyệt đối.
