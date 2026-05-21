"use client";

import type { ReactNode } from "react";
import { ArrowRight } from "lucide-react";

type SuggestionRowProps = {
  title: ReactNode;
  description?: ReactNode;
  onSelect?: () => void;
};

export function SuggestionRow({ title, description, onSelect }: SuggestionRowProps) {
  return (
    <button type="button" className="attention" onClick={onSelect}>
      <span className="attention__icon">
        <ArrowRight size={16} />
      </span>
      <span>
        <span className="attention__title">{title}</span>
        {description ? <span className="attention__desc">{description}</span> : null}
      </span>
      <ArrowRight size={14} />
    </button>
  );
}
