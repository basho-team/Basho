import type { ComponentType, SVGProps } from "react";
import { FileCheck2, FileText, FolderOpen, GitBranch, Scale, ShieldCheck } from "lucide-react";
import { BashoLogo, BashoMark } from "@/components/brand/logo";

/**
 * Lado de marca do login: fontes (GitHub, Notion, Drive) convergem por feixes animados no Basho,
 * que entrega relatório verificado e dossiê fiscal. Inspirado nos padrões "Animated Beam" e
 * "Retro Grid" do Magic UI, feito só com SVG + CSS (sem dependência nova). Animações respeitam
 * `prefers-reduced-motion` (ver `globals.css`, prefixo `basho-`). Dados exibidos são fictícios.
 */

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

// Sistema de coordenadas do diagrama (o container mantém a mesma proporção).
const W = 480;
const H = 300;
const HUB = { x: 240, y: 150 };

interface Node {
  id: string;
  label: string;
  icon: Icon;
  x: number;
  y: number;
}

const SOURCES: Node[] = [
  { id: "github", label: "GitHub", icon: GitBranch, x: 52, y: 58 },
  { id: "notion", label: "Notion", icon: FileText, x: 52, y: 150 },
  { id: "drive", label: "Google Drive", icon: FolderOpen, x: 52, y: 242 },
];

const OUTPUTS: Node[] = [
  { id: "report", label: "Relatório verificado", icon: FileCheck2, x: 428, y: 100 },
  { id: "dossier", label: "Dossiê Lei do Bem", icon: Scale, x: 428, y: 200 },
];

const LEDGER = [
  { kind: "pull_request_observed", ref: "demo/experimentos#1", hash: "a3f9c1" },
  { kind: "document_observed", ref: "Plano de trabalho · T2.1", hash: "7be204" },
  { kind: "verification_result", ref: "Checker · pass", hash: "c51d8e" },
  { kind: "commit_observed", ref: "bench: p95 sem melhora", hash: "e09a77" },
];

function curve(from: { x: number; y: number }, to: { x: number; y: number }) {
  const mid = (from.x + to.x) / 2;
  return `M ${from.x} ${from.y} C ${mid} ${from.y}, ${mid} ${to.y}, ${to.x} ${to.y}`;
}

const pct = (value: number, total: number) => `${(value / total) * 100}%`;

function Beam({ d, delay, reverse = false }: { d: string; delay: number; reverse?: boolean }) {
  return (
    <g>
      <path d={d} className="stroke-white/10" strokeWidth={1.5} fill="none" />
      <path
        d={d}
        stroke={reverse ? "url(#basho-beam-out)" : "url(#basho-beam-in)"}
        strokeWidth={2.2}
        strokeLinecap="round"
        fill="none"
        pathLength={100}
        strokeDasharray="18 82"
        className="basho-beam"
        style={{ animationDelay: `${delay}s` }}
      />
    </g>
  );
}

function NodeChip({ node, align }: { node: Node; align: "left" | "right" }) {
  const Icon = node.icon;
  return (
    <div
      className="absolute flex items-center"
      style={{ top: pct(node.y, H), left: pct(node.x, W), transform: "translate(-50%, -50%)" }}
      data-align={align}
    >
      <div className="relative flex size-11 items-center justify-center rounded-xl border border-white/15 bg-[#0d1b33]/90 shadow-[0_0_24px_-6px_rgba(99,102,241,0.6)] backdrop-blur">
        <Icon className="size-5 text-blue-100" aria-hidden />
      </div>
      <span className="absolute top-full left-1/2 mt-1.5 -translate-x-1/2 whitespace-nowrap text-[11px] font-medium text-blue-100/75">
        {node.label}
      </span>
    </div>
  );
}

function FlowDiagram() {
  return (
    <div className="relative mx-auto w-full max-w-md shrink xl:max-w-lg [@media(max-height:820px)]:max-w-sm" style={{ aspectRatio: `${W} / ${H}` }} aria-hidden>
      <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 size-full overflow-visible">
        <defs>
          <linearGradient id="basho-beam-in" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#818cf8" stopOpacity="0" />
            <stop offset="50%" stopColor="#a5b4fc" />
            <stop offset="100%" stopColor="#22d3ee" />
          </linearGradient>
          <linearGradient id="basho-beam-out" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#22d3ee" />
            <stop offset="100%" stopColor="#34d399" />
          </linearGradient>
        </defs>
        {SOURCES.map((node, i) => (
          <Beam key={node.id} d={curve({ x: node.x + 24, y: node.y }, HUB)} delay={i * 0.7} />
        ))}
        {OUTPUTS.map((node, i) => (
          <Beam key={node.id} d={curve(HUB, { x: node.x - 24, y: node.y })} delay={1.4 + i * 0.6} reverse />
        ))}
      </svg>

      {SOURCES.map(node => (
        <NodeChip key={node.id} node={node} align="left" />
      ))}
      {OUTPUTS.map(node => (
        <NodeChip key={node.id} node={node} align="right" />
      ))}

      {/* Hub: monograma com anéis pulsando. */}
      <div
        className="absolute flex items-center justify-center"
        style={{ left: pct(HUB.x, W), top: pct(HUB.y, H), transform: "translate(-50%, -50%)" }}
      >
        <span className="basho-ring absolute size-24 rounded-full border border-indigo-300/30" />
        <span className="basho-ring absolute size-24 rounded-full border border-cyan-300/25" style={{ animationDelay: "1.2s" }} />
        <div className="relative flex size-20 items-center justify-center rounded-2xl border border-white/20 bg-gradient-to-br from-indigo-500/30 via-[#13254a] to-cyan-500/20 shadow-[0_0_60px_-10px_rgba(129,140,248,0.9)] backdrop-blur">
          <BashoMark className="size-10 text-white" />
        </div>
      </div>
    </div>
  );
}

