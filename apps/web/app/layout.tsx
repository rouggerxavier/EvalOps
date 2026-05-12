import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "EvalOps Studio",
  description: "AI observability, tracing and evaluation for production AI systems.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
