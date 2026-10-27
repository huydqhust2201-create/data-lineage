# Gate G2 — MVP — Hồ sơ nộp

> Team Baby Sharks (P-116) — DATA-04 Data Lineage Agent. Các file trong thư mục này là **bản sao chụp nhanh** (snapshot) tại thời điểm nộp Gate G2, gom lại 1 chỗ cho tiện chấm — bản gốc đang được duy trì và cập nhật liên tục tại đường dẫn gốc trong repo (link bên dưới), không phải ở đây.

## Đối chiếu 4 deliverable

| # | Yêu cầu Gate G2 | File trong thư mục này | Bản gốc trong repo |
|---|---|---|---|
| 1 | Architecture diagram — sơ đồ components, data flow | [`ARCHITECTURE.md`](ARCHITECTURE.md) | [`/ARCHITECTURE.md`](../ARCHITECTURE.md) |
| 2 | Repo ≥ 10 PR merged | *(không phải file — xác minh trực tiếp trên GitHub)* | [Danh sách PR đã merge](https://github.com/AI20K-Build-Phase-Cohort-3/P-116/pulls?q=is%3Apr+is%3Amerged) — hiện có **51 PR** |
| 3 | README.md — setup instructions, env vars, sample queries | [`README.md`](README.md) | [`/README.md`](../README.md) |
| 4 | Eval evidences — ít nhất 5 test case manual với output thực tế | [`eval/manual_test_cases.md`](eval/manual_test_cases.md) (6 test case, test trực tiếp trên UI thật, kèm [ảnh chụp màn hình](eval/manual_test_screenshots/) từng bước) + [`eval/DATA-04_Manual_Test_Cases.xlsx`](eval/DATA-04_Manual_Test_Cases.xlsx) | [`/eval/manual_test_cases.md`](../eval/manual_test_cases.md) |

## Bonus — eval tự động (không bắt buộc, đính kèm để chấm điểm chất lượng thêm)

- [`eval/pipeline_eval.md`](eval/pipeline_eval.md) — đo Precision/Recall/F1 thật trên toàn bộ pipeline (parser + LLM fallback), 12 fixture, đạt 85%/85%, vượt mục tiêu SMART ≥80% trong `docs/PRD.md`.

## Lưu ý

- Video Demo + Pitch Deck đã nộp qua link riêng ngoài repo (xem README.md mục Deliverables).
- Sửa/cập nhật nội dung thì sửa ở **bản gốc** (cột phải bảng trên), không sửa trực tiếp trong `gate-g2/` — thư mục này chỉ là ảnh chụp tại thời điểm nộp, không tự đồng bộ lại.
