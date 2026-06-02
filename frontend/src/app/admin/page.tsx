"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentLog, RefundRequest } from "@/types";
import {
  fetchCustomers,
  fetchEscalations,
  fetchLogDetail,
  fetchLogs,
  fetchRefundRequests,
} from "@/lib/api";

import EscalationQueue from "./components/EscalationQueue";
import LogDetail from "./components/LogDetail";
import LogsTable from "./components/LogsTable";
import RefundTable from "./components/RefundTable";
import StatsBar from "./components/StatsBar";

type Tab = "conversations" | "refunds" | "escalations" | "customers";

const TABS: { id: Tab; label: string }[] = [
  { id: "conversations", label: "Conversations" },
  { id: "refunds", label: "Refunds" },
  { id: "escalations", label: "Escalations" },
  { id: "customers", label: "Customers" },
];

const PAGE_SIZE = 20;

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState<Tab>("conversations");

  // Logs state
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [logsMeta, setLogsMeta] = useState({ total: 0, page: 1, pageSize: PAGE_SIZE });
  const [selectedLog, setSelectedLog] = useState<AgentLog | null>(null);

  // Refunds state
  const [refunds, setRefunds] = useState<RefundRequest[]>([]);
  const [refundsMeta, setRefundsMeta] = useState({ total: 0, page: 1, pageSize: PAGE_SIZE });
  const [decisionFilter, setDecisionFilter] = useState("");

  // Escalations state
  const [escalations, setEscalations] = useState<RefundRequest[]>([]);
  const [escalationCount, setEscalationCount] = useState(0);

  // Customers state
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [customers, setCustomers] = useState<any[]>([]);
  const [customersMeta, setCustomersMeta] = useState({ total: 0, page: 1, pageSize: PAGE_SIZE });

  const [isLoading, setIsLoading] = useState(true);
  const [isLogsLoading, setIsLogsLoading] = useState(false);
  const [isRefundsLoading, setIsRefundsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const escalationIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Data fetchers ────────────────────────────────────────────────────────

  const loadEscalations = useCallback(async () => {
    try {
      const data = await fetchEscalations();
      setEscalations(data.items);
      setEscalationCount(data.count);
    } catch {
      // silent on background refresh; initial errors are caught below
    }
  }, []);

  const loadLogs = useCallback(async (page: number) => {
    setIsLogsLoading(true);
    try {
      const data = await fetchLogs(page, PAGE_SIZE);
      setLogs(data.items);
      setLogsMeta({ total: data.total, page, pageSize: PAGE_SIZE });
    } catch {
      setError("Failed to load conversation logs.");
    } finally {
      setIsLogsLoading(false);
    }
  }, []);

  const loadRefunds = useCallback(async (page: number, decision: string) => {
    setIsRefundsLoading(true);
    try {
      const data = await fetchRefundRequests(page, PAGE_SIZE, decision || undefined);
      setRefunds(data.items);
      setRefundsMeta({ total: data.total, page, pageSize: PAGE_SIZE });
    } catch {
      setError("Failed to load refund requests.");
    } finally {
      setIsRefundsLoading(false);
    }
  }, []);

  // ── Initial parallel load ────────────────────────────────────────────────

  const loadAll = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [logsData, refundsData, escalationsData, customersData] =
        await Promise.all([
          fetchLogs(1, PAGE_SIZE),
          fetchRefundRequests(1, PAGE_SIZE),
          fetchEscalations(),
          fetchCustomers(1, PAGE_SIZE),
        ]);

      setLogs(logsData.items);
      setLogsMeta({ total: logsData.total, page: 1, pageSize: PAGE_SIZE });

      setRefunds(refundsData.items);
      setRefundsMeta({ total: refundsData.total, page: 1, pageSize: PAGE_SIZE });

      setEscalations(escalationsData.items);
      setEscalationCount(escalationsData.count);

      setCustomers(customersData.items);
      setCustomersMeta({ total: customersData.total, page: 1, pageSize: PAGE_SIZE });
    } catch {
      setError("Failed to load data. Retrying...");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // ── Auto-refresh escalations every 30s ──────────────────────────────────

  useEffect(() => {
    escalationIntervalRef.current = setInterval(loadEscalations, 30_000);
    return () => {
      if (escalationIntervalRef.current) clearInterval(escalationIntervalRef.current);
    };
  }, [loadEscalations]);

  // ── Re-fetch on page/filter changes ─────────────────────────────────────

  useEffect(() => {
    if (!isLoading) loadLogs(logsMeta.page);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logsMeta.page]);

  useEffect(() => {
    if (!isLoading) loadRefunds(refundsMeta.page, decisionFilter);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refundsMeta.page, decisionFilter]);

  // ── Log row selection ────────────────────────────────────────────────────

  const handleSelectLog = useCallback(async (log: AgentLog) => {
    // Show the panel immediately with list-level data, then replace with full detail
    setSelectedLog(log);
    try {
      const detail = await fetchLogDetail(log.log_id);
      setSelectedLog(detail);
    } catch {
      // keep the partial data already shown
    }
  }, []);

  // ── Derived stats ────────────────────────────────────────────────────────

  const approvedCount = refunds.filter((r) => r.decision === "approved").length;
  const deniedCount = refunds.filter((r) => r.decision === "denied").length;
  const decidedCount = approvedCount + deniedCount;
  const approvalRate = decidedCount > 0 ? (approvedCount / decidedCount) * 100 : 0;

  // ── Customers pagination ─────────────────────────────────────────────────

  const handleCustomersPage = useCallback(async (page: number) => {
    try {
      const data = await fetchCustomers(page, PAGE_SIZE);
      setCustomers(data.items);
      setCustomersMeta({ total: data.total, page, pageSize: PAGE_SIZE });
    } catch {
      setError("Failed to load customers.");
    }
  }, []);

  // ── Tab change with filter reset ─────────────────────────────────────────

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    setSelectedLog(null);
  };

  // ────────────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-950 text-gray-200">
      {/* Fixed header */}
      <header className="fixed top-0 left-0 right-0 z-40 bg-gray-950 border-b border-gray-800 px-6 py-3 flex items-center justify-between">
        <span className="font-bold text-white text-lg">🛠️ Admin Dashboard</span>
        <span className="text-sm text-gray-500">Refund Agent</span>
      </header>

      {/* Content offset for fixed header */}
      <div className="pt-[57px]">
        {/* Error banner */}
        {error && (
          <div className="flex items-center justify-between bg-red-950 border-b border-red-800 px-6 py-2 text-sm text-red-300">
            <span>{error}</span>
            <button
              onClick={loadAll}
              className="ml-4 px-3 py-1 rounded bg-red-800 hover:bg-red-700 text-red-100 text-xs"
            >
              Retry
            </button>
          </div>
        )}

        {/* Stats bar */}
        <StatsBar
          totalLogs={logsMeta.total}
          totalRefunds={refundsMeta.total}
          escalationCount={escalationCount}
          approvalRate={approvalRate}
        />

        {/* Tab bar */}
        <div className="bg-gray-950 border-b border-gray-800 px-6 flex gap-0">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={`px-5 py-3 text-sm transition-colors border-b-2 ${
                activeTab === tab.id
                  ? "text-white border-blue-500"
                  : "text-gray-400 border-transparent hover:text-white"
              }`}
            >
              {tab.label}
              {tab.id === "escalations" && escalationCount > 0 && (
                <span className="ml-2 px-1.5 py-0.5 rounded-full text-xs bg-yellow-600 text-yellow-100">
                  {escalationCount}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex">
          <main className="flex-1 p-6 min-w-0">
            {isLoading ? (
              <div className="text-center text-gray-500 py-20">Loading...</div>
            ) : (
              <>
                {activeTab === "conversations" && (
                  <LogsTable
                    logs={logs}
                    total={logsMeta.total}
                    page={logsMeta.page}
                    pageSize={logsMeta.pageSize}
                    onPageChange={(p) =>
                      setLogsMeta((m) => ({ ...m, page: p }))
                    }
                    onSelectLog={handleSelectLog}
                    selectedLogId={selectedLog?.log_id ?? null}
                    isLoading={isLogsLoading}
                  />
                )}

                {activeTab === "refunds" && (
                  <RefundTable
                    requests={refunds}
                    total={refundsMeta.total}
                    page={refundsMeta.page}
                    pageSize={refundsMeta.pageSize}
                    onPageChange={(p) =>
                      setRefundsMeta((m) => ({ ...m, page: p }))
                    }
                    decisionFilter={decisionFilter}
                    onDecisionFilter={(d) => {
                      setDecisionFilter(d);
                      setRefundsMeta((m) => ({ ...m, page: 1 }));
                    }}
                    isLoading={isRefundsLoading}
                  />
                )}

                {activeTab === "escalations" && (
                  <EscalationQueue
                    escalations={escalations}
                    count={escalationCount}
                  />
                )}

                {activeTab === "customers" && (
                  <CustomersTab
                    customers={customers}
                    meta={customersMeta}
                    onPageChange={handleCustomersPage}
                  />
                )}
              </>
            )}
          </main>

          {/* Log detail panel */}
          {selectedLog && (
            <LogDetail
              log={selectedLog}
              onClose={() => setSelectedLog(null)}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ── Inline Customers tab ─────────────────────────────────────────────────────

function CustomersTab({
  customers,
  meta,
  onPageChange,
}: {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  customers: any[];
  meta: { total: number; page: number; pageSize: number };
  onPageChange: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(meta.total / meta.pageSize));

  return (
    <div className="flex flex-col gap-0">
      <div className="bg-gray-900 rounded-lg overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-gray-800/50">
              <th className="p-3 text-left text-xs uppercase text-gray-400">ID</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Name</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Email</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Loyalty Tier</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Orders</th>
              <th className="p-3 text-left text-xs uppercase text-gray-400">Joined</th>
            </tr>
          </thead>
          <tbody>
            {customers.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-gray-500">
                  No customers found.
                </td>
              </tr>
            ) : (
              customers.map((c) => (
                <tr
                  key={c.customer_id}
                  className="border-b border-gray-800 hover:bg-gray-800 transition-colors"
                >
                  <td className="p-3 text-sm text-gray-400 font-mono">
                    {c.customer_id}
                  </td>
                  <td className="p-3 text-sm text-gray-200">{c.name}</td>
                  <td className="p-3 text-sm text-gray-300">{c.email}</td>
                  <td className="p-3 text-sm">
                    <span
                      className={`px-2 py-0.5 rounded text-xs ${
                        c.loyalty_tier === "gold"
                          ? "bg-yellow-900 text-yellow-300"
                          : c.loyalty_tier === "silver"
                          ? "bg-gray-700 text-gray-300"
                          : "bg-gray-800 text-gray-400"
                      }`}
                    >
                      {c.loyalty_tier ?? "standard"}
                    </span>
                  </td>
                  <td className="p-3 text-sm text-gray-200">{c.order_count}</td>
                  <td className="p-3 text-sm text-gray-400 whitespace-nowrap">
                    {formatDate(c.created_at)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between p-3 text-sm text-gray-400">
        <button
          onClick={() => onPageChange(meta.page - 1)}
          disabled={meta.page <= 1}
          className="px-3 py-1 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          ← Prev
        </button>
        <span>
          Page {meta.page} of {totalPages}
        </span>
        <button
          onClick={() => onPageChange(meta.page + 1)}
          disabled={meta.page >= totalPages}
          className="px-3 py-1 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
