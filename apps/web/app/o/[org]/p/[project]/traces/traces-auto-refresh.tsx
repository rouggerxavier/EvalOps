"use client";

import { useCallback, useEffect, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw } from "lucide-react";

type Props = {
  enabledByDefault: boolean;
  intervalMs?: number;
  disabledReason?: string;
};

const DEFAULT_INTERVAL_MS = 30_000;

function formatRefreshTime(date: Date | null): string {
  if (!date) return "Carregado";
  return `Atualizado ${date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
}

export function TracesAutoRefresh({
  enabledByDefault,
  intervalMs = DEFAULT_INTERVAL_MS,
  disabledReason,
}: Props) {
  const router = useRouter();
  const [enabled, setEnabled] = useState(enabledByDefault);
  const [isVisible, setIsVisible] = useState(true);
  const [lastRefreshAt, setLastRefreshAt] = useState<Date | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isPending, startTransition] = useTransition();
  const refreshingRef = useRef(false);
  const doneTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!enabledByDefault) {
      setEnabled(false);
    }
  }, [enabledByDefault]);

  useEffect(() => {
    setIsVisible(!document.hidden);
    setLastRefreshAt(new Date());

    const handleVisibilityChange = () => {
      setIsVisible(!document.hidden);
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      if (doneTimerRef.current !== null) {
        window.clearTimeout(doneTimerRef.current);
      }
    };
  }, []);

  const refreshNow = useCallback(() => {
    if (refreshingRef.current || document.hidden) return;

    refreshingRef.current = true;
    setIsRefreshing(true);
    startTransition(() => {
      router.refresh();
    });

    if (doneTimerRef.current !== null) {
      window.clearTimeout(doneTimerRef.current);
    }
    doneTimerRef.current = window.setTimeout(() => {
      refreshingRef.current = false;
      setIsRefreshing(false);
      setLastRefreshAt(new Date());
      doneTimerRef.current = null;
    }, 600);
  }, [router, startTransition]);

  useEffect(() => {
    if (!enabled || disabledReason || !isVisible) return;

    const intervalId = window.setInterval(() => {
      if (document.hidden || refreshingRef.current) return;
      refreshNow();
    }, intervalMs);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [disabledReason, enabled, intervalMs, isVisible, refreshNow]);

  const isBusy = isRefreshing || isPending;
  const autoRefreshActive = enabled && isVisible && !disabledReason;
  const intervalLabel = `${Math.round(intervalMs / 1000)}s`;
  const statusLabel = disabledReason
    ? disabledReason
    : !isVisible
      ? "Pausado: aba oculta"
      : autoRefreshActive
        ? isBusy
          ? "Atualizando..."
          : formatRefreshTime(lastRefreshAt)
        : "Auto-refresh pausado";

  return (
    <div
      className="evo-row"
      aria-live="polite"
      style={{ gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}
    >
      <button
        type="button"
        className="evo-btn evo-btn--sm"
        onClick={refreshNow}
        disabled={isBusy}
        aria-label="Atualizar traces agora"
        title="Atualizar traces agora"
        style={{ minWidth: 126, justifyContent: "center" }}
      >
        <RefreshCw size={13} aria-hidden="true" />
        {isBusy ? "Atualizando..." : "Atualizar agora"}
      </button>

      <button
        type="button"
        className="evo-btn evo-btn--sm"
        onClick={() => setEnabled((current) => !current)}
        disabled={Boolean(disabledReason)}
        aria-pressed={enabled}
        aria-label={enabled ? "Pausar auto-refresh de traces" : "Ativar auto-refresh de traces"}
        title={disabledReason ?? `Auto-refresh a cada ${intervalLabel}`}
        style={{ minWidth: 104, justifyContent: "center" }}
      >
        {autoRefreshActive ? `Auto ${intervalLabel}` : "Auto pausado"}
      </button>

      <span className="evo-muted" style={{ minWidth: 144, fontSize: 12, textAlign: "right" }}>
        {statusLabel}
      </span>
    </div>
  );
}
