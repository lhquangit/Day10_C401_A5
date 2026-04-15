# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Nguyễn Đức Hải
**Vai trò:** Ingestion Owner (Sprint 1)
**Ngày nộp:** 15/04/2026
**Độ dài yêu cầu:** ~500 từ

---

## 1. Tôi phụ trách phần nào?

**File / module:**
Em đóng vai trò là **Ingestion Owner**, kiểm soát nguồn dữ liệu đầu vào của hệ thống trước khi chuyển tới bướctransform.
- Hoàn thiện Data Contract tại `docs/data_contract.md`: Khảo sát raw data, phân tích chi tiết source map (từ CSV batch export và canonical docs), đồng thời chỉ ra 6 failure modes kèm theo threshold alert (ví dụ `missing_field_quarantined`).
-  Khai báo role trên `contracts/data_contract.yaml`: Điển `owner_team: "Nguyễn Hải — Ingestion Owner (C401_A5)"` và định tuyến cảnh báo tới kênh Slack `alert_channel: "slack:#data-pipeline-alerts"`.
- Vận hành Ingestion Entrypoint: Thực thi pipeline với `python etl_pipeline.py run --run-id sprint1`, kiểm duyệt format path đầu vào, ghi chép run log, và output `manifest_sprint1.json` cũng như phân loại output logic (6 record cleaned và 4 record quarantine).

**Kết nối với thành viên khác:**
Data pipeline hoạt động nối tiếp nhau. Tôi cung cấp `raw_records` và cấu trúc `artifacts/*` ổn định. Clean Owner / Quality Owner sau đó dựa vào `cleaned_records` của tôi để so khớp rules validation. Embed Owner sẽ dùng `cleaned_csv` để push vector lên ChromaDB, và Monitoring Owner sẽ sử dụng tệp `manifest_<run_id>.json` do pipeline của tôi tạo để trích xuất `latest_exported_at` để đánh giá freshness.

**Bằng chứng:**
Tôi đã commit việc cấu hình và chạy thành công pipeline. File `artifacts/logs/run_sprint1.log`, `manifest_sprint1.json` và code config file chứng minh module Ingestion hoạt động chính xác.

---

## 2. Một quyết định kỹ thuật

**Chiến lược xử lý Quarantine thay vì Drop:**
Với các lỗi format như thiếu field (missing `effective_date`) hay doc_id lạ, tôi quyết định duy trì chiến lược "Quarantine" thay vì "Hard Drop" và ghi rõ rule vào `docs/data_contract.md`. 
Tức là, thay vì huỷ bỏ dòng lỗi, ta redirect nó sang một file riêng `quarantine_<run_id>.csv` và gán label lỗi `reason`. Vì sao? Drop ngay tại ingest sẽ làm mất tính traceability khi cần đối soát lại với source raw DB ban đầu. Nhờ đẩy sang quarantine folder, ta vẫn biết tổng `raw` có vào hệ thống, nhưng vì failure mode nào mà bị chặn. Một alert rule sẽ kích hoạt khi `quarantine_records / raw_records > 30%` để cảnh báo team rà soát lại script export (upstream).

---

## 3. Một lỗi hoặc anomaly đã xử lý



---

## 4. Bằng chứng trước / sau

Quá trình chạy lệnh pipeline `etl_pipeline.py` lấy đầu vào là `policy_export_dirty.csv`. Log chạy `artifacts/logs/run_sprint1.log` hiển thị đúng expected metric baseline:

```text
run_id=sprint1
raw_records=10
cleaned_records=6
quarantine_records=4
...
freshness_check=FAIL {"latest_exported_at": "2026-04-10T08:00:00", "age_hours": 117.497, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}
```

SLA theo freshness log báo `FAIL` đúng như thiết kế vì dữ liệu mẫu test chứa `exported_at` là 10/04/2026, cách runtime hiện tại quá SLA quy định 24h. Sự logic này bảo đảm cơ chế tracking Ingestion Timestamp hoạt động nhạy.

---

## 5. Cải tiến tiếp theo

Nếu có thêm thời gian, thay vì giới hạn `ALLOWED_DOC_IDS` hard-code string trong file Python `cleaning_rules.py`, tôi sẽ code một script load trực tiếp bảng ID này từ YAML contract (`contracts/data_contract.yaml`). Điều này biến data contract thành một source of truth tự động đồng bộ (Configuration as Code) (thỏa mãn tiêu chí Distinction d).
