"use client";

import { Check, Circle, FileText, Folder, GitPullRequest, HardDrive, Loader2, Minus, NotebookPen, RotateCcw, ShieldCheck, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useDemoUser } from "@/components/auth/session-provider";
import { PageHeader, Section } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  EXAMPLE_LINKS,
  InvalidSourceLink,
  parseSourceLink,
  SOURCE_HINT,
  SOURCE_LABEL,
  type ParsedSource,
  type SourceKind,
} from "@/lib/demo-sources/links";
import { buildReport, publicationPlan, syntheticCommits, type GeneratedReport, type Publication } from "@/lib/demo-sources/simulate";

const KINDS: readonly SourceKind[] = ["github", "drive", "notion"];
const ICON = { github: GitPullRequest, drive: HardDrive, notion: NotebookPen };
const STEP_DELAY_MS = 900;

type StepId = "github" | "maker" | "checker" | "drive" | "notion";
type StepStatus = "waiting" | "running" | "done" | "skipped";
const STEPS: readonly { id: StepId; label: string; detail: string }[] = [
  { id: "github", label: "Ler o GitHub", detail: "Lê commits e PRs do repositório conectado." },
  { id: "maker", label: "O Maker escreve o relatório", detail: "Cada afirmação cita os commits que a sustentam." },
  { id: "checker", label: "O Checker confere", detail: "Outro modelo confere citações; instruções escondidas em commits viram dado." },
  { id: "drive", label: "Publicar na pasta BASHO do Drive", detail: "Cria BASHO dentro da pasta que você conectou." },
  { id: "notion", label: "Publicar na página BASHO do Notion", detail: "Cria BASHO dentro da página que você conectou." },
];
const initialSteps = (): Record<StepId, StepStatus> => ({ github: "waiting", maker: "waiting", checker: "waiting", drive: "waiting", notion: "waiting" });

type Urls = Partial<Record<SourceKind, string>>;
interface Stored {
  urls: Urls;
  ranAt: string | null;
}

const storageKey = (accountId: string) => `basho-demo-sources:${accountId}`;

/** Só o que o usuário colou fica no navegador; o relatório é refeito (é determinístico). */
function load(accountId: string): { links: Partial<Record<SourceKind, ParsedSource>>; urls: Urls; ranAt: string | null } {
  const links: Partial<Record<SourceKind, ParsedSource>> = {};
  const urls: Urls = {};
  try {
    const raw = window.localStorage.getItem(storageKey(accountId));
    const stored = raw ? (JSON.parse(raw) as Partial<Stored>) : null;
    for (const kind of KINDS) {
      const url = stored?.urls?.[kind];
      if (typeof url === "string") {
        links[kind] = parseSourceLink(kind, url);
        urls[kind] = url;
      }
    }
    return { links, urls, ranAt: typeof stored?.ranAt === "string" ? stored.ranAt : null };
  } catch {
    return { links: {}, urls: {}, ranAt: null };
  }
}

function save(accountId: string, urls: Urls, ranAt: string | null) {
  try {
    window.localStorage.setItem(storageKey(accountId), JSON.stringify({ urls, ranAt } satisfies Stored));
  } catch {
    /* sem armazenamento (janela privada): a demonstração segue, só não lembra */
  }
}

const sleep = (ms: number) => new Promise<void>(resolve => window.setTimeout(resolve, ms));

