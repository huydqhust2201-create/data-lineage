# Deploy lên AWS (EC2 + Docker Compose)

Runbook đầy đủ để đưa DATA-04 Lineage AI lên 1 EC2 instance chạy Docker Compose.
Đọc kỹ 2 cảnh báo dưới đây **trước khi** làm theo — cả hai đều là giới hạn thật
của code hiện tại, không phải lỗi khi deploy.

## ⚠️ Đọc trước

1. **Auth hiện tại chỉ dựa vào header `X-User-Id` do client tự khai báo**
   (`src/api/deps.py::current_user`), không có mật khẩu/token nào xác thực. Bất
   kỳ ai gọi API với `X-User-Id: <id bất kỳ>` đều mạo danh được user đó. Runbook
   này giảm rủi ro bằng cách giới hạn Security Group (chỉ IP tin cậy được vào
   cổng SSH; cổng 80/443 vẫn phải mở công khai để phục vụ web/API bình thường)
   — nhưng **không thay thế cho auth thật**. Trước khi cho người dùng thật ngoài
   team dùng, cần thêm xác thực (JWT/OAuth/session) — đây là việc riêng, ngoài
   phạm vi deploy.
2. **Tài khoản AWS tạo sau 15/7/2025 không có Free Tier 12 tháng kiểu cũ.** Chỉ
   có 200 USD credit dùng trong 6 tháng. Kiến trúc ở đây (EC2 `t3.small`) ước
   tính ~18-20 USD/tháng — nằm gọn trong credit trong 6 tháng đầu, nhưng **sẽ bị
   tính phí thật** sau khi hết credit/hết hạn nếu không tắt instance. Bước 1.2
   dưới đây thiết lập cảnh báo chi tiêu qua email — đừng bỏ qua.
3. **Tài khoản mới còn có thể ở "AWS Free Plan"** — một rào chắn cứng hơn 200
   USD credit: chặn hẳn `ModifyInstanceAttribute` (đổi instance type) và
   `RunInstances` cho bất kỳ type nào KHÔNG nằm trong danh sách
   free-tier-eligible của tài khoản, kể cả khi bạn còn dư credit (lỗi
   `FreeTierRestrictionError` / `InvalidParameterCombination`). Kiểm tra danh
   sách type được phép trước khi định cỡ EC2:
   ```bash
   aws ec2 describe-instance-types --filters "Name=free-tier-eligible,Values=true" \
     --query 'InstanceTypes[].{Type:InstanceType,MemMiB:MemoryInfo.SizeInMiB}' --output table
   ```
   Danh sách này có thể gồm cả vài type "flex" khá mạnh (RAM 4-8GB) chứ không
   chỉ `t*.micro/small` — xem mục "Bật Table Description" bên dưới, đã tận
   dụng việc này để không cần nâng cấp lên Paid Plan. Nếu type bạn cần
   (`t3.medium`, `t3.large`, ...) không có trong danh sách, phải nâng cấp tài
   khoản qua Console (Billing and Cost Management → Upgrade to Paid Plan) —
   không có API/CLI nào làm việc này thay bạn được.

---

## Phase 1 — Chuẩn bị tài khoản AWS

