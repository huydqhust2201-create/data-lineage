# Monitoring — Prometheus, Grafana, Loki

Runbook cho tầng quan sát của Lineage AI: metric từ Prometheus, dashboard
Grafana, log tập trung qua Loki. Dành cho người vận hành hoặc mở rộng hệ
thống này.

## Kiến trúc

```
                     ┌──────────────────────┐
  backend:8000       │  /metrics            │  ← Prometheus text format,
  (FastAPI)          │  stdout: JSON log    │    tự viết, không thêm thư viện
                     └──────┬────────┬──────┘
                            │        │
              scrape 15s    │        │  Docker giữ stdout
                            │        │
                     ┌──────▼─────┐  │   ┌──────────────┐
                     │ Prometheus │  └──►│ Alloy        │  đọc Docker socket
                     │ TSDB 15d   │      │ parse JSON   │
                     └──────┬─────┘      └──────┬───────┘
                            │                   │ push
                            │            ┌──────▼───────┐
                            │            │ Loki 7d      │
                            │            └──────┬───────┘
                            │                   │
                     ┌──────▼───────────────────▼───────┐
                     │ Grafana — dashboard provisioned  │
                     │ từ repo, truy cập qua SSH tunnel │
                     └──────────────────────────────────┘
```

Tất cả cấu hình nằm trong `monitoring/` và được commit — dựng lại server mới
là có y hệt, không ai phải nhớ đã click gì trong UI.

## Chạy

Overlay này **không chạy một mình**. Phải kèm compose chính để cùng network,
nhờ đó Prometheus gọi được `backend:8000`:

```bash
# Production
docker compose -f docker-compose.prod.yml -f docker-compose.observability.yml up -d

# Dev
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
```

Cần `GRAFANA_ADMIN_PASSWORD` trong `.env` — compose sẽ từ chối chạy nếu thiếu,
cố ý để không ai vô tình chạy Grafana với mật khẩu `admin/admin`.

## Ngân sách RAM — đọc trước khi bật trên production

| Service | `mem_limit` |
|---|---|
| Prometheus | 256 MB |
| Loki | 256 MB |
| Alloy | 128 MB |
| Grafana | 300 MB |
| **Tổng** | **~940 MB** |

EC2 hiện tại là **`t3.small` (2 GB)** và đang chạy backend + Postgres + Caddy.
Thêm ~940 MB nữa là **không đủ** — bật lên có nguy cơ OOM-kill đúng cái app
đang muốn theo dõi, đúng kiểu thất bại đã gặp với service `embeddings` (xem
`docs/deploy_aws.md`, mục bge-m3: RSS vọt lên ~7,4 GB và bị kernel giết).

Nâng lên ≥ 4 GB trước (`t3.medium`, hoặc `m7i-flex.large` 8 GB nếu tài khoản
có trong danh sách free-tier-eligible). Quy trình đổi instance type không mất
dữ liệu: `docs/deploy_aws.md`, mục "Bật Table Description".

Cách đo trước khi quyết định:

```bash
free -m                              # RAM còn trống thật
docker stats --no-stream             # từng container đang ăn bao nhiêu
```

## Truy cập

Grafana và Prometheus chỉ bind vào `127.0.0.1` của host — **không mở ra
Internet**. Xem dashboard bằng SSH tunnel:

```bash
ssh -L 3000:localhost:3000 -L 9090:localhost:9090 ubuntu@datalineage.uk
```

Rồi mở http://localhost:3000 (Grafana) và http://localhost:9090 (Prometheus).

Lý do không expose: Grafana lộ ra ngoài là thêm một cửa đăng nhập phải canh
(CVE, mật khẩu yếu, brute-force), mà ở quy mô này không ai cần xem dashboard
ngoài người vận hành. `/metrics` cũng không lộ — `Caddyfile` chỉ proxy `/api/*`
và `/health`, nên metric nội bộ không ra Internet dù backend có expose.

