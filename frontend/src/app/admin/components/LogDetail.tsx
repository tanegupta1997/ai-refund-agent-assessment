"use client";

import { useState } from "react";
import type { AgentLog } from "@/types";

interface LogDetailProps {
  log: AgentLog | null;
  onClose: () => void;
}

function Section({
  icon,
  title,
  children,
}: {
  icon: string;
  title: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="border-b border-gray-800 py-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full text-left text-sm font-medium text-gray-200 hover:text-white"
      >
        <span>{icon}</span>
        <span>{title}</span>
        <span className="ml-auto text-gray-600 text-xs">{open ? "▲" : "▼"}</span>
      </button>
      {open && <div className="mt-3">{children}</div>}
    </div>
  );
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const styles: Record<string, string> = {
    approved: "bg-green-900 text-green-300",
    denied: "bg-red-900 text-red-300",
    escalated: "bg-yellow-900 text-yellow-300",
  };
  return (
    <span
      className={`px-3 py-1 rounded text-sm font-medium ${
        styles[verdict] ?? "bg-gray-800 text-gray-400"
      }`}
    >
      {verdict}
    </span>
  );
}

export default function LogDetail({ log, onClose }: LogDetailProps) {
  if (!log) return null;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const pd = log.policy_decision as any;

  return (
    <div className="fixed right-0 top-0 h-full w-[480px] bg-gray-900 border-l border-gray-800 overflow-y-auto z-50 flex flex-col shadow-2xl">
      {/* Sticky header */}
      <div className="flex items-start justify-between p-4 border-b border-gray-800 sticky top-0 bg-gray-900 z-10">
        <div>
          <div className="text-white font-semibold">Run Detail</div>
          <div className="text-xs text-gray-500 font-mono mt-0.5 break-all">
            {log.conversation_id}
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-white text-lg leading-none ml-4 shrink-0"
        >
          ✕
        </button>
      </div>

      {/* Timeline sections */}
      <div className="px-4 flex-1">
        <Section icon="💬" title="Customer Message">
          <div className="bg-gray-800 rounded p-3 text-sm text-gray-200 whitespace-pre-wrap">
            {log.user_message || "—"}
          </div>
        </Section>

        <Section icon="🔍" title="Parsed Intent">
          {log.parsed_intent ? (
            <pre className="bg-gray-950 rounded p-3 font-mono text-sm text-green-400 overflow-x-auto whitespace-pre-wrap break-all">
              {JSON.stringify(log.parsed_intent, null, 2)}
            </pre>
          ) : (
            <div className="text-sm text-gray-500">No intent parsed</div>
          )}
        </Section>

        <Section icon="🔧" title="Tool Calls">
          {!log.tool_calls || log.tool_calls.length === 0 ? (
            <div className="text-sm text-gray-500">No tools called</div>
          ) : (
            <div className="flex flex-col gap-3">
              {log.tool_calls.map((tc, i) => (
                <div key={i} className="border border-gray-700 rounded p-3">
                  <div className="text-sm font-bold text-blue-400 mb-2">
                    {tc.tool}
                  </div>
                  <pre className="text-xs text-gray-400 whitespace-pre-wrap break-all mb-2">
                    {JSON.stringify(tc.args, null, 2)}
                  </pre>
                  <div className="text-xs text-gray-300 border-t border-gray-700 pt-2">
                    {tc.result_summary}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Section>

        <Section icon="📋" title="Policy Input">
          {log.policy_input ? (
            <pre className="bg-gray-950 rounded p-3 font-mono text-sm text-green-400 overflow-x-auto whitespace-pre-wrap break-all">
              {JSON.stringify(log.policy_input, null, 2)}
            </pre>
          ) : (
            <div className="text-sm text-gray-500">No policy input</div>
          )}
        </Section>

        <Section icon="⚖️" title="Policy Decision">
          {!pd ? (
            <div className="text-sm text-gray-500">No policy decision</div>
          ) : (
            <div className="flex flex-col gap-3">
              {pd.verdict && <VerdictBadge verdict={pd.verdict} />}
              {Array.isArray(pd.reason_codes) && pd.reason_codes.length > 0 && (
                <div>
                  <div className="text-xs text-gray-400 mb-1">Reason Codes:</div>
                  <div className="flex flex-wrap gap-1">
                    {pd.reason_codes.map((code: string, i: number) => (
                      <span
                        key={i}
                        className="text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-300"
                      >
                        {code}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {pd.primary_reason && (
                <div className="text-sm">
                  <span className="text-gray-400">Primary Reason: </span>
                  <span className="text-white">{pd.primary_reason}</span>
                </div>
              )}
              {pd.approved_amount != null && (
                <div className="text-sm">
                  <span className="text-gray-400">Approved Amount: </span>
                  <span className="text-green-400">${pd.approved_amount}</span>
                </div>
              )}
              {pd.requires_human != null && (
                <div className="text-sm">
                  <span className="text-gray-400">Requires Human: </span>
                  <span className="text-white">
                    {pd.requires_human ? "Yes" : "No"}
                  </span>
                </div>
              )}
            </div>
          )}
        </Section>

        <Section icon="💬" title="Final Response">
          <div className="bg-gray-800 rounded p-3 text-sm text-gray-200 italic whitespace-pre-wrap">
            {log.final_response || "—"}
          </div>
        </Section>

        <Section icon="🛡️" title="Safety">
          {!log.injection_flags || log.injection_flags.length === 0 ? (
            <div className="text-sm text-green-400">No injection flags</div>
          ) : (
            <div className="flex flex-wrap gap-1">
              {log.injection_flags.map((flag, i) => (
                <span
                  key={i}
                  className="text-xs px-2 py-0.5 rounded bg-red-900 text-red-400"
                >
                  {flag}
                </span>
              ))}
            </div>
          )}
          {log.latency_ms != null && (
            <div className="text-xs text-gray-500 mt-2">
              Total: {(log.latency_ms / 1000).toFixed(1)}s
            </div>
          )}
        </Section>

        {/* Bottom padding so last section isn't flush against edge */}
        <div className="h-6" />
      </div>
    </div>
  );
}
