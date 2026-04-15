# Data contract — Lab Day 10

> Bắt đầu từ `contracts/data_contract.yaml` — mở rộng và đồng bộ file này.
> **Owner:** Nguyễn Hải — Ingestion Owner (Sprint 1)

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| **policy_export_dirty.csv** — Export CSV từ hệ thống quản lý chính sách nội bộ (Policy Management System). Chứa chunk text đã split sẵn từ các tài liệu policy, SLA, IT FAQ, HR. | Batch CSV export → `load_raw_csv()` đọc file vào list of dict. Đường dẫn mặc định: `data/raw/policy_export_dirty.csv`. Trigger: manual hoặc schedule theo sprint. | **1) Duplicate rows:** Cùng chunk_text xuất hiện nhiều lần do export lặp (ví dụ: row 1 & 2 cùng nội dung "7 ngày làm việc"). **2) Missing fields:** `chunk_text` hoặc `effective_date` rỗng (row 5). **3) Unknown doc_id:** Export kéo nhầm catalog ngoài allowlist (ví dụ: `legacy_catalog_xyz_zzz`). | `raw_records` — tổng dòng đọc được; `quarantine_records` — dòng bị loại; alert nếu `quarantine_records / raw_records > 30%`. |
| **data/docs/*.txt** — 5 tài liệu gốc text thuần (policy_refund_v4, sla_p1_2026, it_helpdesk_faq, hr_leave_policy, access_control_sop). Đây là **canonical source of truth** được dùng để đối chiếu khi cleaning. | Tải trực tiếp từ repo / shared drive. Các file `.txt` là reference — CSV export được so sánh ngược lại với nội dung canonical để phát hiện stale data. | **1) Stale version conflict:** CSV chứa nội dung HR bản 2025 (10 ngày phép) trong khi canonical đã cập nhật lên 12 ngày phép 2026 → `effective_date < 2026-01-01` bị quarantine. **2) Stale refund window:** Policy refund v3 ghi "14 ngày làm việc" nhưng v4 canonical là "7 ngày" → cần rule fix `14→7`. **3) Date format inconsistency:** Một số dòng export dùng DD/MM/YYYY thay vì ISO YYYY-MM-DD. | `cleaned_records` — dòng pass sau clean; expectation `refund_no_stale_14d_window` halt nếu còn chunk "14 ngày" sau fix; `hr_leave_no_stale_10d_annual` halt nếu còn chunk "10 ngày phép năm". |

### Chi tiết failure mode & metric tóm tắt

| # | Failure Mode | Ảnh hưởng | Metric giám sát | Ngưỡng alert |
|---|-------------|-----------|-----------------|-------------|
| 1 | Duplicate chunk_text | Vector store chứa vector trùng → retrieval trả kết quả lặp, tốn resource | `duplicate_quarantined` (count) | > 0 là cần review |
| 2 | Missing effective_date / chunk_text | Không xác định version → embed sai hoặc thiếu nội dung | `missing_field_quarantined` | > 0 → pipeline ghi log warn |
| 3 | Unknown doc_id (ngoài allowlist) | Chunk từ nguồn lạ lọt vào KB → agent trả lời sai context | `unknown_doc_id_quarantined` | > 0 → review allowlist |
| 4 | Stale HR version (effective_date < 2026-01-01) | Thông tin phép cũ (10 ngày) conflict với chính sách mới (12 ngày) | `stale_hr_quarantined` | expectation halt |
| 5 | Stale refund window (14 ngày thay vì 7 ngày) | Agent trả lời sai cửa sổ hoàn tiền cho khách hàng | expectation `refund_no_stale_14d_window` | halt pipeline |
| 6 | Date format không chuẩn (DD/MM/YYYY) | Parse fail → quarantine nếu không normalize | `date_format_normalized` (count) | warn nếu > 20% dòng cần normalize |

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| chunk_id | string | Có | ID ổn định — hash SHA256 của `doc_id|chunk_text|seq`, prefix `doc_id_seq_`. Dùng làm Chroma upsert key. |
| doc_id | string | Có | Phải thuộc allowlist: `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy`. |
| chunk_text | string | Có | Nội dung chunk ≥ 8 ký tự. Sau clean có thể gắn tag `[cleaned: stale_refund_window]`. |
| effective_date | date | Có | Chuẩn ISO `YYYY-MM-DD`. Mọi format khác (DD/MM/YYYY) được normalize trước khi ghi. |
| exported_at | datetime | Có | Timestamp export gốc từ hệ nguồn. Dùng cho freshness check (SLA 24h). |

---

## 3. Quy tắc quarantine vs drop

> **Quarantine** (không drop): Tất cả record bị flag đều được ghi vào `artifacts/quarantine/quarantine_<run_id>.csv` kèm cột `reason`.
> Không có record nào bị **drop** hoàn toàn — mọi dòng đều có traceability.
>
> **Reasons:**
> - `unknown_doc_id` — doc_id không thuộc allowlist
> - `missing_effective_date` — effective_date rỗng
> - `invalid_effective_date_format` — không parse được ngày
> - `stale_hr_policy_effective_date` — HR cũ (< 2026-01-01)
> - `missing_chunk_text` — chunk_text rỗng
> - `duplicate_chunk_text` — trùng nội dung (giữ bản đầu)
>
> **Ai approve merge lại?** Ingestion Owner (Nguyễn Hải) review quarantine CSV. Nếu dòng bị quarantine sai (ví dụ allowlist thiếu doc_id mới), cập nhật `ALLOWED_DOC_IDS` trong `cleaning_rules.py` và re-run pipeline.

---

## 4. Phiên bản & canonical

> **Source of truth cho policy refund:**
> - File canonical: `data/docs/policy_refund_v4.txt` — version 4, cửa sổ hoàn tiền = **7 ngày làm việc**.
> - CSV export có thể chứa nội dung v3 cũ ("14 ngày") do lỗi migration → pipeline rule tự động fix `14→7` khi `apply_refund_window_fix=True`.
>
> **Source of truth cho HR leave:**
> - File canonical: `data/docs/hr_leave_policy.txt` — chính sách 2026, **12 ngày phép năm**.
> - Bản HR 2025 (10 ngày phép) bị quarantine dựa trên `effective_date < 2026-01-01`.
>
> **Versioning rule:** Cutoff date `hr_leave_min_effective_date: 2026-01-01` được định nghĩa trong `contracts/data_contract.yaml`. Có thể mở rộng sang env variable để tránh hard-code.
