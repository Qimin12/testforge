"use client";

/** 极简 toast：成功/失败提示，3.5 秒自动消失。 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { IconAlert, IconCheck, IconX } from "@/components/icons";
import { cn } from "@/lib/utils";

type ToastTone = "success" | "error" | "info";

interface ToastItem {
  id: number;
  tone: ToastTone;
  message: string;
}

interface ToastContextValue {
  toast: (message: string, tone?: ToastTone) => void;
  success: (message: string) => void;
  error: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const remove = useCallback((id: number) => {
    setItems((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const toast = useCallback(
    (message: string, tone: ToastTone = "info") => {
      const id = nextId++;
      setItems((prev) => [...prev, { id, tone, message }]);
      window.setTimeout(() => remove(id), 3500);
    },
    [remove],
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      toast,
      success: (message: string) => toast(message, "success"),
      error: (message: string) => toast(message, "error"),
    }),
    [toast],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2">
        {items.map((item) => (
          <div
            key={item.id}
            className={cn(
              "pointer-events-auto flex items-start gap-2 rounded-md border px-3 py-2 text-sm shadow-lg",
              item.tone === "success" && "border-emerald-200 bg-white text-emerald-800",
              item.tone === "error" && "border-red-200 bg-white text-red-800",
              item.tone === "info" && "border-slate-200 bg-white text-slate-800",
            )}
            role="status"
          >
            <span className="mt-0.5 shrink-0">
              {item.tone === "success" ? (
                <IconCheck size={14} />
              ) : item.tone === "error" ? (
                <IconAlert size={14} />
              ) : (
                <IconCheck size={14} />
              )}
            </span>
            <p className="flex-1 break-words">{item.message}</p>
            <button
              type="button"
              onClick={() => remove(item.id)}
              className="shrink-0 rounded p-0.5 text-slate-400 hover:bg-slate-100"
              aria-label="关闭提示"
            >
              <IconX size={12} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast 必须在 ToastProvider 内使用");
  return ctx;
}
