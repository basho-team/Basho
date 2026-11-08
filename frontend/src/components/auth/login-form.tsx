"use client";

import { useState, type FormEvent } from "react";
import { ArrowRight, FlaskConical, LayoutDashboard, Scale } from "lucide-react";
import { LoginBackdrop, LoginHero } from "@/components/auth/login-hero";
import { BashoLogo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { DEMO_ACCOUNTS, ROLE_HOME, ROLE_LABELS, type AppRole } from "@/lib/auth/shared";

const ROLE_DESCRIPTION: Record<AppRole, string> = {
  researcher: "Seus relatórios, fontes de pesquisa e pendências. Você revisa somente o próprio trabalho.",
  manager: "Consolidação da equipe, acompanhamento, fechamento do período e configuração das fontes simuladas.",
  fiscal: "Pacote fiscal, documentos e sinalizações. Sem edição dos relatórios técnicos ou configuração das fontes.",
};
const ICONS = { researcher: FlaskConical, manager: LayoutDashboard, fiscal: Scale };
const FIELD = "mt-2 h-12 w-full rounded-xl border border-input bg-background/70 px-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/40";

function useLoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<AppRole | "">("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setMessage("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password, role }),
      });
      const result: { message?: string } = await response.json();
      if (!response.ok) { setMessage(result.message ?? "Não foi possível entrar."); return; }
      window.location.assign(role ? ROLE_HOME[role] : "/");
    } catch { setMessage("Não foi possível conectar. Tente novamente."); }
    finally { setPending(false); }
  }

  /** Entrada rápida (opt-in no servidor): um clique na conta cria a sessão, sem senha. */
  async function quickLogin(account: (typeof DEMO_ACCOUNTS)[number]) {
    setPending(true);
    setMessage("");
    try {
      const response = await fetch("/api/auth/demo", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accountId: account.id }),
      });
      const result: { message?: string } = await response.json();
      if (!response.ok) { setMessage(result.message ?? "Não foi possível entrar."); return; }
      window.location.assign(ROLE_HOME[account.role]);
    } catch { setMessage("Não foi possível conectar. Tente novamente."); }
    finally { setPending(false); }
  }

  return { email, setEmail, password, setPassword, role, setRole, message, pending, submit, quickLogin };
}

type LoginState = ReturnType<typeof useLoginForm>;

function LoginFields({ state }: { state: LoginState }) {
  const { email, setEmail, password, setPassword, role, setRole } = state;
  return <>
            <label className="block text-sm font-medium" htmlFor="email">E-mail
              <input id="email" name="email" type="email" autoComplete="username" value={email}
                onChange={event => setEmail(event.target.value)} required maxLength={254} className={FIELD} placeholder="seu.nome@organizacao.com" />
            </label>
            <label className="block text-sm font-medium" htmlFor="password">Senha
              <input id="password" name="password" type="password" autoComplete="current-password" value={password}
                onChange={event => setPassword(event.target.value)} required maxLength={256} className={FIELD} />
            </label>
            <label className="block text-sm font-medium" htmlFor="role">Sua função na organização
              <select id="role" name="role" value={role} required className={FIELD}
                onChange={event => setRole(event.target.value as AppRole | "")}>
                <option value="" disabled>Selecione sua função</option>
                {Object.entries(ROLE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
  </>;
}

function DemoAccounts({ state, openAccess }: { state: LoginState; openAccess: boolean }) {
  const { setEmail, setRole, quickLogin, pending } = state;
  return (          <details className="mt-8 border-t pt-5 text-sm" open={openAccess}>
            <summary className="cursor-pointer text-muted-foreground">
              {openAccess ? "Entrar com uma conta de demonstração" : "Contas disponíveis para demonstração"}
            </summary>
            <div className="mt-3 grid gap-2">
              {DEMO_ACCOUNTS.map(account => {
                const Icon = ICONS[account.role];
                return <button key={account.id} type="button" disabled={pending}
                  onClick={() => { if (openAccess) void quickLogin(account); else { setEmail(account.email); setRole(account.role); } }}
                  className="flex items-center gap-3 rounded-lg border bg-card/60 p-3 text-left outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/40">
                  <Icon className="size-4 text-primary" aria-hidden />
                  <span><span className="block font-medium">{account.name}</span><span className="text-xs text-muted-foreground">{account.email} · {ROLE_LABELS[account.role]}</span></span>
                </button>;
              })}
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              {openAccess
                ? "Clique em uma conta para entrar: modo de demonstração com dados fictícios, sem senha."
                : "Use a senha local fornecida para esta demonstração. A função deve corresponder à conta."}
            </p>
          </details>);
}

export function LoginForm({ openAccess = false }: { openAccess?: boolean }) {
  const state = useLoginForm();
  const { role, message, pending, submit } = state;
  return (
    <div className="relative min-h-dvh">
      <LoginBackdrop />
      <div className="relative grid min-h-dvh lg:grid-cols-[1.1fr_1fr]">
      <LoginHero />
      <section className="relative flex flex-col items-center justify-center p-4 sm:p-8 lg:px-12">
        <div className="dark w-full max-w-md rounded-3xl border border-white/12 bg-[#0b1226]/70 p-7 text-foreground shadow-[0_30px_80px_-20px_rgba(2,6,23,0.9)] backdrop-blur-2xl sm:p-9">
          <BashoLogo className="mb-8 lg:hidden" />
          <p className="text-xs font-semibold tracking-widest text-primary uppercase">Bem-vindo ao Basho</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight">Entre na sua organização</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">Lumen Sensores · demonstração local</p>
          <form className="mt-8 space-y-5" onSubmit={submit}>
            <LoginFields state={state} />
            {role && <p className="rounded-xl border bg-card/60 p-3 text-sm leading-relaxed text-muted-foreground">{ROLE_DESCRIPTION[role]}</p>}
            {message && <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{message}</p>}
            <Button type="submit" disabled={pending} className="h-12 w-full">
              {pending ? "Entrando…" : "Entrar no Basho"} <ArrowRight className="size-4" aria-hidden />
            </Button>
          </form>
          <DemoAccounts state={state} openAccess={openAccess} />
        </div>
      </section>
      </div>
    </div>
  );
}