function SourceField(props: {
  kind: SourceKind;
  value: string;
  connected: ParsedSource | undefined;
  error: string | undefined;
  onChange: (value: string) => void;
  onConnect: () => void;
  onRemove: () => void;
}) {
  const { kind, value, connected, error, onChange, onConnect, onRemove } = props;
  const Icon = ICON[kind];
  return (
    <div className="space-y-2 rounded-xl border p-4" data-source={kind}>
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-medium"><Icon className="size-4 text-primary" aria-hidden />{SOURCE_LABEL[kind]}</p>
        {connected && <Badge variant="secondary">Conectado (simulado)</Badge>}
      </div>
      {connected ? (
        <div className="flex items-center justify-between gap-2 text-sm">
          <span className="break-all font-mono text-xs text-muted-foreground">{connected.label}</span>
          <Button size="sm" variant="ghost" onClick={onRemove}>Remover</Button>
        </div>
      ) : (
        <>
          <label className="sr-only" htmlFor={`link-${kind}`}>Link: {SOURCE_LABEL[kind]}</label>
          <input
            id={`link-${kind}`}
            value={value}
            onChange={event => onChange(event.target.value)}
            onKeyDown={event => { if (event.key === "Enter") onConnect(); }}
            placeholder={SOURCE_HINT[kind]}
            autoComplete="off"
            spellCheck={false}
            className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
          />
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <Button size="sm" variant="outline" disabled={value.trim().length < 8} onClick={onConnect}>Conectar</Button>
        </>
      )}
    </div>
  );
}

function StepIcon({ status }: { status: StepStatus }) {
  if (status === "done") return <Check className="size-4 text-primary" aria-hidden />;
  if (status === "running") return <Loader2 className="size-4 animate-spin text-primary" aria-hidden />;
  if (status === "skipped") return <Minus className="size-4 text-muted-foreground" aria-hidden />;
  return <Circle className="size-4 text-muted-foreground" aria-hidden />;
}

