# Fixture — KHÔNG nằm trong đường ingest mẫu

Thư mục này chứa file SQL dựng riêng để thử một tính năng, **không** phải dữ liệu
mẫu của dự án. Nó **không** được đặt dưới `samples/hospital/` hay `samples/jaffle-shop/`.

## Vì sao tách ra

`asset_lifecycle_test.sql` trước nằm ở `samples/hospital/ddl/`, nên **mỗi lần
ingest hospital** nó lại đổ bảng giả (`asset_lifecycle_*`) vào đồ thị thật.

Hậu quả đo được: cột `total_revenue` xuất hiện ở **hai** bảng —
`department_revenue` (thật) và `asset_lifecycle_revenue_report` (fixture) — nên
`resolve_table("total_revenue")` trả `ambiguous`, và case eval
`03_assess_total_revenue` **không thể đạt** dù agent chọn đúng tool.

Nó cũng là nguồn của các alert mồ côi: `record_breaking_change_alert` không
dedupe, nên mỗi lần ingest lại nhân thêm một bản sao.

## Dùng khi nào

Ingest **có chủ đích**, trỏ thẳng vào thư mục này, khi muốn thử vòng đời
rename/drop. Đừng để nó lọt vào lần ingest dữ liệu mẫu.
