# 📋 NHẬT KÝ PHÂN CÔNG CÔNG VIỆC (WORKLOGS)

**Dự án:** Day 08 — LangGraph Support-Ticket AI Agent Lab  
**Nhóm thực hiện:**
- **Thành viên 1:** Giáp Hoàng Thịnh (MSV: `2A202601492`)
- **Thành viên 2:** Hoàng Văn Quang (MSV: `2A202601334`)  
**Ngày hoàn thành:** 25/08/2026  
**Kết quả đạt được:** 100% Benchmark Pass (7/7 Scenarios), 0 Crash Guarantee, PostgreSQL Supabase Persistence.

---

## 👥 1. Phân Chia Vai Trò & Trách Nhiệm

- **👨‍💻 Thành viên 1: Giáp Hoàng Thịnh (MSV: 2A202601492)**
  - **Vai trò:** *Core Workflow & State Architect*
  - Thiết kế State Schema & Reducers (`state.py`)
  - LLM Intent Classifier với Structured Output (`classify_node`)
  - LLM Grounded Answer Generator (`answer_node`)
  - 4 Conditional Routing Functions (`routing.py`)
  - Graph Topology (11 Nodes Wiring, `graph.py`)
  - Báo cáo Lab Report Markdown (`report.py`)

- **👨‍💻 Thành viên 2: Hoàng Văn Quang (MSV: 2A202601334)**
  - **Vai trò:** *Safety, Resilience & Data Engineer*
  - Chuẩn hóa Error Model & Safe Fallback (`nodes.py`, `state.py`)
  - HITL Safety & Frozen Actions (`risky_action_node`, `approval_node`)
  - Idempotency & Bounded Retry Policy (`retry_or_fallback_node`)
  - PostgreSQL Supabase Checkpointer (`persistence.py`)
  - CI/CD Quality Gate (0 lỗi Ruff, 0 lỗi Mypy, 33/33 Pytest pass)
  - Interactive HTML Slide Deck (`presentation.html`)

---

## 🛠️ 2. Phân Công Chi Tiết Theo Các Gói Tối Ưu Hóa (Optimization Modules)

### 🔹 Giáp Hoàng Thịnh: Core Flow & LLM Intelligence
1. **Pydantic State Schema (`state.py`):**
   - Thiết kế các trường `messages`, `tool_results`, `errors`, `events` với toán tử `add`.
   - Khởi tạo hàm `initial_state()` đồng nhất cho mọi kịch bản.
2. **Intent Classification & LLM Grounding (`nodes.py`):**
   - Xây dựng prompt phân loại 5 intent với độ ưu tiên nghiêm ngặt (`risky > tool > missing_info > error > simple`).
   - Xây dựng `answer_node` tổng hợp ngữ cảnh trung thực từ kết quả thực thi công cụ.
3. **Graph Architecture & Terminal Flow (`graph.py`, `routing.py`):**
   - Khởi tạo StateGraph, đăng ký đủ 11 node và đấu nối 4 conditional edges.
   - Đảm bảo tính toàn vẹn của đồ thị: Không luồng nào bị ngắt quãng giữa chừng.
4. **Lab Report Renderer (`report.py`):**
   - Thiết kế hàm `render_report()` sinh báo cáo chuẩn format Markdown.

### 🔹 Hoàng Văn Quang: Safety, Error Policy & Enterprise Infrastructure
1. **Chuẩn Hóa Error Model (`nodes.py`, `state.py`):**
   - Tách biệt lỗi người dùng yêu cầu chẩn đoán (`route="error"`) và lỗi runtime mạng/timeout.
   - Bổ sung các trường `error_type`, `retryable`, `safe_error`, `internal_error`.
2. **HITL Security & Frozen Actions (`nodes.py`):**
   - Cấp phát `action_id` và đóng băng payload trước khi xin duyệt con người.
   - Ngăn chặn LLM thay đổi tham số API sau khi đã có quyết định phê duyệt.
   - Tạo `idempotency_key` chống trừ tiền/gửi email trùng lặp khi retry.
3. **3-Way Evaluation & Bounded Exponential Backoff (`nodes.py`, `routing.py`):**
   - Hỗ trợ 3 trạng thái: `success`, `needs_retry`, `failed_permanently`.
   - Chuyển thẳng lỗi 401/404 sang `dead_letter`, không retry lãng phí token.
   - Áp dụng giãn cách lũy thừa `0.25 * (2^attempt)` giây khi retry lỗi tạm thời.
4. **PostgreSQL Persistence & Supabase Integration (`persistence.py`):**
   - Cấu hình Connection Pool với `psycopg3` và tham số `prepare_threshold=None` tương thích Supabase Transaction Pooler (Port 6543).
   - Tự động migration schema 4 bảng checkpoint (`checkpoints`, `writes`, `blobs`, `migrations`).
5. **Quality Assurance, CI/CD Gate & Slide Deck (`presentation.html`):**
   - Đưa codebase đạt chuẩn 0 lỗi Lint (`ruff`), 0 lỗi Type (`mypy`), 33/33 tests pass (`pytest`).
   - Xây dựng slide thuyết trình tương tác dạng Single-Page HTML hiện đại.

---

## 📅 3. Nhật Ký Tiến Độ Thực Hiện

| Giai đoạn | Nội dung thực hiện | Người tham gia | Kết quả nghiệm thu |
|---|---|:---:|---|
| **Phase 1** | Khởi tạo State Schema, đọc đề bài, phân tích kiến trúc 11 nodes | Cả 2 | Hoàn thành `state.py` ban đầu & skeleton file |
| **Phase 2** | Triển khai 11 Nodes, 4 Routers, LLM Structured Output & Graph wiring | Cả 2 | 32/32 Unit Tests ban đầu pass |
| **Phase 3** | Áp dụng 6 nhóm tối ưu (Error Model, Frozen Actions, Idempotency, 3-Way Evaluate, Backoff) | Cả 2 | Không còn lỗi unhandled exception, HITL an toàn |
| **Phase 4** | Cấu hình Supabase PostgreSQL Checkpointer qua IPv4 Pooler | Hoàng Văn Quang | Dữ liệu checkpoint ghi nhận thành công trên Supabase |
| **Phase 5** | Chạy benchmark 7 scenarios, sinh metrics và hoàn thiện lab report | Cả 2 | `100% success rate` ghi vào `outputs/metrics.json` |
| **Phase 6** | Chuẩn hóa Quality Gate (Ruff, Mypy, Pytest) & dựng Slide Deck | Cả 2 | Quality Gate pass 100%, hoàn thiện `presentation.html` |

---

## 🎯 4. Kết Luận & Đánh Giá Đóng Góp

- **Giáp Hoàng Thịnh (MSV: 2A202601492):** Đóng góp 50% khối lượng công việc (Phụ trách Kiến trúc dòng chảy Agent, LLM Prompting & Formatting).
- **Hoàng Văn Quang (MSV: 2A202601334):** Đóng góp 50% khối lượng công việc (Phụ trách An toàn hệ thống, Cơ chế phục hồi lỗi, Database Persistence & Quality Gate).
- **Tổng thể:** Dự án hoàn thành xuất sắc 100% các tiêu chí kỹ thuật và sẵn sàng đưa vào vận hành thực tế.
