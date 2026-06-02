import type { RefundRequest } from "@/types";

interface EscalationQueueProps {
  escalations: RefundRequest[];
  count: number;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function EscalationQueue({
  escalations,
  count,
}: EscalationQueueProps) {
  if (count === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <div className="text-5xl">✅</div>
        <div className="text-lg font-medium text-green-400">
          No pending escalations
        </div>
        <div className="text-sm text-gray-500">
          All refund requests have been resolved
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="text-yellow-400 font-semibold mb-4">
        🚨 {count} request{count !== 1 ? "s" : ""} need human review
      </div>

      {escalations.map((r) => (
        <div
          key={r.refund_request_id}
          className="bg-gray-800 rounded-lg p-4 mb-3 border-l-4 border-yellow-500"
        >
          {/* Row 1: order + amount + badge */}
          <div className="flex items-center justify-between mb-1">
            <span className="font-bold text-white">{r.order_id}</span>
            <div className="flex items-center gap-3">
              <span className="text-green-400 font-medium">
                ${r.requested_amount.toFixed(2)}
              </span>
              <span className="px-2 py-0.5 rounded text-xs bg-yellow-900 text-yellow-300">
                Escalated
              </span>
            </div>
          </div>

          {/* Row 2: customer */}
          <div className="text-sm text-gray-400 mb-1">{r.customer_id}</div>

          {/* Row 3: reason */}
          <div className="text-sm text-gray-300 mb-2">
            {r.reason_category
              .split("_")
              .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
              .join(" ")}
          </div>

          {/* Row 4: decision reasons chips */}
          {Array.isArray(r.decision_reasons) && r.decision_reasons.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-2">
              {r.decision_reasons.map((reason, i) => (
                <span
                  key={i}
                  className="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-400"
                >
                  {reason}
                </span>
              ))}
            </div>
          )}

          {/* Row 5: date */}
          <div className="text-xs text-gray-500">{formatDate(r.created_at)}</div>
        </div>
      ))}
    </div>
  );
}
