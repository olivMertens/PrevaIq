'use client';

import { CheckCircle, XCircle, AlertTriangle } from 'lucide-react';

export default function DecisionBadge({ decision }: { decision: 'APPROVE' | 'DECLINE' | 'REFER' }) {
  const styles = {
    APPROVE: 'bg-green-100 text-green-700 border-green-200',
    DECLINE: 'bg-red-100 text-red-700 border-red-200',
    REFER: 'bg-amber-100 text-amber-700 border-amber-200',
  };

  const icons = {
    APPROVE: CheckCircle,
    DECLINE: XCircle,
    REFER: AlertTriangle,
  };

  const Icon = icons[decision];

  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium border ${styles[decision]}`}>
      <Icon className="w-4 h-4" />
      {decision}
    </span>
  );
}