Yêu cầu: đã cài [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
và chạy `aws configure` với access key của **IAM user** (không dùng root).

### 1.1 Bật MFA cho root + tạo IAM user riêng

Làm qua AWS Console (không có CLI cho bước bật MFA root):
1. Console → tên tài khoản (góc phải trên) → **Security credentials** → bật MFA cho root.
2. IAM → Users → Create user → tên `deploy-admin` → gắn policy `AdministratorAccess`
   (đủ dùng cho scope đồ án; production thật nên thu hẹp quyền hơn) → tạo access key loại
   "Command Line Interface (CLI)" → lưu lại `Access key ID` / `Secret access key`.
3. `aws configure` → nhập access key vừa tạo, region gợi ý `ap-southeast-1` (Singapore, gần VN nhất) hoặc `us-east-1` (rẻ nhất).

### 1.2 Tạo Budget cảnh báo chi tiêu (QUAN TRỌNG)

```bash
aws budgets create-budget --account-id $(aws sts get-caller-identity --query Account --output text) \
  --budget '{
    "BudgetName": "lineage-ai-monthly",
    "BudgetLimit": {"Amount": "25", "Unit": "USD"},
    "TimeUnit": "MONTHLY",
    "BudgetType": "COST"
  }' \
  --notifications-with-subscribers '[
    {
      "Notification": {"NotificationType":"ACTUAL","ComparisonOperator":"GREATER_THAN","Threshold":50},
      "Subscribers": [{"SubscriptionType":"EMAIL","Address":"YOUR_EMAIL@example.com"}]
    },
    {
      "Notification": {"NotificationType":"ACTUAL","ComparisonOperator":"GREATER_THAN","Threshold":100},
      "Subscribers": [{"SubscriptionType":"EMAIL","Address":"YOUR_EMAIL@example.com"}]
    }
  ]'
```

Thay `YOUR_EMAIL@example.com` bằng email thật. Ngưỡng 50%/100% của 25 USD/tháng
(~12.5 USD, 25 USD) — cảnh báo sớm nếu có gì bất thường (vd quên tắt instance).

### 1.3 Tạo key pair để SSH

```bash
aws ec2 create-key-pair --key-name lineage-ai-key \
  --query 'KeyMaterial' --output text > lineage-ai-key.pem
chmod 400 lineage-ai-key.pem   # macOS/Linux; trên Windows: icacls thay tương đương
```

**Giữ file `.pem` này an toàn, không commit vào git.**

### 1.4 Tạo Security Group

```bash
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
MY_IP=$(curl -s https://checkip.amazonaws.com)/32

SG_ID=$(aws ec2 create-security-group --group-name lineage-ai-sg \
  --description "Lineage AI production" --vpc-id "$VPC_ID" \
  --query 'GroupId' --output text)

# SSH chỉ từ IP của bạn
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
  --protocol tcp --port 22 --cidr "$MY_IP"

# HTTP/HTTPS công khai (web + API qua Caddy)
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
  --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
  --protocol tcp --port 443 --cidr 0.0.0.0/0

echo "SG_ID=$SG_ID"   # lưu lại dùng ở Phase 2
```

Cổng 8000 (backend), 5435 (Postgres) **không** mở ra ngoài — chỉ Caddy (80/443) lộ diện.

---

## Phase 2 — Tạo EC2 instance

```bash
AMI_ID=$(aws ec2 describe-images --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
            "Name=state,Values=available" \
  --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)

cat > user-data.sh <<'EOF'
#!/bin/bash
apt-get update -y
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
usermod -aG docker ubuntu
EOF

INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type t3.small \
  --key-name lineage-ai-key \
  --security-group-ids "$SG_ID" \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":20,"VolumeType":"gp3"}}]' \
  --user-data file://user-data.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=lineage-ai-prod}]' \
  --query 'Instances[0].InstanceId' --output text)

aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

ALLOC_ID=$(aws ec2 allocate-address --domain vpc --query 'AllocationId' --output text)
aws ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID"

PUBLIC_IP=$(aws ec2 describe-addresses --allocation-ids "$ALLOC_ID" \
  --query 'Addresses[0].PublicIp' --output text)
echo "PUBLIC_IP=$PUBLIC_IP"   # dùng ở các bước sau
```

Đợi ~1-2 phút để user-data cài xong Docker trước khi SSH vào.

---

## Phase 3 — Deploy lần đầu

### 3.1 SSH vào instance và lấy code

```bash
ssh -i lineage-ai-key.pem ubuntu@$PUBLIC_IP

# Trên EC2:
sudo apt-get install -y git
git clone https://github.com/AI20K-Build-Phase-Cohort-3/P-116.git lineage-ai
cd lineage-ai
```

### 3.2 Cấu hình `.env`

```bash
cp .env.production.example .env
nano .env
# - Điền OPENROUTER_API_KEY (key thật)
# - Đổi POSTGRES_PASSWORD sang mật khẩu mạnh
# - CORS_ORIGINS=http://<PUBLIC_IP>   (thay bằng IP thật ở trên)
```

### 3.3 Build frontend

Cách đơn giản nhất là build trên máy dev rồi copy `frontend/dist` lên (tránh cài
Node trên EC2 chỉ để build 1 lần):

```bash
# Trên máy dev (không phải EC2):
cd frontend && npm ci && npm run build
scp -i lineage-ai-key.pem -r dist ubuntu@$PUBLIC_IP:~/lineage-ai/frontend/dist
```

Hoặc build thẳng trên EC2 nếu muốn (`sudo apt-get install -y nodejs npm` rồi
`cd frontend && npm ci && npm run build`).

### 3.4 Chạy

```bash
# Trên EC2, trong thư mục lineage-ai:
docker compose -f docker-compose.prod.yml config   # lint trước, phát hiện lỗi env sớm
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps        # cả 3 container phải healthy/running
```

### 3.5 Verify

```bash
curl -sf http://$PUBLIC_IP/health
# {"status":"ok","env":"production"}
```

Mở `http://<PUBLIC_IP>` trên trình duyệt, kiểm tra frontend load được. Thử
ingest 1 file mẫu trong `samples/jaffle-shop` và hỏi impact analysis 1 cột để
xác nhận pipeline chạy đúng end-to-end.

### 3.6 Seed user demo (một lần)

```bash
docker compose -f docker-compose.prod.yml exec backend python -m scripts.seed_auth
```

(Chạy bằng `-m scripts.seed_auth` chứ không phải `python scripts/seed_auth.py` trực tiếp —
cách sau khiến Python không thấy được package `src` vì `sys.path[0]` trỏ vào
`scripts/` thay vì `/app`, lỗi `ModuleNotFoundError: No module named 'src'`.)

---

## Phase 4 — CI/CD tự động deploy (`.github/workflows/cd.yml`)

Đã thêm, có **approval gate**: `cd.yml` chạy sau khi workflow `CI` (lint+test)
pass trên `main`, nhưng job `deploy` gắn với GitHub Environment `production` —
nếu environment đó có "Required reviewers", job dừng lại chờ người duyệt
trước khi thực sự SSH vào server và chạy
`git pull && docker compose -f docker-compose.prod.yml up -d --build`.

**Bước thủ công cần làm 1 lần trên GitHub** (đây là quyết định "ai được duyệt
deploy production" — không tự động hoá được, cần người có quyền admin repo):
1. Repo → **Settings → Environments → New environment** → đặt tên đúng
   **`production`** (phải khớp `environment: production` trong `cd.yml`).
2. Tick **Required reviewers** → thêm người/nhóm được phép duyệt deploy.
3. Save.

Secrets `EC2_SSH_KEY` (private key **riêng cho CD**, không phải key admin cá
nhân — xem cách tạo ở mục "Tạo key deploy riêng" bên dưới) và `EC2_HOST`
(`datalineage.uk`) đã được set qua GitHub API. Muốn set lại/xoay vòng key:
Settings → Secrets and variables → Actions.

### Tạo key deploy riêng (nếu cần xoay vòng)

```bash
ssh-keygen -t ed25519 -f ./deploy-key -N "" -C "github-actions-cd@lineage-ai"
# Thêm public key vào EC2 (KHÔNG xoá key admin hiện có trong authorized_keys):
ssh -i ~/.ssh/lineage-ai-key.pem ubuntu@$PUBLIC_IP "echo '$(cat ./deploy-key.pub)' >> ~/.ssh/authorized_keys"
# Set secret EC2_SSH_KEY = nội dung file ./deploy-key (private key) qua
# Settings → Secrets and variables → Actions → EC2_SSH_KEY.
```

### Kiểm tra hoạt động

Sau khi merge 1 PR vào `main`: tab **Actions** trên GitHub → workflow `CI`
chạy xong pass → workflow `CD (Deploy to Production)` tự kích hoạt → job
`deploy` hiện trạng thái **Waiting** (nếu có required reviewers) → người được
chỉ định vào Actions → Approve → job chạy SSH deploy thật + verify
`curl https://datalineage.uk/health`.

---

## Phase 5 — Thêm domain + HTTPS sau này

1. Mua/trỏ domain: tạo A record trỏ về `$PUBLIC_IP` (Elastic IP không đổi kể cả
   khi restart instance, chỉ mất nếu bạn release nó).
2. Trên EC2: sửa `Caddyfile`, thay khối `:80` bằng khối domain đã comment sẵn ở
   cuối file (đổi `yourdomain.com` thành domain thật).
3. Cập nhật `.env`: `CORS_ORIGINS=https://yourdomain.com`.
4. `docker compose -f docker-compose.prod.yml up -d --build proxy backend`.

Caddy tự xin và gia hạn chứng chỉ Let's Encrypt — không cần thao tác Certbot thủ công.

---

## Phase 6 — Vận hành

**Backup DB (thủ công, định kỳ)**:
```bash
aws ec2 create-snapshot --volume-id $(aws ec2 describe-volumes \
  --filters "Name=attachment.instance-id,Values=$INSTANCE_ID" \
  --query 'Volumes[0].VolumeId' --output text) \
  --description "lineage-ai backup $(date +%F)"
```

**Xem log**: `docker compose -f docker-compose.prod.yml logs -f backend`

**Restart 1 service**: `docker compose -f docker-compose.prod.yml restart backend`

**Deploy bản code mới** (thủ công, chưa có CI/CD):
```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

**Dừng hẳn để không tốn phí** (vd cuối kỳ đồ án):
```bash
aws ec2 stop-instances --instance-ids $INSTANCE_ID   # vẫn tốn phí EBS+EIP (nhỏ)
# hoặc xoá hẳn:
aws ec2 terminate-instances --instance-ids $INSTANCE_ID
aws ec2 release-address --allocation-id $ALLOC_ID
```

**Không commit**: file `.pem`, `.env` thật (đã có trong `.gitignore`).

---

## Bật Table Description / Semantic Search (bge-m3 qua TEI)

`docker-compose.prod.yml` đã có sẵn service `embeddings` (TEI, image
`cpu-latest`, `--model-id BAAI/bge-m3` — tự tải model từ HuggingFace vào
volume `tei_data` lúc container khởi động lần đầu, không cần
predownload/scp model thủ công như bản dev). Đã deploy và verify thật
(2026-08-24) — 2 điều cần biết trước khi làm lại từ đầu:

- **Dùng đúng image `cpu-latest`, KHÔNG dùng `cpu-1.5`**: `cpu-1.5` có bug ở
  crate `hf-hub` 0.3.2, tải model bị lỗi `request error: builder error:
  relative URL without a base` và crash-loop vĩnh viễn.
- **`--max-batch-tokens` mặc định (16384) làm OOM-kill** khi ONNX runtime
  warmup trên CPU (đã tái hiện: RSS vọt lên ~7.4GB, kernel OOM-killer giết
  process — xem `dmesg | grep -i 'killed process'` nếu nghi ngờ). Compose đã
  set sẵn `--max-batch-tokens 2048 --max-client-batch-size 8`, đủ cho text mô
  tả bảng/cột (input dài hơn tự bị truncate, không lỗi).

Các bước:

1. **Đổi EC2 sang instance lớn hơn trước** (tối thiểu ~4GB RAM — instance hiện
   tại `t3.small`/2GB không đủ chạy thêm bge-m3, sẽ OOM). Kiểm tra danh sách
   free-tier-eligible của tài khoản trước (xem cảnh báo #3 đầu file) — có thể
   có sẵn type RAM lớn (vd `m7i-flex.large` 8GB) mà không cần nâng Paid Plan:
   ```bash
   aws ec2 stop-instances --instance-ids $INSTANCE_ID
   aws ec2 wait instance-stopped --instance-ids $INSTANCE_ID
   aws ec2 modify-instance-attribute --instance-id $INSTANCE_ID --instance-type m7i-flex.large
   aws ec2 start-instances --instance-ids $INSTANCE_ID
   ```
   Downtime vài phút, dữ liệu EBS (Postgres, data/) giữ nguyên. Elastic IP tự
   gắn lại vào instance sau khi start. Nếu type free-tier-eligible không đủ
   RAM cho nhu cầu của bạn, phải nâng cấp Paid Plan trước rồi mới dùng
   `t3.medium`/`t3.large`.
2. Cập nhật `AWS Budget` (`lineage-ai-monthly`) lên mức phù hợp với instance
   mới (`aws budgets update-budget`).
3. Trong `.env` trên EC2: `DESCRIPTION_ENABLED=true`.
4. `docker compose -f docker-compose.prod.yml up -d` — lần đầu chạy sẽ mất
   thêm khoảng 1 phút để container `embeddings` tải model bge-m3 (~2.1GB) từ
   HuggingFace; theo dõi bằng `docker compose -f docker-compose.prod.yml logs -f embeddings`,
   chờ tới dòng log `Ready`.

Không cần sửa code — chỉ cấu hình + hạ tầng.
