/* eslint-disable @typescript-eslint/no-require-imports */
require("./register.cjs");
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { createInitialState } = require("../src/data/seedData.ts");
const {
  defaultConfig,
  saveIntegration,
  setPolicy,
} = require("../src/services/settingsService.ts");
const {
  executeCommand,
  makeDocument,
  completeness,
  reconcile,
} = require("../src/services/simulationService.ts");
const {
  startScenario,
  advanceRun,
  resolveApproval,
  receiveGithubEvent,
  retryRun,
} = require("../src/services/workflowEngine.ts");
const {
  decodeState,
  encodeState,
} = require("../src/services/persistenceService.ts");
const { createDemoStore } = require("../src/store/demoStore.ts");
function connected() {
  let state = createInitialState();
  for (const integration of state.integrations)
    state = saveIntegration(state, integration.id, {
      status: "connected",
      config: defaultConfig(integration.provider),
    });
  return state;
}
function drain(state) {
  for (let i = 0; i < 80; i++) {
    const runs = state.agentRuns.filter((r) => r.status === "running");
    if (!runs.length) return state;
    state = runs.reduce((s, r) => advanceRun(s, r.id), state);
  }
  throw new Error("Workflow did not settle");
}
function policy(state, provider, operation, level, projectId, resourceId) {
  return setPolicy(
    state,
    state.permissionPolicies.find(
      (p) => p.provider === provider && p.operation === operation,
    ),
    level,
    projectId,
    resourceId,
  );
}
function decide(state, decision, note = "Decisão sintética de teste") {
  return resolveApproval(
    state,
    state.approvalRequests.find((a) => a.status === "pending").id,
    decision,
    note,
  );
}
function reportCount(state) {
  return state.driveItems.filter((d) => d.category === "report").length;
}

