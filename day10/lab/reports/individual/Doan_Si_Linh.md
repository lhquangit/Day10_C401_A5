# Báo cáo cá nhân — Lab Day 10

**Họ và tên:** Đoàn Sĩ Linh  
**Vai trò:** Cleaning & Quality Owner  
**Độ dài:** ~450 từ

---

## 1. Phụ trách

Trong Lab Day 10, tôi chịu trách nhiệm chính về phần xử lý và làm sạch dữ liệu trong file [cleaning_rules.py](day10/lab/transform/cleaning_rules.py). Công việc của tôi tập trung vào việc chuyển đổi dữ liệu thô (raw export) thành dữ liệu sạch (cleaned snapshot) sẵn sàng để vector hóa, đồng thời thiết lập cơ chế cách ly (quarantine) cho các bản ghi không đạt chuẩn nghiệp vụ. 

Tôi đã phối hợp chặt chẽ với Ingestion Owner để hiểu cấu trúc file CSV bẩn và với Embed Owner để thống nhất định dạng output giúp đảm bảo tính idempotent của toàn bộ pipeline.

**Bằng chứng:** Các logic xử lý quan trọng trong `cleaning_rules.py` như `clean_rows`, `_stable_chunk_id`, và các rule mở rộng như `stale_source_marker`, `low_text_quality` đều được tôi trực tiếp triển khai và kiểm thử qua các run `local-check` và `inject-bad`.

---

## 2. Quyết định kỹ thuật

Quyết định kỹ thuật quan trọng nhất tôi thực hiện là **thiết lập cơ chế `chunk_id` ổn định (stable IDs)** dựa trên hash nội dung thay vì dùng số thứ tự (`seq`). 

Trong phiên bản đầu tiên, `chunk_id` dễ bị thay đổi nếu thứ tự dòng trong raw CSV thay đổi, dẫn đến việc ChromaDB tạo ra các vector trùng lặp không đáng có. Tôi đã đổi sang dùng hash SHA-256 từ bộ 3: `doc_id + effective_date + normalized_text`. Quyết định này giúp đảm bảo tính **idempotency**: dù chạy lại pipeline bao nhiêu lần trên cùng một bộ dữ liệu, các ID vẫn giữ nguyên, giúp tiết kiệm tài nguyên và bảo trì tính nhất quán cho Vector DB.

Ngoài ra, tôi cũng triển khai rule **"fix fact bẩn có chủ đích"** cho trường hợp refund. Thay vì loại bỏ hoàn toàn các dòng chứa thông tin cũ "14 ngày", tôi chọn sửa chúng về "7 ngày" theo đúng canonical source, giúp giữ lại coverage dữ liệu mà vẫn đảm bảo tính chính xác cho Agent.

---

## 3. Sự cố / anomaly

Sự cố đáng chú ý nhất là khi parse timestamp `exported_at`. Ban đầu pipeline liên tục quarantine dữ liệu hợp lệ vì format ISO có timezone (`+07:00` hoặc `Z`) không khớp với regex cũ. 

Tôi đã xử lý bằng cách sử dụng `datetime.fromisoformat()` và thêm logic chuẩn hóa hậu tố `Z` về `+00:00`. Việc này giúp pipeline hoạt động bền bỉ hơn với các biến thể của chuẩn ISO 8601 mà không cần phải hard-code quá nhiều regex phức tạp.

---

## 4. Before/after

**Log:** Trong run `inject-bad` (trước khi thêm rule), nhiều bản ghi rác vẫn lọt vào cleaned data. Sau khi tôi thêm rule `stale_source_marker` và `low_text_quality`, log của run `local-check` đã báo cáo chính xác:
- `cleaned_records=5`
- `quarantine_records=5`
Điều này chứng minh bộ lọc đã hoạt động hiệu quả, ngăn chặn được 50% dữ liệu bẩn.

**CSV:** File [quarantine_local-check.csv](day10/lab/artifacts/quarantine/quarantine_local-check.csv) liệt kê rõ các lý do `low_text_quality` và `stale_source_marker`, cung cấp bằng chứng minh bạch cho team Monitoring theo dõi chất lượng nguồn dữ liệu.

---

## 5. Cải tiến thêm 2 giờ

Nếu có thêm 2 giờ, tôi sẽ triển khai thêm cơ chế **Schema Validation tự động** sử dụng Pydantic hoặc Cerberus thay vì dùng các hàm `if-else` thủ công. Điều này sẽ giúp code sạch hơn, dễ mở rộng khi `data_contract` thay đổi và tự động hóa việc sinh báo cáo lỗi chi tiết cho từng field.
