"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, AlertCircle, AlertTriangle, Info, X } from "lucide-react";

import { TOAST_EVENT, type ToastDetail, type ToastTone } from "@/lib/toast";

type ToastItem = ToastDetail & { id: number };

const ICONS: Record<ToastTone, React.ElementType> = {
  ok: CheckCircle2,
  err: AlertCircle,
  warn: AlertTriangle,
  info: Info,
};

const DEFAULT_TTL = 5000;

export function EvoToastHost() {
  const [items, setItems] = useState<ToastItem[]>([]);

  useEffect(() => {
    let counter = 0;
    function onToast(event: Event) {
      const detail = (event as CustomEvent<ToastDetail>).detail;
      if (!detail || typeof detail.message !== "string") return;
      const id = ++counter;
      const ttl = typeof detail.ttl === "number" && detail.ttl > 0 ? detail.ttl : DEFAULT_TTL;
      setItems((prev) => [...prev, { ...detail, id }]);
      window.setTimeout(() => {
        setItems((prev) => prev.filter((item) => item.id !== id));
      }, ttl);
    }
    window.addEventListener(TOAST_EVENT, onToast);
    return () => window.removeEventListener(TOAST_EVENT, onToast);
  }, []);

  function dismiss(id: number) {
    setItems((prev) => prev.filter((item) => item.id !== id));
  }

  if (items.length === 0) return null;

  return (
    <div className="evo-toast-host" role="region" aria-label="Notificações" aria-live="polite">
      {items.map((item) => {
        const Icon = ICONS[item.tone];
        return (
          <div
            key={item.id}
            className={`evo-toast evo-toast--${item.tone}`}
            role={item.tone === "err" ? "alert" : "status"}
          >
            <Icon size={16} className="evo-toast__icon" aria-hidden="true" />
            <div className="evo-toast__body">
              {item.title && <div className="evo-toast__title">{item.title}</div>}
              <div className="evo-toast__message">{item.message}</div>
            </div>
            <button
              type="button"
              className="evo-toast__close"
              aria-label="Fechar notificação"
              onClick={() => dismiss(item.id)}
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
