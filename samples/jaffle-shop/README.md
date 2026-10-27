# jaffle-shop (sample data — dùng để test/demo)

Nguồn: [dbt-labs/jaffle-shop](https://github.com/dbt-labs/jaffle-shop) — dbt project mẫu chính chủ dbt Labs, dùng công khai cho mục đích học tập/demo. Đã copy `models/`, `macros/`, `dbt_project.yml` vào đây ngày 2026-08-05 (bỏ phần dbt Cloud/CI không cần thiết).

## Quyết định thay cho "đối tác thật"

PRD ban đầu để ngỏ việc chờ xác nhận đối tác thật. Team đã quyết định (2026-08-05): **dùng project mã nguồn mở này làm dữ liệu test chính thức**, không chờ đối tác nữa. Đã cập nhật lại PRD.md mục 8.

## Vì sao chọn project này

13 model SQL thật (7 marts + 6 staging) — vừa khớp mục tiêu "10-15 pipeline" trong Project Charter. Có đủ độ đa dạng transform cần cho demo: CTE, JOIN, aggregation (`stg_orders`→`orders`→`customers`), macro tuỳ biến (`cents_to_dollars`).

## ⚠️ Lưu ý kỹ thuật quan trọng cho Công (parser_service)

Các file `.sql` ở đây **không phải SQL thuần** — chúng là dbt Jinja template, dùng `{{ ref('stg_customers') }}` và `{{ source('ecom', 'raw_customers') }}` thay vì tên bảng thật. Ví dụ trong `models/staging/stg_customers.sql`:

```sql
select * from {{ source('ecom', 'raw_customers') }}
```

`sqlglot` parse thẳng file này **sẽ lỗi** vì `{{ }}` không phải cú pháp SQL hợp lệ. Trước khi đưa vào `parser_service.parse_file()`, cần 1 bước tiền xử lý đơn giản: thay `{{ ref('x') }}` → `x` và `{{ source('a', 'b') }}` → `a.b` bằng regex (không cần dbt compile đầy đủ, project này không dùng macro Jinja phức tạp ngoài `ref`/`source`/`cents_to_dollars`). Danh sách bảng nguồn thật đã khai báo sẵn trong `models/staging/__sources.yml`.

Đây cũng là ví dụ thật cho nhánh "LLM fallback" nếu muốn test case parser không tự xử lý được — không cần bịa case giả nữa.

> Lưu ý vị trí: thư mục này nằm ở `samples/` (root), không phải `data/` — vì `data/` bị `.gitignore` chặn (dành cho runtime artifact như sqlite db/chroma), còn đây là mã nguồn tĩnh cần commit vào git.

## Cấu trúc

```
models/staging/   — đọc trực tiếp từ source (raw_customers, raw_orders, ...)
models/marts/     — join/aggregate từ các staging model qua ref()
macros/           — cents_to_dollars, generate_schema_name
```

## Không copy

`seeds/` (dữ liệu CSV mẫu) — không cần vì agent chỉ đọc code, không đọc dữ liệu (đúng nguyên tắc kiến trúc trong PRD.md mục 4).
