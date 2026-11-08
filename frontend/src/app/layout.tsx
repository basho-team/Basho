import type { Metadata } from "next";
import "./globals.css";
import { LayoutShell } from "@/components/layout/LayoutShell";

export const metadata: Metadata = {
  title: "Basho — Plataforma Agentiva de PD&I",
  description:
    "Plataforma de gestão de PD&I com agentes autônomos, rastreabilidade de evidências e conformidade com a Lei do Bem.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" className="h-full antialiased">
      <body className="min-h-full">
        <LayoutShell>{children}</LayoutShell>
      </body>
    </html>
  );
}
