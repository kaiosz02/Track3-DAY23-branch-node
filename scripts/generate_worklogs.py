# -*- coding: utf-8 -*-
content = """# 📋 NHẬT KÝ PHÂN CÔNG CÔNG VIỆC (WORKLOGS)

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

## 📌 2. Phân Công Chi Tiết Theo 18 Tiêu Chí Checklist

| # | Hạng mục Checklist | Thành viên phụ trách | File mã nguồn liên quan | Chi tiết công việc thực hiện |
|---|---|:---:|---|---|
| **1** | State fields và reducers đúng | **Giáp Hoàng Thịnh** | `src/langgraph_agent_lab/state.py` | Thiết kế `AgentState` TypedDict, định nghĩa đúng reducers `Annotated[list, add]` cho append-only audit và overwrite cho scalars. |
| **2** | 10 Node TODO đã được implement | **Cả 2 Thành viên** | `src/langgraph_agent_lab/nodes.py` | **Thịnh:** `classify`, `answer`, `clarify`, `finalize`.<br>**Quang:** `tool`, `evaluate`, `risky_action`, `approval`, `retry`, `dead_letter`. |
| **3** | 4 Routing function hoạt động | **Giáp Hoàng Thịnh** | `src/langgraph_agent_lab/routing.py` | Viết `route_after_classify`, `route_after_evaluate`, `route_after_retry`, `route_after_approval`. |
| **4** | Graph có đủ 11 node | **Giáp Hoàng Thịnh** | `src/langgraph_agent_lab/graph.py` | Xây dựng hàm `build_graph()` với đầy đủ 11 node và liên kết fixed/conditional edges. |
| **5** | Classifier dùng LLM Structured Output | **Giáp Hoàng Thịnh** | `src/langgraph_agent_lab/nodes.py` | Tích hợp Pydantic `ClassificationResult` với `llm.with_structured_output()` và enforce priority. |
| **6** | Answer dùng LLM & grounded context | **Giáp Hoàng Thịnh** | `src/langgraph_agent_lab/nodes.py` | Prompt engineering grounded trên User Query, Tool Results, Approval Data và Safe Fallback. |
| **7** | Không hard-code sample scenarios | **Giáp Hoàng Thịnh** | `src/langgraph_agent_lab/scenarios.py` | Xử lý dữ liệu động từ file JSONL, loại bỏ hoàn toàn các điều kiện if cứng ID `S01..S07`. |
| **8** | Retry hữu hạn và dead-letter hoạt động | **Hoàng Văn Quang** | `src/langgraph_agent_lab/routing.py`<br>`src/langgraph_agent_lab/nodes.py` | Kiểm soát `attempt < max_attempts`, kích hoạt `dead_letter_node` khi quá số lần retry. |
| **9** | Risky action đi qua approval | **Hoàng Văn Quang** | `src/langgraph_agent_lab/nodes.py` | Xây dựng luồng `risky_action` → `approval` và tích hợp `interrupt()` cho HITL thật. |
| **10** | Rejected approval đi clarification | **Hoàng Văn Quang** | `src/langgraph_agent_lab/routing.py` | Xử lý trường hợp người duyệt bấm `False` → chuyển sang `clarify` mà không gọi tool. |
| **11** | Mọi route đi qua finalize | **Giáp Hoàng Thịnh** | `src/langgraph_agent_lab/graph.py` | Thiết lập topological guarantee: Mọi nhánh rẽ đều bắt buộc nối về `finalize_node -> END`. |
| **12** | Checkpointer và thread_id được sử dụng | **Hoàng Văn Quang** | `src/langgraph_agent_lab/cli.py`<br>`src/langgraph_agent_lab/persistence.py` | Quản lý `thread_id` theo từng scenario; kết nối Memory, SQLite và PostgreSQL checkpointer. |
| **13** | Có persistence / recovery evidence | **Hoàng Văn Quang** | `scripts/inspect_db.py`<br>`scripts/demo_checkpoint_postgres.py` | Tạo script kiểm tra 4 bảng checkpoint trên Supabase Postgres (`checkpoints`, `writes`, `blobs`). |
| **14** | `outputs/metrics.json` hợp lệ & có số liệu | **Hoàng Văn Quang** | `src/langgraph_agent_lab/metrics.py` | Thu thập metrics chạy thực tế (100% pass 7/7 scenarios, 7 retries, 2 interrupts). |
| **15** | `reports/lab_report.md` đã hoàn thiện | **Giáp Hoàng Thịnh** | `src/langgraph_agent_lab/report.py`<br>`reports/lab_report.md` | Tự động render Markdown Report với đầy đủ bảng biểu, số liệu và phân tích chuyên sâu. |
| **16** | Báo cáo phân tích ít nhất 2 failure modes | **Giáp Hoàng Thịnh** | `reports/lab_report.md` | Phân tích 2 lỗi: *Tool exception crash graph* và *Risky action bypass HITL approval*. |
| **17** | Không có secret trong Git | **Hoàng Văn Quang** | `.gitignore` | Cấu hình loại bỏ `.env`, `checkpoints/`, `*.db`, bảo đảm git commit sạch. |
| **18** | Không có hidden grading data | **Hoàng Văn Quang** | `.gitignore` | Đảm bảo thư mục `data/grading/` không bị đưa vào bài nộp. |

---

## 🛠️ 3. Phân Công Chi Tiết Theo Các Gói Tối Ưu Hóa (Optimization Modules)

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

## 📅 4. Nhật Ký Tiến Độ Thực Hiện

| Giai đoạn | Nội dung thực hiện | Người tham gia | Kết quả nghiệm thu |
|---|---|:---:|---|
| **Phase 1** | Khởi tạo State Schema, đọc đề bài, phân tích kiến trúc 11 nodes | Cả 2 | Hoàn thành `state.py` ban đầu & skeleton file |
| **Phase 2** | Triển khai 11 Nodes, 4 Routers, LLM Structured Output & Graph wiring | Cả 2 | 32/32 Unit Tests ban đầu pass |
| **Phase 3** | Áp dụng 6 nhóm tối ưu (Error Model, Frozen Actions, Idempotency, 3-Way Evaluate, Backoff) | Cả 2 | Không còn lỗi unhandled exception, HITL an toàn |
| **Phase 4** | Cấu hình Supabase PostgreSQL Checkpointer qua IPv4 Pooler | Hoàng Văn Quang | Dữ liệu checkpoint ghi nhận thành công trên Supabase |
| **Phase 5** | Chạy benchmark 7 scenarios, sinh metrics và hoàn thiện lab report | Cả 2 | `100% success rate` ghi vào `outputs/metrics.json` |
| **Phase 6** | Chuẩn hóa Quality Gate (Ruff, Mypy, Pytest) & dựng Slide Deck | Cả 2 | Quality Gate pass 100%, hoàn thiện `presentation.html` |

---

## 🎯 5. Kết Luận & Đánh Giá Đóng Góp

- **Giáp Hoàng Thịnh (MSV: 2A202601492):** Đóng góp 50% khối lượng công việc (Phụ trách Kiến trúc dòng chảy Agent, LLM Prompting & Formatting).
- **Hoàng Văn Quang (MSV: 2A202601334):** Đóng góp 50% khối lượng công việc (Phụ trách An toàn hệ thống, Cơ chế phục hồi lỗi, Database Persistence & Quality Gate).
- **Tổng thể:** Dự án hoàn thành xuất sắc 100% các tiêu chí kỹ thuật và sẵn sàng đưa vào vận hành thực tế.
"""

with open("reports/WORKLOGS.md", "w", encoding="utf-8") as f:
    f.write(content)
print("reports/WORKLOGS.md written successfully!")
