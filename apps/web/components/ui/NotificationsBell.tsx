"use client";

import { Bell } from "lucide-react";
import { useState } from "react";

import { markNotificationsReadAction } from "@/lib/actions";
import type { NotificationItem } from "@/lib/types";

const VALID_KINDS = new Set(["info", "warn", "err", "ok"]);

function kindClass(kind: string): "info" | "warn" | "err" | "ok" {
  return VALID_KINDS.has(kind) ? (kind as "info" | "warn" | "err" | "ok") : "info";
}

type NotificationsBellProps = {
  notifications: NotificationItem[];
  org: string;
  project: string;
  projectId: string | null;
  currentPath: string;
};

export function NotificationsBell({
  notifications,
  org,
  project,
  projectId,
  currentPath,
}: NotificationsBellProps) {
  const [open, setOpen] = useState(false);
  const unread = notifications.filter((n) => !n.read_at);
  const canMarkRead = unread.length > 0 && projectId !== null;

  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        className="icon-btn"
        onClick={() => setOpen((value) => !value)}
        aria-label="Notificacoes"
        aria-expanded={open}
      >
        <Bell size={15} />
        {unread.length > 0 ? <span className="icon-btn__badge" /> : null}
      </button>
      {open ? (
        <div className="card notifications-popover">
          <div
            className="card__header"
            style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
          >
            <span className="card__title" style={{ fontSize: 13 }}>
              Notificações
            </span>
            {canMarkRead ? (
              <form action={markNotificationsReadAction} style={{ margin: 0 }}>
                <input type="hidden" name="org" value={org} />
                <input type="hidden" name="project" value={project} />
                <input type="hidden" name="project_id" value={projectId ?? ""} />
                <input type="hidden" name="current_path" value={currentPath} />
                {unread.map((item) => (
                  <input key={item.id} type="hidden" name="ids" value={item.id} />
                ))}
                <button type="submit" className="btn btn--sm btn--ghost" style={{ fontSize: 11 }}>
                  Marcar lidas
                </button>
              </form>
            ) : null}
          </div>
          <div className="card__body">
            <div className="col">
              {notifications.length ? notifications.map((item) => (
                <div className="citation" key={item.id}>
                  <span className={`badge badge--${kindClass(item.kind)}`}><span className="badge__dot" /></span>
                  <span>
                    <span className="citation__title">{item.title}</span>
                    {item.read_at ? null : <span className="citation__meta">nao lida</span>}
                  </span>
                </div>
              )) : <div className="faint">Sem notificacoes</div>}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
