"use client";

import { RouteError } from "@/components/RouteError";

export default function Error(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError eyebrow="Operações / Config · Chaves API" title="Chaves API" {...props} />;
}
