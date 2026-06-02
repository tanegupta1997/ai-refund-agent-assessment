import type {
  AgentLog,
  ChatRequest,
  ChatResponse,
  PaginatedResponse,
  RefundRequest,
} from "@/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const ADMIN_SECRET =
  process.env.NEXT_PUBLIC_ADMIN_SECRET || "changeme";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `Request failed: ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) message = body.detail;
    } catch {
      // ignore parse errors
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export async function sendChatMessage(
  request: ChatRequest
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return handleResponse<ChatResponse>(res);
}

export async function fetchLogs(
  page: number,
  pageSize: number,
  conversationId?: string
): Promise<PaginatedResponse<AgentLog>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (conversationId) params.set("conversation_id", conversationId);
  const res = await fetch(`${API_BASE}/admin/logs?${params}`, {
    headers: { "x-admin-secret": ADMIN_SECRET },
  });
  return handleResponse<PaginatedResponse<AgentLog>>(res);
}

export async function fetchLogDetail(logId: string): Promise<AgentLog> {
  const res = await fetch(`${API_BASE}/admin/logs/${logId}`, {
    headers: { "x-admin-secret": ADMIN_SECRET },
  });
  return handleResponse<AgentLog>(res);
}

export async function fetchRefundRequests(
  page: number,
  pageSize: number,
  decision?: string
): Promise<PaginatedResponse<RefundRequest>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (decision) params.set("decision", decision);
  const res = await fetch(`${API_BASE}/admin/refund-requests?${params}`, {
    headers: { "x-admin-secret": ADMIN_SECRET },
  });
  return handleResponse<PaginatedResponse<RefundRequest>>(res);
}

export async function fetchEscalations(): Promise<{
  count: number;
  items: RefundRequest[];
}> {
  const res = await fetch(`${API_BASE}/admin/escalations`, {
    headers: { "x-admin-secret": ADMIN_SECRET },
  });
  return handleResponse<{ count: number; items: RefundRequest[] }>(res);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function fetchCustomers(
  page: number,
  pageSize: number
): Promise<PaginatedResponse<any>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  const res = await fetch(`${API_BASE}/admin/customers?${params}`, {
    headers: { "x-admin-secret": ADMIN_SECRET },
  });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return handleResponse<PaginatedResponse<any>>(res);
}
