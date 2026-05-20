"use client";

import { RefreshCw } from "lucide-react";

import { safeErrorMessage } from "@/lib/safe-error";

type Props = {
  eyebrow: string;
  title: string;
  error: Error & { digest?: string };
  reset: () => void;
};

export function RouteError({ eyebrow, title, error, reset }: Props) {
  return (
    <div className="evo-page">
      <div className="evo-page-header">
        <div>
          <p className="evo-page-header__eyebrow">{eyebrow}</p>
          <h1 className="evo-page-header__title">{title}</h1>
          <p className="evo-page-header__subtitle">Não foi possível carregar esta tela.</p>
        </div>
      </div>
      <div className="evo-card">
        <div className="evo-card__body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <p style={{ margin: 0, color: "var(--err)", fontSize: 13 }}>
            Erro: {safeErrorMessage(error, "falha inesperada")}
          </p>
          {error.digest ? (
            <p style={{ margin: 0, color: "var(--text-faint)", fontSize: 12, fontFamily: "var(--font-mono)" }}>
              digest: {error.digest}
            </p>
          ) : null}
          <button
            type="button"
            className="evo-btn evo-btn--sm"
            onClick={reset}
            style={{ alignSelf: "flex-start" }}
          >
            <RefreshCw size={13} />
            Tentar novamente
          </button>
        </div>
      </div>
    </div>
  );
}