test("A updates Notion, records evidence and creates a linked Drive report", () => {
  const before = connected();
  const state = drain(startScenario(before, "A"));
  const run = state.agentRuns[0];
  assert.equal(run.status, "completed");
  assert.equal(reportCount(state), reportCount(before) + 1);
  const evidence = state.evidence[0];
  assert.ok(
    state.activities
      .find((a) => a.id === evidence.relatedActivityId)
      .evidenceIds.includes(evidence.id),
  );
  const project = state.projects.find((p) => p.id === run.projectId);
  assert.ok(project.evidenceIds.includes(evidence.id));
  assert.ok(
    project.reportIds.some((id) => !before.projects[0].reportIds.includes(id)),
  );
  assert.ok(
    state.auditLogs.some(
      (log) =>
        log.executionId === run.id && log.operation === "workflow.completed",
    ),
  );
  assert.equal(advanceRun(state, run.id), state);
});
test("A respects a blocked document policy and retry resumes without duplicate evidence", () => {
  const before = policy(
    connected(),
    "google_drive",
    "create_documents",
    "blocked",
  );
  let state = drain(startScenario(before, "A"));
  assert.equal(state.agentRuns[0].status, "blocked_by_policy");
  assert.equal(reportCount(state), reportCount(before));
  const count = state.evidence.length;
  state = policy(state, "google_drive", "create_documents", "automatic");
  state = drain(retryRun(state, state.agentRuns[0].id));
  assert.equal(state.agentRuns[0].status, "completed");
  assert.equal(state.evidence.length, count);
  assert.equal(reportCount(state), reportCount(before) + 1);
});
test("a document requiring approval remains absent until the exact action is approved", () => {
  const before = policy(
    connected(),
    "google_drive",
    "create_documents",
    "requires_approval",
  );
  let state = drain(startScenario(before, "A"));
  assert.equal(state.agentRuns[0].status, "awaiting_approval");
  assert.equal(reportCount(state), reportCount(before));
  state = drain(decide(decodeState(encodeState(state)), "approved"));
  assert.equal(state.agentRuns[0].status, "completed");
  assert.equal(reportCount(state), reportCount(before) + 1);
});
test("approval cannot bypass a newly blocked policy", () => {
  let state = drain(
    startScenario(
      policy(
        connected(),
        "google_drive",
        "create_documents",
        "requires_approval",
      ),
      "A",
    ),
  );
  const count = reportCount(state);
  state = policy(state, "google_drive", "create_documents", "blocked");
  state = drain(decide(state, "approved"));
  assert.equal(state.agentRuns[0].status, "blocked_by_policy");
  assert.equal(reportCount(state), count);
});
test("a Notion status grant does not bypass the separate evidence policy", () => {
  let state = policy(connected(), "notion", "add_evidence", "blocked");
  state = drain(startScenario(state, "A"));
  assert.equal(state.agentRuns[0].status, "blocked_by_policy");
  assert.equal(state.activities[0].evidenceIds.length, 0);
});
test("B preserves an original byte-for-byte and records a derived work copy", () => {
  const state = drain(startScenario(connected(), "B"));
  const original = state.driveItems.find((d) =>
    d.name.startsWith("Comprovante original"),
  );
  const copy = state.driveItems.find((d) => d.derivedFromId === original.id);
  assert.equal(state.agentRuns[0].status, "completed");
  assert.ok(original.isOriginal && original.isProtected);
  assert.equal(original.parentId, "drive-folder-pd001");
  assert.equal(copy.content, original.content);
  assert.equal(copy.parentId, "drive-folder-pd001-agent-work");
  assert.equal(copy.isOriginal, false);
});
test("B does not create a work copy when copying is blocked", () => {
  const state = drain(
    startScenario(
      policy(connected(), "google_drive", "copy_documents", "blocked"),
      "B",
    ),
  );
  assert.equal(state.agentRuns[0].status, "blocked_by_policy");
  assert.equal(state.driveItems.filter((d) => d.derivedFromId).length, 0);
});
test("B can move a derived document when the policy allows", () => {
  const state = drain(startScenario(connected(), "B", "pd-001", false));
  assert.equal(state.agentRuns[0].status, "completed");
  assert.equal(
    state.driveItems.find((d) => d.name.startsWith("Experimento derivado"))
      .parentId,
    "drive-folder-pd001-agent-work",
  );
});
test("C persists, requests context and resumes after human approval", () => {
  let state = drain(startScenario(connected(), "C"));
  assert.equal(state.agentRuns[0].status, "awaiting_approval");
  assert.ok(state.approvalRequests[0].context.length >= 3);
  state = drain(decide(decodeState(encodeState(state)), "approved"));
  assert.equal(state.agentRuns[0].status, "completed");
  assert.equal(state.activities[0].status, "review");
  assert.equal(state.activities[0].evidenceIds.length, 0);
});
test("C rejects without applying its prepared mutation", () => {
  const before = connected();
  const state = drain(decide(drain(startScenario(before, "C")), "rejected"));
  assert.equal(state.agentRuns[0].status, "failed");
  assert.deepEqual(state.activities, before.activities);
  assert.equal(state.approvalRequests[0].status, "rejected");
});
test("C adjustments remain suspended, can be resubmitted and then approved", () => {
  let state = drain(startScenario(connected(), "C"));
  const id = state.approvalRequests[0].id;
  state = resolveApproval(
    state,
    id,
    "needs_revision",
    "Anexe o protocolo experimental",
  );
  assert.equal(state.agentRuns[0].status, "awaiting_approval");
  state = resolveApproval(
    state,
    id,
    "pending",
    "Protocolo sintético complementado",
  );
  state = drain(
    resolveApproval(state, id, "approved", "Encaminhar para revisão"),
  );
  assert.equal(state.agentRuns[0].status, "completed");
  assert.ok(
    state.auditLogs.some((l) => l.operation === "approval.needs_revision"),
  );
});
test("originals and folders containing originals cannot be modified", () => {
  for (const id of ["drive-file-invoice-001", "drive-folder-pd001"]) {
    const before = connected();
    const result = executeCommand(before, {
      kind: "drive.update",
      id,
      patch: { name: "Alterado" },
    });
    assert.equal(result.outcome, "blocked");
    assert.deepEqual(result.state.driveItems, before.driveItems);
  }
});
test("folder cycles and cross-project moves are rejected", () => {
  let state = connected();
  const folder = {
    ...makeDocument("Pasta segura", "drive-folder-pd001", "pd-001"),
    type: "folder",
  };
  state = executeCommand(state, { kind: "drive.create", item: folder }).state;
  assert.equal(
    executeCommand(state, {
      kind: "drive.update",
      id: folder.id,
      patch: { parentId: folder.id },
    }).outcome,
    "blocked",
  );
  assert.equal(
    executeCommand(state, {
      kind: "drive.update",
      id: folder.id,
      patch: { parentId: "drive-folder-pd002" },
    }).outcome,
    "blocked",
  );
});
test("workspace writing and Notion editing flags are enforced", () => {
  let state = connected();
  state = saveIntegration(state, "int-drive", {
    config: { ...defaultConfig("google_drive"), writableFolderIds: [] },
  });
  assert.equal(
    executeCommand(state, {
      kind: "drive.create",
      item: makeDocument("Teste", "drive-folder-pd001", "pd-001"),
    }).outcome,
    "blocked",
  );
  state = saveIntegration(state, "int-notion", {
    config: { ...defaultConfig("notion"), allowEditTasks: false },
  });
  assert.equal(
    executeCommand(state, {
      kind: "activity.update",
      id: "act-1",
      patch: { description: "Teste" },
    }).outcome,
    "blocked",
  );
});
test("permissions are scoped by project and exact resource", () => {
  let state = policy(
    connected(),
    "github",
    "read_events",
    "blocked",
    "pd-002",
    "gh-repo-2",
  );
  assert.equal(
    drain(startScenario(state, "A", "pd-001")).agentRuns[0].status,
    "completed",
  );
  assert.equal(
    drain(startScenario(state, "A", "pd-002")).agentRuns[0].status,
    "blocked_by_policy",
  );
});
test("GitHub triggers start the corresponding workflow, disabled triggers do not", () => {
  let state = connected();
  state = receiveGithubEvent(state, "pr_merged", "gh-repo-1");
  assert.equal(state.githubEvents.length, 1);
  assert.equal(state.agentRuns.length, 1);
  assert.equal(drain(state).agentRuns[0].status, "completed");
  state = saveIntegration(connected(), "int-github", {
    config: { ...defaultConfig("github"), eventTriggers: [] },
  });
  state = receiveGithubEvent(state, "pr_merged", "gh-repo-1");
  assert.equal(state.githubEvents.length, 1);
  assert.equal(state.agentRuns.length, 0);
});
test("manual task completion uses the same individual approval gate", () => {
  const before = connected();
  let result = executeCommand(before, {
    kind: "activity.update",
    id: "act-1",
    patch: { status: "done" },
  });
  assert.equal(result.outcome, "pending_approval");
  assert.equal(result.state.activities[0].status, "in_progress");
  const state = decide(result.state, "approved");
  assert.equal(state.activities[0].status, "done");
  assert.equal(
    resolveApproval(state, state.approvalRequests[0].id, "approved", ""),
    state,
  );
});
test("disconnected integrations cannot perform simulated writes", () => {
  const state = drain(startScenario(createInitialState(), "A"));
  assert.equal(state.agentRuns[0].status, "blocked_by_policy");
  assert.equal(state.evidence.length, 0);
});
test("initial state restoration is isolated and derived completeness is explicit", () => {
  const a = createInitialState(),
    b = createInitialState();
  a.projects[0].name = "Changed";
  assert.notEqual(b.projects[0].name, a.projects[0].name);
  assert.equal(completeness(b, "pd-001"), 45);
  assert.equal(completeness(b, "pd-002"), 0);
  assert.equal(reconcile(b).projects[0].completeness, 45);
});
test("persistence rejects malformed payloads and preserves running workflow plans", () => {
  assert.throws(() => decodeState("{}"));
  assert.throws(() => decodeState("bad JSON"));
  const state = startScenario(connected(), "A");
  const restored = decodeState(encodeState(state));
  assert.deepEqual(restored.agentRuns, state.agentRuns);
  assert.equal(drain(restored).agentRuns[0].status, "completed");
});
test("audit is appended with before and after states without mutating input", () => {
  const before = connected(),
    previous = structuredClone(before);
  const result = executeCommand(before, {
    kind: "activity.update",
    id: "act-1",
    patch: { description: "Novo contexto" },
  });
  assert.deepEqual(before, previous);
  assert.equal(result.state.auditLogs.length, before.auditLogs.length + 1);
  assert.notEqual(
    result.state.auditLogs[0].previousState,
    result.state.auditLogs[0].newState,
  );
});
test("corrupt or unavailable local storage is reported and never silently overwritten", () => {
  const old = global.localStorage;
  let writes = 0;
  global.localStorage = {
    getItem: () => "bad",
    setItem: () => {
      writes++;
    },
  };
  const store = createDemoStore(),
    unmount = store.mount();
  assert.ok(store.getSnapshot().storageError);
  store.transact((s) => s);
  assert.equal(writes, 0);
  unmount();
  store.resetData();
  assert.equal(writes, 1);
  assert.equal(store.getSnapshot().storageError, "");
  global.localStorage = old;
});

