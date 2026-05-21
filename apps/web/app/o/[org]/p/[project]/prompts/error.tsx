"use client";

import { RouteError } from "@/components/RouteError";

export default function Error(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError eyebrow="Recursos · Prompts" title="Prompts" {...props} />;
}
