"use client";

import { RouteError } from "@/components/RouteError";

export default function Error(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError eyebrow="Operação · Traces" title="Traces" {...props} />;
}
