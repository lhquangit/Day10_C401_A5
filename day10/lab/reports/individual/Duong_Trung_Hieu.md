# Báo cáo cá nhân — mẫu GV (reference)

**Họ và tên:** Dương Trung Hiếu  
**Vai trò:** Cleaning & Quality  
**Độ dài:** ~450 từ (mẫu)

---

## 1. Phụ trách

Tôi triển khai phần kiểm định dữ liệu trong `quality/expectations.py` (bổ sung rule E7–E9) và phối hợp review logic làm sạch trong `transform/cleaning_rules.py`. Kết nối với Ingestion Owner (để nhận raw data và báo số lượng quarantine) và Embed Owner qua việc kiểm soát chất lượng file `cleaned_*.csv`, đảm bảo chỉ dữ liệu Passed mới được vector hóa.

**Bằng chứng:** Code logic E7-E9 trong file `expectations.py` và commit "Thêm ít nhất 2 expectations mới, quyết định rule nào chỉ warn, rule nào phải halt".

---

## 2. Quyết định kỹ thuật

**Halt vs warn:** Tôi chọn halt cho rule E8 (`allowed_doc_ids_only`). Nếu doc_id rác không có trong data_contract.yaml (ví dụ policy_v5_draft) lọt vào ChromaDB, Agent Day 09 sẽ lấy nhầm context gây ảo giác (hallucination) sai chính sách công ty. Trái lại, rule E7 (`no_duplicate_chunk_text`) được set là warn. Do đặc thù văn bản pháp lý thường chứa nhiều đoạn boilerplate (văn mẫu) trùng lặp, việc block cứng pipeline sẽ làm tắc nghẽn luồng xử lý không cần thiết; thay vào đó, chỉ ghi log để theo dõi.

---

## 3. Sự cố / anomaly

Trong Sprint 3, khi nhóm chạy kịch bản inject lỗi (`--run-id inject-bad`), nhóm phát hiện Agent thỉnh thoảng phản hồi dựa trên tài liệu lạ. Nguyên nhân do bộ kiểm định baseline kiểm tra `ALLOWED_DOC_IDS` quá lỏng lẻo.
Fix: Tôi thiết lập rule `allowed_doc_ids_only` đối chiếu chặt chẽ với danh sách chuẩn. Bất kỳ dòng nào vi phạm sẽ kích hoạt cơ chế `HALTED` và yêu cầu đẩy record sang quarantine.

---

## 4. Before/after

**Log:** Trước khi fix (Run ID `inject-bad`), log báo `[INFO] Expectations PASSED`. Sau khi bật rule của tôi (Run ID `hieu-quality-check`), log báo chính xác: `[WARN] Expectation failed: allowed_doc_ids_only (Severity: HALT) - invalid_doc_rows=5` → `[FATAL] Pipeline HALTED`.

**CSV:** Số lượng dòng vi phạm được cách ly thành công thể hiện qua việc file `artifacts/quarantine/quarantine_hieu-quality-check.csv` tăng từ 0 lên 5 dòng so với bản trước đó.

---

## 5. Cải tiến thêm 2 giờ

Tích hợp thư viện Pydantic vào `expectations.py` để tự động load và đối chiếu schema/allowlist động trực tiếp từ file `contracts/data_contract.yaml`, thay vì parse thủ công bằng Python cơ bản, giúp hệ thống scale linh hoạt hơn khi thêm tài liệu mới.