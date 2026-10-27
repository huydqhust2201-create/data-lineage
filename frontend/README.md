# Lineage AI — Frontend

React 19 + TypeScript + Vite. Single-page app — không dùng `react-router-dom` để điều hướng dù có cài (`App.tsx` tự quản lý màn hình bằng state, xem [Điều hướng](#điều-hướng)).

## Kiến trúc thư mục

```
src/
├── App.tsx           # entry thật — auth gate, quản lý màn hình hiện tại, bọc 4 Provider (xem Điều hướng)
├── api/               # fetch layer qua http.ts dùng chung, 1 file / resource:
│                       # auth, database, graph, impact, review, ingest, chat,
│                       # breakingChangeAlerts, status
├── types/
│   ├── backend.ts     # mirror 1:1 src/models/schemas.py — sửa BE trước, sửa file này theo sau
│   ├── lineage.ts     # kiểu dữ liệu hiển thị trên canvas (LineageNodeData/EdgeData, khác backend.ts)
│   └── workspace.ts   # kiểu Workspace dùng cho Workspace Hub (nhóm các database của 1 user)
├── hooks/
│   ├── useGraph.ts, useReview.ts, useChat.ts, useImpact.ts, useIngest.ts, useStatus.ts
│   │                   # data-fetching hook riêng theo từng resource
│   └── GraphProvider.tsx, ReviewProvider.tsx, ChatProvider.tsx, PopupProvider.tsx
│                       # bọc useGraph/useReview/useChat bằng React Context — 1 lần fetch,
│                       # dùng chung toàn app thay vì mỗi màn hình tự gọi lại
├── adapters/backendToLineage.ts   # GraphResponse (BE) → LineageNodeData/EdgeData (canvas)
├── components/
│   ├── Sidebar.tsx      # 6 tab: overview/explorer/impact/hitl/ingest/catalog (TabType)
│   ├── OverviewDashboard.tsx, LineageExplorer.tsx, ImpactAnalysisView.tsx,
│   │   HITLDashboard.tsx, SqlIngestScanner.tsx, DataCatalogView.tsx
│   │                     # 1 component / tab, khớp Sidebar
│   ├── FloatingChatbot.tsx   # Lineage Copilot — widget nổi, KHÔNG phải 1 tab riêng
│   ├── CustomTableNode.tsx, ImpactBlastRadiusGraph.tsx   # node/canvas dùng chung cho @xyflow/react
│   ├── ExportModal.tsx, SettingsModal.tsx, BreakingChangeAlertsPanel.tsx
│   ├── intro/            # IntroductionPage.tsx (landing marketing) + leader/ (các section trang chủ)
│   ├── landing/           # LandingPage.tsx — màn đăng nhập/đăng ký thật (email+mật khẩu, Google)
│   └── workspace/         # WorkspaceManager.tsx (Workspace Hub), WorkspaceCard.tsx,
│                           # NewWorkspaceModal.tsx (tạo database mới), AccountSettingsModal.tsx
├── services/lineageEngine.ts   # tính toán phụ (risk badge, SQL preview...) từ dữ liệu đã fetch
├── utils/computeDepths.ts       # tự tính tầng (topological depth) cho layout đồ thị — không dùng elkjs/dagre
└── data/                        # mockProjects.ts, mockWorkspaces.ts — dữ liệu demo, không gọi API thật
```

## Điều hướng

Không có route URL (`/lineage`, `/impact`...) — `App.tsx` tự quản lý màn hình hiện tại bằng state, theo đúng thứ tự:

1. Chưa đăng nhập → `IntroductionPage` (landing marketing) → bấm "Đăng nhập ngay" → `LandingPage` (form đăng nhập/đăng ký + nút Google).
2. Đăng nhập xong, chưa chọn database → `WorkspaceManager` (Workspace Hub — liệt kê các database của user, tạo mới qua `NewWorkspaceModal`).
3. Đã chọn 1 database → `MainAppLayout` — `Sidebar` 6 tab (Overview/Lineage Explorer/Impact/HITL/Ingest/Data Catalog) + `FloatingChatbot` nổi ở góc màn hình, không phụ thuộc tab đang mở.

`App.tsx` bọc toàn bộ trong `<GraphProvider><ReviewProvider><ChatProvider><PopupProvider>` — đồ thị/hàng đợi HITL/chat chỉ fetch 1 lần, dùng chung giữa các tab thay vì mỗi tab tự gọi lại API.

## Auth

`LandingPage.tsx` gọi `api/auth.ts` (`register`/`login`/`loginWithGoogle`) — đăng nhập Google dùng `@react-oauth/google` (Google Identity Services), tự ẩn nút nếu chưa cấu hình `VITE_GOOGLE_CLIENT_ID` (xem `.env.example`). Token JWT trả về lưu ở `localStorage["data_lineage_token"]`; `api/http.ts` tự đính `Authorization: Bearer <token>` vào mọi request. Không còn cơ chế `X-User-Id`. Chi tiết cơ chế backend: [README gốc § Auth & Multi-tenancy](../README.md#auth--multi-tenancy).

## Nguyên tắc xuyên suốt

- **Confirmed (solid, xanh) vs Pending/Inferred (dashed, cam) luôn tách biệt** — không bao giờ gộp chung, ở mọi nơi hiển thị quan hệ dữ liệu (Lineage Explorer, Impact Analysis, HITL Dashboard, Chat).
- FE chỉ hiển thị đúng field API thật trả về — không tự bịa field/status. Vd Overview chỉ render đúng số liệu từ `GET /graph`/`GET /pending-review`, không tự thêm chỉ số giả.
- Cột hiển thị trên `CustomTableNode` chỉ là các cột **đã xuất hiện trong 1 cạnh lineage nào đó** — không phải introspect schema DB thật (BE không có quyền truy cập DB nguồn, chỉ đọc source code SQL/dbt).
- "Paste SQL" ở SQL Ingest Scanner không có endpoint riêng nhận raw text — gói nội dung dán thành 1 `File` ảo (`new File([content], path)`) rồi gọi chung `POST /ingest/upload` (multipart), không tạo thêm endpoint chỉ để nhận text.
- Ingest nhiều lần cộng dồn vào cùng 1 đồ thị theo thiết kế (xem `docs/api_contract.md` ở BE) — nút xoá đồ thị (Settings/Danger Zone, `DELETE /graph`) là lối thoát thủ công.
- Modal "Add Database" chỉ nhận Tên + Mô tả — BE không kết nối DB thật (chỉ ingest source code SQL/dbt), nên không hiển thị Connector Type/host/port/password giả.

## Layout đồ thị không dùng elkjs/dagre

`utils/computeDepths.ts` tự tính tầng (topological depth từ node gốc) cho layout — elkjs từng chiếm 597KB gzip trong 1 bản trước, quy mô đồ thị dự án này nhỏ (~10-20 bảng) nên không cần thuật toán layout nặng. Canvas render bằng `@xyflow/react`.

## Chạy dev

```bash
npm install
cp .env.example .env.local   # (tuỳ chọn) điền VITE_GOOGLE_CLIENT_ID nếu muốn bật đăng nhập Google
npm run dev        # http://127.0.0.1:5173, proxy /api và /health sang backend 127.0.0.1:8001
npm run build       # typecheck (tsc -b --noEmit) rồi build production
npm run typecheck    # chỉ typecheck, không build
```
