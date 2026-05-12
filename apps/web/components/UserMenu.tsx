"use client";

import { LogOut } from "lucide-react";

import { logoutAction } from "@/lib/auth-actions";

type Props = {
  initials: string;
  email?: string | null;
  name?: string | null;
};

export function UserMenu({ initials, email, name }: Props) {
  return (
    <form action={logoutAction} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <div className="tb-avatar" title={name || email || ""}>
        {initials}
      </div>
      <button
        type="submit"
        className="icon-btn"
        aria-label="Sign out"
        title="Sign out"
        style={{ background: "transparent", border: "1px solid var(--border-subtle)" }}
      >
        <LogOut size={14} />
      </button>
    </form>
  );
}


