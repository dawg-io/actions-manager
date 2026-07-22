export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface ToastItem {
  id: string;
  message: string;
  type: ToastType;
}

type Listener = (toasts: ToastItem[]) => void;

const DEFAULT_DURATION: Record<ToastType, number> = {
  success: 4000,
  info: 4000,
  warning: 5000,
  error: 6000,
};

export class ToastService {
  private toasts: ToastItem[] = [];
  private listeners: Set<Listener> = new Set();

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    fn([...this.toasts]);
    return () => {
      this.listeners.delete(fn);
    };
  }

  private emit(): void {
    const snapshot = [...this.toasts];
    this.listeners.forEach((fn) => fn(snapshot));
  }

  show(message: string, type: ToastType, duration?: number): void {
    if (this.toasts.some(t => t.type === type && t.message === message)) {
      return;
    }
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    this.toasts = [...this.toasts, { id, message, type }];
    this.emit();

    const ms = duration ?? DEFAULT_DURATION[type];
    if (ms > 0) {
      setTimeout(() => this.dismiss(id), ms);
    }
  }

  success(message: string): void {
    this.show(message, 'success');
  }

  error(message: string): void {
    this.show(message, 'error');
  }

  info(message: string): void {
    this.show(message, 'info');
  }

  warning(message: string): void {
    this.show(message, 'warning');
  }

  dismiss(id: string): void {
    this.toasts = this.toasts.filter((t) => t.id !== id);
    this.emit();
  }
}

export const toast = new ToastService();
