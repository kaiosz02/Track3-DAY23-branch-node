 Dưới đây là tổng quan toàn bộ những công việc bạn cần thực hiện trong dự án Day 08 Lab — LangGraph Agentic Orchestration.
  ──────
  ### 🎯 Mục tiêu dự án

  Xây dựng một hệ thống Support-Ticket Agent hoàn chỉnh chuẩn production bằng LangGraph, bao gồm:

  • Quản lý trạng thái đồ thị (State Management).
  • Điều hướng luồng có điều kiện (Conditional Routing).
  • Vòng lặp thử lại có giới hạn (Bounded Retry Loop & Dead-letter handling).
  • Phê duyệt của con người đối với các tác vụ rủi ro (Human-in-the-Loop Approval).
  • Lưu trữ và phục hồi trạng thái (Persistence / Checkpointing).
  • Tích hợp LLM thực tế (Structured Output & Grounded Generation).
  • Thu thập số liệu đánh giá (Metrics) và viết báo cáo (Lab Report).
  ──────
  ### 📊 Luồng hoạt động của đồ thị (Target Graph Flow)

    START -> intake -> classify -> [route_after_classify]
      ├─ simple       ──> answer ──> finalize ──> END
      ├─ tool         ──> tool ──> evaluate ──> [route_after_evaluate]
      │                             ├─ success ──> answer ──> finalize ──> END
      │                             └─ needs_retry ──> retry ──> [route_after_retry]
      │                                                 ├─ attempt < max ──> tool (loop)
      │                                                 └─ attempt >= max ──> dead_letter ──> finalize ──> END
      ├─ missing_info ──> clarify ──> finalize ──> END
      ├─ risky        ──> risky_action ──> approval ──> [route_after_approval]
      │                                     ├─ approved ──> tool ──> evaluate ──> ...
      │                                     └─ rejected ──> clarify ──> finalize ──> END
      └─ error        ──> retry ──> [route_after_retry] ──> ...
  ──────
  ### 📝 Chi tiết các công việc cần làm (Theo từng giai đoạn)

  #### 1. Cấu hình môi trường & LLM API Key

  • Tạo file .env từ .env.example và điền API key (hỗ trợ GEMINI_API_KEY, OPENAI_API_KEY, hoặc ANTHROPIC_API_KEY).
  • Kiểm tra helper tạo LLM trong llm.py.
  ──────
  #### 2. Phase 1: Mở rộng State Schema & Cài đặt các Node (30 điểm)

  • **state.py**:
      • Bổ sung các trường còn thiếu vào AgentState như evaluation_result, pending_question, proposed_action, approval.
      • Thiết lập đúng loại cập nhật (overwrite giá trị hay append dạng Annotated[list, add]).
  • **nodes.py** (Cài đặt 10 nodes có TODO):
      • classify_node: Bắt buộc dùng LLM với .with_structured_output() để phân loại ý định người dùng thành: risky, tool, missing_info, error, simple
      (theo thứ tự ưu tiên).
      • tool_node: Thực thi mock tool và mô phỏng lỗi tạm thời khi gặp route error.
      • evaluate_node: Đánh giá kết quả trả về từ tool (success hoặc needs_retry). Khuyến khích dùng LLM-as-judge.
      • answer_node: Bắt buộc dùng LLM sinh câu trả lời hoàn chỉnh dựa trên kết quả tool và ngữ cảnh.
      • ask_clarification_node: Sinh câu hỏi yêu cầu người dùng làm rõ khi câu hỏi thiếu thông tin.
      • risky_action_node: Chuẩn bị hành động rủi ro cần người phê duyệt.
      • approval_node: Mock phê duyệt (hoặc tích hợp interrupt() cho HITL thực tế).
      • retry_or_fallback_node: Tăng biến đếm số lần attempt và ghi log lỗi vào errors.
      • dead_letter_node: Xử lý khi vượt quá số lần retry tối đa (max_attempts).
      • finalize_node: Ghi lại audit event cuối cùng trước khi kết thúc.

  ──────
  #### 3. Phase 2: Cài đặt Routing & Lắp ráp Đồ thị (35 điểm)

  • **routing.py**:
      • Cài đặt 4 hàm điều hướng:
          1. route_after_classify: Điều hướng từ kết quả classify sang node kế tiếp.
          2. route_after_evaluate: needs_retry ➔ retry, ngược lại ➔ answer.
          3. route_after_retry: attempt < max_attempts ➔ tool, ngược lại ➔ dead_letter.
          4. route_after_approval: approved ➔ tool, rejected ➔ clarify.

  • **graph.py**:
      • Khởi tạo StateGraph(AgentState).
      • Đăng ký 11 nodes.
      • Nối các cạnh cố định (add_edge) và cạnh điều kiện (add_conditional_edges).
      • Đảm bảo mọi nhánh đều đi qua finalize ➔ END.
      • Biên dịch đồ thị cùng checkpointer.

  ──────
  #### 4. Phase 3: Lưu trữ & Phục hồi Trạng thái (Persistence) (10 điểm)

  • **persistence.py**:
      • Cài đặt SqliteSaver (dùng thư viện langgraph-checkpoint-sqlite) với chế độ WAL mode khi chọn kind="sqlite".

  ──────
  #### 5. Phase 4: Báo cáo & Đánh giá Metrics (25 điểm)

  • **report.py**:
      • Cài đặt hàm render_report() để tự động tổng hợp kết quả chạy kịch bản thành Markdown dựa trên lab_report_template.md.
  • Kiểm thử & Xuất kết quả:
      • Chạy make run-scenarios để chạy qua 7 kịch bản mẫu trong scenarios.jsonl và xuất ra file outputs/metrics.json.
      • Chạy make grade-local để kiểm tra tính hợp lệ của metrics.json.
      • Hoàn thiện file báo cáo tại reports/lab_report.md.

  ──────
  #### 6. Phase 5: Tính năng mở rộng để đạt 90–100 điểm

  Chọn làm thêm ít nhất một trong các phần mở rộng:

  • LLM-as-judge: Dùng LLM đánh giá chất lượng kết quả tool trong evaluate_node.
  • Real HITL (Human-in-the-loop): Dùng interrupt() của LangGraph khi có cờ LANGGRAPH_INTERRUPT=true.
  • Graph Mermaid Diagram: Xuất sơ đồ Mermaid trực quan bằng graph.get_graph().draw_mermaid().
  • Time travel / Crash recovery: Minh họa việc phục hồi state từ checkpoint SQLite.
  ──────
  ### 📋 Bảng tiêu chí chấm điểm (Rubric)

   Hạng mục                    |                       Điểm | Tiêu chí đánh giá
  -----------------------------|----------------------------|--------------------------------------------------------------------------------------------
   Architecture & state schema |                         15 | Khai báo AgentState chuẩn typed, đúng reducer, bổ sung đầy đủ trường cần thiết
   Graph construction & wiring |                         15 | Đăng ký đủ node, nối cạnh chính xác, đồ thị compile thành công
   LLM integration             |                         15 | classify_node và answer_node gọi LLM thật (không hard-code hay chỉ dùng regex/keyword)
   Graph behavior              |                         20 | Vượt qua tất cả các scenarios, retry có chặn trên, HITL hoạt động, mọi luồng đều terminate
   Persistence & recovery      |                         10 | Hỗ trợ checkpointer (Memory/SQLite), quản lý thread_id
   Metrics & tests             |                         15 | Tất cả unit test pytest đều pass, metrics.json hợp lệ, grade-local thành công
   Report & demo               |                         10 | Điền đầy đủ báo cáo phân tích kiến trúc, lỗi và hướng cải tiến
  ──────
  ### 🛠️ Các lệnh thường dùng

    # 1. Chạy unit tests
    pytest

    # 2. Chạy 7 kịch bản đánh giá & xuất metrics.json
    python -m langgraph_agent_lab.cli run-scenarios --config configs/lab.yaml --output outputs/metrics.json

    # 3. Kiểm tra tính hợp lệ của file metrics
    python -m langgraph_agent_lab.cli validate-metrics --metrics outputs/metrics.json
  ──────
  │ Bạn có muốn bắt đầu từng bước từ việc hoàn thiện State schema trong state.py và các Nodes trong nodes.py ngay bây giờ không?