"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { emitToast } from "@/lib/toast";

type CopyableProps = {
  value: string;
  display?: string;
};

export function Copyable({ value, display }: CopyableProps) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    if (!value) return;
    await navigator.clipboard.writeText(value);
    setCopied(true);
    emitToast({ tone: "ok", title: "Copiado", message: value.slice(0, 80) });
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <button type="button" className="copyable" onClick={copy}>
      <span>{display ?? value}</span>
      {copied ? <Check size={10} aria-hidden="true" /> : <Copy size={10} aria-hidden="true" />}
    </button>
  );
}
