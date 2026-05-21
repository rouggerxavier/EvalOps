"use client";

import { RefreshCw } from "lucide-react";

import { safeErrorMessage } from "@/lib/safe-error";

type Props = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function Error({ error, reset }: Props) {
  return (
    <div className="evo-page">
      <div className="evo-page-header">
        <div>
          <p className="evo-page-header__eyebrow">Dados · Exports</p>
          <h1 className="evo-page-header__title">Exports</h1>
          <p className="evo-page-header__subtitle">Nao foi possivel carregar esta tela.</p>
        </div>
      </div>
      <div className="evo-card">
        <div className="evo-card__body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <p style={{ margin: 0, color: "var(--err)", fontSize: 13 }}>
            Erro: {safeErrorMessage(error, "falha inesperada")}
          </p>
          <button type="button" className="evo-btn evo-btn--sm" onClick={reset} style={{ alignSelf: "flex-start" }}>
            <RefreshCw size={13} />
            Tentar novamente
          </button>
        </div>
      </div>
    </div>
  );
}

