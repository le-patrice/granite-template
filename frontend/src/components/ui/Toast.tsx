import React, { createContext, useContext, useState, useCallback, useId } from "react";
import { CheckCircle2, AlertCircle, AlertTriangle, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToastType = "success" | "error" | "warning" | "info";

export interface ToastItem {
  id: string;
  type: ToastType;
  title?: string;
  description: string;
  duration?: number;
}

interface ToastContextType {
  toasts: ToastItem[];
  addToast: (toast: Omit<ToastItem, "id">) => string;
  removeToast: (id: string) => void;
  showSuccessToast: (description: string, title?: string) => string;
  showErrorToast: (description: string, title?: string) => string;
  showWarningToast: (description: string, title?: string) => string;
  showInfoToast: (description: string, title?: string) => string;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback(
    ({ type, title, description, duration = 4000 }: Omit<ToastItem, "id">) => {
      const id = Math.random().toString(36).substring(2, 9);
      const newToast: ToastItem = { id, type, title, description, duration };

      setToasts((prev) => [...prev, newToast]);

      if (duration > 0) {
        setTimeout(() => {
          removeToast(id);
        }, duration);
      }

      return id;
    },
    [removeToast]
  );

  const showSuccessToast = useCallback(
    (description: string, title?: string) => {
      return addToast({ type: "success", title: title || "Success", description });
    },
    [addToast]
  );

  const showErrorToast = useCallback(
    (description: string, title?: string) => {
      return addToast({ type: "error", title: title || "Error", description });
    },
    [addToast]
  );

  const showWarningToast = useCallback(
    (description: string, title?: string) => {
      return addToast({ type: "warning", title: title || "Warning", description });
    },
    [addToast]
  );

  const showInfoToast = useCallback(
    (description: string, title?: string) => {
      return addToast({ type: "info", title: title || "Info", description });
    },
    [addToast]
  );

  return (
    <ToastContext.Provider
      value={{
        toasts,
        addToast,
        removeToast,
        showSuccessToast,
        showErrorToast,
        showWarningToast,
        showInfoToast,
      }}
    >
      {children}
      {/* Toast Container Floating Top-Right */}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="fixed top-4 right-4 z-50 flex flex-col gap-2.5 max-w-sm w-full pointer-events-none"
      >
        {toasts.map((toast) => (
          <ToastCard key={toast.id} toast={toast} onDismiss={() => removeToast(toast.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
};

export const useToastContext = (): ToastContextType => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToastContext must be used within a ToastProvider");
  }
  return context;
};

const ToastCard: React.FC<{ toast: ToastItem; onDismiss: () => void }> = ({ toast, onDismiss }) => {
  const icons = {
    success: <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />,
    error: <AlertCircle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />,
    warning: <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />,
    info: <Info className="h-4 w-4 text-primary shrink-0 mt-0.5" />,
  };

  const borders = {
    success: "border-emerald-500/20 bg-card dark:bg-zinc-900",
    error: "border-destructive/30 bg-card dark:bg-zinc-900",
    warning: "border-amber-500/30 bg-card dark:bg-zinc-900",
    info: "border-primary/20 bg-card dark:bg-zinc-900",
  };

  return (
    <div
      role="alert"
      className={cn(
        "pointer-events-auto flex items-start gap-3 rounded-lg border p-4 shadow-lg transition-all duration-200 animate-in slide-in-from-top-2 text-card-foreground",
        borders[toast.type]
      )}
    >
      {icons[toast.type]}
      <div className="flex-1 min-w-0">
        {toast.title && (
          <h4 className="text-xs font-semibold text-foreground tracking-tight">{toast.title}</h4>
        )}
        <p className="text-xs text-muted-foreground mt-0.5 break-words">{toast.description}</p>
      </div>
      <button
        onClick={onDismiss}
        className="rounded-sm p-0.5 text-muted-foreground hover:text-foreground transition-colors"
        aria-label="Close notification"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
};
