"use client";

import { useEffect } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";

import { APP_SHELL_NAV_ITEMS, projectHref } from "@/components/app-shell-nav";

const SHORTCUT_TIMEOUT_MS = 1200;

function shortcutMap(): Map<string, string> {
  const map = new Map<string, string>();
  for (const item of APP_SHELL_NAV_ITEMS) {
    if (!item.shortcut) continue;
    const parts = item.shortcut.toLowerCase().split(/\s+/);
    if (parts.length !== 2 || parts[0] !== "g") continue;
    map.set(parts[1], item.path);
  }
  return map;
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  const role = target.getAttribute("role");
  if (role === "textbox" || role === "combobox" || role === "searchbox") return true;
  return false;
}

export function EvoShortcuts() {
  const router = useRouter();
  const queryEnvironment = useSearchParams().get("environment");
  const params = useParams<{ org?: string; project?: string }>();

  useEffect(() => {
    const org = typeof params?.org === "string" ? params.org : null;
    const project = typeof params?.project === "string" ? params.project : null;
    if (!org || !project) return;
    const base = `/o/${org}/p/${project}`;
    const shortcuts = shortcutMap();

    let prefixArmed = false;
    let prefixTimer: number | null = null;

    function clearPrefix() {
      prefixArmed = false;
      if (prefixTimer !== null) {
        window.clearTimeout(prefixTimer);
        prefixTimer = null;
      }
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;

      const key = event.key.toLowerCase();
      if (!prefixArmed) {
        if (key === "g") {
          prefixArmed = true;
          prefixTimer = window.setTimeout(clearPrefix, SHORTCUT_TIMEOUT_MS);
        }
        return;
      }

      // prefix armed
      if (key === "escape" || key === "g") {
        clearPrefix();
        return;
      }

      const target = shortcuts.get(key);
      clearPrefix();
      if (!target && target !== "") return;
      event.preventDefault();
      router.push(projectHref(base, target, queryEnvironment));
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      clearPrefix();
    };
  }, [params?.org, params?.project, router, queryEnvironment]);

  return null;
}
