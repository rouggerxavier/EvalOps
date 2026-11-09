"use client";

import { useFormStatus } from "react-dom";

export function ChangePasswordSubmit() {
  const { pending } = useFormStatus();
  return <button type="submit" className="btn btn--primary" disabled={pending} aria-busy={pending}>
    {pending ? "Trocando senha…" : "Trocar senha e sair"}
  </button>;
}
