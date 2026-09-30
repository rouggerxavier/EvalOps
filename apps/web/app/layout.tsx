import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "EvalOps Studio",
  description: "Controle de qualidade para agentes de IA com Quality Gates, tracing, avaliações e experimentos LLMOps.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}

