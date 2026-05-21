"use client";

import { Bell } from "lucide-react";
import { useState } from "react";

type Notification = {
  id: string;
  title: string;
  meta?: string;
  kind?: "info" | "warn" | "err" | "ok";
};

type NotificationsBellProps = {
  notifications: Notification[];
};

export function NotificationsBell({ notifications }: NotificationsBellProps) {
  const [open, setOpen] = useState(false);

  return (
    <div style={{ position: "relative" }}>
      <button type="button" className="icon-btn" onClick={() => setOpen((value) => !value)} aria-label="Notificacoes">
        <Bell size={15} />
        {notifications.length ? <span className="icon-btn__badge" /> : null}
      </button>
      {open ? (
        <div className="card" style={{ position: "absolute", right: 0, top: 36, width: 320, zIndex: 20 }}>
          <div className="card__body">
            <div className="col">
              {notifications.length ? notifications.map((item) => (
                <div className="citation" key={item.id}>
                  <span className={`badge badge--${item.kind ?? "info"}`}><span className="badge__dot" /></span>
                  <span>
                    <span className="citation__title">{item.title}</span>
                    {item.meta ? <span className="citation__meta">{item.meta}</span> : null}
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