function LedgerTicker() {
  return (
    <div className="relative h-[4.6rem] w-full max-w-xl shrink-0 overflow-hidden text-left rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2 font-mono text-[11px] text-blue-100/70">
      <div className="basho-ticker space-y-2">
        {[...LEDGER, ...LEDGER].map((event, i) => (
          <div key={i} className="flex items-center gap-3 whitespace-nowrap">
            <span className="size-1.5 shrink-0 rounded-full bg-emerald-400 shadow-[0_0_8px] shadow-emerald-400" />
            <span className="text-indigo-200">{event.kind}</span>
            <span className="truncate text-blue-100/50">{event.ref}</span>
            <span className="ml-auto text-cyan-200/60">sha256:{event.hash}…</span>
          </div>
        ))}
      </div>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-5 bg-gradient-to-b from-[#0b1730] to-transparent" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-5 bg-gradient-to-t from-[#0b1730] to-transparent" />
    </div>
  );
}

/** Fundo da tela inteira de login: cor, grade em perspectiva e brilhos. */
export function LoginBackdrop() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden bg-[#0b1730]" aria-hidden>
      <div className="absolute inset-0 [perspective:700px]">
        <div className="basho-grid absolute inset-x-[-50%] bottom-[-30%] h-[80%] [transform:rotateX(65deg)] [mask-image:linear-gradient(to_top,black_10%,transparent_85%)]" />
      </div>
      <div className="absolute -top-40 -left-32 size-[30rem] rounded-full bg-indigo-600/25 blur-3xl" />
      <div className="absolute top-1/4 right-[8%] size-[26rem] rounded-full bg-violet-600/20 blur-3xl" />
      <div className="absolute -right-24 bottom-0 size-96 rounded-full bg-cyan-500/15 blur-3xl" />
    </div>
  );
}

/** Conteúdo de marca (lado esquerdo, telas largas). O fundo vem de `LoginBackdrop`. */
export function LoginHero() {
  return (
    <section className="relative hidden min-h-dvh flex-col justify-between gap-4 px-12 py-8 text-white lg:sticky lg:top-0 lg:flex xl:px-16">
      <BashoLogo className="relative shrink-0 gap-2 text-white/90" markClassName="size-6" nameClassName="text-xl" />

      <div className="relative flex min-h-0 flex-1 flex-col items-center justify-center gap-5 text-center">
        <div className="mx-auto flex max-w-xl flex-col items-center space-y-3">
          <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs text-blue-100 backdrop-blur">
            <ShieldCheck className="size-3.5" aria-hidden /> PD&amp;I · Lei do Bem (Lei nº 11.196/2005)
          </span>
          <h1 className="font-serif text-3xl leading-tight font-semibold xl:text-4xl 2xl:text-5xl">
            O trabalho de pesquisa.
            <br />
            <span className="bg-gradient-to-r from-indigo-200 via-cyan-200 to-emerald-200 bg-clip-text text-transparent">
              As evidências no mesmo lugar.
            </span>
          </h1>
          <p className="mx-auto max-w-md text-[15px] leading-relaxed text-blue-100/75">
            O Basho organiza a documentação de PD&amp;I da sua empresa para a análise da Lei do Bem: lê as fontes, prepara os relatórios e verifica cada afirmação com evidência. Pessoas revisam e decidem.
          </p>
        </div>
        <FlowDiagram />
        <LedgerTicker />
      </div>

      <p className="relative mx-auto shrink-0 max-w-xl text-center text-xs leading-relaxed text-blue-100/50">
        Apoio à preparação da documentação de incentivos à inovação. O Basho não garante o benefício, não decide o enquadramento e não envia o FORMP&amp;D. Ambiente de demonstração com dados fictícios.
      </p>
    </section>
  );
}
