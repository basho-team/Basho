import { describe, expect, test } from "vitest";
import {
  EvidenceVersionSchema,
  ExpenseSchema,
  FindingSchema,
  PersonSchema,
  ProjectSchema,
  ReportingPeriodSchema,
  ReportVersionSchema,
  ReviewSchema,
} from "@/lib/contracts/provisional";
import {
  EVIDENCE,
  EXPENSES,
  FINDINGS,
  PEOPLE,
  PERIOD,
  PROJECT,
  REPORT_VERSIONS,
  REVIEWS,
} from "@/lib/data/mock-fixtures";

describe("fixtures sintéticas × contrato provisório", () => {
  test("todas as fixtures passam nos schemas provisórios", () => {
    // Arrange
    const cases = [
      () => ProjectSchema.parse(PROJECT),
      () => ReportingPeriodSchema.parse(PERIOD),
      () => PersonSchema.array().parse(PEOPLE),
      () => EvidenceVersionSchema.array().parse(EVIDENCE),
      () => ReportVersionSchema.array().parse(REPORT_VERSIONS),
      () => ReviewSchema.array().parse(REVIEWS),
      () => ExpenseSchema.array().parse(EXPENSES),
      () => FindingSchema.array().parse(FINDINGS),
    ];

    // Act / Assert
    cases.forEach((parse) => expect(parse).not.toThrow());
  });

  test("dados de demonstração estão marcados como sintéticos", () => {
    // Arrange
    const flagged = [PROJECT, ...PEOPLE, ...EVIDENCE, ...EXPENSES];

    // Act
    const unflagged = flagged.filter((item) => !item.is_synthetic);

    // Assert
    expect(unflagged).toEqual([]);
  });

  test("toda evidência citada por afirmação ou finding existe", () => {
    // Arrange
    const known = new Set(EVIDENCE.map((e) => e.id));
    const cited = [
      ...REPORT_VERSIONS.flatMap((v) => v.claims.flatMap((c) => c.evidence_ids)),
      ...FINDINGS.flatMap((f) => f.evidence_ids),
    ];

    // Act
    const missing = cited.filter((id) => !known.has(id));

    // Assert
    expect(missing).toEqual([]);
  });

  test("horas sem registro formal ficam pendentes e sem evidência inventada", () => {
    // Arrange
    const hoursClaims = REPORT_VERSIONS.flatMap((v) => v.claims).filter((c) => c.section === "hours");

    // Act
    const pendingWithEvidence = hoursClaims.filter((c) => c.status === "pending" && c.evidence_ids.length > 0);

    // Assert
    expect(hoursClaims.some((c) => c.status === "pending")).toBe(true);
    expect(pendingWithEvidence).toEqual([]);
  });
});
