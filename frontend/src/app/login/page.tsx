import { connection } from "next/server";
import { Suspense } from "react";
import { LoginForm } from "@/components/auth/login-form";
import { openAccessEnabled } from "@/lib/auth/session";

/** `connection()` adia a leitura da flag para a requisição: o build não a congela. */
async function LoginContent() {
  await connection();
  return <LoginForm openAccess={openAccessEnabled()} />;
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-dvh bg-background" aria-busy="true" />}>
      <LoginContent />
    </Suspense>
  );
}
