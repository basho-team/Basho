"use client";

import { useState, type FormEvent } from "react";
import { ArrowRight, FlaskConical, LayoutDashboard, Scale, ShieldCheck } from "lucide-react";
import { BashoLogo } from "@/components/brand/logo";
import { ThemeToggle } from "@/components/theme/theme-toggle";
import { Button } from "@/components/ui/button";
import { DEMO_ACCOUNTS, ROLE_HOME, ROLE_LABELS, type AppRole } from "@/lib/auth/shared";

const ROLE_DESCRIPTION: Record<AppRole, string> = {
  researcher: "Seus relatórios, fontes de pesquisa e pendências. Você revisa somente o próprio trabalho.",
  manager: "Consolidação da equipe, acompanhamento, fechamento do período e configuração das fontes.",
  fiscal: "Pacote fiscal, documentos e sinalizações. Sem edição dos relatórios técnicos ou configuração das fontes.",
};
const ICONS = { researcher: FlaskConical, manager: LayoutDashboard, fiscal: Scale };
const FIELD = "mt-2 h-12 w-full rounded-xl border border-input bg-background px-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/40";

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

  return { email, setEmail, password, setPassword, role, setRole, message, pending, submit };
}

type LoginState = ReturnType<typeof useLoginForm>;

function LoginBrand() {
  return (<section className="relative hidden flex-col justify-between overflow-hidden lg:flex bg-[#10243e] p-7 text-white sm:p-12 lg:p-16">
        <BashoLogo />
        <div className="relative my-14 max-w-lg space-y-6 lg:my-20">
          <span className="inline-flex items-center gap-2 rounded-full border border-white/20 px-3 py-1 text-xs text-blue-100">
            <ShieldCheck className="size-3.5" aria-hidden /> Acesso à sua organização
          </span>
          <h1 className="font-serif text-4xl leading-tight font-semibold sm:text-5xl">O trabalho de pesquisa.<br />As evidências no mesmo lugar.</h1>
          <p className="max-w-md text-base leading-relaxed text-blue-100/80">
            Entre com sua conta e escolha a função autorizada. Cada pessoa tem um espaço para acompanhar, revisar e decidir.
          </p>
          <div className="flex flex-wrap gap-2 pt-3 text-xs text-blue-100">
            {["GitHub", "Notion", "Google Drive"].map(name => (
              <span key={name} className="rounded-lg border border-white/15 bg-white/5 px-3 py-2">{name}</span>
            ))}
          </div>
        </div>
        <p className="max-w-md text-xs leading-relaxed text-blue-100/60">Acompanhe pesquisas, documentos e decisões em um só lugar.</p>
      </section>);
}

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

function DemoAccounts({ state }: { state: LoginState }) {
  const { setEmail, setRole } = state;
  return (          <details className="mt-8 border-t pt-5 text-sm">
            <summary className="cursor-pointer text-muted-foreground">Contas disponíveis</summary>
            <div className="mt-3 grid gap-2">
              {DEMO_ACCOUNTS.map(account => {
                const Icon = ICONS[account.role];
                return <button key={account.id} type="button" onClick={() => { setEmail(account.email); setRole(account.role); }}
                  className="flex items-center gap-3 rounded-lg border bg-card p-3 text-left outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/40">
                  <Icon className="size-4 text-primary" aria-hidden />
                  <span><span className="block font-medium">{account.name}</span><span className="text-xs text-muted-foreground">{account.email} · {ROLE_LABELS[account.role]}</span></span>
                </button>;
              })}
            </div>
            <p className="mt-3 text-xs text-muted-foreground">Use a senha fornecida para sua conta. A função deve corresponder à conta.</p>
          </details>);
}

export function LoginForm() {
  const state = useLoginForm();
  const { role, message, pending, submit } = state;
  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.05fr_1fr]">
      <LoginBrand />
      <section className="flex flex-col bg-background p-6 sm:p-12 lg:px-16">
        <div className="flex items-center justify-between lg:justify-end"><span className="lg:hidden"><BashoLogo /></span><ThemeToggle /></div>
        <div className="m-auto w-full max-w-md py-10">
          <p className="text-xs font-semibold tracking-widest text-primary uppercase">Bem-vindo ao Basho</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight">Entre na sua organização</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">Lumen Sensores</p>
          <form className="mt-8 space-y-5" onSubmit={submit}>
            <LoginFields state={state} />
            {role && <p className="rounded-xl border bg-card p-3 text-sm leading-relaxed text-muted-foreground">{ROLE_DESCRIPTION[role]}</p>}
            {message && <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{message}</p>}
            <Button type="submit" disabled={pending} className="h-12 w-full">
              {pending ? "Entrando…" : "Entrar no Basho"} <ArrowRight className="size-4" aria-hidden />
            </Button>
          </form>
          <DemoAccounts state={state} />
        </div>
      </section>
    </div>
  );
}