## Metric đang có

Sinh trong [`src/metrics.py`](../src/metrics.py), thu tại middleware trong
[`src/main.py`](../src/main.py).

| Metric | Loại | Label |
|---|---|---|
| `http_requests_total` | counter | `method`, `path`, `status` |
| `http_request_duration_seconds` | histogram | `method`, `path` (+ `le`) |
| `llm_calls_total` | counter | `kind` (`extraction` / `chat`) |

### Ba quyết định đáng giải thích

**1. Histogram thật, không chỉ `_sum`.**
Bản đầu chỉ có `http_request_duration_ms_sum`. Với một counter tổng, nhiều
nhất bạn tính được **trung bình** — mà trung bình chính là thứ che mất vấn
đề: 99 request 10 ms + 1 request 10 s cho trung bình 110 ms, nhìn như khoẻ.
Có bucket thì `histogram_quantile()` chỉ ra được p95/p99, tức là đúng cái
đuôi chậm mà người dùng thật đang chịu.

Bucket (giây): `0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30`
— bộ mặc định quen thuộc của Prometheus, nới thêm đuôi 30 s vì endpoint chat
gọi LLM nên chậm hơn CRUD thường rất nhiều.

**2. Đơn vị giây, không phải millisecond.**
Quy ước Prometheus là base unit, và mọi ví dụ PromQL/Grafana sẵn có đều giả
định giây. Đổi được không mất gì vì tới giờ **chưa có Prometheus nào từng
scrape** metric này, nên không có series lịch sử phải migrate.

**3. Label `path` là route template, không phải URL thật.**
`/api/v1/assets/{asset_id}` chứ không phải `/api/v1/assets/7`. Nếu dùng URL
thật thì mỗi ID sinh một time series riêng — vài nghìn asset thành vài nghìn
series cho đúng một endpoint, và Prometheus phình RAM theo số series. Request
không khớp route nào (404, bot quét URL ngẫu nhiên) gom hết vào `unmatched`,
để người ngoài không bơm được series mới vào Prometheus chỉ bằng cách gọi URL
lạ.

Access log thì vẫn ghi URL thật — debug cần biết chính xác ID nào lỗi.

### PromQL dùng trong dashboard

```promql
# Request/giây theo route
sum by (path) (rate(http_requests_total{path!="/metrics"}[$__rate_interval]))

# Tỉ lệ lỗi 5xx (%)
100 * sum(rate(http_requests_total{status=~"5.."}[$__rate_interval]))
    / sum(rate(http_requests_total[$__rate_interval]))

# p95 toàn hệ thống
histogram_quantile(0.95,
  sum by (le) (rate(http_request_duration_seconds_bucket{path!="/metrics"}[$__rate_interval])))

# p95 theo route — tìm nút cổ chai
histogram_quantile(0.95,
  sum by (le, path) (rate(http_request_duration_seconds_bucket{path!="/metrics"}[$__rate_interval])))

# LLM call/phút (mỗi call là tiền thật trên OpenRouter)
60 * sum by (kind) (rate(llm_calls_total[$__rate_interval]))
```

Panel "Tỉ lệ lỗi 5xx" hiển thị **No data** khi không có traffic (phép chia
0/0) chứ không phải 0%. Cố ý — để không nhầm "im lặng" với "khoẻ".

## Log

Backend ghi JSON một dòng mỗi log ra stdout
([`src/logging_config.py`](../src/logging_config.py)). Alloy đọc qua Docker
socket, parse JSON, đẩy sang Loki.

### Bug đã sửa khi dựng tầng này

Bản trước dùng format string `'...,"msg":%(message)r'`. `%r` là `repr()` của
Python nên chuỗi ra **dấu nháy đơn**:

```
{"ts":"...","level":"INFO","logger":"access","msg":'{"status": 200}'}
```

