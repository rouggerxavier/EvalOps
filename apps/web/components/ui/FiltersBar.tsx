"use client";

import type { FormEvent } from "react";
import { Search } from "lucide-react";

type FilterOption = {
  label: string;
  value: string;
};

type FiltersBarProps = {
  searchName?: string;
  searchPlaceholder?: string;
  statusOptions?: FilterOption[];
  envOptions?: FilterOption[];
  defaultStatus?: string;
  defaultEnv?: string;
  onSubmit?: (form: FormData) => void;
};

export function FiltersBar({
  searchName = "name",
  searchPlaceholder = "Buscar...",
  statusOptions = [],
  envOptions = [],
  defaultStatus = "",
  defaultEnv = "",
  onSubmit,
}: FiltersBarProps) {
  function submit(event: FormEvent<HTMLFormElement>) {
    if (!onSubmit) return;
    event.preventDefault();
    onSubmit(new FormData(event.currentTarget));
  }

  return (
    <form className="filters" onSubmit={submit}>
      <label className="filter-group">
        <Search size={13} />
        <input className="filter-input" name={searchName} placeholder={searchPlaceholder} />
      </label>
      {statusOptions.length ? (
        <select className="filter-select" name="status" defaultValue={defaultStatus}>
          {statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      ) : null}
      {envOptions.length ? (
        <select className="filter-select" name="environment" defaultValue={defaultEnv}>
          {envOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      ) : null}
      <button className="btn btn--sm" type="submit">Filtrar</button>
    </form>
  );
}
