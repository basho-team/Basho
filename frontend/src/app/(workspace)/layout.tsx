import { Suspense } from "react";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SessionProvider } from "@/components/auth/session-provider";
import { DemoBanner } from "@/components/demo/demo-banner";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { TopBar } from "@/components/layout/top-bar";
import { demoLoginEnabled, SESSION_COOKIE, sessionStore } from "@/lib/auth/session";

async function Workspace({ children }: { children: React.ReactNode }) {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const user = demoLoginEnabled() ? await sessionStore().read(token) : null;
  if (!user) redirect("/login");
  return (
    <SessionProvider user={user}>
      <div className="min-h-dvh md:flex">
        <AppSidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <DemoBanner />
          <TopBar />
          <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-8 md:py-8">{children}</main>
        </div>
      </div>
    </SessionProvider>
  );
}

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<p className="p-8 text-muted-foreground">Verificando acesso…</p>}><Workspace>{children}</Workspace></Suspense>;
}
