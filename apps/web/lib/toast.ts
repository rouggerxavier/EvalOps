export type ToastTone = "ok" | "err" | "info" | "warn";

export type ToastDetail = {
  tone: ToastTone;
  message: string;
  title?: string;
  ttl?: number;
};

export const TOAST_EVENT = "evo:toast";

export function emitToast(detail: ToastDetail): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<ToastDetail>(TOAST_EVENT, { detail }));
}
