# Postmortem — DR Drill Lab 23

Theo đúng template §4 "Sau Failover: Blameless Postmortem". Blameless: câu hỏi là
"hệ thống/process nào cho phép chuyện này", không phải "ai làm sai".

## 1. Timeline (mọi dòng phải có evidence path:line)

| ISO time | Sự kiện | Evidence |
|---|---|---|
| 2026-08-25T17:51:27 | outage bắt đầu | `chaos/chaos-events.jsonl:2` |
| 2026-08-25T17:51:27 | user đầu tiên bị ảnh hưởng | `reports/drill-2-withdr.jsonl:24` |
| 2026-08-25T17:51:27 | health check alert | `reports/health-events.jsonl:1` |
| 2026-08-25T17:51:27 | operator confirm cutover | `reports/failover-events.jsonl:2` |
| 2026-08-25T17:51:27 | resolved (request đầu tiên OK từ region phụ) | `reports/drill-2-withdr.jsonl:42` |

## 2. RTO/RPO đo được vs mục tiêu — gap ở bước nào?

- RTO mục tiêu: 300s -> đo được: `29.6s` -> gap: `0s`
- RPO mục tiêu: 300s -> đo được: `10.01s` (`5` doc bị mất) -> gap: `0s`
- **Bước tốn nhiều giây nhất:** `health_check_phat_hien` — vì interval 5s và threshold 3 tốn ít nhất 15s.

## 3. Root cause (5 whys)

Không phải "vì tôi chạy chaos script". Câu hỏi: *nếu đây là outage thật, bước nào
trong runbook của tôi sẽ thất bại?*
Thiếu tự động hóa hoàn toàn có thể làm quá trình chậm. Nếu operator ngủ quên thì RTO sẽ tăng đột biến.

## 4. Action items (có owner + deadline)

| # | Action | Owner | Deadline | Giảm RTO/RPO bao nhiêu giây |
|---|---|---|---|---|
| 1 | Cải thiện health check interval | Team Infra | 2026-09-01 | 5s |
| 2 | Giảm EDGE TTL xuống 1s | Team Network | 2026-09-02 | 4s |

## 5. Ba câu hỏi bắt buộc trả lời

1. `interval * threshold` của bạn là bao nhiêu giây? Nó chiếm bao nhiêu % RTO?
   15 giây. Chiếm ~75% RTO (29.6s).
2. Nếu hạ interval xuống 1s, RTO giảm mấy giây — và bạn trả giá gì (§4 flapping)?
   RTO giảm khoảng 12 giây, nhưng trả giá bằng false positives cao, dễ bị flapping giữa 2 region nếu network chập chờn 1-2s.
3. Nếu outage kéo dài 6 giờ và region chính mất dữ liệu vĩnh viễn, `docs_lost` của
   bạn có ý nghĩa gì với khách hàng?
   5 documents sẽ mất vĩnh viễn, khách hàng sẽ không search được dữ liệu này.
