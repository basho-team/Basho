import type { Metadata } from "next";
import { Geist_Mono, Inter, Source_Serif_4 } from "next/font/google";
import { DemoBanner } from "@/components/demo/demo-banner";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { TopBar } from "@/components/layout/top-bar";
import { THEME_INIT_SCRIPT } from "@/lib/theme-script";
import "./globals.css";
import { Providers } from "./providers";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

/** Só para o nome da marca e o título da abertura, como o logotipo. */
const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin"],
  weight: ["600", "700"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Basho",
  description: "Operação de projetos de P&D com a conformidade da Lei do Bem embutida no fluxo.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // `suppressHydrationWarning`: o script do <head> aplica a classe `dark` antes da hidratação.
    <html
      lang="pt-BR"
      suppressHydrationWarning
      className={`${inter.variable} ${sourceSerif.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-full">
        <Providers>
          <div className="min-h-dvh md:flex">
            <AppSidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <DemoBanner />
              <TopBar />
              <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-8 md:py-8">{children}</main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
