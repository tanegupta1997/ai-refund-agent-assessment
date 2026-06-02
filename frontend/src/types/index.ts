export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  verdict?: "approved" | "denied" | "escalated" | null;
  refund_request_id?: string | null;
  injection_detected?: boolean;
}

export interface ChatRequest {
  conversation_id?: string;
  message: string;
  conversation_history: Array<{
    role: string;
    content: string;
  }>;
}

export interface ChatResponse {
  conversation_id: string;
  reply: string;
  verdict: "approved" | "denied" | "escalated" | null;
  refund_request_id: string | null;
  needs_clarification: boolean;
  injection_detected: boolean;
}

export interface RefundRequest {
  refund_request_id: string;
  customer_id: string;
  order_id: string;
  requested_amount: number;
  reason_category: string;
  decision: string;
  decision_reasons: string[];
  created_at: string;
  decided_at: string | null;
}

export interface AgentLog {
  log_id: string;
  conversation_id: string;
  timestamp: string;
  user_message: string;
  parsed_intent: Record<string, unknown> | null;
  tool_calls: Array<{
    tool: string;
    args: Record<string, unknown>;
    result_summary: string;
  }> | null;
  policy_input: Record<string, unknown> | null;
  policy_decision: Record<string, unknown> | null;
  final_response: string | null;
  injection_flags: string[] | null;
  latency_ms: number | null;
  refund_request_id: string | null;
  verdict: string | null;
  injection_detected: boolean;
}

export interface PaginatedResponse<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}
