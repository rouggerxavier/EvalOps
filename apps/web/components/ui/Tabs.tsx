"use client";

import type { ReactNode } from "react";

type TabItem = {
  id: string;
  label: ReactNode;
  count?: number;
};

type TabsProps = {
  items: TabItem[];
  value: string;
  onChange?: (value: string) => void;
};

export function Tabs({ items, value, onChange }: TabsProps) {
  return (
    <div className="tabs" role="tablist">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          aria-selected={item.id === value}
          className={`tab${item.id === value ? " is-active" : ""}`}
          onClick={() => onChange?.(item.id)}
        >
          {item.label}
          {item.count !== undefined ? <span className="tab__count">{item.count}</span> : null}
        </button>
      ))}
    </div>
  );
}
