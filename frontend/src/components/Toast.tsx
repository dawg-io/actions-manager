import React, { useState, useEffect } from 'react';
import { toast, ToastItem } from '../utils/toast';

const ICON: Record<string, string> = {
  success: '✓',
  error: '✕',
  info: 'ℹ',
  warning: '⚠',
};

const STYLE: Record<string, string> = {
  success:
    'bg-green-900/90 border border-green-700 text-green-100',
  error:
    'bg-red-900/90 border border-red-700 text-red-100',
  info:
    'bg-blue-900/90 border border-blue-700 text-blue-100',
  warning:
    'bg-yellow-900/90 border border-yellow-700 text-yellow-100',
};

const ICON_STYLE: Record<string, string> = {
  success: 'text-green-400',
  error: 'text-red-400',
  info: 'text-blue-400',
  warning: 'text-yellow-400',
};

interface ToastNotificationProps {
  item: ToastItem;
  onDismiss: (id: string) => void;
}

const ToastNotification: React.FC<ToastNotificationProps> = ({ item, onDismiss }) => (
  <div
    role="alert"
    aria-live="assertive"
    className={`flex items-start gap-3 min-w-[280px] max-w-sm rounded-lg px-4 py-3 shadow-xl text-sm ${STYLE[item.type]}`}
  >
    <span className={`mt-0.5 shrink-0 font-bold ${ICON_STYLE[item.type]}`} aria-hidden="true">
      {ICON[item.type]}
    </span>
    <p className="flex-1 leading-snug whitespace-pre-line">{item.message}</p>
    <button
      onClick={() => onDismiss(item.id)}
      className="shrink-0 opacity-60 hover:opacity-100 transition-opacity ml-2"
      aria-label="Dismiss"
    >
      ✕
    </button>
  </div>
);

const ToastContainer: React.FC = () => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  useEffect(() => {
    return toast.subscribe(setToasts);
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div
      className="fixed bottom-5 right-5 z-[9999] flex flex-col gap-2 pointer-events-none"
      aria-label="Notifications"
    >
      {toasts.map((item) => (
        <div key={item.id} className="pointer-events-auto">
          <ToastNotification item={item} onDismiss={(id) => toast.dismiss(id)} />
        </div>
      ))}
    </div>
  );
};

export default ToastContainer;