test("concurrent PRs preserve both evidence links and both activity annotations", () => {
  let state = connected();
  state = receiveGithubEvent(state, "pr_merged", "gh-repo-1");
  state = receiveGithubEvent(state, "pr_merged", "gh-repo-1");
  state = drain(state);
  assert.equal(
    state.agentRuns.filter((r) => r.status === "completed").length,
    2,
  );
  assert.equal(state.evidence.length, 2);
  const activity = state.activities.find((a) => a.id === "act-1");
  assert.equal(activity.evidenceIds.length, 2);
  state.githubEvents.forEach((event) =>
    assert.ok(activity.description.includes(event.id)),
  );
});
test("creating a completed task cannot bypass the completion approval policy", () => {
  const state = connected(),
    activity = { ...state.activities[0], id: "new-task", status: "done" };
  const result = executeCommand(state, { kind: "activity.create", activity });
  assert.equal(result.outcome, "pending_approval");
  assert.equal(result.state.activities.length, state.activities.length);
});
test("moving a document requires writing permission for the source folder", () => {
  let state = connected();
  state = saveIntegration(state, "int-drive", {
    config: {
      ...defaultConfig("google_drive"),
      writableFolderIds: ["drive-folder-pd001-agent-work"],
    },
  });
  const result = executeCommand(state, {
    kind: "drive.update",
    id: "drive-file-pd001-evidence-001",
    patch: { parentId: "drive-folder-pd001-agent-work" },
  });
  assert.equal(result.outcome, "blocked");
});

test("nested malformed state is rejected before it can reach the UI", () => {
  const state = connected();
  state.activities[0].title = 42;
  assert.throws(() => decodeState(encodeState(state)));
  const broken = startScenario(connected(), "A");
  broken.agentRuns[0].steps[0].command = { kind: "unrecognized" };
  assert.throws(() => decodeState(encodeState(broken)));
  const references = connected();
  references.activities[0].projectId = "missing-project";
  assert.throws(() => decodeState(encodeState(references)));
});
