"use client";

import { useState, useEffect, createContext, useContext, useCallback } from "react";

interface ToastItem {
  id: number;
  message: string;
  type: "success" | "error" | "info" | "warning";
}

interface ToastContextType {
  toasts: ToastItem[];
  addToast: (message: string, type?: ToastItem["type"]) => void;
  removeToast: (id: number) => void;
}

const ToastContext = createContext<ToastContextType>({
  toasts: [],
  addToast: () => {},
  removeToast: () => {},
});

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [nextId, setNextId] = useState(1);

  const addToast = useCallback((message: string, type: ToastItem["type"] = "info") => {
    const id = nextId;
    setNextId((prev) => prev + 1);
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, [nextId]);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const borderColor = (type: ToastItem["type"]) => {
    switch (type) {
      case "success": return "border-l-emerald-500";
      case "error": return "border-l-red-500";
      case "warning": return "border-l-amber-500";
      default: return "border-l-blue-500";
    }
  };

  const iconBg = (type: ToastItem["type"]) => {
    switch (type) {
      case "success": return "bg-emerald-100 text-emerald-600";
      case "error": return "bg-red-100 text-red-600";
      case "warning": return "bg-amber-100 text-amber-600";
      default: return "bg-blue-100 text-blue-600";
    }
  };

  const icon = (type: ToastItem["type"]) => {
    switch (type) {
      case "success": return "\u2713";
      case "error": return "\u2715";
      case "warning": return "!";
      default: return "i";
    }
  };

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
      {children}
      <div className="fixed top-4 right-4 z-50 space-y-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={"animate-slide-in bg-white rounded-lg shadow-soft border border-gray-100 border-l-4 " + borderColor(toast.type)}
            onClick={() => removeToast(toast.id)}
          >
            <span className={"w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 " + iconBg(toast.type)}>
              {icon(toast.type)}
            </span>
            <span className="flex-1 text-gray-700 leading-snug">{toast.message}</span>
            <span className="text-gray-300 text-xs flex-shrink-0 mt-0.5">\u2715</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}