"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { APP_SHELL_NAV_ITEMS, projectHref } from "@/components/app-shell-nav";

type Props = {
  org: string;
  project: string;
};

const SEQUENCE_WINDOW_MS = 1200;

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return false;
}

function parseShortcut(shortcut: string | undefined): string | null {
  if (!shortcut) return null;
  const parts = shortcut.trim().split(/\s+/);
  if (parts.length !== 2) return null;
  if (parts[0].toLowerCase() !== "g") return null;
  const letter = parts[1].toLowerCase();
  if (letter.length !== 1) return null;
  return letter;
}

export function KeyboardShortcuts({ org, project }: Props) {
  const router = useRouter();
  const armedAt = useRef<number>(0);

  useEffect(() => {
    const base = `/o/${org}/p/${project}`;
    const map = new Map<string, string>();
    for (const item of APP_SHELL_NAV_ITEMS) {
      const letter = parseShortcut(item.shortcut);
      if (letter) map.set(letter, projectHref(base, item.path));
    }

    function handler(event: KeyboardEvent) {
      if (event.defaultPrevented) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) {
        armedAt.current = 0;
        return;
      }

      const key = event.key.toLowerCase();
      if (key === "escape") {
        armedAt.current = 0;
        return;
      }

      const now = Date.now();
      const isArmed = armedAt.current > 0 && now - armedAt.current <= SEQUENCE_WINDOW_MS;

      if (!isArmed) {
        if (key === "g") {
          armedAt.current = now;
          event.preventDefault();
        }
        return;
      }

      armedAt.current = 0;
      const target = map.get(key);
      if (target) {
        event.preventDefault();
        router.push(target);
      }
    }

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [org, project, router]);

  return null;
}
