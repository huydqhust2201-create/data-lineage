# Lineage AI trên Kubernetes — lab kubeadm 3 VM (2 ngày)

Hướng dẫn tự làm từ đầu tới cuối: dựng cluster Kubernetes 3 node bằng
kubeadm trên Windows, chuyển Lineage AI từ Docker Compose sang Helm, giám
sát bằng Prometheus/Grafana/Loki, cố tình gây sự cố rồi viết RUNBOOK.

**Máy chạy lab:** Windows 10/11 **Pro** (cần Hyper-V), **16 GB RAM**, CPU
4 nhân trở lên, đã bật ảo hoá trong BIOS, còn trống khoảng 80 GB đĩa.

---

## Mục lục

0. [Tổng quan và lịch 2 ngày](#0-tổng-quan-và-lịch-2-ngày)
1. [Chuẩn bị máy](#1-chuẩn-bị-máy)
2. [Mạng: vì sao cần IP tĩnh](#2-mạng-vì-sao-cần-ip-tĩnh)
3. [Tạo 3 VM](#3-tạo-3-vm)
4. [Chuẩn bị node](#4-chuẩn-bị-node)
5. [Dựng cluster](#5-dựng-cluster)
6. [Storage, MetalLB, Ingress](#6-storage-metallb-ingress)
7. [etcd snapshot và restore](#7-etcd-snapshot-và-restore)
8. [Đưa app lên: manifest thô](#8-đưa-app-lên-manifest-thô)
9. [Helm chart](#9-helm-chart)
10. [Giám sát](#10-giám-sát)
11. [Phá hệ thống và RUNBOOK](#11-phá-hệ-thống-và-runbook)
12. [Tuỳ chọn: nâng version, ArgoCD](#12-tuỳ-chọn-nâng-version-argocd)
13. [Cắt gì khi chậm](#13-cắt-gì-khi-chậm)
14. [Lỗi hay gặp](#14-lỗi-hay-gặp)
15. [Sản phẩm cuối và CV](#15-sản-phẩm-cuối-và-cv)

---

## 0. Tổng quan và lịch 2 ngày

### Kiến trúc đích

```
Windows (kubectl, helm, trình duyệt)
   │  192.168.56.1
   │
   ├── k8s-cp   192.168.56.10   control plane: apiserver, etcd, scheduler, controller-manager
   ├── k8s-w1   192.168.56.11   worker: backend, Prometheus, Loki...
   └── k8s-w2   192.168.56.12   worker: backend, Postgres...
                192.168.56.200  IP do MetalLB cấp cho ingress-nginx
                                 http://lineage.local → backend
```

So với Docker Compose: Caddy được thay bằng **ingress-nginx**, volume
`pgdata` thành **StatefulSet + PVC**, service `embeddings` **bị bỏ** (TEI +
bge-m3 cần tới ~7 GB RAM lúc warmup; production cũng đang chạy với
`DESCRIPTION_ENABLED=false`).

### Lịch

| Ngày | Sáng | Chiều | Tối |
|---|---|---|---|
| **1** | Mục 1–5: máy, mạng, VM, cluster. Trong lúc chờ VM: đẩy code để CI build image (mục 1.4) | Mục 6–8: storage, MetalLB, Ingress, etcd DR, app chạy được | Mục 9: Helm chart |
| **2** | Mục 10.1–10.3: kube-prometheus-stack, ServiceMonitor, dashboard | Mục 10.4–10.6: Loki, Alloy, alert rule | Mục 11: phá hệ thống + RUNBOOK |

Mục 12 (nâng version, ArgoCD) chỉ làm khi mọi thứ trên đã xong. Kế hoạch
gốc ước 9–10 ngày cho toàn bộ phạm vi; 2 ngày là đủ cho phần lõi nếu không
kẹt quá lâu ở một chỗ. **Mỗi bước có giới hạn thời gian; quá giới hạn thì
xem [mục 13](#13-cắt-gì-khi-chậm) và đi tiếp.**

### Những gì đã được kiểm chứng trước khi viết

Kiểm chứng trên máy phát triển (không có Hyper-V nên không chạy được VM):

- Mọi URL cài đặt và package winget đều tồn tại: Multipass, repo
  Kubernetes 1.35/1.36, Calico v3.30.3, local-path-provisioner v0.0.31,
  MetalLB v0.14.9, ingress-nginx v1.12.1 (bản bare-metal), etcd v3.5.21.
- Lệnh `sed` sửa Calico đã chạy thử trên đúng file v3.30.3, YAML vẫn hợp lệ.
- Script `node-prep.sh` qua `bash -n`.
- Ba file values cho kube-prometheus-stack 92.14.0, Loki 7.5.0 và Alloy
  1.14.3 đã render bằng `helm template` mà không lỗi. Service Loki đúng tên
  `loki`, uid datasource khớp với dashboard có sẵn trong repo.
- Config Alloy qua `alloy fmt` và `alloy run`: decode xong mọi component.

**Chưa kiểm chứng:** mọi thứ chạy trong VM. Những chỗ cần tự xác nhận được
đánh dấu ⚠️.

---

## 1. Chuẩn bị máy

*Giới hạn: 60 phút, có 1 lần khởi động lại.*

### 1.1. Bật Hyper-V

PowerShell **bằng quyền Administrator**:

```powershell
# Ảo hoá phải là True; False thì vào BIOS bật Intel VT-x / AMD-V
(Get-CimInstance Win32_Processor).VirtualizationFirmwareEnabled

Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All
```

Khởi động lại máy.

### 1.2. Cài công cụ

PowerShell thường:

```powershell
winget install -e --id Git.Git
winget install -e --id Canonical.Multipass
winget install -e --id Kubernetes.kubectl
winget install -e --id Helm.Helm
```

Đóng PowerShell, mở lại, kiểm tra:

```powershell
git --version; multipass version; kubectl version --client; helm version
```

Không cần Docker trên máy này: image sẽ được build bằng GitHub Actions.

### 1.3. Lấy code

Trên máy chạy lab:

```powershell
# Ngăn Git đổi xuống dòng .sh/.yaml sang CRLF. Script bash có CRLF sẽ lỗi
# "$'\r': command not found" khi chạy trong VM Linux.
git config --global core.autocrlf input

git clone https://github.com/huydqhust2201-create/data-lineage.git D:\lineage
cd D:\lineage
```

Repo đã có sẵn `.gitattributes` ép `*.sh`, `*.yaml`, `*.yml` dùng LF, nên
người khác clone về cũng không gặp lỗi này.

### 1.4. Image backend: build bằng GitHub Actions, đẩy lên GHCR

Cluster kubeadm không có `kind load` như kind. Image phải nằm trên một
registry mà các node kéo về được. Làm bước này **ngay từ sáng ngày 1**, để
CI chạy trong lúc bạn dựng VM.

**a. Thêm liveness và readiness thật vào app.** Hiện app chỉ có `/health`
và luôn trả `ok`. Kubernetes cần hai câu hỏi khác nhau:

- **liveness** hỏi *process còn sống không?* Trả lời "không" thì K8s **giết
  và restart** container.
- **readiness** hỏi *có nhận traffic được chưa?* Trả lời "không" thì K8s
  **gỡ pod khỏi Service** nhưng không giết.

Thêm vào `src/main.py`, ngay dưới route `/health`:

```python
@app.get("/health/live")
async def health_live():
    # CỐ Ý không kiểm tra DB. Nếu liveness phụ thuộc DB thì khi Postgres
    # chết, MỌI pod backend bị restart liên tục, dù restart không sửa được
    # gì. Một sự cố biến thành hai.
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready():
    # DB không tới được thì pod ngừng nhận request (bị gỡ khỏi Service)
    # nhưng không bị giết; DB sống lại là tự nhận traffic lại.
    # storage_service.ping() có sẵn: chỉ SELECT 1 với timeout 2s, không chạy
    # lại schema bootstrap như _connect(). Chạy trong thread vì psycopg2 là sync.
    if not await asyncio.to_thread(storage_service.ping):
        return JSONResponse({"status": "db_unavailable"}, status_code=503)
    return {"status": "ok"}
```

Sửa import ở đầu file: thêm `from fastapi.responses import JSONResponse`, và
đổi `from src.services import ingest_watcher` thành
`from src.services import ingest_watcher, storage_service`.

> Câu hỏi phỏng vấn rất hay gặp: *"Liveness và readiness khác nhau thế nào?
> Liveness có nên check DB không?"* Đoạn code trên chính là câu trả lời, và
> mục 11 sẽ chứng minh nó bằng thực nghiệm.

**b. Workflow build image.** Tạo `.github/workflows/image.yml` (job mới,
**không sửa** `ci.yml`/`cd.yml` đang chạy):

```yaml
name: Build image
on:
  push:
    branches: [main]
    paths-ignore: ["deploy/**", "docs/**"]
  workflow_dispatch: {}
permissions:
  contents: read
  packages: write
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        # Tên image trên GHCR BẮT BUỘC chữ thường. Owner mà có chữ hoa (vd
        # "My-Org") thì không hạ xuống sẽ push lỗi; hạ sẵn cho chắc.
        run: |
          echo "image=ghcr.io/${GITHUB_REPOSITORY_OWNER,,}/lineage-backend" >> "$GITHUB_OUTPUT"
          echo "tag=sha-${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
      - uses: docker/build-push-action@v6
        with:
          push: true
          tags: ${{ steps.meta.outputs.image }}:${{ steps.meta.outputs.tag }}
      - run: echo "Image ${{ steps.meta.outputs.image }}:${{ steps.meta.outputs.tag }}" >> "$GITHUB_STEP_SUMMARY"
```

Commit và push. Vào tab **Actions**, chờ job xanh, rồi ghi lại tên image
đầy đủ ở phần Summary, ví dụ
`ghcr.io/huydqhust2201-create/lineage-backend:sha-1a2b3c4`.

**c. Đặt package Public.** GitHub → trang cá nhân → **Packages** →
`lineage-backend` → **Package settings** → **Change visibility** → Public.
Nếu không, các node không có credential để kéo image và sẽ báo
`ImagePullBackOff`.


---

## 2. Mạng: vì sao cần IP tĩnh

*Đọc kỹ. Đây là chỗ hay làm hỏng cluster kubeadm trên Windows nhất.*

Multipass trên Windows gắn VM vào **Default Switch** của Hyper-V. Switch này
cấp IP động và **đổi IP của VM sau mỗi lần khởi động lại Windows**. Với
kubeadm, chuyện đó phá hỏng cluster:

- chứng chỉ của kube-apiserver được ký cho đúng IP lúc `kubeadm init`;
- mỗi node đăng ký với control plane bằng IP của nó;
- etcd lưu peer URL theo IP.

Vì vậy mỗi VM có **hai card mạng**:

```
                 Windows host
    ┌──────────────────────────────────────┐
    │  Default Switch (DHCP, IP đổi được)  │──► Internet (apt, kéo image)
    │      │          │          │         │
    │   eth0       eth0       eth0         │
    │  k8s-cp     k8s-w1     k8s-w2        │
    │   eth1       eth1       eth1         │
    │  .56.10     .56.11     .56.12        │  ◄── IP TĨNH, cluster chỉ dùng mạng này
    │      │          │          │         │
    │  k8snet (Internal switch) 192.168.56.0/24
    │      │                               │
    │  vEthernet (k8snet) = 192.168.56.1   │  ◄── Windows chạy kubectl qua đây
    └──────────────────────────────────────┘
```

apiserver, kubelet và Calico đều được **ghim vào `eth1`**. `eth0` đổi IP
cũng không sao, vì nó chỉ dùng để ra Internet.

Tạo switch, PowerShell **Administrator**:

```powershell
New-VMSwitch -Name k8snet -SwitchType Internal
New-NetIPAddress -IPAddress 192.168.56.1 -PrefixLength 24 -InterfaceAlias "vEthernet (k8snet)"
Get-NetIPAddress -InterfaceAlias "vEthernet (k8snet)" -AddressFamily IPv4
```

Phải thấy `192.168.56.1`. Switch Internal không tự ra Internet; đó là chủ
đích, vì Internet đi qua `eth0`.

> Nếu mạng nhà/công ty đang dùng dải `192.168.56.x`, đổi **toàn bộ** tài
> liệu sang dải khác, ví dụ `10.77.0.x`. Dải pod `10.244.0.0/16` không được
> trùng với dải này.

Kiểm tra Multipass thấy switch:

```powershell
multipass get local.driver      # phải là hyperv
multipass networks              # phải có dòng k8snet
```

⚠️ Nếu **không** thấy `k8snet`, dừng ở đây: khởi động lại dịch vụ
Multipass (`Restart-Service Multipass` bằng Administrator) rồi chạy lại.
Đừng tạo VM khi chưa thấy switch.

Khi phỏng vấn, đây là một câu chuyện rất đáng kể: *"Em gặp vấn đề IP VM đổi
sau reboot, hiểu vì sao nó phá cluster, và thiết kế lại mạng hai card."*

---

## 3. Tạo 3 VM

*Giới hạn: 30 phút (phần lớn là tải image Ubuntu).*

| VM | CPU | RAM | Đĩa | Vì sao |
|---|---|---|---|---|
| `k8s-cp` | 2 | 2,5 GB | 20 GB | kubeadm yêu cầu tối thiểu 2 CPU và ~1,7 GB |
| `k8s-w1` | 2 | 4 GB | 25 GB | Chứa app + Prometheus/Loki |
| `k8s-w2` | 2 | 4 GB | 25 GB | Như trên |

Tổng 10,5 GB, còn ~5,5 GB cho Windows. **Đóng bớt trình duyệt trong lúc
chạy lab**; 20 tab Chrome chiếm đúng phần RAM mà Prometheus cần.

```powershell
multipass launch 24.04 --name k8s-cp -c 2 -m 2500M -d 20G --network name=k8snet,mode=manual
multipass launch 24.04 --name k8s-w1 -c 2 -m 4G    -d 25G --network name=k8snet,mode=manual
multipass launch 24.04 --name k8s-w2 -c 2 -m 4G    -d 25G --network name=k8snet,mode=manual

multipass list
multipass exec k8s-cp -- ip -br link     # phải thấy eth0 và eth1
```

`mode=manual`: Multipass gắn thêm card `eth1` vào `k8snet` nhưng **không**
cấu hình IP. Script ở mục 4 làm việc đó.

---

## 4. Chuẩn bị node

*Giới hạn: 30 phút.*

### 4.1. Script

Tạo `deploy/kubeadm/node-prep.sh`:

```bash
#!/usr/bin/env bash
# Chuẩn bị 1 node Ubuntu 24.04 cho kubeadm. Chạy trên CẢ 3 VM:
#   sudo bash node-prep.sh 192.168.56.10      (k8s-cp)
#   sudo bash node-prep.sh 192.168.56.11      (k8s-w1)
#   sudo bash node-prep.sh 192.168.56.12      (k8s-w2)
set -euo pipefail

NODE_IP="${1:?Thieu IP. Vi du: sudo bash node-prep.sh 192.168.56.10}"
K8S_MINOR="${K8S_MINOR:-v1.35}"

echo "==> 1/5 IP tinh cho eth1 ($NODE_IP)"
MAC="$(cat /sys/class/net/eth1/address)"
cat > /etc/netplan/60-k8snet.yaml <<NETPLAN
network:
  version: 2
  ethernets:
    eth1:
      dhcp4: false
      match:
        macaddress: "$MAC"
      set-name: eth1
      addresses: [$NODE_IP/24]
NETPLAN
chmod 600 /etc/netplan/60-k8snet.yaml
netplan apply

echo "==> 2/5 Kernel: tat swap, module, sysctl"
swapoff -a
sed -i '/ swap / s/^/#/' /etc/fstab
printf 'overlay\nbr_netfilter\n' > /etc/modules-load.d/k8s.conf
modprobe overlay
modprobe br_netfilter
cat > /etc/sysctl.d/k8s.conf <<SYSCTL
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
SYSCTL
sysctl --system > /dev/null

echo "==> 3/5 containerd (SystemdCgroup = true)"
apt-get update -q
apt-get install -yq containerd apt-transport-https ca-certificates curl gpg
mkdir -p /etc/containerd
containerd config default > /etc/containerd/config.toml
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
grep -q 'SystemdCgroup = true' /etc/containerd/config.toml || { echo "LOI: khong bat duoc SystemdCgroup"; exit 1; }
systemctl restart containerd

echo "==> 4/5 kubeadm, kubelet, kubectl ($K8S_MINOR)"
mkdir -p /etc/apt/keyrings
curl -fsSL "https://pkgs.k8s.io/core:/stable:/$K8S_MINOR/deb/Release.key" \
  | gpg --dearmor --yes -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/$K8S_MINOR/deb/ /" \
  > /etc/apt/sources.list.d/kubernetes.list
apt-get update -q
apt-get install -yq kubelet kubeadm kubectl
apt-mark hold kubelet kubeadm kubectl

echo "==> 5/5 kubelet dung IP tinh"
echo "KUBELET_EXTRA_ARGS=--node-ip=$NODE_IP" > /etc/default/kubelet
systemctl enable --now kubelet

echo "XONG. $(hostname) = $NODE_IP, kubeadm $(kubeadm version -o short)"
```

Từng phần làm gì, để bạn trả lời được khi bị hỏi:

| Phần | Vì sao cần |
|---|---|
| IP tĩnh `eth1` | Xem mục 2 |
| Tắt swap | kubelet mặc định từ chối chạy khi có swap, vì scheduler xếp pod theo RAM request; swap làm con số đó sai |
| `br_netfilter` + `bridge-nf-call-iptables` | Thiếu thì traffic giữa các pod đi qua bridge sẽ lách qua iptables, Service và NetworkPolicy không chạy |
| `ip_forward` | Node phải chuyển tiếp gói tin giữa pod và ra ngoài |
| `SystemdCgroup = true` | **Lỗi số một khi dựng kubeadm.** kubelet dùng cgroup driver systemd; containerd mà dùng cgroupfs thì hai bên quản lý cgroup khác nhau, pod control plane chạy vài phút rồi restart liên tục mà không báo lỗi rõ ràng |
| `apt-mark hold` | Không cho `apt upgrade` vô tình nâng kubelet lệch version control plane. Nâng version phải qua `kubeadm upgrade` (mục 12.1) |
| `--node-ip` | Thiếu thì kubelet tự chọn IP, thường là `eth0`, đúng card có IP đổi được |

### 4.2. Chạy trên cả 3 VM

```powershell
foreach ($n in @(@('k8s-cp','10'), @('k8s-w1','11'), @('k8s-w2','12'))) {
  multipass transfer deploy/kubeadm/node-prep.sh "$($n[0]):/home/ubuntu/node-prep.sh"
  # sed bỏ \r phòng khi file vẫn bị CRLF
  multipass exec $n[0] -- bash -c "sed -i 's/\r$//' node-prep.sh && sudo bash node-prep.sh 192.168.56.$($n[1])"
}
```

> `netplan apply` có thể làm lệnh trông như treo vài giây. Bình thường:
> `exec` đi qua `eth0` nên không bị cắt.

### 4.3. Kiểm tra mạng tĩnh

```powershell
multipass exec k8s-cp -- ping -c 2 192.168.56.11
multipass exec k8s-cp -- ping -c 2 192.168.56.12
ping 192.168.56.10
```

Cả ba lệnh phải thông. Không thông thì **đừng** chạy `kubeadm init`.

---

## 5. Dựng cluster

*Giới hạn: 60 phút.*

### 5.1. `kubeadm init`

```powershell
multipass shell k8s-cp
```

Trong VM:

```bash
sudo kubeadm init \
  --apiserver-advertise-address=192.168.56.10 \
  --apiserver-cert-extra-sans=192.168.56.10 \
  --pod-network-cidr=10.244.0.0/16 \
  --node-name=k8s-cp
```

Đọc kỹ output:

1. Các dòng `[preflight]`: cảnh báo về version image `pause` của containerd
   thì ghi lại, thường không chặn init.
2. Lệnh `kubeadm join ...` ở cuối: **chép lại ngay**.

```bash
mkdir -p $HOME/.kube
sudo cp /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config
kubectl get nodes        # k8s-cp NotReady
```

`NotReady` lúc này là **đúng**: chưa có mạng pod (CNI) nên kubelet báo node
chưa sẵn sàng. Câu hỏi CKA kinh điển.

Nhìn qua control plane một lần, để có câu trả lời khi bị hỏi "control
plane có gì":

```bash
ls /etc/kubernetes/manifests/    # etcd, kube-apiserver, kube-controller-manager, kube-scheduler
ls /etc/kubernetes/pki/          # CA và chứng chỉ
systemctl status kubelet         # kubelet là service hệ thống, KHÔNG phải pod
sudo crictl ps                   # runtime là containerd
```

Ghi lại: *static pod là gì, vì sao kubelet không chạy dưới dạng pod, và vì
sao `kubectl delete pod` một static pod thì nó tự hồi sinh.*

### 5.2. Calico (CNI)

Vẫn trong `k8s-cp`. Lệnh `sed` dưới đây **đã chạy thử trên đúng file v3.30.3**:

```bash
curl -LO https://raw.githubusercontent.com/projectcalico/calico/v3.30.3/manifests/calico.yaml

# Dải IP pod phải khớp --pod-network-cidr lúc init
sed -i 's|# - name: CALICO_IPV4POOL_CIDR|- name: CALICO_IPV4POOL_CIDR|; s|#   value: "192.168.0.0/16"|  value: "10.244.0.0/16"|' calico.yaml
grep -A1 "name: CALICO_IPV4POOL_CIDR" calico.yaml      # phải thấy 10.244.0.0/16

kubectl apply -f calico.yaml

# Ghim Calico vào eth1. File gốc để IP=autodetect và không chỉ định card,
# nên Calico có thể bắt eth0, đúng card đổi IP sau reboot.
kubectl -n kube-system set env daemonset/calico-node IP_AUTODETECTION_METHOD=interface=eth1

kubectl -n kube-system get pods -w      # Ctrl+C khi calico-node và coredns Running
kubectl get nodes                       # Ready
exit
```

⚠️ Mở trang "System requirements" của Calico để xác nhận v3.30.3 hỗ trợ
Kubernetes 1.35. Nếu không, dùng bản Calico mới hơn; chạy
`grep -n CALICO_IPV4POOL_CIDR -A1 calico.yaml` để chắc hai dòng chú thích
vẫn giống trước khi chạy `sed`.

### 5.3. Join 2 worker

Dùng lệnh `join` đã chép. Mất hoặc quá 24 giờ thì tạo lại:
`multipass exec k8s-cp -- sudo kubeadm token create --print-join-command`.

```powershell
multipass exec k8s-w1 -- sudo kubeadm join 192.168.56.10:6443 --token ... --discovery-token-ca-cert-hash sha256:...
multipass exec k8s-w2 -- sudo kubeadm join 192.168.56.10:6443 --token ... --discovery-token-ca-cert-hash sha256:...
```

### 5.4. kubectl từ Windows

```powershell
mkdir $HOME\.kube -Force
multipass transfer k8s-cp:/home/ubuntu/.kube/config $HOME\.kube\config
kubectl get nodes -o wide
kubectl label node k8s-w1 node-role.kubernetes.io/worker=
kubectl label node k8s-w2 node-role.kubernetes.io/worker=
```

Kết quả mong đợi: 3 node `Ready`, cột `INTERNAL-IP` là `192.168.56.10/11/12`.
**Thấy IP ngoài dải `.56`** thì `--node-ip` chưa có tác dụng: kiểm tra
`/etc/default/kubelet` trên node đó, rồi `sudo systemctl restart kubelet`.

### 5.5. Chứng minh thiết kế mạng

Mục RUNBOOK đầu tiên của bạn, làm **ngay**:

```powershell
multipass restart k8s-w1
kubectl get nodes -w       # k8s-w1 NotReady rồi Ready lại, vẫn 192.168.56.11
```

Rồi khởi động lại **cả Windows**, mở lại, `kubectl get nodes`. Cluster vẫn
sống thì thiết kế ở mục 2 đã được chứng minh. Ghi vào RUNBOOK.

---

## 6. Storage, MetalLB, Ingress

*Giới hạn: 45 phút.*

kubeadm không cài sẵn lưu trữ hay cách đưa traffic vào. Phải tự cài là khác
biệt thật giữa cluster tự dựng và cluster cloud (EKS/GKE có sẵn những thứ
này).

### 6.1. StorageClass

PVC của Postgres cần StorageClass, không có thì PVC kẹt `Pending`:

```powershell
kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.31/deploy/local-path-storage.yaml
kubectl patch storageclass local-path -p '{\"metadata\":{\"annotations\":{\"storageclass.kubernetes.io/is-default-class\":\"true\"}}}'
kubectl get storageclass      # local-path (default)
```

> Trong PowerShell, dấu `"` trong JSON phải viết thành `\"` như trên.

### 6.2. MetalLB

Cấp IP cho Service kiểu `LoadBalancer`. Thiếu nó, Service LoadBalancer kẹt
`<pending>` mãi mãi:

```powershell
kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.14.9/config/manifests/metallb-native.yaml
kubectl -n metallb-system wait --for=condition=ready pod --all --timeout=180s
```

`deploy/kubeadm/metallb-pool.yaml`:

```yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: k8snet
  namespace: metallb-system
spec:
  # Một đoạn trong dải k8snet, KHÔNG trùng IP node (.10–.12)
  addresses:
    - 192.168.56.200-192.168.56.220
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: k8snet
  namespace: metallb-system
spec:
  ipAddressPools: [k8snet]
```

```powershell
kubectl apply -f deploy/kubeadm/metallb-pool.yaml
```

### 6.3. ingress-nginx

```powershell
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/baremetal/deploy.yaml
kubectl -n ingress-nginx wait --for=condition=ready pod -l app.kubernetes.io/component=controller --timeout=180s
kubectl -n ingress-nginx patch svc ingress-nginx-controller -p '{\"spec\":{\"type\":\"LoadBalancer\"}}'
kubectl -n ingress-nginx get svc ingress-nginx-controller     # EXTERNAL-IP 192.168.56.200
```

Mở Notepad **bằng quyền Administrator**, sửa
`C:\Windows\System32\drivers\etc\hosts`, thêm:

```
192.168.56.200  lineage.local
```

---

## 7. etcd snapshot và restore

*Giới hạn: 90 phút. Kẹt quá thì giữ snapshot, bỏ restore, ghi vào RUNBOOK
những gì đã thử, rồi đi tiếp.*

Đây là gạch đầu dòng "Disaster Recovery". Thứ tự cả bài: **tạo dữ liệu →
snapshot → xoá dữ liệu → restore → dữ liệu quay lại.**

### 7.1. Tạo dữ liệu làm bằng chứng

```powershell
kubectl create namespace dr-test
kubectl -n dr-test create configmap bang-chung --from-literal=note="toi ton tai truoc snapshot"
```

### 7.2. Đưa công cụ etcd vào control plane

Image etcd của Kubernetes không có shell, nên mang công cụ vào node:

```powershell
curl.exe -L -o etcd.tar.gz https://github.com/etcd-io/etcd/releases/download/v3.5.21/etcd-v3.5.21-linux-amd64.tar.gz
multipass transfer etcd.tar.gz k8s-cp:/home/ubuntu/
multipass shell k8s-cp
```

### 7.3. Snapshot

Trong `k8s-cp`:

```bash
sudo -i
cd /home/ubuntu && tar xzf etcd.tar.gz && cp etcd-v3.5.21-linux-amd64/etcd{ctl,utl} /usr/local/bin/

etcdctl --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  snapshot save /home/ubuntu/snap.db

etcdutl snapshot status /home/ubuntu/snap.db -w table
exit; exit
```

### 7.4. Gây thảm hoạ

```powershell
kubectl delete namespace dr-test
kubectl get ns dr-test        # NotFound
```

### 7.5. Restore

```powershell
multipass shell k8s-cp
```

```bash
sudo -i

# 1. Lấy tên member và peer URL đang dùng, để restore khớp cấu hình cũ
grep -E -- "--name=|--initial-advertise-peer-urls=" /etc/kubernetes/manifests/etcd.yaml

# 2. Dừng etcd: đưa manifest ra khỏi thư mục static pod, kubelet tự giết pod
mv /etc/kubernetes/manifests/etcd.yaml /home/ubuntu/etcd.yaml.bak
sleep 20; crictl ps | grep etcd      # không còn dòng nào là đã dừng

# 3. Restore vào data dir MỚI (không ghi đè dir cũ, phòng khi restore hỏng)
#    Thay <NAME> (thường là k8s-cp) và <PEER_URL> (https://192.168.56.10:2380)
etcdutl snapshot restore /home/ubuntu/snap.db \
  --data-dir /var/lib/etcd-restore \
  --name <NAME> \
  --initial-cluster <NAME>=<PEER_URL> \
  --initial-advertise-peer-urls <PEER_URL>

# 4. Trỏ hostPath sang dir mới rồi trả manifest về
sed -i 's#path: /var/lib/etcd$#path: /var/lib/etcd-restore#' /home/ubuntu/etcd.yaml.bak
grep -n "etcd-restore" /home/ubuntu/etcd.yaml.bak     # phải thấy ở mục hostPath
mv /home/ubuntu/etcd.yaml.bak /etc/kubernetes/manifests/etcd.yaml
exit; exit
```

```powershell
# Chờ 1–2 phút để apiserver kết nối lại
kubectl get ns dr-test
kubectl -n dr-test get configmap bang-chung -o yaml
```

Namespace quay lại là thành công. Ghi vào RUNBOOK kèm thời gian từng bước.

**Thêm một dòng so sánh vào RUNBOOK:** `multipass snapshot k8s-cp` (chụp
nguyên VM, phải tắt VM trước) khôi phục nhanh nhưng nặng; etcd snapshot chỉ
chụp trạng thái cluster, nhẹ, và đúng thứ cần cho DR.

---

## 8. Đưa app lên: manifest thô

*Giới hạn: 2 giờ.*

Viết YAML thô **trước** khi dùng Helm. Helm chỉ là template; hiểu YAML nó
sinh ra thì mới gỡ lỗi được.

### 8.1. Namespace và Secret

```powershell
kubectl create namespace lineage
```

Tạo `.env.k8s` và **thêm vào `.gitignore` ngay**:

```ini
POSTGRES_USER=lineage
POSTGRES_PASSWORD=mat-khau-k8s-cua-ban
POSTGRES_DB=lineage
DATABASE_URL=postgresql://lineage:mat-khau-k8s-cua-ban@postgres:5432/lineage
OPENROUTER_API_KEY=sk-or-...
JWT_SECRET=chuoi-ngau-nhien-dai
```

Đối chiếu tên biến với `.env.production.example`: app cần biến nào thì
Secret phải có biến đó.

```powershell
kubectl -n lineage create secret generic lineage-secrets --from-env-file=.env.k8s
```

> Secret trong K8s chỉ được **base64**, không được mã hoá; ai có quyền
> `get secret` là đọc được. Không commit Secret YAML. Production dùng Sealed
> Secrets hoặc External Secrets (ghi vào mục "việc tiếp theo" của README).

### 8.2. Postgres — StatefulSet + PVC

`deploy/raw/postgres.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: lineage
spec:
  clusterIP: None            # headless: StatefulSet cần để có DNS ổn định postgres-0.postgres
  selector:
    app.kubernetes.io/name: postgres
  ports:
    - port: 5432
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: lineage
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: postgres
  template:
    metadata:
      labels:
        app.kubernetes.io/name: postgres
    spec:
      containers:
        - name: postgres
          image: pgvector/pgvector:pg16
          ports:
            - containerPort: 5432
          envFrom:
            - secretRef:
                name: lineage-secrets
          env:
            # Thư mục CON trong volume. Đĩa cloud (EBS, PD...) có sẵn
            # lost+found ở gốc, và Postgres từ chối init vào thư mục không
            # rỗng. local-path không bị, nhưng cứ viết đúng từ đầu.
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
          resources:
            requests: { cpu: 100m, memory: 256Mi }
            limits: { memory: 512Mi }
          readinessProbe:
            exec:
              command: ["sh", "-c", "pg_isready -U $POSTGRES_USER"]
            periodSeconds: 10
          livenessProbe:
            exec:
              command: ["sh", "-c", "pg_isready -U $POSTGRES_USER"]
            initialDelaySeconds: 30
            periodSeconds: 20
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 2Gi
```

```powershell
kubectl apply -f deploy/raw/postgres.yaml
kubectl -n lineage get pods,pvc -o wide -w     # Ctrl+C khi postgres-0 Running 1/1
```

Ghi lại Postgres nằm trên node nào; mục 11 sẽ cần.

### 8.3. Backend — Deployment + Service

`deploy/raw/backend.yaml`. Thay `image:` bằng tên image bạn ghi lại ở mục
1.4:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: backend-config
  namespace: lineage
data:
  APP_ENV: production
  LOG_LEVEL: INFO
  DESCRIPTION_ENABLED: "false"
  # Watcher re-ingest chạy trong TỪNG pod: 2 replica = ingest trùng 2 lần.
  # Muốn bật thì tách ra thành CronJob riêng, không để trong Deployment.
  AUTO_REINGEST_ENABLED: "false"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: lineage
spec:
  replicas: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: backend
  template:
    metadata:
      labels:
        app.kubernetes.io/name: backend
    spec:
      containers:
        - name: backend
          image: ghcr.io/huydqhust2201-create/lineage-backend:sha-xxxxxxx
          ports:
            - name: http
              containerPort: 8000
          envFrom:
            - configMapRef:
                name: backend-config
            - secretRef:
                name: lineage-secrets
          resources:
            requests: { cpu: 200m, memory: 384Mi }
            limits: { memory: 1Gi }
          # Import langchain/langgraph mất vài giây tới vài chục giây.
          # startupProbe cho tối đa 30 x 5s = 150s để khởi động; trong lúc đó
          # liveness chưa chạy, nên pod không bị giết oan khi đang boot.
          startupProbe:
            httpGet: { path: /health/live, port: http }
            periodSeconds: 5
            failureThreshold: 30
          livenessProbe:
            httpGet: { path: /health/live, port: http }
            periodSeconds: 15
            failureThreshold: 3
          readinessProbe:
            httpGet: { path: /health/ready, port: http }
            periodSeconds: 10
            failureThreshold: 2
          volumeMounts:
            - name: data
              mountPath: /app/data
      volumes:
        # emptyDir chứ không PVC: PVC ReadWriteOnce không gắn được vào 2 pod
        # nằm trên 2 node khác nhau. Dữ liệu cần giữ đã nằm trong Postgres.
        - name: data
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: backend
  namespace: lineage
  labels:
    app.kubernetes.io/name: backend     # ServiceMonitor ở mục 10 chọn theo nhãn này
spec:
  selector:
    app.kubernetes.io/name: backend
  ports:
    - name: http                        # ServiceMonitor tham chiếu theo TÊN cổng
      port: 8000
      targetPort: http
```

```powershell
kubectl apply -f deploy/raw/backend.yaml
kubectl -n lineage get pods -o wide     # 2 pod backend thường nằm trên 2 worker khác nhau
kubectl -n lineage logs deploy/backend --tail=20
```

**Vì sao chạy được 2 replica:** session chat lưu thẳng trong Postgres
(`src/agents/chat/session.py`), không có cache RAM, nên request rơi vào pod
nào cũng thấy cùng một session. Đáng nói khi phỏng vấn: *trước khi scale
ngang, em kiểm tra state nằm ở đâu.* Chỉ còn hai chỗ có state riêng từng
pod: watcher re-ingest (đã tắt) và counter `/metrics` (không sao, vì
Prometheus scrape từng pod rồi `sum()` lại).

### 8.4. Ingress

`deploy/raw/ingress.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: lineage
  namespace: lineage
spec:
  ingressClassName: nginx
  rules:
    - host: lineage.local
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service: { name: backend, port: { number: 8000 } }
          - path: /health
            pathType: Prefix
            backend:
              service: { name: backend, port: { number: 8000 } }
          - path: /docs
            pathType: Prefix
            backend:
              service: { name: backend, port: { number: 8000 } }
          - path: /openapi.json
            pathType: Exact
            backend:
              service: { name: backend, port: { number: 8000 } }
```

Cố ý **không** route `/metrics`, giống Caddyfile bản cũ: metric nội bộ không
đi ra ngoài.

```powershell
kubectl apply -f deploy/raw/ingress.yaml
curl.exe http://lineage.local/health
curl.exe http://lineage.local/health/ready
curl.exe -i http://lineage.local/metrics      # phải là 404
```

Mở http://lineage.local/docs để xem Swagger.

> **Frontend (tuỳ chọn):** viết `Dockerfile.frontend` 2 stage (node build
> `frontend/dist` → `nginx:alpine`), thêm một Deployment và path `/` trỏ vào
> nó. Bỏ qua cũng không ảnh hưởng phần JD hỏi.

---

## 9. Helm chart

*Giới hạn: 2,5 giờ.*

### 9.1. Khung

```powershell
helm create deploy/helm/lineage
```

Xoá gần hết file mẫu, chỉ giữ `Chart.yaml`, `values.yaml`,
`templates/_helpers.tpl`. Cấu trúc đích:

```
deploy/helm/lineage/
├── Chart.yaml
├── values.yaml           # mặc định
├── values-dev.yaml       # lab: tài nguyên nhỏ
├── values-prod.yaml      # nhiều replica hơn, storage lớn hơn
└── templates/
    ├── _helpers.tpl
    ├── configmap.yaml
    ├── backend.yaml           # Deployment + Service
    ├── postgres.yaml          # StatefulSet + Service
    ├── ingress.yaml
    ├── servicemonitor.yaml    # mục 10.2
    └── prometheusrule.yaml    # mục 10.6
```

> **Bẫy nhãn:** helper `selectorLabels` mà `helm create` sinh ra đặt
> `app.kubernetes.io/name` bằng **tên chart** (`lineage`) cho mọi thứ. Như
> vậy backend và Postgres cùng nhãn, Service chọn nhầm pod, còn
> ServiceMonitor và query Loki (`app="backend"`) không khớp. Giữ nhãn
> riêng cho từng thành phần như manifest thô:
> `app.kubernetes.io/name: backend` / `postgres`, cộng thêm
> `app.kubernetes.io/instance: {{ .Release.Name }}`.

### 9.2. Values

`values.yaml`:

```yaml
backend:
  image:
    repository: ghcr.io/huydqhust2201-create/lineage-backend
    tag: "sha-xxxxxxx"
    pullPolicy: IfNotPresent
  replicas: 2
  resources:
    requests: { cpu: 200m, memory: 384Mi }
    limits: { memory: 1Gi }
  config:
    APP_ENV: production
    LOG_LEVEL: INFO
    DESCRIPTION_ENABLED: "false"
    AUTO_REINGEST_ENABLED: "false"

postgres:
  image: pgvector/pgvector:pg16
  storage: 2Gi
  resources:
    requests: { cpu: 100m, memory: 256Mi }
    limits: { memory: 512Mi }

# Secret KHÔNG nằm trong values: chart chỉ tham chiếu Secret đã tạo sẵn.
existingSecret: lineage-secrets

ingress:
  enabled: true
  className: nginx
  host: lineage.local

metrics:
  serviceMonitor:
    enabled: false        # bật ở mục 10, sau khi đã có CRD của Prometheus Operator
```

`values-dev.yaml` chỉ ghi phần **khác** mặc định:

```yaml
backend:
  replicas: 1
  resources:
    requests: { cpu: 100m, memory: 256Mi }
```

`values-prod.yaml`:

```yaml
backend:
  replicas: 3
postgres:
  storage: 20Gi
  resources:
    limits: { memory: 1Gi }
```

### 9.3. Template

Ví dụ một đoạn `templates/backend.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "lineage.fullname" . }}-backend
spec:
  replicas: {{ .Values.backend.replicas }}
  selector:
    matchLabels:
      app.kubernetes.io/name: backend
      app.kubernetes.io/instance: {{ .Release.Name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: backend
        app.kubernetes.io/instance: {{ .Release.Name }}
      annotations:
        # Đổi ConfigMap thì checksum đổi, pod tự rolling restart.
        # Thiếu dòng này thì sửa config xong pod vẫn chạy config cũ.
        checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
    spec:
      containers:
        - name: backend
          image: "{{ .Values.backend.image.repository }}:{{ .Values.backend.image.tag }}"
          imagePullPolicy: {{ .Values.backend.image.pullPolicy }}
          resources:
            {{- toYaml .Values.backend.resources | nindent 12 }}
          envFrom:
            - configMapRef:
                name: {{ include "lineage.fullname" . }}-config
            - secretRef:
                name: {{ .Values.existingSecret }}
          # ... probe, port, volume như manifest thô
```

Lưu ý: tên Service Postgres trong chart sẽ đổi (ví dụ `lineage-postgres`),
nên `DATABASE_URL` trong Secret phải đổi host theo. Cách gọn: đặt cứng tên
Service Postgres là `postgres` trong template.

### 9.4. Kiểm tra trước khi cài

```powershell
helm lint deploy/helm/lineage -f deploy/helm/lineage/values-dev.yaml
helm template lineage deploy/helm/lineage -f deploy/helm/lineage/values-dev.yaml | Out-File rendered.yaml
```

Đọc `rendered.yaml`: nó phải gần giống manifest thô ở mục 8. Khác chỗ nào
thì sửa template.

### 9.5. Thay manifest thô bằng chart

```powershell
kubectl delete -f deploy/raw/backend.yaml -f deploy/raw/ingress.yaml
kubectl delete -f deploy/raw/postgres.yaml
kubectl -n lineage delete pvc -l app.kubernetes.io/name=postgres    # bỏ dòng này nếu muốn giữ dữ liệu

helm install lineage deploy/helm/lineage -n lineage -f deploy/helm/lineage/values-dev.yaml
helm list -n lineage
```

Thử đủ vòng đời:

```powershell
helm upgrade lineage deploy/helm/lineage -n lineage -f deploy/helm/lineage/values-dev.yaml --set backend.replicas=2
helm history lineage -n lineage
helm rollback lineage 1 -n lineage
```

**Hết ngày 1.** Commit `deploy/`.

---

## 10. Giám sát

*Giới hạn: cả ngày 2 tới chiều.*

### 10.1. kube-prometheus-stack

`deploy/monitoring/kps-values.yaml`, **đã render thử với chart 92.14.0**:

```yaml
alertmanager:
  alertmanagerSpec:
    resources:
      requests: { cpu: 10m, memory: 32Mi }
      limits: { memory: 128Mi }
grafana:
  adminPassword: doi-mat-khau-nay
  resources:
    requests: { cpu: 50m, memory: 128Mi }
    limits: { memory: 256Mi }
  sidecar:
    dashboards:
      enabled: true
      label: grafana_dashboard      # ConfigMap có nhãn này sẽ được nạp làm dashboard
      searchNamespace: ALL
  additionalDataSources:
    - name: Loki
      type: loki
      uid: loki                     # trùng uid dashboard trong repo đang dùng
      access: proxy
      url: http://loki.monitoring.svc.cluster.local:3100
prometheus:
  prometheusSpec:
    retention: 3d
    retentionSize: 3GB
    scrapeInterval: 30s
    resources:
      requests: { cpu: 100m, memory: 400Mi }
      limits: { memory: 1Gi }
    # Mặc định Prometheus CHỈ nhận ServiceMonitor/Rule có nhãn
    # release=<tên release>. Ba dòng false dưới đây cho phép nhận tất cả.
    # Thiếu chúng là lỗi phổ biến nhất: viết ServiceMonitor đúng hết mà
    # Prometheus vẫn không scrape.
    serviceMonitorSelectorNilUsesHelmValues: false
    podMonitorSelectorNilUsesHelmValues: false
    ruleSelectorNilUsesHelmValues: false
# kubeadm cho etcd/scheduler/controller-manager chỉ listen ở 127.0.0.1 của
# node, nên Prometheus không scrape được và sẽ báo đỏ. Tắt cho dashboard sạch.
# Muốn bật: sửa --bind-address trong static pod manifest (bài nâng cao).
kubeEtcd:
  enabled: false
kubeControllerManager:
  enabled: false
kubeScheduler:
  enabled: false
kubeProxy:
  enabled: false
```

```powershell
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

kubectl create namespace monitoring
helm install kps prometheus-community/kube-prometheus-stack --version 92.14.0 `
  -n monitoring -f deploy/monitoring/kps-values.yaml
kubectl -n monitoring get pods -w
```

Lần đầu mất 3–5 phút để kéo image.

### 10.2. ServiceMonitor cho backend

`deploy/helm/lineage/templates/servicemonitor.yaml`:

```yaml
{{- if .Values.metrics.serviceMonitor.enabled }}
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: {{ include "lineage.fullname" . }}-backend
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: backend
  endpoints:
    - port: http                # TÊN cổng trong Service, không phải số
      path: /metrics
      interval: 30s
{{- end }}
```

```powershell
helm upgrade lineage deploy/helm/lineage -n lineage -f deploy/helm/lineage/values-dev.yaml `
  --set metrics.serviceMonitor.enabled=true
```

Kiểm tra:

```powershell
kubectl -n monitoring get svc        # tìm service Prometheus, thường là kps-kube-prometheus-stack-prometheus
kubectl -n monitoring port-forward svc/kps-kube-prometheus-stack-prometheus 9090:9090
```

Mở http://localhost:9090/targets: phải có target của backend, **mỗi pod là
một dòng**, trạng thái `UP`. Gọi vài request qua `lineage.local` rồi query
`http_requests_total`.

Metric này chính là histogram trong `src/metrics.py`. Nhãn `path` là route
template (`/api/v1/assets/{asset_id}`) nên dù nhiều pod, nhiều ID, số time
series vẫn nhỏ.

### 10.3. Dashboard có sẵn trong repo

`monitoring/grafana/dashboards/lineage-ai.json` dùng uid `prometheus` và
`loki`. Chart đặt sẵn uid Prometheus là `prometheus` (đã kiểm tra trong
output render), Loki khai báo uid `loki` ở trên.

Chỉ phải sửa **hai panel log**, vì trên K8s nhãn log khác Docker. Trong file
JSON, đổi:

| Panel | Từ | Thành |
|---|---|---|
| "Log lỗi (mọi container)" | `{platform=\"docker\", level=~\"ERROR\|CRITICAL\|WARNING\"}` | `{namespace=\"lineage\", level=~\"ERROR\|CRITICAL\|WARNING\"}` |
| "Access log backend" | `{platform=\"docker\", service=\"backend\"} \| json \| logger=\`access\`` | `{namespace=\"lineage\", app=\"backend\"} \| json \| logger=\`access\`` |

```powershell
kubectl -n monitoring create configmap lineage-dashboard `
  --from-file=lineage-ai.json=monitoring/grafana/dashboards/lineage-ai.json
kubectl -n monitoring label configmap lineage-dashboard grafana_dashboard=1

kubectl -n monitoring port-forward svc/kps-grafana 3000:80
```

Mở http://localhost:3000 (`admin` / mật khẩu trong values), tìm "Lineage AI
— Overview".

### 10.4. Loki (single binary)

`deploy/monitoring/loki-values.yaml`, **đã render thử với chart 7.5.0;
sinh ra Service tên `loki`**, khớp URL mà Grafana và Alloy trỏ tới:

```yaml
deploymentMode: SingleBinary
loki:
  auth_enabled: false
  commonConfig:
    replication_factor: 1
  storage:
    type: filesystem
  schemaConfig:
    configs:
      - from: "2024-01-01"
        store: tsdb
        object_store: filesystem
        schema: v13
        index:
          prefix: index_
          period: 24h
  limits_config:
    retention_period: 72h
  compactor:
    retention_enabled: true
    delete_request_store: filesystem
singleBinary:
  replicas: 1
  resources:
    requests: { cpu: 100m, memory: 256Mi }
    limits: { memory: 512Mi }
  persistence:
    size: 5Gi
# Chart mặc định dựng Loki dạng phân tán (read/write/backend + cache +
# gateway), quá nặng cho lab. Tắt hết, chỉ giữ một binary.
read: { replicas: 0 }
write: { replicas: 0 }
backend: { replicas: 0 }
gateway: { enabled: false }
chunksCache: { enabled: false }
resultsCache: { enabled: false }
lokiCanary: { enabled: false }
test: { enabled: false }
```

```powershell
helm install loki grafana/loki --version 7.5.0 -n monitoring -f deploy/monitoring/loki-values.yaml
```

### 10.5. Alloy thu log pod

`deploy/monitoring/alloy-values.yaml`, **đã render thử với chart 1.14.3;
config bên trong qua `alloy fmt` và `alloy run`**:

```yaml
alloy:
  resources:
    requests: { cpu: 50m, memory: 64Mi }
    limits: { memory: 256Mi }
  configMap:
    content: |
      discovery.kubernetes "pods" {
        role = "pod"
      }

      discovery.relabel "pods" {
        targets = discovery.kubernetes.pods.targets

        rule {
          source_labels = ["__meta_kubernetes_namespace"]
          target_label  = "namespace"
        }

        rule {
          source_labels = ["__meta_kubernetes_pod_name"]
          target_label  = "pod"
        }

        rule {
          source_labels = ["__meta_kubernetes_pod_container_name"]
          target_label  = "container"
        }

        rule {
          source_labels = ["__meta_kubernetes_pod_label_app_kubernetes_io_name"]
          target_label  = "app"
        }
      }

      loki.source.kubernetes "pods" {
        targets    = discovery.relabel.pods.output
        forward_to = [loki.process.app_logs.receiver]
      }

      loki.process "app_logs" {
        forward_to = [loki.write.default.receiver]

        stage.json {
          expressions = {
            level = "level",
            route = "route",
          }
        }

        stage.labels {
          values = {
            level = "",
            route = "",
          }
        }
      }

      loki.write "default" {
        endpoint {
          url = "http://loki.monitoring.svc.cluster.local:3100/loki/api/v1/push"
        }
      }
```

```powershell
helm install alloy grafana/alloy --version 1.14.3 -n monitoring -f deploy/monitoring/alloy-values.yaml
```

Alloy chạy dạng **DaemonSet**, mỗi node một pod. Grafana → Explore → Loki:

```logql
{namespace="lineage", app="backend"} | json | status >= 500
{namespace="lineage"} | json | duration_ms > 1000
```

Query theo `status`, `duration_ms` được là nhờ JSON log của backend có field
phẳng (`src/logging_config.py`).

### 10.6. Alert rule

kube-prometheus-stack **có sẵn** khoảng 30 nhóm rule, trong đó có
`KubePodCrashLooping` và `KubeNodeNotReady` (xem tab Alerts). Đừng viết lại.
Viết rule **riêng cho app**, những thứ chart không thể biết.

`deploy/helm/lineage/templates/prometheusrule.yaml`:

```yaml
{{- if .Values.metrics.serviceMonitor.enabled }}
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: {{ include "lineage.fullname" . }}-rules
spec:
  groups:
    - name: lineage-backend
      rules:
        - alert: LineageHighErrorRate
          expr: |
            sum(rate(http_requests_total{namespace="{{ .Release.Namespace }}",status=~"5.."}[5m]))
              / sum(rate(http_requests_total{namespace="{{ .Release.Namespace }}"}[5m])) > 0.05
          for: 5m
          labels: { severity: critical }
          annotations:
            summary: "Hơn 5% request trả 5xx trong 5 phút"
            runbook_url: "https://github.com/huydqhust2201-create/data-lineage/blob/main/RUNBOOK.md#loi-5xx-tang-vot"

        - alert: LineageHighLatencyP95
          # Loại /api/v1/chat vì endpoint đó gọi LLM, chậm là bình thường;
          # để chung thì alert kêu suốt và mọi người tập lờ nó đi.
          expr: |
            histogram_quantile(0.95,
              sum by (le) (rate(http_request_duration_seconds_bucket{namespace="{{ .Release.Namespace }}",path!~"/metrics|/api/v1/chat.*"}[5m]))
            ) > 1
          for: 10m
          labels: { severity: warning }
          annotations:
            summary: "p95 vượt 1 giây trong 10 phút (không tính chat)"

        - alert: LineageBackendDown
          expr: absent(up{job=~".*backend.*", namespace="{{ .Release.Namespace }}"} == 1)
          for: 2m
          labels: { severity: critical }
          annotations:
            summary: "Không còn pod backend nào để Prometheus scrape"
{{- end }}
```

> `for:` để không alert vì vài giây chập chờn. `runbook_url` dẫn thẳng tới
> mục trong RUNBOOK, để người nhận alert lúc 3 giờ sáng biết phải làm gì.

```powershell
helm upgrade lineage deploy/helm/lineage -n lineage -f deploy/helm/lineage/values-dev.yaml `
  --set metrics.serviceMonitor.enabled=true
```

Mở http://localhost:9090/alerts, tìm nhóm `lineage-backend`.

---

## 11. Phá hệ thống và RUNBOOK

*Phần quan trọng nhất cho phỏng vấn. Giới hạn: 3 giờ.*

Mỗi sự cố ghi vào `RUNBOOK.md` ở gốc repo theo mẫu dưới, **viết ngay lúc
đang xử lý**, đừng để cuối ngày mới nhớ lại. Mở Grafana song song để chụp
màn hình dashboard lúc sự cố xảy ra.

### Mẫu

```markdown
## OOMKill backend

**Triệu chứng:** pod restart liên tục, p95 trên dashboard có lỗ hổng, alert ... kêu
**Lần ra:** `kubectl describe pod` → `Last State: Terminated, Reason: OOMKilled, Exit Code: 137`
**Nguyên nhân gốc:** limit 128Mi < bộ nhớ cần để import langchain (~xxx Mi, đo bằng `kubectl top pod`)
**Xử lý:** nâng limit trong values, `helm upgrade`
**Phòng ngừa:** đặt limit theo số đo thật + 30% dư, không đoán
**Thời gian:** phát hiện 2 phút, xử lý 5 phút
```

> `kubectl top` cần **metrics-server**, mà kubeadm không cài sẵn. Muốn dùng
> thì cài chart `metrics-server` với tham số `--kubelet-insecure-tls` (vì
> chứng chỉ kubelet do kubeadm tự ký), hoặc xem RAM trên Grafana.

### Bảy sự cố, sắp theo giá trị khi phỏng vấn

**1. Reboot.** Đã làm ở mục 5.5. Chép kết quả vào đây.

**2. Postgres chết; readiness làm đúng việc.**

```powershell
kubectl -n lineage scale statefulset postgres --replicas=0
kubectl -n lineage get pods -w     # backend 0/1 READY nhưng KHÔNG restart
curl.exe -i http://lineage.local/health/ready
kubectl -n lineage scale statefulset postgres --replicas=1
```

Bằng chứng sống cho thiết kế ở mục 1.4a: *liveness không check DB, nên
không có vòng restart.*

**3. Worker node chết.**

```powershell
kubectl -n lineage get pods -o wide        # ghi lại pod nào trên node nào
multipass stop k8s-w2                       # giống mất điện một máy thật
kubectl get nodes -w
```

Ghi **thời gian**: node chuyển `NotReady` sau bao lâu, alert
`KubeNodeNotReady` kêu sau bao lâu, pod trên node đó **bao lâu sau mới được
dời** (mặc định ~5 phút, do toleration `node.kubernetes.io/unreachable`
300 giây).

Nếu Postgres nằm trên node vừa tắt, nó **không** tự dời được, vì PVC
`local-path` gắn chặt vào ổ đĩa của node đó. Đây là bài học lớn nhất về
storage: *cluster nhiều node mà storage chỉ nằm trên một node thì DB vẫn là
điểm chết duy nhất.* Ghi kỹ, kèm hướng giải quyết thật (storage phân tán
như Longhorn/Ceph, hoặc DB managed như RDS).

```powershell
multipass start k8s-w2
```

**4. OOMKill.**

```powershell
helm upgrade lineage deploy/helm/lineage -n lineage -f deploy/helm/lineage/values-dev.yaml `
  --set metrics.serviceMonitor.enabled=true --set backend.resources.limits.memory=128Mi
kubectl -n lineage get pods -w
kubectl -n lineage describe pod <ten-pod>     # OOMKilled, exit code 137
```

Ghi: vì sao **137** (128 + 9 = SIGKILL). Sau đó `helm rollback`.

**5. ImagePullBackOff khi deploy sai.**

```powershell
helm upgrade lineage deploy/helm/lineage -n lineage -f deploy/helm/lineage/values-dev.yaml `
  --set metrics.serviceMonitor.enabled=true --set backend.image.tag=khong-ton-tai
kubectl -n lineage get pods -w
```

`helm upgrade` vẫn báo thành công, pod mới kẹt `ImagePullBackOff`, **nhưng
pod cũ vẫn phục vụ bình thường**: nhờ rolling update + readiness, pod mới
chưa ready thì pod cũ chưa bị gỡ. Sửa bằng `helm rollback`.

**6. Xoá pod đang chạy.**

```powershell
kubectl -n lineage delete pod -l app.kubernetes.io/name=backend --wait=false
```

Chạy song song một vòng lặp `curl` (ví dụ
`while ($true) { curl.exe -s -o NUL -w "%{http_code} " http://lineage.local/health; Start-Sleep -Milliseconds 300 }`)
xem có request lỗi không. So sánh `replicas: 2` với `replicas: 1`.

**7. Đầy đĩa.**

```powershell
kubectl -n lineage exec -it postgres-0 -- bash -c "fallocate -l 1800M /var/lib/postgresql/data/rac.bin; df -h /var/lib/postgresql/data"
```

Bạn sẽ thấy PVC "2Gi" **không thực sự giới hạn** dung lượng: `local-path`
dùng chung đĩa của node. Ghi lại phát hiện này (*quota PVC phụ thuộc storage
driver; local-path không enforce*) có giá trị hơn việc làm đầy đĩa thành
công. Dọn bằng `rm` file vừa tạo.

---

## 12. Tuỳ chọn: nâng version, ArgoCD

Chỉ làm khi mục 1–11 đã xong và RUNBOOK có ít nhất 4 mục.

### 12.1. Nâng cluster 1.35 → 1.36 (bài CKA, ~60 phút)

Control plane trước:

```bash
# multipass shell k8s-cp
sudo sed -i 's/v1.35/v1.36/' /etc/apt/sources.list.d/kubernetes.list
sudo apt-get update
apt-cache madison kubeadm | head -3          # xem bản 1.36.x chính xác

sudo apt-mark unhold kubeadm
sudo apt-get install -y kubeadm=1.36.X-*     # thay X
sudo apt-mark hold kubeadm

sudo kubeadm upgrade plan
sudo kubeadm upgrade apply v1.36.X
```

```powershell
kubectl drain k8s-cp --ignore-daemonsets
```

```bash
# vẫn trong k8s-cp
sudo apt-mark unhold kubelet kubectl
sudo apt-get install -y kubelet=1.36.X-* kubectl=1.36.X-*
sudo apt-mark hold kubelet kubectl
sudo systemctl daemon-reload && sudo systemctl restart kubelet
```

```powershell
kubectl uncordon k8s-cp
```

Rồi **từng worker một**, không bao giờ cả hai cùng lúc:

```powershell
kubectl drain k8s-w1 --ignore-daemonsets --delete-emptydir-data
```

```bash
# multipass shell k8s-w1: đổi repo, nâng kubeadm như trên, rồi
sudo kubeadm upgrade node
# nâng kubelet + kubectl như trên, restart kubelet
```

```powershell
kubectl uncordon k8s-w1
# lặp lại với k8s-w2
kubectl get nodes        # cột VERSION toàn bộ v1.36.X
```

Ghi vào RUNBOOK: thứ tự nâng, vì sao phải `drain`, app có gián đoạn lúc
drain không. Câu trả lời phụ thuộc vào việc backend có 2 replica nằm trên 2
worker khác nhau hay không.

Thêm một kiểm tra:

```bash
sudo kubeadm certs check-expiration
```

Chứng chỉ kubeadm hết hạn sau **1 năm**, và `kubeadm upgrade` tự gia hạn
chúng. Ghi vào RUNBOOK: *cluster không nâng version trong 1 năm thì đúng
ngày cert hết hạn, apiserver từ chối mọi kết nối.* Sự cố này hay xảy ra ở
các công ty thật.

### 12.2. ArgoCD (GitOps)

```powershell
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v2.14.11/manifests/install.yaml
kubectl -n argocd wait --for=condition=available deploy --all --timeout=300s

kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" |
  % { [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($_)) }

kubectl -n argocd port-forward svc/argocd-server 8080:443
```

Kế hoạch gốc tách repo manifest riêng. Ở quy mô lab, **dùng chung repo,
thư mục `deploy/helm/`**, và ghi trade-off vào README: *tách repo giúp phân
quyền và tránh vòng lặp CI (commit đổi tag lại kích hoạt CI); dùng chung
thì đơn giản hơn với 1 người.*

**CI ghi tag cho ArgoCD.** Thêm vào cuối job trong `image.yml`, và đổi
`permissions.contents` thành `write`:

```yaml
      - name: Ghi tag mới cho ArgoCD
        # Ghi đè nguyên file thay vì sed vào values-*.yaml: file chỉ chứa
        # image nên không sửa nhầm dòng "tag:" nào khác.
        run: |
          cat > deploy/helm/lineage/values-image.yaml <<EOF
          backend:
            image:
              repository: ${{ steps.meta.outputs.image }}
              tag: "${{ steps.meta.outputs.tag }}"
          EOF
          git config user.name "github-actions"
          git config user.email "github-actions@users.noreply.github.com"
          git add deploy/helm/lineage/values-image.yaml
          git commit -m "deploy: backend ${{ steps.meta.outputs.tag }}"
          git push
```

`paths-ignore: ["deploy/**", ...]` ở đầu workflow đảm bảo commit này không
kích hoạt lại chính nó. Tạo sẵn `values-image.yaml` với image hiện tại và
commit trước lần chạy đầu tiên.

> ⚠️ Nếu `main` có branch protection thì `GITHUB_TOKEN` không push được. Khi
> đó cho job push sang nhánh `deploy`, và trỏ `targetRevision` vào nhánh đó.

`deploy/argocd/application.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: lineage
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/huydqhust2201-create/data-lineage.git
    targetRevision: main
    path: deploy/helm/lineage
    helm:
      # values-image.yaml đặt SAU để đè tag mặc định
      valueFiles:
        - values-dev.yaml
        - values-image.yaml
      parameters:
        - name: metrics.serviceMonitor.enabled
          value: "true"
  destination:
    server: https://kubernetes.default.svc
    namespace: lineage
  syncPolicy:
    automated:
      prune: true        # xoá khỏi Git thì xoá khỏi cluster
      selfHeal: true     # ai kubectl edit tay, ArgoCD kéo về như Git
```

```powershell
helm uninstall lineage -n lineage       # giao quyền quản lý cho ArgoCD
kubectl apply -f deploy/argocd/application.yaml
```

Thử `selfHeal`: `kubectl -n lineage scale deploy <ten-deploy-backend> --replicas=5`,
rồi xem ArgoCD tự đưa về số replica trong Git.

> Cluster nằm trên máy bạn nên ArgoCD **kéo** từ GitHub về; GitHub không
> cần đẩy được vào máy bạn. Đó là ưu điểm của mô hình pull trong GitOps so
> với CD kiểu SSH đang dùng: cluster không cần mở cửa nào ra ngoài.

---

## 13. Cắt gì khi chậm

Cắt theo thứ tự từ trên xuống:

1. ArgoCD (12.2): ghi vào README phần "kế hoạch tiếp theo".
2. Nâng version (12.1).
3. Frontend trên K8s.
4. etcd **restore**: giữ snapshot, bỏ restore.
5. Loki + Alloy (10.4–10.5): giữ Prometheus, dashboard và alert rule.
6. Sự cố 5, 6, 7 trong RUNBOOK.

**Không cắt:** cluster kubeadm 3 node, mạng IP tĩnh + bằng chứng reboot,
Helm chart, probe + resource limit, ServiceMonitor + alert rule, RUNBOOK ít
nhất 3 mục (reboot, Postgres chết, node chết).

---

## 14. Lỗi hay gặp

| Triệu chứng | Nguyên nhân thường gặp |
|---|---|
| `$'\r': command not found` khi chạy script | File có xuống dòng CRLF. Xem mục 1.3 |
| `multipass networks` không có `k8snet` | Driver không phải `hyperv`, hoặc dịch vụ Multipass chưa nhận switch mới: `Restart-Service Multipass` |
| Pod control plane restart vài phút một lần | `SystemdCgroup` vẫn `false` |
| `kubeadm init` dừng ở preflight | VM control plane dưới 2 CPU hoặc ~1,7 GB RAM |
| Node `NotReady` mãi sau khi cài Calico | `calico-node` chưa Running: `kubectl -n kube-system describe pod -l k8s-app=calico-node` |
| Pod ở hai node không gọi được nhau | Calico bắt nhầm `eth0`: kiểm tra `IP_AUTODETECTION_METHOD=interface=eth1` |
| `INTERNAL-IP` của node không phải `192.168.56.x` | Thiếu `--node-ip` trong `/etc/default/kubelet` |
| Reboot Windows xong `kubectl` timeout | `ping 192.168.56.10`. Nếu `vEthernet (k8snet)` mất IP thì chạy lại `New-NetIPAddress` (mục 2) |
| `kubeadm join` báo token không hợp lệ | Token hết hạn sau 24 giờ: `kubeadm token create --print-join-command` |
| PVC kẹt `Pending` | Chưa có StorageClass mặc định (mục 6.1) |
| Service LoadBalancer kẹt `<pending>` | MetalLB chưa có `IPAddressPool` / `L2Advertisement` |
| `ImagePullBackOff` với image GHCR | Package vẫn Private, hoặc tên image có chữ hoa |
| CI push GHCR lỗi "repository name must be lowercase" | Thiếu `${GITHUB_REPOSITORY_OWNER,,}` |
| Backend `CrashLoopBackOff` ngay khi start | Thiếu biến trong Secret: `kubectl logs --previous` |
| Backend `Running` nhưng `0/1 READY` mãi | `/health/ready` không tới DB: `DATABASE_URL` sai host (phải là tên Service Postgres, không phải `localhost` hay `db`) |
| Ingress 404 mọi đường dẫn | Thiếu `ingressClassName: nginx`, hoặc chưa sửa file hosts |
| ServiceMonitor có mà Prometheus không thấy target | Thiếu 3 dòng `...SelectorNilUsesHelmValues: false`, `port:` ghi số thay vì tên, hoặc nhãn Service không khớp (xem bẫy nhãn mục 9.1) |
| Máy đơ | Hết RAM: đóng trình duyệt; tạm `multipass stop` các VM không dùng |

Bất cứ lúc nào: `kubectl get events -n <ns> --sort-by=.lastTimestamp` thường
chỉ ra vấn đề nhanh hơn đọc log.

Dựng lại từ đầu:

```powershell
multipass delete k8s-cp k8s-w1 k8s-w2
multipass purge
```

---

## 15. Sản phẩm cuối và CV

```
deploy/
├── kubeadm/                # node-prep.sh, metallb-pool.yaml
├── raw/                    # manifest thô (giữ lại để thấy quá trình)
├── helm/lineage/           # chart + values-dev / values-prod
├── monitoring/             # values cho kps, loki, alloy
└── argocd/                 # nếu làm 12.2
.github/workflows/image.yml
RUNBOOK.md                  # tối thiểu 3, lý tưởng 7 sự cố
README.md                   # thêm sơ đồ kiến trúc + mục "Đã quyết định gì, vì sao"
```

Dòng CV **trung thực** sau 2 ngày. Chỉ giữ phần nào bạn đã thật sự làm:

> **Lineage AI Platform — Kubernetes** · Tự dựng cluster Kubernetes 3 node
> bằng kubeadm trên Hyper-V (containerd, Calico, MetalLB, ingress-nginx);
> thiết kế mạng hai card với IP tĩnh để cluster sống sót qua reboot. Migrate
> ứng dụng từ Docker Compose sang Helm chart (StatefulSet + PVC, liveness/
> readiness/startup probe, resource limit), image build bằng GitHub Actions
> đẩy lên GHCR. Giám sát bằng kube-prometheus-stack (ServiceMonitor,
> PrometheusRule tự viết cho p95 và tỉ lệ 5xx), log tập trung qua Loki +
> Alloy. Thực hành etcd snapshot/restore; chủ động gây sự cố (mất node,
> OOMKill, mất DB, reboot) và viết runbook phân tích nguyên nhân gốc.
> *(Nâng version cluster bằng kubeadm upgrade; GitOps với ArgoCD.)*

Khi bị hỏi "cluster này chạy ở đâu", trả lời đúng là **"lab tự dựng trên
máy cá nhân"**. Không cần giả vờ là production. RUNBOOK mới là thứ chứng
minh bạn biết vận hành.
