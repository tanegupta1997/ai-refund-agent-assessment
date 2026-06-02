"use client";

import type { AgentLog } from "@/types";

interface LogsTableProps {
  logs: AgentLog[];
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onSelectLog: (log: AgentLog) => void;
  selectedLogId: string | null;
  isLoading?: boolean;
}

function VerdictBadge({ verdict }: { verdict: string | null }) {
  if (!verdict) {
    return (
      <span className="px-2 py-0.5 rounded text-xs bg-gray-800 text-gray-400">
        —
      </span>
    );
  }
  const styles: Record<string, string> = {
    approved: "bg-green-900 text-green-300",
    denied: "bg-red-900 text-red-300",
    escalated: "bg-yellow-900 text-yellow-300",
  };
  return (
    <span
      className={`px-2 py-0.5 rounded text-xs ${styles[verdict] ?? "bg-gray-800 text-gray-400"}`}
    >
      {verdict}
    </span>
  );
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function LogsTable({
  logs,
  total,
  page,
  pageSize,
  onPageChange,
  onSelectLog,
  selectedLogId,
  isLoading,
}: LogsTableProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="flex flex-col gap-0">
      <div className="bg-gray-900 rounded-lg overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-gray-800/50">
              <th className="p-3 text-left text-xs uppercase text-gray-400">Time</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Message</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Verdict</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Node</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Latency</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Injection</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={7} className="p-8 text-center text-gray-500">
                  Loading...
                </td>
              </tr>
            ) : logs.length === 0 ? (
              <tr>
                <td colSpan={7} className="p-8 text-center text-gray-500">
                  No conversation logs found.
                </td>
              </tr>
            ) : (
              logs.map((log) => {
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const logAny = log as any;
                const currentNode =
                  logAny.current_node ??
                  (log.policy_decision as Record<string, unknown> | null)
                    ?.current_node ??
                  "—";
                return (
                  <tr
                    key={log.log_id}
                    onClick={() => onSelectLog(log)}
                    className={`border-b border-gray-800 cursor-pointer hover:bg-gray-800 transition-colors ${
                      selectedLogId === log.log_id ? "bg-gray-800" : ""
                    }`}
                  >
                    <td className="p-3 text-sm text-gray-200 whitespace-nowrap">
                      {formatTime(log.timestamp)}
                    </td>
                    <td className="p-3 text-sm text-gray-200 max-w-xs">
                      <span className="block truncate" style={{ maxWidth: "320px" }}>
                        {(log.user_message ?? "").slice(0, 60)}
                      </span>
                    </td>
                    <td className="p-3">
                      <VerdictBadge verdict={log.verdict} />
                    </td>
                    <td className="p-3 text-sm text-gray-200">
                      {String(currentNode)}
                    </td>
                    <td className="p-3 text-sm text-gray-400">
                      {log.latency_ms != null
                        ? `${(log.latency_ms / 1000).toFixed(1)}s`
                        : "—"}
                    </td>
                    <td className="p-3 text-sm">
                      {log.injection_detected ? "🛡️" : ""}
                    </td>
                    <td className="p-3">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectLog(log);
                        }}
                        className="text-xs text-blue-400 hover:text-blue-300 px-2 py-1 rounded border border-gray-700 hover:border-blue-400 transition-colors"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                );
              })
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
