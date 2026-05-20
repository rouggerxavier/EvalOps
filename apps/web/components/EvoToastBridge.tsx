"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { emitToast, type ToastDetail } from "@/lib/toast";

type FlashRule = {
  key: string;
  tone: ToastDetail["tone"];
  title?: string;
  message: string | ((value: string) => string);
  consumeKeys?: string[];
};

const FLASH_RULES: FlashRule[] = [
  { key: "created", tone: "ok", title: "Criado", message: "Recurso criado com sucesso." },
  { key: "revoked", tone: "ok", title: "Revogado", message: "Chave API revogada." },
  { key: "versioned", tone: "ok", title: "Nova versão", message: "Versão registrada." },
  { key: "feedback", tone: "ok", title: "Feedback", message: "Feedback registrado." },
  { key: "built", tone: "ok", title: "Dataset", message: "Dataset construído a partir de traces." },
  { key: "items_added", tone: "ok", title: "Item adicionado", message: "Item do dataset salvo." },
  {
    key: "run",
    tone: "info",
    title: "Experimento",
    message: "Execução do experimento iniciada.",
    consumeKeys: ["run", "run_id", "experiment_id"],
  },
  {
    key: "error",
    tone: "err",
    title: "Falha",
    message: (value) => value || "Operação falhou.",
  },
];

export function EvoToastBridge() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const lastSignatureRef = useRef<string | null>(null);

  useEffect(() => {
    if (!searchParams) return;
    const matched: FlashRule[] = [];
    for (const rule of FLASH_RULES) {
      if (searchParams.get(rule.key) !== null) matched.push(rule);
    }
    if (matched.length === 0) {
      lastSignatureRef.current = null;
      return;
    }

    const signature = `${pathname}?${matched
      .map((rule) => `${rule.key}=${searchParams.get(rule.key) ?? ""}`)
      .join("&")}`;
    if (signature === lastSignatureRef.current) return;
    lastSignatureRef.current = signature;

    for (const rule of matched) {
      const raw = searchParams.get(rule.key) ?? "";
      const message = typeof rule.message === "function" ? rule.message(raw) : rule.message;
      emitToast({ tone: rule.tone, title: rule.title, message });
    }

    const next = new URLSearchParams(searchParams.toString());
    for (const rule of matched) {
      const keys = rule.consumeKeys ?? [rule.key];
      for (const k of keys) next.delete(k);
    }
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }, [pathname, router, searchParams]);

  return null;
}
