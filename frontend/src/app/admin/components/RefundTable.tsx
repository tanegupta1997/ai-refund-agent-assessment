"use client";

import type { RefundRequest } from "@/types";

interface RefundTableProps {
  requests: RefundRequest[];
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  decisionFilter: string;
  onDecisionFilter: (decision: string) => void;
  isLoading?: boolean;
}

const FILTERS = [
  { label: "All", value: "" },
  { label: "Approved", value: "approved" },
  { label: "Denied", value: "denied" },
  { label: "Escalated", value: "escalated" },
  { label: "Pending", value: "pending" },
];

function VerdictBadge({ decision }: { decision: string }) {
  const styles: Record<string, string> = {
    approved: "bg-green-900 text-green-300",
    denied: "bg-red-900 text-red-300",
    escalated: "bg-yellow-900 text-yellow-300",
    pending: "bg-gray-800 text-gray-400",
  };
  return (
    <span
      className={`px-2 py-0.5 rounded text-xs ${
        styles[decision] ?? "bg-gray-800 text-gray-400"
      }`}
    >
      {decision || "—"}
    </span>
  );
}

function formatReason(raw: string) {
  return raw
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function formatDate(iso: string | null) {
  if (!iso) return "Pending";
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function RefundTable({
  requests,
  total,
  page,
  pageSize,
  onPageChange,
  decisionFilter,
  onDecisionFilter,
  isLoading,
}: RefundTableProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="flex flex-col gap-0">
      {/* Filter bar */}
      <div className="flex gap-2 mb-4">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => onDecisionFilter(f.value)}
            className={`px-3 py-1.5 rounded text-sm transition-colors ${
              decisionFilter === f.value
                ? "bg-blue-600 text-white"
                : "bg-gray-800 text-gray-400 hover:text-white"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="bg-gray-900 rounded-lg overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-gray-800/50">
              <th className="p-3 text-left text-xs uppercase text-gray-400">Request ID</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Customer</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Order</th>
              <th className="p-3 text-right text-xs uppercase text-gray-400">Amount</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Reason</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Decision</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Created</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Decided</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={8} className="p-8 text-center text-gray-500">
                  Loading...
                </td>
              </tr>
            ) : requests.length === 0 ? (
              <tr>
                <td colSpan={8} className="p-8 text-center text-gray-500">
                  No refund requests found.
                </td>
              </tr>
            ) : (
              requests.map((r) => (
                <tr
                  key={r.refund_request_id}
                  className="border-b border-gray-800 hover:bg-gray-800 transition-colors"
                >
                  <td className="p-3 text-sm text-gray-200 font-mono">
                    {r.refund_request_id.slice(0, 8)}...
                  </td>
                  <td className="p-3 text-sm text-gray-200">{r.customer_id}</td>
                  <td className="p-3 text-sm text-gray-200">{r.order_id}</td>
                  <td className="p-3 text-sm text-gray-200 text-right">
                    ${r.requested_amount.toFixed(2)}
                  </td>
                  <td className="p-3 text-sm text-gray-200">
                    {formatReason(r.reason_category)}
                  </td>
                  <td className="p-3">
                    <VerdictBadge decision={r.decision} />
                  </td>
                  <td className="p-3 text-sm text-gray-400 whitespace-nowrap">
                    {formatDate(r.created_at)}
                  </td>
                  <td className="p-3 text-sm text-gray-400 whitespace-nowrap">
                    {formatDate(r.decided_at)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between p-3 text-sm text-gray-400">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="px-3 py-1 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          ← Prev
        </button>
        <span>
          Page {page} of {totalPages}
        </span>
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          className="px-3 py-1 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