Dòng này **không phải JSON hợp lệ** — `json.loads()` ném lỗi ngay. Tức là
tầng log "có cấu trúc" đó chưa từng parse được, dù docstring ghi là để ingest
vào Loki/CloudWatch. Đã thay bằng `JsonFormatter` tự build dict rồi
`json.dumps()`, và có test khẳng định `json.loads()` chạy được
([`tests/test_observability.py`](../tests/test_observability.py)).

Thêm vào đó, field giờ truyền qua `extra=` nên nằm ở **JSON cấp 1**:

```json
{"ts":"2026-10-19T09:49:32.521+00:00","level":"INFO","logger":"access",
 "msg":"http_request","method":"GET","path":"/api/v1/assets/7",
 "route":"/api/v1/assets/{asset_id}","status":200,"duration_ms":12.5}
```

Nhờ vậy query được `| json | status >= 500` thay vì phải parse chuỗi lồng
trong chuỗi.

### Label trong Loki

Alloy promote đúng **hai** field thành label: `level` và `route`, cộng
`platform` và `service` từ metadata Docker.

`status` và `logger` cố ý **không** promote. Label trong Loki là chiều index,
mỗi tổ hợp label là một stream riêng — thêm bừa thì nổ cardinality đúng như
bên Prometheus. Hai field đó vẫn query được qua `| json`, chỉ là không được
index sẵn. `loki-config.yml` còn đặt `max_streams_per_user: 1000` làm chốt
an toàn: nếu ai đó promote nhầm một label cardinality cao, Loki bị ép dừng
thay vì ăn hết RAM.

### Query hay dùng

```logql
# Request lỗi server
{platform="docker", service="backend"} | json | status >= 500

# Request chậm hơn 1 giây
{platform="docker", service="backend"} | json | duration_ms > 1000

# Mọi log ERROR, mọi container
{platform="docker", level=~"ERROR|CRITICAL"}

# Một route cụ thể
{platform="docker", route="/api/v1/chat"}
```

### Vì sao Alloy mà không phải Promtail

Grafana đã công bố deprecate Promtail, EOL tháng 3/2026. Viết mới bằng
Promtail bây giờ là viết vào thứ đã hết hạn hỗ trợ. Alloy là bản thay thế
chính thức.

Alloy mount Docker socket `:ro` và chạy `user: root` — socket thuộc group
`docker` của host mà user `alloy` trong image không thuộc group đó. Ở quy mô
một server thì đây là cách gọn nhất; muốn chặt hơn thì truyền `group_add`
đúng GID group `docker` trên host (GID khác nhau giữa các AMI).

Lưu ý: Docker socket là quyền tương đương root trên host. Chỉ chạy Alloy
trên server mình kiểm soát.

## Đã kiểm chứng tới đâu

Thành thật về mức độ chắc chắn, vì chưa deploy:

**Đã chạy và pass thật:**
- 18 test trong `tests/test_observability.py` — bucket luỹ tiến, ngữ nghĩa
  `le`, `+Inf` bằng `_count`, định dạng nhãn `le="1"` (không phải `1.0`),
  escape label, `json.loads()` trên log thật, field `extra` lên cấp 1,
  tiếng Việt không thành `\uXXXX`.
- `ruff check src/ tests/` — sạch.
- Mọi YAML/JSON parse được; mọi bind mount trỏ tới file tồn tại; uid
  datasource khớp giữa provisioning và dashboard; panel id duy nhất; layout
  không vượt 24 cột.
- Mọi tên metric và label trong PromQL của dashboard được đối chiếu với
  output thật của `render_prometheus_text()` — khớp 100%.
- Bốn tag image đều tồn tại trên Docker Hub (`prom/prometheus:v3.4.1`,
  `grafana/grafana:11.6.1`, `grafana/loki:3.5.0`, `grafana/alloy:v1.8.1`).
