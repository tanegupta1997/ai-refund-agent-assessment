interface StatsBarProps {
  totalLogs: number;
  totalRefunds: number;
  escalationCount: number;
  approvalRate: number;
}

export default function StatsBar({
  totalLogs,
  totalRefunds,
  escalationCount,
  approvalRate,
}: StatsBarProps) {
  return (
    <div className="grid grid-cols-4 gap-4 p-4 bg-gray-950 border-b border-gray-800">
      <div className="bg-gray-900 rounded-lg p-4">
        <div className="text-2xl font-bold text-blue-400">{totalLogs}</div>
        <div className="text-sm text-gray-400">Total Conversations</div>
      </div>
      <div className="bg-gray-900 rounded-lg p-4">
        <div className="text-2xl font-bold text-white">{totalRefunds}</div>
        <div className="text-sm text-gray-400">Refund Requests</div>
      </div>
      <div className="bg-gray-900 rounded-lg p-4">
        <div className="text-2xl font-bold text-yellow-400">{escalationCount}</div>
        <div className="text-sm text-gray-400">Escalations</div>
      </div>
      <div className="bg-gray-900 rounded-lg p-4">
        <div className="text-2xl font-bold text-green-400">{approvalRate.toFixed(1)}%</div>
        <div className="text-sm text-gray-400">Approval Rate</div>
      </div>
    </div>
  );
}
