# Review `cleaning_rules.py` - Ver 1

Tài liệu này tổng hợp các điểm cần xem lại trong [cleaning_rules.py](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/transform/cleaning_rules.py), tập trung vào tính đúng đắn nghiệp vụ, độ ổn định khi rerun pipeline, và mức độ an toàn trước khi publish vào Chroma.

## 1. `chunk_id` chưa thật sự ổn định

**Phần đang đảm nhiệm**

- Tạo `chunk_id` cho từng row sau khi clean.
- `chunk_id` này được dùng làm `id` để `upsert` vào Chroma trong [etl_pipeline.py](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/etl_pipeline.py:154).

**Logic hiện tại**

- Hàm [_stable_chunk_id()](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/transform/cleaning_rules.py:42) tạo hash từ `doc_id | chunk_text | seq`.
- Biến `seq` tăng dần theo thứ tự các row hợp lệ khi build `cleaned`.

**Vấn đề**

- Nếu chèn thêm một row hợp lệ ở đầu file, toàn bộ `seq` phía sau đổi theo.
- Nội dung chunk có thể không đổi, nhưng `chunk_id` vẫn đổi.
- Khi đó Chroma sẽ coi các vector cũ là record khác, làm giảm tính idempotent của pipeline.

**Đề xuất sửa**

- Bỏ `seq` khỏi công thức tạo `chunk_id`.
- Tạo ID từ dữ liệu ổn định hơn như `doc_id + effective_date + normalized_text`.
- Ví dụ: hash từ `doc_id|effective_date|normalized_chunk_text`.

**Vì sao nên sửa**

- Rerun pipeline sẽ ổn định hơn.
- Tránh churn vector DB khi dữ liệu thực chất không đổi.
- Phù hợp với yêu cầu idempotency của Day 10.

## 2. Rule dedupe đang quá rộng

**Phần đang đảm nhiệm**

- Phát hiện row trùng để tránh embed lặp và làm phình collection.

**Logic hiện tại**

- Normalize `chunk_text`.
- Nếu text đã từng xuất hiện thì row sau bị đưa vào quarantine với reason `duplicate_chunk_text`.

**Vấn đề**

- Key dedupe hiện chỉ dựa vào `chunk_text`.
- Hai `doc_id` khác nhau nhưng có chung một câu boilerplate vẫn bị coi là duplicate.
- Hai version khác nhau của cùng một policy cũng có thể bị coi là duplicate dù nghiệp vụ không giống nhau.

**Đề xuất sửa**

- Ít nhất đổi dedupe key thành `doc_id + normalized_text`.
- Nếu muốn giữ cả version, dùng `doc_id + effective_date + normalized_text`.

**Vì sao nên sửa**

- Giảm false positive.
- Không làm mất chunk hợp lệ chỉ vì trùng câu giữa các tài liệu khác nhau.
- Phản ánh đúng hơn khái niệm duplicate trong ngữ cảnh business data.

## 3. Rule `effective_date_after_exported_at` cần xem lại

**Phần đang đảm nhiệm**

- Cố gắng bắt dữ liệu có mốc thời gian bị xem là "vô lý".

**Logic hiện tại**

- Parse `effective_date`.
- Parse `exported_at`.
- Nếu `effective_date > exported_at.date()` thì quarantine row đó.

**Vấn đề**

- Trong thực tế, một policy có thể được export hôm nay nhưng có hiệu lực từ tuần sau hoặc tháng sau.
- Như vậy `effective_date > exported_at` không phải lúc nào cũng là lỗi.

**Đề xuất sửa**

- Hoặc bỏ rule này.
- Hoặc chuyển nó sang expectation mức `warn`.
- Hoặc chỉ áp dụng cho một số nguồn dữ liệu mà nghiệp vụ xác nhận không được phép có hiệu lực tương lai.

**Vì sao nên sửa**

- Đây là rule dễ quarantine nhầm dữ liệu hợp lệ nhất.
- Hiện tại rule đang encode một giả định nghiệp vụ chưa được chứng minh.
- Với cleaning, chỉ nên mạnh tay với các lỗi chắc chắn sai.

## 4. Parse `exported_at` đang hơi chặt

**Phần đang đảm nhiệm**

- Xác nhận `exported_at` có đúng định dạng datetime để phục vụ rule thời gian và monitoring.

**Logic hiện tại**

- Chỉ chấp nhận `YYYY-MM-DDTHH:MM:SS`.
- Hoặc cùng định dạng nhưng có hậu tố `Z`.
- Sau đó parse bằng `datetime.strptime`.

**Vấn đề**

- Nhiều timestamp ISO hợp lệ ngoài đời có timezone offset, ví dụ:
  - `2026-04-10T08:00:00+00:00`
  - `2026-04-10T15:00:00+07:00`
