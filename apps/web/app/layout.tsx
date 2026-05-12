import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "EvalOps Studio",
  description: "Observabilidade, tracing e avaliação para sistemas de IA em produção.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}