- **Cấu hình đã qua chính parser của từng công cụ** — dùng binary Windows
  chính thức, không cần Docker, không deploy gì, không tốn phí hạ tầng:

  | Lệnh | Kết quả |
  |---|---|
  | `promtool check config monitoring/prometheus/prometheus.yml` | `SUCCESS: ... is valid prometheus config file syntax` |
  | `loki -verify-config -config.file=monitoring/loki/loki-config.yml` | exit 0, không cảnh báo |
  | `alloy fmt monitoring/alloy/config.alloy` | output **trùng từng byte** với file trong repo |
  | `alloy run monitoring/alloy/config.alloy` | decode xong toàn bộ; `loki.write`, `loki.process`, `discovery.relabel` build thành công |

  `alloy run` có báo lỗi ở `discovery.docker` và `loki.source.docker`:
  `building component: error setting up docker client: protocol not available`
  — vì Windows không có `unix:///var/run/docker.sock`, không phải lỗi config.
  Cách đọc này đã được kiểm chứng bằng một đối chứng ngược: đổi
  `refresh_interval` thành tên không tồn tại thì Alloy báo lỗi ở tầng
  **decode** (`unrecognized attribute name`), khác tầng **build**. Config
  thật không có lỗi decode nào, nghĩa là mọi tên component và mọi thuộc tính
  đều hợp lệ.

**Chưa kiểm chứng** (cần chạy container thật mới biết):
- Grafana nạp dashboard JSON (schemaVersion 39) có cần migrate gì không —
  mục duy nhất còn lại thuộc về file trong repo.
- Alloy có thật sự đọc được Docker socket với `user: root` trên AMI của EC2
  (GID của group `docker` khác nhau giữa các AMI).
- Số RAM thật từng container tiêu thụ so với `mem_limit` đã đặt.

Khi deploy, chạy theo thứ tự này để lỗi lộ ra sớm:

```bash
# 1. Cú pháp compose sau khi merge 2 file
docker compose -f docker-compose.prod.yml -f docker-compose.observability.yml config

# 2. Từng service một, xem log trước khi lên tiếp
docker compose ... up -d prometheus && docker compose ... logs prometheus
docker compose ... up -d loki       && docker compose ... logs loki
docker compose ... up -d alloy      && docker compose ... logs alloy
docker compose ... up -d grafana    && docker compose ... logs grafana

# 3. Prometheus có scrape được backend chưa (state phải là "up")
curl -s localhost:9090/api/v1/targets | python3 -m json.tool | grep -A2 health

# 4. Loki đã nhận log chưa
curl -s "localhost:3100/loki/api/v1/labels"

# 5. RAM thật
docker stats --no-stream
```

## Việc nên làm tiếp

- **Alert.** Hiện chỉ có dashboard — ai không mở dashboard thì không biết có
  sự cố. Thêm `alerting rules` cho 5xx tăng vọt, p95 vượt ngưỡng, và
  `up == 0`. Cần một kênh nhận (email/Slack/Telegram).
- **Histogram cho LLM.** `llm_calls_total` chỉ đếm số lần, chưa có độ trễ và
  chưa có token/chi phí. Thêm `llm_call_duration_seconds` và
  `llm_tokens_total` cần sửa `llm_extraction_service` + `chat_service`.
- **Metric nghiệp vụ.** Số bảng/cột đã ingest, số breaking change phát hiện,
  tỉ lệ review bị reject — những con số nói về sản phẩm, không chỉ về hạ tầng.
- **`/metrics` khi chạy nhiều worker.** Hiện Uvicorn một process nên counter
  trong RAM là đủ. Nếu scale lên nhiều worker, mỗi process giữ counter riêng
  và scrape sẽ lấy được đúng một process — lúc đó mới cần
  `prometheus-client` ở multiprocess mode.
- **Node exporter.** Hiện chỉ có metric tầng ứng dụng, chưa có CPU/RAM/đĩa
  của host — mà RAM chính là thứ hay giết dự án này.
