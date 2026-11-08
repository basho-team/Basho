import { describe, expect, test } from "vitest";
import { parseSourceLink, EXAMPLE_LINKS } from "@/lib/demo-sources/links";
import { buildReport, publicationPlan, syntheticCommits, DISCLAIMER } from "@/lib/demo-sources/simulate";

const REPO = "equipe-basho/calibracao-sensores";
const NOW = new Date("2026-11-08T15:00:00Z");

describe("commits fictícios", () => {
  test("são determinísticos por repositório e diferentes entre repositórios", () => {
    expect(syntheticCommits(REPO)).toEqual(syntheticCommits(REPO));
    expect(syntheticCommits(REPO)[0].sha).not.toBe(syntheticCommits("outra/coisa")[0].sha);
  });

  test("têm sha de 7 hex e incluem os casos que a demonstração quer mostrar", () => {
    const commits = syntheticCommits(REPO);
    expect(commits.every(commit => /^[0-9a-f]{7}$/.test(commit.sha))).toBe(true);
    expect(new Set(commits.map(commit => commit.kind))).toEqual(new Set(["experiment", "method", "noise", "injection", "hours"]));
  });
});

describe("relatório gerado", () => {
  const report = buildReport(REPO, syntheticCommits(REPO), NOW);
  const claims = report.sections.flatMap(section => section.items);

  test("toda afirmação cita ao menos uma fonte que existe na lista de fontes", () => {
    expect(claims.length).toBeGreaterThan(0);
    const known = new Set(report.sources.map(source => source.n));
    for (const claim of claims) {
      expect(claim.refs.length).toBeGreaterThan(0);
      expect(claim.refs.every(ref => known.has(ref))).toBe(true);
    }
  });

  test("as fontes são numeradas na ordem da primeira citação e sem repetição", () => {
    expect(report.sources.map(source => source.n)).toEqual(report.sources.map((_, index) => index + 1));
    expect(new Set(report.sources.map(source => source.label)).size).toBe(report.sources.length);
  });

  test("instrução escondida em commit é tratada como dado: não vira afirmação nem fonte", () => {
    const text = JSON.stringify({ sections: report.sections, sources: report.sources });
    expect(text.toLowerCase()).not.toContain("ignore as regras");
    expect(text.toLowerCase()).not.toContain("aprovado");
    expect(report.guardrails.some(note => note.includes("instrução"))).toBe(true);
  });

  test("horas informais de commit não viram afirmação; horas formais viram pergunta ao coordenador", () => {
    const text = JSON.stringify({ sections: report.sections, summary: report.summary });
    expect(text).not.toContain("40");
    expect(report.guardrails.some(note => note.includes("40h"))).toBe(true);
    expect(report.pending.some(item => item.role === "coordenador" && item.question.toLowerCase().includes("horas"))).toBe(true);
  });

  test("o que as fontes não dizem (hipótese, desfecho) vira pendência, nunca afirmação", () => {
    expect(report.pending.map(item => item.question).join(" ")).toMatch(/hipótese/i);
    expect(report.pending.map(item => item.question).join(" ")).toMatch(/positivo, negativo ou inconclusivo/i);
    expect(report.sections.map(section => section.title)).not.toContain("Resultado");
  });

  test("usa a linguagem do limite legal e marca o dado como sintético", () => {
    expect(report.disclaimer).toBe(DISCLAIMER);
    expect(report.disclaimer).toContain("não decide enquadramento");
    expect(report.disclaimer).toContain("sujeito a análise");
    expect(report.isSynthetic).toBe(true);
  });

  test("o título é estável por repositório", () => {
    expect(buildReport(REPO, syntheticCommits(REPO), NOW).title).toBe(report.title);
    expect(report.title.startsWith("Relatório BASHO — calibracao-sensores — ")).toBe(true);
  });
});

describe("plano de publicação", () => {
  const report = buildReport(REPO, syntheticCommits(REPO), NOW);
  const drive = parseSourceLink("drive", EXAMPLE_LINKS.drive);
  const notion = parseSourceLink("notion", EXAMPLE_LINKS.notion);

  test("publica em <destino>/BASHO/<relatório> só nos destinos conectados", () => {
    const both = publicationPlan(report, drive, notion);
    expect(both.map(item => item.destination)).toEqual(["drive", "notion"]);
    for (const item of both) {
      expect(item.path[1]).toBe("BASHO");
      expect(item.path[2]).toBe(report.title);
    }
    expect(publicationPlan(report, drive, undefined).map(item => item.destination)).toEqual(["drive"]);
    expect(publicationPlan(report, undefined, undefined)).toEqual([]);
  });
});