function Pipeline({ steps }: { steps: Record<StepId, StepStatus> }) {
  return (
    <ol className="space-y-2" aria-live="polite">
      {STEPS.map(step => (
        <li key={step.id} className="flex items-start gap-3 text-sm">
          <span className="mt-0.5"><StepIcon status={steps[step.id]} /></span>
          <span>
            <span className={steps[step.id] === "waiting" ? "text-muted-foreground" : "font-medium"}>{step.label}</span>
            {steps[step.id] === "skipped" && <span className="text-muted-foreground"> · não conectado, pulado</span>}
            <span className="block text-xs text-muted-foreground">{step.detail}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

function ReportView({ report }: { report: GeneratedReport }) {
  return (
    <article className="space-y-4 rounded-xl border bg-card p-5 text-sm leading-relaxed">
      <header>
        <h3 className="text-base font-semibold">{report.title}</h3>
        <p className="mt-1 text-muted-foreground">{report.summary}</p>
        <Badge variant="outline" className="mt-2">Dado sintético</Badge>
      </header>
      {report.sections.map(section => (
        <section key={section.title}>
          <h4 className="font-semibold">{section.title}</h4>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {section.items.map(item => (
              <li key={item.text}>{item.text} <span className="text-muted-foreground">{item.refs.map(ref => `[${ref}]`).join("")}</span></li>
            ))}
          </ul>
        </section>
      ))}
      <section>
        <h4 className="font-semibold">Pendências para os responsáveis</h4>
        <ul className="mt-1 list-disc space-y-1 pl-5">
          {report.pending.map(item => <li key={item.question}>{item.question} <span className="text-muted-foreground">(responsável: {item.role})</span></li>)}
        </ul>
      </section>
      <section>
        <h4 className="font-semibold">Fontes</h4>
        <ul className="mt-1 space-y-1">
          {report.sources.map(source => <li key={source.n} className="font-mono text-xs text-muted-foreground">[{source.n}] {source.label}</li>)}
        </ul>
      </section>
      {report.guardrails.length > 0 && (
        <section className="rounded-lg border border-primary/30 bg-primary/5 p-3">
          <h4 className="flex items-center gap-2 font-semibold"><ShieldCheck className="size-4 text-primary" aria-hidden />O que a plataforma não fez</h4>
          <ul className="mt-1 list-disc space-y-1 pl-5">{report.guardrails.map(note => <li key={note}>{note}</li>)}</ul>
        </section>
      )}
      <p className="text-xs text-muted-foreground">{report.disclaimer}</p>
    </article>
  );
}

function PublishedTree({ published }: { published: Publication[] }) {
  if (published.length === 0) {
    return <p className="text-sm text-muted-foreground">Nada foi publicado: conecte uma pasta do Drive ou uma página do Notion para ver a pasta BASHO.</p>;
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {published.map(item => {
        const Icon = ICON[item.destination];
        return (
          <div key={item.destination} className="rounded-xl border p-4 text-sm" data-published={item.destination}>
            <p className="mb-2 flex items-center gap-2 font-medium"><Icon className="size-4 text-primary" aria-hidden />{item.destination === "drive" ? "Google Drive" : "Notion"} <Badge variant="secondary">Publicado (simulado)</Badge></p>
            <ul className="space-y-1.5">
              {item.path.map((part, index) => (
                <li key={`${part}-${index}`} style={{ paddingLeft: `${index * 16}px` }} className="flex items-start gap-2">
                  {index === item.path.length - 1 ? <FileText className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden /> : <Folder className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />}
                  <span className={index === 1 ? "font-semibold" : "break-words"}>{part}</span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

/** `stepDelayMs` só existe para os testes não esperarem a animação dos passos. */
export function SourcesPanel({ stepDelayMs = STEP_DELAY_MS }: { stepDelayMs?: number } = {}) {
  const user = useDemoUser();
  const [drafts, setDrafts] = useState<Record<SourceKind, string>>({ github: "", drive: "", notion: "" });
  const [links, setLinks] = useState<Partial<Record<SourceKind, ParsedSource>>>({});
  const [errors, setErrors] = useState<Partial<Record<SourceKind, string>>>({});
  const [steps, setSteps] = useState<Record<StepId, StepStatus>>(initialSteps);
  const [running, setRunning] = useState(false);
  const [ranAt, setRanAt] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const alive = useRef(true);
  const rawLinks = useRef<Record<SourceKind, string>>({ github: "", drive: "", notion: "" });

  useEffect(() => {
    alive.current = true;
    const restored = load(user.accountId);
    rawLinks.current = { github: "", drive: "", notion: "", ...restored.urls };
    setLinks(restored.links);
    setRanAt(restored.ranAt && restored.links.github ? restored.ranAt : null);
    setReady(true);
    return () => { alive.current = false; };
  }, [user.accountId]);

  const persist = useCallback((next: Partial<Record<SourceKind, ParsedSource>>, when: string | null, raw: Record<SourceKind, string>) => {
    const urls: Urls = {};
    for (const kind of KINDS) if (next[kind]) urls[kind] = raw[kind] || EXAMPLE_LINKS[kind];
    save(user.accountId, urls, when);
  }, [user.accountId]);

  function connect(kind: SourceKind, value = drafts[kind]): boolean {
    try {
      const parsed = parseSourceLink(kind, value);
      rawLinks.current = { ...rawLinks.current, [kind]: value.trim() };
      const next = { ...links, [kind]: parsed };
      setLinks(next);
      setErrors(current => ({ ...current, [kind]: undefined }));
      setRanAt(null);
      persist(next, null, rawLinks.current);
      return true;
    } catch (error) {
      setErrors(current => ({ ...current, [kind]: error instanceof InvalidSourceLink ? error.message : "Link inválido." }));
      return false;
    }
  }

  function remove(kind: SourceKind) {
    const next = { ...links };
    delete next[kind];
    setLinks(next);
    setRanAt(null);
    persist(next, null, rawLinks.current);
  }

  function fillExamples() {
    setDrafts({ ...EXAMPLE_LINKS });
    setErrors({});
  }

  function connectAll() {
    let next = { ...links };
    const raw = { ...rawLinks.current };
    for (const kind of KINDS) {
      if (next[kind] || !drafts[kind].trim()) continue;
      try {
        next = { ...next, [kind]: parseSourceLink(kind, drafts[kind]) };
        raw[kind] = drafts[kind].trim();
        setErrors(current => ({ ...current, [kind]: undefined }));
      } catch (error) {
        setErrors(current => ({ ...current, [kind]: error instanceof InvalidSourceLink ? error.message : "Link inválido." }));
      }
    }
    rawLinks.current = raw;
    setLinks(next);
    setRanAt(null);
    persist(next, null, raw);
  }

  async function run() {
    if (!links.github) return;
    setRunning(true);
    setRanAt(null);
    const status = initialSteps();
    setSteps({ ...status });
    for (const step of STEPS) {
      const connected = step.id === "drive" ? links.drive : step.id === "notion" ? links.notion : links.github;
      if (!connected) {
        status[step.id] = "skipped";
        setSteps({ ...status });
        continue;
      }
      status[step.id] = "running";
      setSteps({ ...status });
      await sleep(stepDelayMs);
      if (!alive.current) return;
      status[step.id] = "done";
      setSteps({ ...status });
    }
    const finishedAt = new Date().toISOString();
    setRanAt(finishedAt);
    persist(links, finishedAt, rawLinks.current);
    setRunning(false);
  }

  function reset() {
    setLinks({});
    setDrafts({ github: "", drive: "", notion: "" });
    setErrors({});
    setSteps(initialSteps());
    setRanAt(null);
    rawLinks.current = { github: "", drive: "", notion: "" };
    save(user.accountId, {}, null);
  }

  const report = ranAt && links.github ? buildReport(links.github.id, syntheticCommits(links.github.id), new Date(ranAt)) : null;
  const published = report ? publicationPlan(report, links.drive, links.notion) : [];
  const anyDraft = KINDS.some(kind => drafts[kind].trim().length > 0 && !links[kind]);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Minhas fontes"
        subtitle="Conecte seu GitHub, seu Drive e seu Notion. A plataforma lê o GitHub, escreve o relatório e organiza tudo na pasta BASHO."
        actions={<Button variant="ghost" size="sm" onClick={reset} disabled={running}><RotateCcw aria-hidden />Recomeçar</Button>}
      />
      <div className="flex gap-3 rounded-xl border bg-card p-4 text-sm">
        <ShieldCheck className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
        <p className="leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground">Simulação de demonstração.</span> Nenhum serviço externo é acessado: os commits são fictícios
          (gerados a partir do nome do repositório), os links só servem para identificar origem e destino, e tudo fica neste navegador.
        </p>
      </div>

      <Section title="1. Conecte suas fontes">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Cole os links (podem ser hipotéticos)</CardTitle>
            <CardDescription>O Basho confere o formato e guarda só o identificador. Na versão real, a pasta e a página precisam estar compartilhadas com a conta do Basho.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 lg:grid-cols-3">
              {KINDS.map(kind => (
                <SourceField
                  key={kind}
                  kind={kind}
                  value={drafts[kind]}
                  connected={links[kind]}
                  error={errors[kind]}
                  onChange={value => setDrafts(current => ({ ...current, [kind]: value }))}
                  onConnect={() => connect(kind)}
                  onRemove={() => remove(kind)}
                />
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={fillExamples}>Preencher com exemplos</Button>
              <Button size="sm" disabled={!anyDraft} onClick={connectAll}>Conectar tudo</Button>
            </div>
          </CardContent>
        </Card>
      </Section>

      <Section title="2. Deixe a plataforma trabalhar">
        <Card>
          <CardContent className="space-y-4 pt-6">
            <Button disabled={!ready || !links.github || running} onClick={() => void run()}>
              <Sparkles aria-hidden />{running ? "Trabalhando…" : "Gerar e publicar relatório"}
            </Button>
            {!links.github && <p className="text-sm text-muted-foreground">Conecte um repositório do GitHub para começar. Drive e Notion são os destinos.</p>}
            {(running || report) && <Pipeline steps={steps} />}
          </CardContent>
        </Card>
      </Section>

      {report && (
        <>
          <Section title="3. O que a plataforma publicou">
            <PublishedTree published={published} />
          </Section>
          <Section title="4. O relatório gerado"><ReportView report={report} /></Section>
        </>
      )}
    </div>
  );
}
