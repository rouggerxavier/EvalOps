"use client";

import { useRouter, usePathname } from "next/navigation";
import { Search, Filter, RefreshCw, Download, X } from "lucide-react";
import { useCallback, useState, useTransition } from "react";

type Props = {
  initialName?: string;
  initialStatus?: string;
  initialEnv?: string;
  count: number;
  total: number;
};

const STATUS_OPTIONS = ["ok", "error", "partial"] as const;
const ENV_OPTIONS = ["dev", "staging", "prod"] as const;

export function TracesFilterBar({ initialName = "", initialStatus = "", initialEnv = "", count, total }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const [, startTransition] = useTransition();
  const [name, setName] = useState(initialName);

  const push = useCallback(
    (overrides: { name?: string; status?: string; env?: string }) => {
      const n = overrides.name !== undefined ? overrides.name : name;
      const s = overrides.status !== undefined ? overrides.status : initialStatus;
      const e = overrides.env !== undefined ? overrides.env : initialEnv;
      const sp = new URLSearchParams();
      if (n) sp.set("name", n);
      if (s) sp.set("status", s);
      if (e) sp.set("environment", e);
      const q = sp.toString();
      startTransition(() => router.push(`${pathname}${q ? `?${q}` : ""}`));
    },
    [name, initialStatus, initialEnv, pathname, router],
  );

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    push({ name });
  };

  const toggleStatus = (val: string) => push({ status: initialStatus === val ? "" : val });
  const toggleEnv = (val: string) => push({ env: initialEnv === val ? "" : val });

  return (
    <div>
      <div className="evo-filterbar">
        <form onSubmit={handleSearch} className="evo-input" style={{ minWidth: 300 }}>
          <Search size={14} className="evo-input__icon" />
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Buscar por nome, trace ID, user ref…"
          />
          {name && (
            <button
              type="button"
              onClick={() => { setName(""); push({ name: "" }); }}
              style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-faint)", padding: 0, display: "flex" }}
            >
              <X size={12} />
            </button>
          )}
          <span className="evo-kbd">/</span>
        </form>

        {STATUS_OPTIONS.map((s) => (
          <button
            key={s}
            type="button"
            className={`evo-filter-chip ${initialStatus === s ? "is-active" : ""}`}
            onClick={() => toggleStatus(s)}
          >
            <span className="evo-filter-chip__key">status</span>
            <span className="evo-filter-chip__val">{s}</span>
            {initialStatus === s && <X size={10} style={{ marginLeft: 2 }} />}
          </button>
        ))}

        {ENV_OPTIONS.map((e) => (
          <button
            key={e}
            type="button"
            className={`evo-filter-chip ${initialEnv === e ? "is-active" : ""}`}
            onClick={() => toggleEnv(e)}
          >
            <span className="evo-filter-chip__key">env</span>
            <span className="evo-filter-chip__val">{e}</span>
            {initialEnv === e && <X size={10} style={{ marginLeft: 2 }} />}
          </button>
        ))}

        <div className="evo-spacer" />
        <span className="evo-mono" style={{ fontSize: 11, color: "var(--text-faint)" }}>
          {count.toLocaleString("pt-BR")} de {total.toLocaleString("pt-BR")}
        </span>
        <span
          aria-label="Live"
          title="Live"
          style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--ok)", display: "inline-block", position: "relative" }}
        />
      </div>
    </div>
  );
}