- Hai dạng trên hiện tại sẽ bị quarantine dù hoàn toàn hợp lệ.

**Đề xuất sửa**

- Dùng `datetime.fromisoformat()` thay vì regex quá chặt.
- Nếu có `Z`, đổi sang `+00:00` rồi parse.

**Vì sao nên sửa**

- Pipeline bền hơn khi nguồn đổi format timestamp.
- Tránh quarantine sai toàn bộ dataset chỉ vì khác biến thể ISO.
- Đồng bộ hơn với logic freshness/monitoring.

## 5. Rule `low_text_quality` cần dùng cẩn thận

**Phần đang đảm nhiệm**

- Bắt các chunk có nội dung quá ít hoặc gần như vô nghĩa trước khi embed.

**Logic hiện tại**

- Loại các ký tự `non-content`.
- Nếu phần còn lại ngắn hơn 8 ký tự thì fail.
- Hoặc nếu số chữ cái ít hơn 6 thì fail.

**Vấn đề**

- Đây là heuristic, không phải business rule cứng.
- Một số chunk ngắn vẫn có giá trị thật, ví dụ:
  - câu ngắn nhưng đúng trọng tâm
  - thông tin SLA ngắn
  - heading hoặc FAQ answer súc tích

**Đề xuất sửa**

- Thu hẹp điều kiện bắt lỗi.
- Hoặc chỉ áp dụng cho một số `doc_id`.
- Hoặc chuyển một phần logic sang expectation mức `warn`.

**Vì sao nên sửa**

- Cleaning nên xử lý lỗi chắc chắn.
- Các rule heuristic nên đặt ở tầng signal/cảnh báo hơn là hard reject.

## 6. Rule mới nên thêm từ dữ liệu thực tế

Phần dưới đây bám trực tiếp vào dữ liệu trong thư mục `day10/lab/data`.

### 6.1. `stale_source_marker`

**Nguồn gợi ý**

- [policy_export_dirty.csv:4](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/data/raw/policy_export_dirty.csv:4)
- [policy_export_dirty.csv:8](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/data/raw/policy_export_dirty.csv:8)

**Ý tưởng**

- Nếu text chứa các marker stale rõ ràng như `policy-v3`, `lỗi migration`, `bản HR 2025`, thì quarantine.
- Với refund row, có thể strip phần note stale sau khi sửa `14 -> 7` nếu muốn giữ lại nội dung hợp lệ.

**Vì sao nên thêm**

- Hiện code sửa được fact sai, nhưng vẫn có thể giữ lại chú thích mang tính "rác vận hành" trong embedding.

### 6.2. `critical_doc_presence`

**Nguồn gợi ý**

- [test_questions.json](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/data/test_questions.json)

**Ý tưởng**

- Sau khi clean, các `doc_id` quan trọng như `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy` phải còn ít nhất 1 row.

**Vì sao nên thêm**

- Pipeline có thể pass kỹ thuật nhưng vẫn fail retrieval nếu làm sạch quá tay và xóa sạch một tài liệu quan trọng.

### 6.3. `business_anchor_per_doc`

**Nguồn gợi ý**

- [policy_refund_v4.txt:14](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/data/docs/policy_refund_v4.txt:14)
- [sla_p1_2026.txt:26](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/data/docs/sla_p1_2026.txt:26)
- [sla_p1_2026.txt:27](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/data/docs/sla_p1_2026.txt:27)
- [it_helpdesk_faq.txt:12](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/data/docs/it_helpdesk_faq.txt:12)
- [hr_leave_policy.txt:10](/Users/quanliver/Projects/AI_Vin_Learner/Lecture-Day-08-09-10/day10/lab/data/docs/hr_leave_policy.txt:10)

**Ý tưởng**

- Kiểm tra trong cleaned data còn các fact cốt lõi:
  - refund: `7 ngày`
  - P1 first response: `15 phút`
  - P1 resolution: `4 giờ`
  - lockout: `5 lần`
  - annual leave hiện hành: `12 ngày`

**Vì sao nên thêm**

- Bám rất sát tiêu chí eval và grading của bài lab.
- Chứng minh pipeline bảo toàn được dữ liệu nghiệp vụ quan trọng.

## 7. Ưu tiên sửa trước

1. Ổn định lại `chunk_id`.
2. Thu hẹp dedupe key.
3. Xem lại rule `effective_date_after_exported_at`.
4. Nới parse `exported_at`.
5. Cân nhắc hạ `low_text_quality` xuống mức nhẹ hơn.
6. Nếu cần thêm rule mới, ưu tiên `stale_source_marker`, `critical_doc_presence`, và `business_anchor_per_doc`.
