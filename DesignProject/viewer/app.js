const VIEW_DEFINITIONS = [
  {
    id: "overview",
    label: "项目总览",
    eyebrow: "PROJECT OVERVIEW",
    description: "当前 Story 设计的阶段、核心叙事与资源完成度。",
  },
  {
    id: "story",
    label: "故事核心",
    eyebrow: "STORY CORE",
    description: "故事标题、摘要、主题、边界与固定提示词。",
  },
  {
    id: "openings",
    label: "开局",
    eyebrow: "OPENING SCENES",
    description: "新 Session 可选择的开局消息，最多三条。",
    countPath: ["resources", "openings"],
  },
  {
    id: "characters",
    label: "角色",
    eyebrow: "CHARACTER ARCHIVE",
    description: "角色客观身份卡、分层详情与视觉锚点。",
    countPath: ["resources", "characters"],
  },
  {
    id: "lorebook",
    label: "世界书",
    eyebrow: "LOREBOOK",
    description: "世界设定、地点、组织、规则与关联标签。",
    countPath: ["resources", "lorebook"],
  },
  {
    id: "status-tables",
    label: "状态表",
    eyebrow: "STATUS TABLES",
    description: "Scene 与普通状态表的字段和即时更新语义。",
    countPath: ["resources", "statusTables"],
  },
  {
    id: "plot-schedule",
    label: "剧情调度",
    eyebrow: "PLOT SCHEDULE",
    description: "剧情线与事件池的分层导航，以及可寻址的事件详情。",
    countPath: ["resources", "plotSchedule"],
  },
  {
    id: "rp-modules",
    label: "RP Modules",
    eyebrow: "RP MODULES",
    description: "Story 已选择的 RP 玩法模块及其配置。",
    countPath: ["resources", "rpModules"],
  },
  {
    id: "narrative-styles",
    label: "叙事风格",
    eyebrow: "NARRATIVE STYLES",
    description: "基础与附加叙事风格的 Prompt 配置。",
    countPath: ["resources", "narrativeStyles"],
  },
  {
    id: "quick-replies",
    label: "快捷回复",
    eyebrow: "QUICK REPLIES",
    description: "故事级可复用的玩家输入模板。",
    countPath: ["resources", "quickReplies"],
  },
  {
    id: "visual-catalog",
    label: "视觉目录",
    eyebrow: "VISUAL CATALOG",
    description: "值得独立生图的角色、场景、地点与物件规格。",
    countPath: ["resources", "visualCatalog"],
  },
  {
    id: "decisions",
    label: "决策与问题",
    eyebrow: "DESIGN RECORD",
    description: "已确认设计决策、理由与仍待回答的问题。",
    countPath: ["decisions"],
  },
  {
    id: "sources",
    label: "来源与笔记",
    eyebrow: "SOURCES & NOTES",
    description: "设计参考、定位信息与项目笔记。",
    countPath: ["sources"],
  },
  {
    id: "field-guide",
    label: "字段指南",
    eyebrow: "AUTHORING CONTRACT",
    description: "字段职责、示例、运行时影响与当前 revision 诊断。",
  },
  {
    id: "schemas",
    label: "Schema",
    eyebrow: "SCHEMA REFERENCE",
    description: "Story Design 与 Story Pack 的字段和约束参考。",
  },
  {
    id: "story-packs",
    label: "Story Packs",
    eyebrow: "PACK ARCHIVE",
    description: "已经生成的 Story Pack 产物及其来源 revision。",
  },
];

const PHASE_LABELS = {
  idea: "想法阶段",
  architecture: "架构设计",
  resource_design: "资源设计",
  package_ready: "可构建",
  runtime_synced: "已同步",
};

const PLOT_DETAIL_KINDS = new Set(["outline", "pool", "event"]);

const REVISION_CHANGE_COLLECTIONS = [
  {
    key: "openings",
    viewId: "openings",
    getValues: (document) => document.resources?.openings,
    getIdentity: (item, index) => item.stableId || item.title || index,
  },
  {
    key: "characters",
    viewId: "characters",
    getValues: (document) => document.resources?.characters,
    getIdentity: (item, index) => item.stableId || item.name || index,
  },
  {
    key: "lorebook",
    viewId: "lorebook",
    getValues: (document) => document.resources?.lorebook,
    getIdentity: (item, index) => item.stableId || item.name || index,
  },
  {
    key: "statusTables",
    viewId: "status-tables",
    getValues: (document) => document.resources?.statusTables,
    getIdentity: (item, index) => item.stableId || item.name || index,
  },
  {
    key: "plotOutlines",
    viewId: "plot-schedule",
    getValues: (document) => document.resources?.plotSchedule?.outlines,
    getIdentity: (item, index) => item.stableId || item.name || index,
  },
  {
    key: "plotPools",
    viewId: "plot-schedule",
    getValues: (document) => document.resources?.plotSchedule?.pools,
    getIdentity: (item, index) => item.stableId || item.name || index,
  },
  {
    key: "plotEvents",
    viewId: "plot-schedule",
    getValues: (document) => document.resources?.plotSchedule?.events,
    getIdentity: (item, index) => item.stableId || item.title || index,
  },
  {
    key: "plotNodes",
    viewId: "plot-schedule",
    getValues: (document) => safeArray(
      document.resources?.plotSchedule?.outlines,
    ).flatMap((outline) => safeArray(outline.nodes)),
    getIdentity: (item, index) => item.stableId || item.eventRef || index,
  },
  {
    key: "rpModules",
    viewId: "rp-modules",
    getValues: (document) => document.resources?.rpModules,
    getIdentity: (item, index) => item.moduleName || index,
  },
  {
    key: "narrativeStyles",
    viewId: "narrative-styles",
    getValues: (document) => document.resources?.narrativeStyles,
    getIdentity: (item, index) => item.stableId || item.name || index,
  },
  {
    key: "quickReplies",
    viewId: "quick-replies",
    getValues: (document) => document.resources?.quickReplies,
    getIdentity: (item, index) => item.stableId || item.title || index,
  },
  {
    key: "visualCatalog",
    viewId: "visual-catalog",
    getValues: (document) => document.resources?.visualCatalog,
    getIdentity: (item, index) => item.stableId || item.title || index,
  },
  {
    key: "decisions",
    viewId: "decisions",
    getValues: (document) => document.decisions,
    getIdentity: (item, index) => item.id || index,
  },
  {
    key: "openQuestions",
    viewId: "decisions",
    getValues: (document) => document.openQuestions,
    getIdentity: (item, index) => item.id || index,
  },
  {
    key: "sources",
    viewId: "sources",
    getValues: (document) => document.sources,
    getIdentity: (item, index) => item.id || item.title || index,
  },
];

const state = {
  manifest: null,
  history: { revisions: [], checkpoints: [] },
  packs: [],
  schemas: {},
  authoringRules: null,
  authoringAssetsDigest: null,
  packSignature: null,
  diagnostics: { diagnostics: [], errors: [], warnings: [] },
  diagnosticProfile: "draft",
  selectedRevisionId: null,
  selectedRevision: null,
  headRevisionId: null,
  pendingHeadId: null,
  activeView: "overview",
  plotSelection: null,
  schemaKind: "story-design",
  selectedPack: null,
  rawValue: null,
  rawPath: "/",
  eventSource: null,
  pollTimer: null,
  toastTimer: null,
  selectionToken: 0,
  diagnosticRequestToken: 0,
  packRequestToken: 0,
  authoringRulesRequestToken: 0,
  schemaRequestToken: 0,
  revisionChanges: createEmptyRevisionChanges(),
};

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
  collectElements();
  bindStaticEvents();
  initialize().catch((error) => {
    setLiveStatus("offline", "读取失败");
    renderFatalError(error);
  });
});

function collectElements() {
  [
    "projectTitle",
    "projectPhase",
    "selectedRevision",
    "liveIndicator",
    "liveLabel",
    "refreshButton",
    "sectionToggle",
    "historyToggle",
    "sectionSidebar",
    "historyRail",
    "mainContent",
    "panelBackdrop",
    "sectionNavigation",
    "viewEyebrow",
    "viewTitle",
    "viewDescription",
    "compareButton",
    "rawButton",
    "updateBanner",
    "updateBannerText",
    "followLatestButton",
    "contentStage",
    "historyCount",
    "historyList",
    "headDigest",
    "rawDialog",
    "rawDialogTitle",
    "rawDialogPath",
    "rawJsonContent",
    "copyRawButton",
    "compareDialog",
    "compareFrom",
    "compareTo",
    "runCompareButton",
    "compareResult",
    "toast",
    "toastTitle",
    "toastMessage",
  ].forEach((id) => {
    elements[id] = document.getElementById(id);
  });
}

function bindStaticEvents() {
  elements.refreshButton.addEventListener("click", () => {
    refreshProject({ manual: true }).catch(showErrorToast);
  });
  elements.followLatestButton.addEventListener("click", () => {
    followLatest().catch(showErrorToast);
  });
  elements.rawButton.addEventListener("click", openRawDialog);
  elements.compareButton.addEventListener("click", openCompareDialog);
  elements.runCompareButton.addEventListener("click", () => {
    runComparison().catch(showErrorToast);
  });
  elements.copyRawButton.addEventListener("click", copyRawJson);
  elements.sectionToggle.addEventListener("click", () => togglePanel("sections"));
  elements.historyToggle.addEventListener("click", () => togglePanel("history"));
  elements.panelBackdrop.addEventListener("click", closePanels);

  document.querySelectorAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => {
      document.getElementById(button.dataset.closeDialog)?.close();
    });
  });
  [elements.rawDialog, elements.compareDialog].forEach((dialog) => {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) {
        dialog.close();
      }
    });
  });

  elements.sectionNavigation.addEventListener("click", (event) => {
    const button = event.target.closest("[data-view]");
    if (!button) {
      return;
    }
    setActiveView(button.dataset.view);
    closePanels();
  });

  elements.historyList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-revision]");
    if (!button) {
      return;
    }
    selectRevision(button.dataset.revision).catch(showErrorToast);
    closePanels();
  });

  elements.contentStage.addEventListener("click", (event) => {
    const profileButton = event.target.closest("[data-diagnostic-profile]");
    if (profileButton) {
      state.diagnosticProfile = profileButton.dataset.diagnosticProfile;
      loadDiagnostics(state.selectedRevisionId).catch(showErrorToast);
      return;
    }
    const schemaButton = event.target.closest("[data-schema-kind]");
    if (schemaButton) {
      state.schemaKind = schemaButton.dataset.schemaKind;
      renderActiveView();
      return;
    }
    const packButton = event.target.closest("[data-pack-file]");
    if (packButton) {
      loadStoryPack(packButton.dataset.packFile).catch(showErrorToast);
      return;
    }
    const actionButton = event.target.closest("[data-viewer-action]");
    if (actionButton?.dataset.viewerAction === "back-to-packs") {
      state.packRequestToken += 1;
      state.selectedPack = null;
      renderActiveView();
    }
  });

  elements.contentStage.addEventListener("input", (event) => {
    if (event.target.id === "schemaSearch") {
      filterSchemaCards(event.target.value);
    }
    if (event.target.id === "fieldGuideSearch") {
      filterFieldGuideCards(event.target.value);
    }
  });

  window.addEventListener("hashchange", () => {
    const route = parseViewerRoute(window.location.hash);
    if (route.recognized) {
      applyViewerRoute(route);
    }
  });

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closePanels();
    }
  });
}

async function initialize() {
  renderNavigation();
  const route = parseViewerRoute(window.location.hash);
  state.activeView = route.viewId;
  state.plotSelection = route.plotSelection;
  await refreshProject({ initial: true });
  connectRevisionStream();
}

async function api(path) {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `请求失败：HTTP ${response.status}`;
    try {
      const error = await response.json();
      message = error.message || message;
    } catch {
      // Preserve the HTTP fallback message.
    }
    throw new Error(message);
  }
  return response.json();
}

async function refreshProject({ initial = false, manual = false } = {}) {
  const previousHead = state.headRevisionId;
  const previousAuthoringAssetsDigest = state.authoringAssetsDigest;
  const [
    projectResult,
    historyResult,
    packsResult,
    authoringRules,
  ] = await Promise.all([
    api("/api/project"),
    api("/api/revisions"),
    api("/api/story-packs"),
    api("/api/authoring-rules"),
  ]);

  state.manifest = projectResult.project;
  state.history = historyResult;
  state.packs = packsResult.packs || [];
  state.authoringRules = authoringRules;
  state.headRevisionId = projectResult.live.currentRevision;
  state.authoringAssetsDigest =
    projectResult.live.authoringAssetsDigest || null;
  if (
    Object.keys(state.schemas).length
    && previousAuthoringAssetsDigest !== state.authoringAssetsDigest
  ) {
    invalidateSchemaCache();
  }
  state.packSignature =
    packsResult.signature || projectResult.live.packSignature || null;

  const wasFollowingHead =
    state.selectedRevisionId === null ||
    state.selectedRevisionId === previousHead;

  updateProjectChrome();
  renderNavigation();
  renderHistory();

  if (initial || wasFollowingHead) {
    await selectRevision(state.headRevisionId, {
      quiet: true,
      followHead: true,
    });
  } else if (state.selectedRevisionId !== state.headRevisionId) {
    state.pendingHeadId = state.headRevisionId;
    showUpdateBanner();
    renderActiveView();
  }

  if (manual) {
    showToast(
      "项目已刷新",
      state.pendingHeadId
        ? `最新版为 ${state.pendingHeadId}，当前历史阅读位置已保留。`
        : `当前已是 ${state.headRevisionId}。`,
    );
  }
}

async function selectRevision(
  revisionId,
  { quiet = false, followHead = false } = {},
) {
  if (!revisionId) {
    throw new Error("没有可读取的 revision。");
  }
  const selectionToken = ++state.selectionToken;
  const diagnosticProfile = state.diagnosticProfile;
  const diagnosticRequestToken = ++state.diagnosticRequestToken;
  state.revisionChanges = createEmptyRevisionChanges();
  setContentLoading();
  const revision = await api(`/api/revisions/${encodeURIComponent(revisionId)}`);
  const [revisionChanges, diagnostics] = await Promise.all([
    loadRevisionChanges(revision),
    fetchDiagnostics(revision.revisionId, diagnosticProfile),
  ]);
  if (selectionToken !== state.selectionToken) {
    return;
  }
  state.selectedRevision = revision;
  state.selectedRevisionId = revision.revisionId;
  state.revisionChanges = revisionChanges;
  const diagnosticsAreCurrent =
    diagnosticRequestToken === state.diagnosticRequestToken
    && diagnosticProfile === state.diagnosticProfile;
  state.diagnostics = diagnosticsAreCurrent
    ? diagnostics
    : { diagnostics: [], errors: [], warnings: [] };
  if (followHead || revision.revisionId === state.headRevisionId) {
    state.pendingHeadId = null;
  } else if (state.headRevisionId !== revision.revisionId) {
    state.pendingHeadId = state.headRevisionId;
  }
  updateProjectChrome();
  renderNavigation();
  renderHistory();
  showUpdateBanner();
  renderActiveView();
  if (!diagnosticsAreCurrent) {
    loadDiagnostics(revision.revisionId).catch(showErrorToast);
  }
  if (!quiet) {
    showToast(
      revision.revisionId === state.headRevisionId ? "已回到最新版" : "正在查看历史版本",
      `${revision.revisionId} · ${revision.reason || "未记录修订原因"}`,
    );
  }
}

async function fetchDiagnostics(
  revisionId,
  profile = state.diagnosticProfile,
) {
  const query = new URLSearchParams({
    revision: revisionId,
    profile,
  });
  return api(`/api/diagnostics?${query.toString()}`);
}

async function loadDiagnostics(revisionId) {
  if (!revisionId) {
    return;
  }
  const profile = state.diagnosticProfile;
  const requestToken = ++state.diagnosticRequestToken;
  const diagnostics = await fetchDiagnostics(revisionId, profile);
  if (
    requestToken !== state.diagnosticRequestToken
    || state.selectedRevisionId !== revisionId
    || state.diagnosticProfile !== profile
  ) {
    return;
  }
  state.diagnostics = diagnostics;
  renderNavigation();
  if (state.activeView === "field-guide") {
    renderActiveView();
  }
}

async function followLatest() {
  await refreshProject();
  await selectRevision(state.headRevisionId, {
    quiet: true,
    followHead: true,
  });
  showToast("已跟随最新版本", `${state.headRevisionId} 已载入。`);
}

function connectRevisionStream() {
  state.eventSource?.close();
  setLiveStatus("connecting", "连接中");
  const source = new EventSource("/events");
  state.eventSource = source;

  source.addEventListener("open", () => {
    setLiveStatus("live", "实时");
    stopFallbackPolling();
  });
  source.addEventListener("snapshot", (event) => {
    handleStreamSnapshot(event).catch(showErrorToast);
  });
  source.addEventListener("revision", (event) => {
    handleRevisionEvent(event).catch(showErrorToast);
  });
  source.addEventListener("packs", (event) => {
    handlePacksEvent(event).catch(showErrorToast);
  });
  source.addEventListener("authoring-rules", (event) => {
    handleAuthoringRulesEvent(event).catch(showErrorToast);
  });
  source.addEventListener("error", () => {
    setLiveStatus("offline", "重连中");
    startFallbackPolling();
  });
}

async function handleStreamSnapshot(event) {
  const snapshot = parseEventData(event);
  if (
    state.headRevisionId &&
    snapshot.currentRevision !== state.headRevisionId
  ) {
    await handleIncomingRevision(snapshot.currentRevision);
  }
  if (
    snapshot.authoringAssetsDigest
    && snapshot.authoringAssetsDigest !== state.authoringAssetsDigest
  ) {
    await refreshAuthoringRules(snapshot);
  }
  if (
    snapshot.packSignature
    && snapshot.packSignature !== state.packSignature
  ) {
    await refreshPacks();
  }
}

async function handleRevisionEvent(event) {
  const snapshot = parseEventData(event);
  await handleIncomingRevision(snapshot.currentRevision);
}

async function handlePacksEvent(event) {
  const snapshot = parseEventData(event);
  if (snapshot.packSignature !== state.packSignature) {
    await refreshPacks();
  }
}

async function handleAuthoringRulesEvent(event) {
  const snapshot = parseEventData(event);
  if (
    snapshot.authoringAssetsDigest !== state.authoringAssetsDigest
  ) {
    await refreshAuthoringRules(snapshot);
  }
}

function parseEventData(event) {
  try {
    return JSON.parse(event.data);
  } catch {
    throw new Error("实时项目通知格式无效。");
  }
}

async function handleIncomingRevision(revisionId) {
  if (!revisionId || revisionId === state.headRevisionId) {
    return;
  }
  const previousHead = state.headRevisionId;
  const wasFollowingHead = state.selectedRevisionId === previousHead;
  await refreshProject();
  if (wasFollowingHead) {
    showToast("Story 已更新", `${revisionId} 已自动载入。`);
  } else {
    state.pendingHeadId = revisionId;
    showUpdateBanner();
    showToast(
      "发现新的 revision",
      `${revisionId} 已就绪；当前历史阅读位置保持不变。`,
    );
  }
}

async function refreshPacks() {
  state.packRequestToken += 1;
  const result = await api("/api/story-packs");
  state.packs = result.packs || [];
  state.packSignature = result.signature || null;
  renderNavigation();
  if (state.activeView === "story-packs") {
    state.selectedPack = null;
    renderActiveView();
  }
  showToast("Story Pack 已更新", "产物列表已经刷新。");
}

async function refreshAuthoringRules(snapshot = {}) {
  const requestToken = ++state.authoringRulesRequestToken;
  const rules = await api("/api/authoring-rules");
  if (requestToken !== state.authoringRulesRequestToken) {
    return;
  }
  state.authoringRules = rules;
  state.authoringAssetsDigest =
    snapshot.authoringAssetsDigest || state.authoringAssetsDigest;
  invalidateSchemaCache();
  if (state.selectedRevisionId) {
    await loadDiagnostics(state.selectedRevisionId);
  } else {
    renderNavigation();
    if (state.activeView === "field-guide") {
      renderActiveView();
    }
  }
  if (state.activeView === "schemas") {
    renderActiveView();
  }
  showToast("字段指南已更新", "最新约束与诊断规则已经载入。");
}

function startFallbackPolling() {
  if (state.pollTimer) {
    return;
  }
  state.pollTimer = window.setInterval(async () => {
    try {
      const project = await api("/api/project");
      const live = project.live || {};
      const incoming = live.currentRevision;
      if (incoming && incoming !== state.headRevisionId) {
        await handleIncomingRevision(incoming);
      }
      if (
        live.authoringAssetsDigest
        && live.authoringAssetsDigest !== state.authoringAssetsDigest
      ) {
        await refreshAuthoringRules(live);
      }
      if (
        live.packSignature
        && live.packSignature !== state.packSignature
      ) {
        await refreshPacks();
      }
    } catch {
      setLiveStatus("offline", "离线");
    }
  }, 3000);
}

function stopFallbackPolling() {
  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function updateProjectChrome() {
  const document = state.selectedRevision?.document;
  const project = document?.project || {};
  const story = document?.story || {};
  const title =
    story.title?.trim() ||
    project.name?.trim() ||
    state.manifest?.name ||
    "未命名故事设计";
  elements.projectTitle.textContent = title;
  documentTitle(title);
  elements.projectPhase.textContent =
    PHASE_LABELS[project.phase] || project.phase || "未设置阶段";
  elements.selectedRevision.textContent = state.selectedRevisionId || "—";
  elements.headDigest.textContent = state.manifest?.headDigest || "—";
}

function documentTitle(title) {
  document.title = `${title} · Story Design Viewer`;
}

function setLiveStatus(mode, label) {
  elements.liveIndicator.classList.toggle("is-live", mode === "live");
  elements.liveIndicator.classList.toggle("is-offline", mode === "offline");
  elements.liveLabel.textContent = label;
}

function renderNavigation() {
  const document = state.selectedRevision?.document || {};
  elements.sectionNavigation.innerHTML = VIEW_DEFINITIONS.map((item, index) => {
    const count = getViewCount(item, document);
    const hasRevisionChange = hasViewRevisionChange(item.id);
    return `
      <button
        class="nav-button ${item.id === state.activeView ? "is-active" : ""} ${hasRevisionChange ? "is-changed" : ""}"
        type="button"
        data-view="${escapeHtml(item.id)}"
        aria-current="${item.id === state.activeView ? "page" : "false"}"
      >
        <span class="nav-index">${String(index + 1).padStart(2, "0")}</span>
        <span class="nav-label">${escapeHtml(item.label)}</span>
        <span class="nav-tail">
          ${hasRevisionChange ? '<span class="nav-change-marker" aria-label="与上一版本相比有变化">更新</span>' : ""}
          ${count === null ? "" : `<span class="section-count">${count}</span>`}
        </span>
      </button>
    `;
  }).join("");
}

function getViewCount(definition, document) {
  if (definition.id === "story-packs") {
    return state.packs.length;
  }
  if (definition.id === "schemas") {
    return 2;
  }
  if (definition.id === "field-guide") {
    return safeArray(state.diagnostics?.diagnostics).length;
  }
  if (!definition.countPath) {
    return null;
  }
  const value = getAtPath(document, definition.countPath);
  if (definition.id === "plot-schedule") {
    return ["outlines", "pools"].reduce(
      (total, key) => total + safeArray(value?.[key]).length,
      0,
    );
  }
  return Array.isArray(value) ? value.length : 0;
}

function renderHistory() {
  const revisions = state.history.revisions || [];
  const checkpoints = state.history.checkpoints || [];
  const checkpointByRevision = new Map();
  checkpoints.forEach((checkpoint) => {
    const existing = checkpointByRevision.get(checkpoint.revision) || [];
    existing.push(checkpoint.name);
    checkpointByRevision.set(checkpoint.revision, existing);
  });
  elements.historyCount.textContent = String(revisions.length);
  elements.historyList.innerHTML = revisions.map((revision) => {
    const isHead = revision.revisionId === state.headRevisionId;
    const isSelected = revision.revisionId === state.selectedRevisionId;
    const names = checkpointByRevision.get(revision.revisionId) || [];
    return `
      <button
        class="revision-item ${isHead ? "is-head" : ""} ${isSelected ? "is-selected" : ""}"
        type="button"
        data-revision="${escapeHtml(revision.revisionId)}"
        aria-current="${isSelected ? "true" : "false"}"
      >
        <span class="revision-line">
          <strong>${escapeHtml(revision.revisionId)}</strong>
          ${isHead ? '<span class="head-label">HEAD</span>' : ""}
        </span>
        <span class="revision-reason">${escapeHtml(revision.reason || "未记录修订原因")}</span>
        <span class="revision-date">${escapeHtml(formatDate(revision.createdAt))}</span>
        ${names.map((name) => `<span class="checkpoint-label">${escapeHtml(name)}</span>`).join("")}
      </button>
    `;
  }).join("");
}

function parseViewerRoute(hashValue) {
  const requested = String(hashValue || "").replace(/^#/, "");
  const segments = requested.split("/");
  const requestedView = segments[0];
  const hasKnownView = VIEW_DEFINITIONS.some(
    (item) => item.id === requestedView,
  );
  const viewId = hasKnownView
    ? requestedView
    : "overview";
  let plotSelection = null;
  if (viewId === "plot-schedule" && segments.length > 1) {
    if (
      segments.length === 3
      && PLOT_DETAIL_KINDS.has(segments[1])
    ) {
      try {
        const stableId = decodeURIComponent(segments[2]);
        if (stableId) {
          plotSelection = {
            kind: segments[1],
            stableId,
          };
        } else {
          plotSelection = {
            kind: "invalid",
            stableId: requested,
          };
        }
      } catch {
        plotSelection = {
          kind: "invalid",
          stableId: requested,
        };
      }
    } else {
      plotSelection = {
        kind: "invalid",
        stableId: requested,
      };
    }
  }
  return {
    viewId,
    plotSelection,
    recognized: requested === "" || hasKnownView,
  };
}

function plotDetailHref(kind, stableId) {
  return `#plot-schedule/${kind}/${encodeURIComponent(stableId)}`;
}

function applyViewerRoute(
  { viewId, plotSelection = null },
  { scroll = true } = {},
) {
  if (!VIEW_DEFINITIONS.some((item) => item.id === viewId)) {
    return;
  }
  if (viewId !== "story-packs") {
    state.packRequestToken += 1;
  }
  state.activeView = viewId;
  state.plotSelection = viewId === "plot-schedule" ? plotSelection : null;
  state.selectedPack = viewId === "story-packs" ? state.selectedPack : null;
  renderNavigation();
  renderActiveView();
  if (scroll) {
    const scrollOptions = { top: 0, behavior: "smooth" };
    elements.mainContent?.focus?.({ preventScroll: true });
    elements.mainContent?.scrollTo?.(scrollOptions);
    window.scrollTo?.(scrollOptions);
  }
}

function setActiveView(viewId, { updateHash = true } = {}) {
  if (!VIEW_DEFINITIONS.some((item) => item.id === viewId)) {
    return;
  }
  if (updateHash) {
    history.replaceState(null, "", `#${viewId}`);
  }
  applyViewerRoute({ viewId, plotSelection: null });
}

function renderActiveView() {
  if (!state.selectedRevision) {
    setContentLoading();
    return;
  }
  const definition =
    VIEW_DEFINITIONS.find((item) => item.id === state.activeView) ||
    VIEW_DEFINITIONS[0];
  elements.viewEyebrow.textContent = definition.eyebrow;
  elements.viewTitle.textContent = definition.label;
  elements.viewDescription.textContent = definition.description;

  const document = state.selectedRevision.document;
  let result;
  switch (state.activeView) {
    case "overview":
      result = renderOverview(document);
      break;
    case "story":
      result = renderStory(document);
      break;
    case "openings":
      result = renderOpenings(document.resources?.openings);
      break;
    case "characters":
      result = renderCharacters(document.resources?.characters);
      break;
    case "lorebook":
      result = renderLorebook(document.resources?.lorebook);
      break;
    case "status-tables":
      result = renderStatusTables(document.resources?.statusTables);
      break;
    case "plot-schedule":
      result = renderPlotSchedule(document.resources?.plotSchedule);
      break;
    case "rp-modules":
      result = renderRPModules(document.resources?.rpModules);
      break;
    case "narrative-styles":
      result = renderNarrativeStyles(document.resources?.narrativeStyles);
      break;
    case "quick-replies":
      result = renderQuickReplies(document.resources?.quickReplies);
      break;
    case "visual-catalog":
      result = renderVisualCatalog(document.resources?.visualCatalog);
      break;
    case "decisions":
      result = renderDecisions(document.decisions, document.openQuestions);
      break;
    case "sources":
      result = renderSources(document.sources, document.notes);
      break;
    case "field-guide":
      result = renderFieldGuide();
      break;
    case "schemas":
      result = renderSchemas();
      break;
    case "story-packs":
      result = renderStoryPacks();
      break;
    default:
      result = renderOverview(document);
  }
  elements.contentStage.innerHTML = `${renderRevisionChangeSummary(
    definition.id,
  )}${result.html}`;
  state.rawValue = result.raw;
  state.rawPath = result.path;
  elements.rawButton.disabled = result.raw === undefined;
}

function createEmptyRevisionChanges() {
  return {
    revisionId: null,
    previousRevisionId: null,
    hasPrevious: false,
    changedViews: new Set(),
    changedSections: new Set(),
    itemChanges: new Map(),
    removedCounts: new Map(),
  };
}

async function loadRevisionChanges(revision) {
  const changes = createEmptyRevisionChanges();
  changes.revisionId = revision.revisionId || null;
  const previousRevisionId = revision.parentRevision;
  if (!previousRevisionId) {
    return changes;
  }
  try {
    const previous = await api(
      `/api/revisions/${encodeURIComponent(previousRevisionId)}`,
    );
    return compareRevisionDocuments(
      previous.document,
      revision.document,
      previousRevisionId,
      revision.revisionId,
    );
  } catch {
    return changes;
  }
}

function compareRevisionDocuments(
  previousDocument,
  currentDocument,
  previousRevisionId,
  revisionId,
) {
  const changes = createEmptyRevisionChanges();
  changes.revisionId = revisionId || null;
  changes.previousRevisionId = previousRevisionId || null;
  changes.hasPrevious = true;

  if (!sameRevisionValue(previousDocument, currentDocument)) {
    changes.changedViews.add("overview");
  }
  for (const [key, viewId] of [
    ["project", "overview"],
    ["target", "overview"],
    ["story", "story"],
    ["notes", "sources"],
  ]) {
    if (!sameRevisionValue(previousDocument?.[key], currentDocument?.[key])) {
      changes.changedSections.add(key);
      changes.changedViews.add(viewId);
      if (key === "story") {
        changes.changedViews.add("overview");
      }
    }
  }

  REVISION_CHANGE_COLLECTIONS.forEach((definition) => {
    compareRevisionCollection(
      changes,
      definition,
      definition.getValues(previousDocument || {}),
      definition.getValues(currentDocument || {}),
    );
  });
  return changes;
}

function compareRevisionCollection(
  changes,
  definition,
  previousValues,
  currentValues,
) {
  const previous = safeArray(previousValues);
  const current = safeArray(currentValues);
  const previousById = new Map(
    previous.map((item, index) => [
      String(definition.getIdentity(item, index)),
      { item, index },
    ]),
  );
  const currentIds = new Set();
  const itemChanges = new Map();

  current.forEach((item, index) => {
    const identity = String(definition.getIdentity(item, index));
    currentIds.add(identity);
    const previousEntry = previousById.get(identity);
    if (previousEntry === undefined) {
      itemChanges.set(identity, "added");
    } else if (
      previousEntry.index !== index
      || !sameRevisionValue(previousEntry.item, item)
    ) {
      itemChanges.set(identity, "updated");
    }
  });

  const removedCount = previous.filter((item, index) => (
    !currentIds.has(String(definition.getIdentity(item, index)))
  )).length;
  if (
    itemChanges.size === 0
    && removedCount === 0
    && sameRevisionValue(previous, current)
  ) {
    return;
  }

  changes.changedViews.add(definition.viewId);
  changes.changedViews.add("overview");
  changes.changedSections.add(definition.key);
  changes.itemChanges.set(definition.key, itemChanges);
  if (removedCount > 0) {
    changes.removedCounts.set(definition.key, removedCount);
  }
}

function sameRevisionValue(left, right) {
  return canonicalRevisionValue(left) === canonicalRevisionValue(right);
}

function canonicalRevisionValue(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalRevisionValue(item)).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => (
      `${JSON.stringify(key)}:${canonicalRevisionValue(value[key])}`
    )).join(",")}}`;
  }
  return JSON.stringify(value);
}

function hasViewRevisionChange(viewId) {
  return state.revisionChanges.hasPrevious
    && state.revisionChanges.changedViews.has(viewId);
}

function revisionChangeClass(key, identity = null) {
  if (identity === null) {
    return state.revisionChanges.changedSections.has(key)
      ? " is-revision-changed"
      : "";
  }
  return state.revisionChanges.itemChanges.get(key)?.has(String(identity))
    ? " is-revision-changed"
    : "";
}

function revisionChangeClassForSections(...keys) {
  return keys.some((key) => state.revisionChanges.changedSections.has(key))
    ? " is-revision-changed"
    : "";
}

function renderRevisionChangeSummary(viewId) {
  if (!hasViewRevisionChange(viewId)) {
    return "";
  }
  const change = state.revisionChanges;
  const removed = totalRemovedForView(viewId);
  const copy = removed > 0
    ? `本板块含有新增、修改或删除内容；带亮边的卡片是当前仍可查看的新增或修改项，另有 ${removed} 项已移除。`
    : "带亮边的内容块为相对上一 revision 新增或修改的内容。";
  return `
    <aside class="revision-change-banner" aria-label="当前页面的 revision 变化">
      <div>
        <span>REVISION DELTA</span>
        <strong>与 ${escapeHtml(change.previousRevisionId)} 相比，此板块有更新</strong>
        <p>${escapeHtml(copy)}</p>
      </div>
      <span class="revision-delta-id">${escapeHtml(change.previousRevisionId)} → ${escapeHtml(change.revisionId)}</span>
    </aside>
  `;
}

function totalRemovedForView(viewId) {
  return REVISION_CHANGE_COLLECTIONS
    .filter((definition) => definition.viewId === viewId)
    .reduce(
      (total, definition) => (
        total + (state.revisionChanges.removedCounts.get(definition.key) || 0)
      ),
      0,
    );
}

function renderOverview(document) {
  const project = document.project || {};
  const story = document.story || {};
  const resources = document.resources || {};
  const plot = resources.plotSchedule || {};
  const totalResources = [
    "characters",
    "lorebook",
    "narrativeStyles",
    "openings",
    "quickReplies",
    "rpModules",
    "statusTables",
    "visualCatalog",
  ].reduce((total, key) => total + safeArray(resources[key]).length, 0);
  const plotCount = ["events", "outlines", "pools"].reduce(
    (total, key) => total + safeArray(plot[key]).length,
    0,
  );
  const openQuestions = safeArray(document.openQuestions).filter(
    (question) => question.status === "open",
  );
  const recentDecisions = safeArray(document.decisions).slice(-3).reverse();
  const notes = safeArray(document.notes);
  const target = document.target || {};

  return {
    path: "/",
    raw: document,
    html: `
      <div class="section-stack">
        <article class="story-hero${revisionChangeClassForSections("project", "story")}">
          <p class="section-kicker">${escapeHtml(
            PHASE_LABELS[project.phase] || project.phase || "STORY DESIGN",
          )}</p>
          <h3>${escapeHtml(story.title || project.name || "未命名故事设计")}</h3>
          <p class="story-logline">${
            story.logline
              ? escapeHtml(story.logline)
              : "故事的核心句尚未写下。下一次 revision 会在这里留下它的第一行。"
          }</p>
          <div class="hero-meta">
            ${tag(story.timeSetting || "时间背景未设置", "is-accent")}
            ${safeArray(story.themes).map((theme) => tag(theme)).join("")}
            ${tag(state.selectedRevisionId || "—")}
          </div>
        </article>

        <div class="metric-grid">
          ${metricCard(
            "设计资源",
            totalResources + plotCount,
            "当前 revision 中的结构化资源",
            revisionChangeClassForSections(
              "openings",
              "characters",
              "lorebook",
              "statusTables",
              "plotOutlines",
              "plotPools",
              "plotEvents",
              "rpModules",
              "narrativeStyles",
              "quickReplies",
              "visualCatalog",
            ),
          )}
          ${metricCard(
            "角色",
            safeArray(resources.characters).length,
            "Story 直接拥有",
            revisionChangeClass("characters"),
          )}
          ${metricCard(
            "剧情节点",
            plotCount,
            "大纲、事件池与事件",
            revisionChangeClassForSections(
              "plotOutlines",
              "plotPools",
              "plotEvents",
              "plotNodes",
            ),
          )}
          ${metricCard(
            "开放问题",
            openQuestions.length,
            "仍需要确认的设计选择",
            revisionChangeClass("openQuestions"),
          )}
        </div>

        <div class="two-column">
          <article class="content-card${revisionChangeClass("story")}">
            <p class="card-eyebrow">STORY SUMMARY</p>
            <h3>故事摘要</h3>
            <p class="prose-block">${
              story.summary
                ? escapeHtml(story.summary)
                : '<span class="muted">尚未形成故事摘要。</span>'
            }</p>
          </article>
          <article class="content-card${revisionChangeClass("target")}">
            <p class="card-eyebrow">RUNTIME TARGET</p>
            <h3>运行时目标</h3>
            <div class="detail-list">
              ${detailRow("Workspace", target.workspaceName || target.workspaceId || "未设置")}
              ${detailRow("Story ID", target.storyId || "待创建 / 未绑定")}
              ${detailRow("允许创建 Workspace", target.allowCreateWorkspace ? "是" : "否")}
            </div>
          </article>
        </div>

        <div class="two-column">
          <article class="content-card${revisionChangeClass("decisions")}">
            <p class="card-eyebrow">RECENT DECISIONS</p>
            <h3>最近决策</h3>
            ${
              recentDecisions.length
                ? `<ul class="compact-list">${recentDecisions
                    .map(
                      (decision) => `
                        <li class="detail-row">
                          <span class="detail-key">${escapeHtml(decision.topic || decision.id)}</span>
                          <span class="detail-value">${escapeHtml(decision.decision || "")}</span>
                        </li>`,
                    )
                    .join("")}</ul>`
                : emptyInline("还没有确认过设计决策。")
            }
          </article>
          <article class="content-card${revisionChangeClass("notes")}">
            <p class="card-eyebrow">NOTES</p>
            <h3>项目笔记</h3>
            ${
              notes.length
                ? `<ul class="compact-list">${notes
                    .map((note) => `<li class="card-copy">${escapeHtml(note)}</li>`)
                    .join("")}</ul>`
                : emptyInline("暂无项目笔记。")
            }
          </article>
        </div>
      </div>
    `,
  };
}

function renderStory(document) {
  const story = document.story || {};
  const boundaries = safeArray(story.boundaries);
  return {
    path: "/story",
    raw: story,
    html: `
      <div class="section-stack">
        <article class="story-hero${revisionChangeClass("story")}">
          <p class="section-kicker">${escapeHtml(story.stableId || "story")}</p>
          <h3>${escapeHtml(story.title || "未命名故事")}</h3>
          <p class="story-logline">${
            story.logline
              ? escapeHtml(story.logline)
              : "Logline 尚未设置。"
          }</p>
          <div class="hero-meta">
            ${tag(story.timeSetting || "时间背景未设置", "is-accent")}
            ${safeArray(story.themes).map((theme) => tag(theme)).join("")}
          </div>
        </article>
        <div class="two-column">
          ${proseCard(
            "SUMMARY",
            "故事摘要",
            story.summary,
            "尚未形成故事摘要。",
            revisionChangeClass("story"),
          )}
          ${proseCard(
            "BOUNDARIES",
            "叙事边界",
            boundaries.join("\n"),
            "尚未设置叙事边界。",
            revisionChangeClass("story"),
          )}
        </div>
        ${proseCard(
          "FIXED STORY PROMPT",
          "Story Prompt",
          story.storyPrompt,
          "尚未定义固定故事提示词。",
          revisionChangeClass("story"),
        )}
        ${
          hasKeys(story.metadata)
            ? genericCard(
              "METADATA",
              "扩展元数据",
              story.metadata,
              revisionChangeClass("story"),
            )
            : ""
        }
      </div>
    `,
  };
}

function renderOpenings(value) {
  const openings = sortedResources(value);
  if (!openings.length) {
    return emptyResult(
      "/resources/openings",
      openings,
      "还没有开局",
      "新 Session 暂时不会获得 authored Opening。",
    );
  }
  return {
    path: "/resources/openings",
    raw: openings,
    html: `
      <div class="resource-grid">
        ${openings.map((opening, index) => `
          <article class="resource-card${revisionChangeClass(
            "openings",
            opening.stableId || opening.title || index,
          )}">
            <div class="card-heading">
              <div>
                <p class="card-eyebrow">OPENING ${String(index + 1).padStart(2, "0")}</p>
                <h3>${escapeHtml(opening.title || "未命名开局")}</h3>
              </div>
              ${statusPill(index === 0 ? "缺省" : `顺序 ${opening.sortOrder ?? index}`, index === 0 ? "is-accent" : "")}
            </div>
            <p class="prose-block">${escapeHtml(opening.message || "")}</p>
            ${metaGrid([
              ["Stable ID", opening.stableId || "—"],
              ["Sort Order", opening.sortOrder ?? index],
            ])}
          </article>
        `).join("")}
      </div>
    `,
  };
}

function renderCharacters(value) {
  const characters = sortedResources(value);
  if (!characters.length) {
    return emptyResult(
      "/resources/characters",
      characters,
      "角色档案还是空的",
      "确认角色设计后，角色卡会按 Story 维度出现在这里。",
    );
  }
  return {
    path: "/resources/characters",
    raw: characters,
    html: `
      <div class="resource-grid">
        ${characters.map((character, index) => `
          <article class="resource-card${revisionChangeClass(
            "characters",
            character.stableId || character.name || index,
          )}">
            <div class="card-heading">
              <div>
                <p class="card-eyebrow">${escapeHtml(character.stableId || "CHARACTER")}</p>
                <h3>${escapeHtml(character.name || "未命名角色")}</h3>
              </div>
              ${statusPill(`顺序 ${character.sortOrder ?? 0}`)}
            </div>
            ${
              safeArray(character.aliases).length
                ? `<div class="tag-row">${safeArray(character.aliases)
                    .map((alias) => tag(alias))
                    .join("")}</div>`
                : ""
            }
            ${
              character.description
                ? `<h4>角色描述</h4><p class="card-copy">${escapeHtml(character.description)}</p>`
                : ""
            }
            ${renderCharacterDetails(character.details)}
            ${renderVisualSummary(character.visual)}
            ${hasKeys(character.metadata) ? renderDetails(character.metadata) : ""}
          </article>
        `).join("")}
      </div>
    `,
  };
}

function renderCharacterDetails(detailsValue) {
  const details = safeArray(detailsValue);
  if (!details.length) {
    return "";
  }
  return `
    <h4>详情条目</h4>
    <div class="detail-list">
      ${details.map((detail) => {
        const key = detail.title || detail.name || detail.key || detail.stableId || "详情";
        const value = detail.content || detail.value || detail.description || stringifyCompact(detail);
        return detailRow(key, value);
      }).join("")}
    </div>
  `;
}

function renderLorebook(value) {
  const entries = sortedResources(value);
  if (!entries.length) {
    return emptyResult(
      "/resources/lorebook",
      entries,
      "世界书尚未展开",
      "地点、组织、规则和背景事实会作为独立条目展示。",
    );
  }
  return {
    path: "/resources/lorebook",
    raw: entries,
    html: `
      <div class="resource-grid">
        ${entries.map((entry, index) => `
          <article class="resource-card${revisionChangeClass(
            "lorebook",
            entry.stableId || entry.name || index,
          )}">
            <div class="card-heading">
              <div>
                <p class="card-eyebrow">${escapeHtml(entry.stableId || "LORE")}</p>
                <h3>${escapeHtml(entry.name || "未命名世界书条目")}</h3>
              </div>
              ${statusPill(`顺序 ${entry.sortOrder ?? 0}`)}
            </div>
            ${
              safeArray(entry.tags).length
                ? `<div class="tag-row">${safeArray(entry.tags).map((item) => tag(item)).join("")}</div>`
                : ""
            }
            ${
              entry.description
                ? `<p class="card-copy">${escapeHtml(entry.description)}</p>`
                : ""
            }
            ${
              entry.content
                ? `<h4>正文</h4><p class="prose-block">${escapeHtml(entry.content)}</p>`
                : ""
            }
            ${renderVisualSummary(entry.visual)}
            ${hasKeys(entry.metadata) ? renderDetails(entry.metadata) : ""}
          </article>
        `).join("")}
      </div>
    `,
  };
}

function renderStatusTables(value) {
  const tables = sortedResources(value);
  if (!tables.length) {
    return emptyResult(
      "/resources/statusTables",
      tables,
      "还没有状态表",
      "Scene 与角色状态表确认后，会以完整字段表格呈现。",
    );
  }
  return {
    path: "/resources/statusTables",
    raw: tables,
    html: `
      <div class="section-stack">
        ${tables.map((table, index) => `
          <article class="resource-card${revisionChangeClass(
            "statusTables",
            table.stableId || table.name || index,
          )}">
            <div class="card-heading">
              <div>
                <p class="card-eyebrow">${escapeHtml(table.stableId || "STATUS TABLE")}</p>
                <h3>${escapeHtml(table.name || "未命名状态表")}</h3>
              </div>
              ${statusPill(table.statusKind === "scene" ? "Scene" : "Normal", table.statusKind === "scene" ? "is-accent" : "")}
            </div>
            ${
              table.description
                ? `<p class="card-copy">${escapeHtml(table.description)}</p>`
                : ""
            }
            ${metaGrid([
              ["角色绑定", table.characterRef || "无"],
              ["Sort Order", table.sortOrder ?? 0],
            ])}
            ${renderStatusRows(table.rows)}
            ${hasKeys(table.metadata) ? renderDetails(table.metadata) : ""}
          </article>
        `).join("")}
      </div>
    `,
  };
}

function renderStatusRows(value) {
  const rows = safeArray(value);
  if (!rows.length) {
    return emptyInline("该状态表尚未定义字段。");
  }
  return `
    <div class="status-table-wrap">
      <table class="status-table">
        <thead>
          <tr>
            <th>字段</th>
            <th>初始值</th>
            <th>更新规则</th>
            <th>Key 结构</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td><code>${escapeHtml(row.key || "")}</code></td>
              <td>${escapeHtml(row.value || "—")}</td>
              <td>${escapeHtml(row.updateRule || "—")}</td>
              <td>${row.runtimeKeyLocked ? "键锁定" : "未锁定"}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderPlotSchedule(value) {
  const plot = value || { outlines: [], pools: [], events: [] };
  const plotIndex = createPlotScheduleIndex(plot);
  if (state.plotSelection) {
    return renderPlotSelection(plotIndex, state.plotSelection);
  }
  return renderPlotDirectory(plot, plotIndex);
}

function createPlotScheduleIndex(plot) {
  return {
    outlines: indexPlotResources(plot.outlines),
    pools: indexPlotResources(plot.pools),
    events: indexPlotResources(plot.events),
  };
}

function indexPlotResources(value) {
  const all = safeArray(value);
  const byStableId = new Map();
  all.forEach((resource, arrayIndex) => {
    const stableId = String(resource?.stableId || "");
    if (!stableId) {
      return;
    }
    const entries = byStableId.get(stableId) || [];
    entries.push({ resource, arrayIndex });
    byStableId.set(stableId, entries);
  });
  return { all, byStableId };
}

function resolvePlotResource(index, stableId) {
  const entries = index.byStableId.get(String(stableId || "")) || [];
  if (entries.length === 1) {
    return { status: "found", entry: entries[0], entries };
  }
  return {
    status: entries.length ? "ambiguous" : "missing",
    entry: null,
    entries,
  };
}

function renderPlotDirectory(plot, plotIndex) {
  const outlines = sortedResources(plotIndex.outlines.all, "priority");
  const pools = plotIndex.pools.all;
  const events = plotIndex.events.all;
  if (!outlines.length && !pools.length && !events.length) {
    return emptyResult(
      "/resources/plotSchedule",
      plot,
      "剧情调度还是空的",
      "大纲节点与事件池可以并存；确认后会在这里形成调度全景。",
    );
  }
  return {
    path: "/resources/plotSchedule",
    raw: plot,
    html: `
      <div class="plot-layout">
        ${renderPlotDirectorySection(
          "PLOT OUTLINES",
          "剧情线",
          "按优先级进入各条剧情线，再沿节点定位实际事件。",
          outlines.length,
          outlines.length
            ? `<div class="resource-grid">${outlines.map((outline, index) => (
              renderPlotOutlineSummary(outline, index)
            )).join("")}</div>`
            : emptyInline("当前没有剧情线。"),
        )}
        ${renderPlotDirectorySection(
          "EVENT POOLS",
          "事件池",
          "进入事件池查看稳定抽取权重、soft 候选批次、池级冷却与大纲专用事件。",
          pools.length,
          pools.length
            ? `<div class="resource-grid">${pools.map((pool, index) => (
              renderPlotPoolSummary(pool, plotIndex, index)
            )).join("")}</div>`
            : emptyInline("当前没有事件池。"),
        )}
      </div>
    `,
  };
}

function renderPlotDirectorySection(
  eyebrow,
  title,
  description,
  count,
  content,
) {
  return `
    <section class="plot-directory-section">
      <header class="plot-section-header">
        <div>
          <p class="card-eyebrow">${escapeHtml(eyebrow)}</p>
          <h3>${escapeHtml(title)}</h3>
          <p>${escapeHtml(description)}</p>
        </div>
        <span class="plot-section-count">${escapeHtml(count)}</span>
      </header>
      ${content}
    </section>
  `;
}

function renderPlotOutlineSummary(outline, index) {
  const stableId = String(outline.stableId || "");
  const className = `resource-card plot-directory-card${revisionChangeClass(
    "plotOutlines",
    stableId || outline.name || index,
  )}`;
  const content = `
    <div class="card-heading">
      <div>
        <p class="card-eyebrow">${escapeHtml(stableId || "OUTLINE")}</p>
        <h3>${escapeHtml(outline.name || "未命名剧情线")}</h3>
      </div>
      ${statusPill(
        outline.enabled === false ? "停用" : "启用",
        outline.enabled === false ? "is-warning" : "is-positive",
      )}
    </div>
    <p class="card-copy">${escapeHtml(outline.description || "暂无剧情线说明。")}</p>
    ${metaGrid([
      ["优先级", outline.priority ?? 0],
      ["节点数", safeArray(outline.nodes).length],
    ])}
    <span class="plot-card-action">查看剧情线 <span aria-hidden="true">→</span></span>
  `;
  if (!stableId) {
    return `<article class="${className} is-unresolved">${content}</article>`;
  }
  return `
    <a
      class="${className}"
      href="${escapeHtml(plotDetailHref("outline", stableId))}"
      aria-label="查看剧情线：${escapeHtml(outline.name || stableId)}"
    >${content}</a>
  `;
}

function renderPlotPoolSummary(pool, plotIndex, index) {
  const stableId = String(pool.stableId || "");
  const className = `resource-card plot-directory-card${revisionChangeClass(
    "plotPools",
    stableId || pool.name || index,
  )}`;
  const events = plotIndex.events.all.filter(
    (event) => event.poolRef === stableId,
  );
  const outlineBoundCount = events.filter(
    (event) => collectPlotEventReferences(
      plotIndex.outlines.all,
      event.stableId,
    ).length > 0,
  ).length;
  const content = `
    <div class="card-heading">
      <div>
        <p class="card-eyebrow">${escapeHtml(stableId || "POOL")}</p>
        <h3>${escapeHtml(pool.name || "未命名事件池")}</h3>
      </div>
      <span class="plot-card-pills">
        ${statusPill(pool.selectionMode || "random", "is-accent")}
        ${statusPill(`权重 ${pool.selectionWeight ?? 1}`)}
        ${pool.selectionMode === "sequential"
          ? statusPill("严格顺序")
          : statusPill(`soft batch ${pool.candidateBatchSize ?? 3}`)}
        ${statusPill(
          Number(pool.cooldownMinutes || 0) > 0
            ? `冷却 ${pool.cooldownMinutes} 分钟`
            : "无池级冷却",
          Number(pool.cooldownMinutes || 0) > 0 ? "is-warning" : "",
        )}
        ${statusPill(
          pool.enabled === false ? "停用" : "启用",
          pool.enabled === false ? "is-warning" : "is-positive",
        )}
      </span>
    </div>
    <p class="card-copy">${escapeHtml(pool.description || "暂无事件池说明。")}</p>
    ${metaGrid([
      ["稳定抽取权重", pool.selectionWeight ?? 1],
      [
        "soft 候选批次",
        pool.selectionMode === "sequential"
          ? `${pool.candidateBatchSize ?? 3}（顺序池忽略）`
          : pool.candidateBatchSize ?? 3,
      ],
      ["事件数", events.length],
      ["自动池候选", events.length - outlineBoundCount],
      ["大纲专用", outlineBoundCount],
    ])}
    <span class="plot-card-action">展开事件池 <span aria-hidden="true">→</span></span>
  `;
  if (!stableId) {
    return `<article class="${className} is-unresolved">${content}</article>`;
  }
  return `
    <a
      class="${className}"
      href="${escapeHtml(plotDetailHref("pool", stableId))}"
      aria-label="展开事件池：${escapeHtml(pool.name || stableId)}"
    >${content}</a>
  `;
}

function renderPlotSelection(plotIndex, selection) {
  if (selection.kind === "invalid") {
    return renderPlotInvalidRoute(selection.stableId);
  }
  const index = plotIndex[`${selection.kind}s`];
  const resolution = resolvePlotResource(index, selection.stableId);
  if (resolution.status !== "found") {
    return renderPlotLookupError(
      selection.kind,
      selection.stableId,
      resolution,
    );
  }
  if (selection.kind === "outline") {
    return renderPlotOutlineDetail(resolution.entry, plotIndex);
  }
  if (selection.kind === "pool") {
    return renderPlotPoolDetail(resolution.entry, plotIndex);
  }
  return renderPlotEventDetail(resolution.entry, plotIndex);
}

function renderPlotInvalidRoute(routeValue) {
  return {
    path: "/resources/plotSchedule",
    raw: undefined,
    html: `
      ${renderPlotBreadcrumb([], "详情链接无效")}
      <div class="empty-state plot-lookup-error">
        <div>
          <strong>剧情调度详情链接无效</strong>
          <p><code>${escapeHtml(routeValue)}</code></p>
          <p>请从剧情线或事件池重新进入详情。</p>
          <a class="primary-button plot-back-link" href="#plot-schedule">
            返回剧情调度
          </a>
        </div>
      </div>
    `,
  };
}

function renderPlotLookupError(kind, stableId, resolution) {
  const labels = {
    outline: "剧情线",
    pool: "事件池",
    event: "事件",
  };
  const label = labels[kind] || "剧情资源";
  const reason = resolution.status === "ambiguous"
    ? `发现 ${resolution.entries.length} 个相同 stableId，无法唯一定位。`
    : "当前 revision 中没有这个 stableId。";
  return {
    path: "/resources/plotSchedule",
    raw: undefined,
    html: `
      ${renderPlotBreadcrumb([], `${label}未找到`)}
      <div class="empty-state plot-lookup-error">
        <div>
          <strong>${escapeHtml(label)}无法定位</strong>
          <p><code>${escapeHtml(stableId)}</code></p>
          <p>${escapeHtml(reason)}</p>
          <a class="primary-button plot-back-link" href="#plot-schedule">
            返回剧情调度
          </a>
        </div>
      </div>
    `,
  };
}

function renderPlotOutlineDetail(entry, plotIndex) {
  const outline = entry.resource;
  const nodes = safeArray(outline.nodes);
  return {
    path: `/resources/plotSchedule/outlines/${entry.arrayIndex}`,
    raw: outline,
    html: `
      ${renderPlotBreadcrumb([], outline.name || "未命名剧情线")}
      <div class="plot-layout">
        <article class="plot-lane plot-detail-card${revisionChangeClass(
          "plotOutlines",
          outline.stableId || outline.name || entry.arrayIndex,
        )}">
          <div class="plot-lane-header">
            <div>
              <p class="card-eyebrow">${escapeHtml(outline.stableId || "OUTLINE")}</p>
              <h3>${escapeHtml(outline.name || "未命名剧情线")}</h3>
              <p class="card-copy">${escapeHtml(outline.description || "暂无剧情线说明。")}</p>
            </div>
            ${statusPill(
              outline.enabled === false ? "停用" : "启用",
              outline.enabled === false ? "is-warning" : "is-positive",
            )}
          </div>
          ${metaGrid([
            ["优先级", outline.priority ?? 0],
            ["节点数", nodes.length],
          ])}
        </article>
        <section class="plot-detail-section">
          <header class="plot-section-header">
            <div>
              <p class="card-eyebrow">ORDERED NODES</p>
              <h3>剧情节点</h3>
              <p>点击节点查看它通过 eventRef 引用的完整事件。</p>
            </div>
            <span class="plot-section-count">${escapeHtml(nodes.length)}</span>
          </header>
          ${renderOutlineNodes(nodes, plotIndex)}
        </section>
      </div>
    `,
  };
}

function renderOutlineNodes(value, plotIndex) {
  const nodes = sortedResources(value, "position");
  if (!nodes.length) {
    return emptyInline("该大纲还没有节点。");
  }
  return `
    <ol class="plot-node-list">
      ${nodes.map((node, index) => {
        const resolution = resolvePlotResource(
          plotIndex.events,
          node.eventRef,
        );
        const event = resolution.entry?.resource;
        const className = `plot-node${revisionChangeClass(
          "plotNodes",
          node.stableId || node.eventRef || index,
        )}`;
        const content = `
          <span class="node-index">${String(index + 1).padStart(2, "0")}</span>
          <div>
            <strong>${escapeHtml(event?.title || node.eventRef || "未绑定事件")}</strong>
            <p>${escapeHtml(node.scheduledTime || "未设置时间")} · ${escapeHtml(node.dispatchMode || "soft")}</p>
            <span class="plot-node-ref">${escapeHtml(node.eventRef || "缺少 eventRef")}</span>
            ${
              resolution.status === "found"
                ? ""
                : `<span class="plot-node-warning">${escapeHtml(
                  resolution.status === "ambiguous"
                    ? "eventRef 对应多个事件，无法唯一定位。"
                    : "eventRef 没有对应事件。",
                )}</span>`
            }
          </div>
          ${statusPill(
            resolution.status === "found"
              ? (node.enabled === false ? "停用" : "启用")
              : (resolution.status === "ambiguous" ? "引用不唯一" : "引用缺失"),
            resolution.status === "found" && node.enabled !== false
              ? "is-positive"
              : "is-warning",
          )}
        `;
        if (resolution.status !== "found") {
          return `
            <li class="${className} is-unresolved">
              ${content}
            </li>
          `;
        }
        return `
          <li class="plot-node-item">
            <a
              class="${className}"
              href="${escapeHtml(plotDetailHref("event", event.stableId))}"
              aria-label="查看事件：${escapeHtml(event.title || event.stableId)}"
            >${content}</a>
          </li>
        `;
      }).join("")}
    </ol>
  `;
}

function renderPlotPoolDetail(entry, plotIndex) {
  const pool = entry.resource;
  const events = sortedResources(
    plotIndex.events.all.filter(
      (event) => event.poolRef === pool.stableId,
    ),
    "position",
  );
  const outlineBoundCount = events.filter(
    (event) => collectPlotEventReferences(
      plotIndex.outlines.all,
      event.stableId,
    ).length > 0,
  ).length;
  return {
    path: `/resources/plotSchedule/pools/${entry.arrayIndex}`,
    raw: pool,
    html: `
      ${renderPlotBreadcrumb([], pool.name || "未命名事件池")}
      <div class="plot-layout">
        <article class="resource-card plot-detail-card${revisionChangeClass(
          "plotPools",
          pool.stableId || pool.name || entry.arrayIndex,
        )}">
          <div class="card-heading">
            <div>
              <p class="card-eyebrow">${escapeHtml(pool.stableId || "POOL")}</p>
              <h3>${escapeHtml(pool.name || "未命名事件池")}</h3>
            </div>
            <span class="plot-card-pills">
              ${statusPill(pool.selectionMode || "random", "is-accent")}
              ${statusPill(`权重 ${pool.selectionWeight ?? 1}`)}
              ${pool.selectionMode === "sequential"
                ? statusPill("严格顺序")
                : statusPill(`soft batch ${pool.candidateBatchSize ?? 3}`)}
              ${statusPill(
                Number(pool.cooldownMinutes || 0) > 0
                  ? `冷却 ${pool.cooldownMinutes} 分钟`
                  : "无池级冷却",
                Number(pool.cooldownMinutes || 0) > 0 ? "is-warning" : "",
              )}
              ${statusPill(
                pool.enabled === false ? "停用" : "启用",
                pool.enabled === false ? "is-warning" : "is-positive",
              )}
            </span>
          </div>
          <p class="card-copy">${escapeHtml(pool.description || "暂无事件池说明。")}</p>
          ${metaGrid([
            ["稳定抽取权重", pool.selectionWeight ?? 1],
            [
              "soft 候选批次",
              pool.selectionMode === "sequential"
                ? `${pool.candidateBatchSize ?? 3}（顺序池忽略）`
                : pool.candidateBatchSize ?? 3,
            ],
            ["事件数", events.length],
            ["自动池候选", events.length - outlineBoundCount],
            ["大纲专用", outlineBoundCount],
            ["池级冷却分钟", pool.cooldownMinutes ?? 0],
          ])}
        </article>
        <section class="plot-detail-section">
          <header class="plot-section-header">
            <div>
              <p class="card-eyebrow">POOL EVENTS</p>
              <h3>池内事件</h3>
              <p>random 池按事件权重无放回召回 soft batch，再由一次适宜性判断选出一项；sequential 池仍按 position 严格推进。大纲绑定事件不参与自动池抽取。</p>
            </div>
            <span class="plot-section-count">${escapeHtml(events.length)}</span>
          </header>
          ${
            events.length
              ? `<div class="resource-grid">${events.map((event, index) => (
                renderPlotEventSummary(event, plotIndex, index)
              )).join("")}</div>`
              : emptyInline("该事件池还没有事件。")
          }
        </section>
      </div>
    `,
  };
}

function renderPlotEventSummary(event, plotIndex, index) {
  const stableId = String(event.stableId || "");
  const resolution = resolvePlotResource(plotIndex.events, stableId);
  const className = `resource-card plot-directory-card plot-event-summary${revisionChangeClass(
    "plotEvents",
    stableId || event.title || index,
  )}`;
  const outlineReferenceCount = collectPlotEventReferences(
    plotIndex.outlines.all,
    stableId,
  ).length;
  const content = `
    <div class="card-heading">
      <div>
        <p class="card-eyebrow">${escapeHtml(stableId || "EVENT")}</p>
        <h3>${escapeHtml(event.title || "未命名事件")}</h3>
      </div>
      ${statusPill(
        event.dispatchMode || "soft",
        event.dispatchMode === "forced" ? "is-accent" : "",
      )}
      ${outlineReferenceCount
        ? statusPill(`大纲专用 · ${outlineReferenceCount} 节点`, "is-accent")
        : statusPill("自动池候选", "is-positive")}
    </div>
    <p class="card-copy">${escapeHtml(event.description || "暂无事件摘要。")}</p>
    ${metaGrid([
      ["随机召回权重", event.selectionWeight ?? 1],
      ["计划时间", event.scheduledTime || "可选"],
      ["截止时间", event.deadlineTime || "无限制"],
      ["状态", event.enabled === false ? "停用" : "启用"],
      ["允许重复", event.allowRepeat ? "是" : "否"],
    ])}
    <span class="plot-card-action">查看完整事件 <span aria-hidden="true">→</span></span>
  `;
  if (!stableId || resolution.status !== "found") {
    const issue = resolution.status === "ambiguous"
      ? "stableId 重复，无法唯一定位。"
      : "缺少可定位的 stableId。";
    return `
      <article class="${className} is-unresolved">
        ${content}
        <span class="plot-node-warning">${escapeHtml(issue)}</span>
      </article>
    `;
  }
  return `
    <a
      class="${className}"
      href="${escapeHtml(plotDetailHref("event", stableId))}"
      aria-label="查看事件：${escapeHtml(event.title || stableId)}"
    >${content}</a>
  `;
}

function renderPlotEventDetail(entry, plotIndex) {
  const event = entry.resource;
  const poolResolution = resolvePlotResource(
    plotIndex.pools,
    event.poolRef,
  );
  const pool = poolResolution.entry?.resource;
  const references = collectPlotEventReferences(
    plotIndex.outlines.all,
    event.stableId,
  );
  const breadcrumbLinks = pool
    ? [{
      label: pool.name || pool.stableId,
      href: plotDetailHref("pool", pool.stableId),
    }]
    : [];
  return {
    path: `/resources/plotSchedule/events/${entry.arrayIndex}`,
    raw: event,
    html: `
      ${renderPlotBreadcrumb(
        breadcrumbLinks,
        event.title || "未命名事件",
      )}
      <div class="plot-layout">
        ${renderPlotEventDetailCard(event, entry.arrayIndex, references.length)}
        <section class="plot-detail-section">
          <header class="plot-section-header">
            <div>
              <p class="card-eyebrow">RELATIONSHIPS</p>
              <h3>调度关系</h3>
              <p>事件池归属与剧情线节点分别展示，不合并两套调度字段。</p>
            </div>
          </header>
          <div class="plot-reference-grid">
            <div>
              <h4>所属事件池</h4>
              ${renderPlotPoolReference(event.poolRef, poolResolution)}
            </div>
            <div>
              <h4>剧情线引用</h4>
              ${renderPlotOutlineReferences(references, plotIndex)}
            </div>
          </div>
        </section>
      </div>
    `,
  };
}

function renderPlotEventDetailCard(event, index, outlineReferenceCount) {
  return `
    <article class="resource-card plot-detail-card plot-event-detail${revisionChangeClass(
      "plotEvents",
      event.stableId || event.title || index,
    )}">
      <div class="card-heading">
        <div>
          <p class="card-eyebrow">${escapeHtml(event.stableId || "EVENT")}</p>
          <h3>${escapeHtml(event.title || "未命名事件")}</h3>
        </div>
        ${statusPill(event.dispatchMode || "soft", event.dispatchMode === "forced" ? "is-accent" : "")}
        ${outlineReferenceCount
          ? statusPill(`大纲专用 · ${outlineReferenceCount} 节点`, "is-accent")
          : statusPill("自动池候选", "is-positive")}
      </div>
      ${
        event.description
          ? `<h4>管理摘要</h4><p class="card-copy">${escapeHtml(event.description)}</p>`
          : ""
      }
      <h4>动态指令</h4>
      <p class="prose-block">${escapeHtml(event.directive || "—")}</p>
      ${metaGrid([
        ["事件池", event.poolRef || "—"],
        ["随机召回权重", event.selectionWeight ?? 1],
        ["计划时间", event.scheduledTime || "可选"],
        ["截止时间", event.deadlineTime || "无限制"],
        ["允许重复", event.allowRepeat ? "是" : "否"],
        ["冷却分钟", event.repeatCooldownMinutes ?? 0],
        ["状态", event.enabled === false ? "停用" : "启用"],
        ["自动池归属", outlineReferenceCount ? "结构绑定期间排除" : "可参与"],
      ])}
      ${
        event.suitabilityHint
          ? `<h4>适宜性提示</h4><p class="card-copy">${escapeHtml(event.suitabilityHint)}</p>`
          : `<h4>适宜性提示</h4><p class="card-copy muted">未填写。</p>`
      }
    </article>
  `;
}

function collectPlotEventReferences(outlines, eventStableId) {
  const references = [];
  sortedResources(outlines, "priority").forEach((outline) => {
    sortedResources(outline.nodes, "position").forEach((node) => {
      if (node.eventRef === eventStableId) {
        references.push({ outline, node });
      }
    });
  });
  return references;
}

function renderPlotPoolReference(poolRef, resolution) {
  if (resolution.status !== "found") {
    const reason = resolution.status === "ambiguous"
      ? "poolRef 对应多个事件池，无法唯一定位。"
      : "poolRef 没有对应事件池。";
    return `
      <div class="plot-reference-card is-unresolved">
        <strong>${escapeHtml(poolRef || "缺少 poolRef")}</strong>
        <p>${escapeHtml(reason)}</p>
      </div>
    `;
  }
  const pool = resolution.entry.resource;
  return `
    <a
      class="plot-reference-card"
      href="${escapeHtml(plotDetailHref("pool", pool.stableId))}"
    >
      <strong>${escapeHtml(pool.name || pool.stableId)}</strong>
      <p>${escapeHtml(pool.selectionMode || "random")} · 权重 ${escapeHtml(pool.selectionWeight ?? 1)} · soft batch ${escapeHtml(pool.candidateBatchSize ?? 3)} · 池级冷却 ${escapeHtml(pool.cooldownMinutes ?? 0)} 分钟</p>
      <span>${escapeHtml(pool.stableId)}</span>
    </a>
  `;
}

function renderPlotOutlineReferences(references, plotIndex) {
  if (!references.length) {
    return emptyInline("该事件没有被剧情线节点引用，只通过事件池进入候选。");
  }
  return `
    <div class="plot-reference-list">
      ${references.map(({ outline, node }) => {
        const stableId = String(outline.stableId || "");
        const resolution = resolvePlotResource(
          plotIndex.outlines,
          stableId,
        );
        const className = `plot-reference-card${revisionChangeClass(
          "plotNodes",
          node.stableId || node.eventRef,
        )}`;
        const content = `
          <strong>${escapeHtml(outline.name || outline.stableId)}</strong>
          <p>${escapeHtml(node.scheduledTime || "未设置时间")} · ${escapeHtml(node.dispatchMode || "soft")}</p>
          <span>${escapeHtml(node.stableId || node.eventRef)}</span>
        `;
        if (!stableId || resolution.status !== "found") {
          const reason = resolution.status === "ambiguous"
            ? "剧情线 stableId 重复，无法唯一定位。"
            : "剧情线缺少可定位的 stableId。";
          return `
            <div class="${className} is-unresolved">
              ${content}
              <p class="plot-node-warning">${escapeHtml(reason)}</p>
            </div>
          `;
        }
        return `
          <a
            class="${className}"
            href="${escapeHtml(plotDetailHref("outline", stableId))}"
          >${content}</a>
        `;
      }).join("")}
    </div>
  `;
}

function renderPlotBreadcrumb(links, currentLabel) {
  return `
    <nav class="plot-breadcrumb" aria-label="剧情调度层级">
      <a href="#plot-schedule">剧情调度</a>
      ${links.map((link) => `
        <span aria-hidden="true">/</span>
        <a href="${escapeHtml(link.href)}">${escapeHtml(link.label)}</a>
      `).join("")}
      <span aria-hidden="true">/</span>
      <strong aria-current="page">${escapeHtml(currentLabel)}</strong>
    </nav>
  `;
}

function renderRPModules(value) {
  const modules = safeArray(value);
  if (!modules.length) {
    return emptyResult(
      "/resources/rpModules",
      modules,
      "没有挂载 RP Module",
      "模块选择确认后，会显示启用状态和 Story 级配置。",
    );
  }
  return {
    path: "/resources/rpModules",
    raw: modules,
    html: `
      <div class="resource-grid">
        ${modules.map((module, index) => `
          <article class="resource-card${revisionChangeClass(
            "rpModules",
            module.moduleName || index,
          )}">
            <div class="card-heading">
              <div>
                <p class="card-eyebrow">RP MODULE</p>
                <h3>${escapeHtml(module.moduleName || "未命名模块")}</h3>
              </div>
              ${statusPill(module.enabled === false ? "停用" : "启用", module.enabled === false ? "is-warning" : "is-positive")}
            </div>
            ${hasKeys(module.config) ? renderDetails(module.config) : emptyInline("使用模块缺省配置。")}
          </article>
        `).join("")}
      </div>
    `,
  };
}

function renderNarrativeStyles(value) {
  const styles = sortedResources(value);
  if (!styles.length) {
    return emptyResult(
      "/resources/narrativeStyles",
      styles,
      "未选择叙事风格",
      "基础风格与附加风格会在这里形成可阅读的 Prompt 卡片。",
    );
  }
  return {
    path: "/resources/narrativeStyles",
    raw: styles,
    html: `
      <div class="resource-grid">
        ${styles.map((style, index) => `
          <article class="resource-card${revisionChangeClass(
            "narrativeStyles",
            style.stableId || style.name || index,
          )}">
            <div class="card-heading">
              <div>
                <p class="card-eyebrow">${escapeHtml(style.stableId || "STYLE")}</p>
                <h3>${escapeHtml(style.name || "未命名风格")}</h3>
              </div>
              ${statusPill(style.isBase ? "基础风格" : "附加风格", style.isBase ? "is-accent" : "")}
            </div>
            <p class="prose-block">${escapeHtml(style.prompt || "尚未设置 Prompt。")}</p>
            ${metaGrid([["Sort Order", style.sortOrder ?? 0]])}
          </article>
        `).join("")}
      </div>
    `,
  };
}

function renderQuickReplies(value) {
  const replies = sortedResources(value);
  if (!replies.length) {
    return emptyResult(
      "/resources/quickReplies",
      replies,
      "没有快捷回复",
      "需要复用的玩家输入模板会按顺序显示。",
    );
  }
  return {
    path: "/resources/quickReplies",
    raw: replies,
    html: `
      <div class="resource-grid">
        ${replies.map((reply, index) => `
          <article class="resource-card${revisionChangeClass(
            "quickReplies",
            reply.stableId || reply.title || index,
          )}">
            <div class="card-heading">
              <div>
                <p class="card-eyebrow">${escapeHtml(reply.stableId || "QUICK REPLY")}</p>
                <h3>${escapeHtml(reply.title || "未命名快捷回复")}</h3>
              </div>
              ${statusPill(reply.enabled === false ? "停用" : "启用", reply.enabled === false ? "is-warning" : "is-positive")}
            </div>
            <p class="prose-block">${escapeHtml(reply.message || "")}</p>
            ${metaGrid([["Sort Order", reply.sortOrder ?? 0]])}
          </article>
        `).join("")}
      </div>
    `,
  };
}

function renderVisualCatalog(value) {
  const visuals = safeArray(value);
  if (!visuals.length) {
    return emptyResult(
      "/resources/visualCatalog",
      visuals,
      "视觉目录还是空的",
      "值得独立生图的角色、场景和物件会形成可归档的视觉规格。",
    );
  }
  return {
    path: "/resources/visualCatalog",
    raw: visuals,
    html: `
      <div class="resource-grid">
        ${visuals.map((visual, index) => `
          <article class="resource-card${revisionChangeClass(
            "visualCatalog",
            visual.stableId || visual.title || index,
          )}">
            <div class="card-heading">
              <div>
                <p class="card-eyebrow">${escapeHtml(visual.stableId || "VISUAL")}</p>
                <h3>${escapeHtml(visual.title || "未命名视觉规格")}</h3>
              </div>
              ${statusPill(visual.assetType || "other", "is-accent")}
            </div>
            <h4>Prompt</h4>
            <p class="prose-block">${escapeHtml(visual.prompt || "")}</p>
            ${
              visual.negativePrompt
                ? `<h4>Negative Prompt</h4><p class="card-copy">${escapeHtml(visual.negativePrompt)}</p>`
                : ""
            }
            ${
              safeArray(visual.visualAnchors).length
                ? `<div class="tag-row">${safeArray(visual.visualAnchors).map((item) => tag(item)).join("")}</div>`
                : ""
            }
            ${metaGrid([
              ["Subject Refs", safeArray(visual.subjectRefs).join(", ") || "无"],
              ["Asset Type", visual.assetType || "other"],
            ])}
            ${hasKeys(visual.metadata) ? renderDetails(visual.metadata) : ""}
          </article>
        `).join("")}
      </div>
    `,
  };
}

function renderDecisions(decisionValue, questionValue) {
  const decisions = safeArray(decisionValue)
    .map((decision, index) => ({ decision, index }))
    .reverse();
  const questions = safeArray(questionValue);
  return {
    path: "/decisions",
    raw: { decisions: safeArray(decisionValue), openQuestions: questions },
    html: `
      <div class="section-stack">
        <div class="metric-grid">
          ${metricCard(
            "已确认",
            decisions.filter(({ decision }) => decision.status === "confirmed").length,
            "confirmed decisions",
            revisionChangeClass("decisions"),
          )}
          ${metricCard(
            "暂定",
            decisions.filter(({ decision }) => decision.status === "tentative").length,
            "tentative decisions",
            revisionChangeClass("decisions"),
          )}
          ${metricCard(
            "开放问题",
            questions.filter((item) => item.status === "open").length,
            "waiting for decision",
            revisionChangeClass("openQuestions"),
          )}
          ${metricCard(
            "已解决",
            questions.filter((item) => item.status === "resolved").length,
            "resolved questions",
            revisionChangeClass("openQuestions"),
          )}
        </div>
        <div class="two-column">
          <div class="section-stack">
            <p class="section-kicker">DECISIONS</p>
            ${
              decisions.length
                ? decisions.map(({ decision, index }) => `
                    <article class="decision-card${revisionChangeClass(
                      "decisions",
                      decision.id || index,
                    )}">
                      <div class="card-heading">
                        <div>
                          <p class="card-eyebrow">${escapeHtml(decision.id || "DECISION")}</p>
                          <h3>${escapeHtml(decision.topic || "未命名决策")}</h3>
                        </div>
                        ${statusPill(decision.status || "confirmed", decision.status === "confirmed" ? "is-positive" : "is-warning")}
                      </div>
                      <p class="prose-block">${escapeHtml(decision.decision || "")}</p>
                      ${
                        decision.rationale
                          ? `<h4>理由</h4><p class="card-copy">${escapeHtml(decision.rationale)}</p>`
                          : ""
                      }
                      ${metaGrid([["Decided At", formatDate(decision.decidedAt)]])}
                    </article>
                  `).join("")
                : emptyInline("尚未记录设计决策。")
            }
          </div>
          <div class="section-stack">
            <p class="section-kicker">OPEN QUESTIONS</p>
            ${
              questions.length
                ? questions.map((question, index) => `
                    <article class="question-card${revisionChangeClass(
                      "openQuestions",
                      question.id || index,
                    )}">
                      <div class="card-heading">
                        <div>
                          <p class="card-eyebrow">${escapeHtml(question.id || "QUESTION")}</p>
                          <h3>${escapeHtml(question.question || "未命名问题")}</h3>
                        </div>
                        ${statusPill(question.status || "open", question.status === "resolved" ? "is-positive" : "is-warning")}
                      </div>
                      ${
                        question.context
                          ? `<p class="card-copy">${escapeHtml(question.context)}</p>`
                          : ""
                      }
                      ${
                        safeArray(question.options).length
                          ? `<div class="tag-row">${safeArray(question.options).map((option) => tag(option)).join("")}</div>`
                          : ""
                      }
                    </article>
                  `).join("")
                : emptyInline("当前没有开放问题。")
            }
          </div>
        </div>
      </div>
    `,
  };
}

function renderSources(sourceValue, noteValue) {
  const sources = safeArray(sourceValue);
  const notes = safeArray(noteValue);
  if (!sources.length && !notes.length) {
    return emptyResult(
      "/sources",
      { sources, notes },
      "没有来源或笔记",
      "参考资料与简短设计笔记会集中显示在这里。",
    );
  }
  return {
    path: "/sources",
    raw: { sources, notes },
    html: `
      <div class="section-stack">
        ${
          notes.length
            ? `<article class="content-card${revisionChangeClass("notes")}">
                <p class="card-eyebrow">PROJECT NOTES</p>
                <h3>项目笔记</h3>
                <div class="detail-list">
                  ${notes.map((note, index) => detailRow(String(index + 1).padStart(2, "0"), note)).join("")}
                </div>
              </article>`
            : ""
        }
        <div class="resource-grid">
          ${sources.map((source, index) => `
            <article class="resource-card${revisionChangeClass(
              "sources",
              source.id || source.title || index,
            )}">
              <div class="card-heading">
                <div>
                  <p class="card-eyebrow">${escapeHtml(source.id || "SOURCE")}</p>
                  <h3>${escapeHtml(source.title || "未命名来源")}</h3>
                </div>
                ${statusPill(source.sourceType || "reference")}
              </div>
              ${
                source.notes
                  ? `<p class="card-copy">${escapeHtml(source.notes)}</p>`
                  : ""
              }
              ${metaGrid([["Locator", source.locator || "未记录"]])}
            </article>
          `).join("")}
        </div>
      </div>
    `,
  };
}

function renderFieldGuide() {
  const catalog = state.authoringRules;
  if (!catalog) {
    return {
      path: "/schemas/story-authoring-rules-v1.json",
      raw: undefined,
      html: loadingMarkup("正在读取字段语义目录…"),
    };
  }
  const diagnostics = safeArray(state.diagnostics?.diagnostics);
  const errors = diagnostics.filter((item) => item.severity === "error");
  const warnings = diagnostics.filter((item) => item.severity === "warning");
  const fields = safeArray(catalog.fields);
  const principles = safeArray(catalog.principles);
  const domains = safeArray(catalog.domains);
  return {
    path: "/authoring-rules",
    raw: {
      catalog,
      validation: state.diagnostics,
    },
    html: `
      <div class="schema-toolbar field-guide-toolbar">
        <div class="segmented" aria-label="校验 Profile">
          ${diagnosticProfileButton("draft", "草稿")}
          ${diagnosticProfileButton("package", "发布包")}
        </div>
        <input
          class="search-input"
          id="fieldGuideSearch"
          type="search"
          placeholder="搜索路径、字段、职责或运行时影响…"
          autocomplete="off"
          aria-label="搜索字段指南"
        >
      </div>
      <article class="content-card schema-summary">
        <div>
          <p class="card-eyebrow">AUTHORING RULES ${escapeHtml(catalog.authoringRulesVersion || "—")}</p>
          <h3>当前 revision · ${escapeHtml(state.diagnosticProfile)} profile</h3>
          <p class="card-copy">
            error 是确定性发布门禁；warning 用于字段职责与创作质量复核。
            规则版本独立于 Story Pack contractVersion。
          </p>
        </div>
        <div class="tag-row">
          ${tag(`${errors.length} errors`, errors.length ? "is-danger" : "is-accent")}
          ${tag(`${warnings.length} warnings`)}
          ${tag(`${fields.length} field rules`)}
          ${tag(`${domains.length} domains`)}
        </div>
      </article>
      <section class="section-stack">
        <div>
          <p class="section-kicker">REVISION DIAGNOSTICS</p>
          <h3>结构化诊断</h3>
        </div>
        ${
          diagnostics.length
            ? `<div class="diagnostic-grid">${diagnostics.map(renderAuthoringDiagnostic).join("")}</div>`
            : `<article class="content-card diagnostic-clear">
                <p class="card-eyebrow">CLEAR</p>
                <h3>当前 profile 没有诊断项</h3>
                <p class="card-copy">仍需由作者判断故事本身是否达到目标体验。</p>
              </article>`
        }
      </section>
      <section class="section-stack">
        <div>
          <p class="section-kicker">CROSS-FIELD PRINCIPLES</p>
          <h3>跨字段原则</h3>
        </div>
        <div class="schema-definition-list">
          ${principles.map((item) => `
            <article
              class="schema-card"
              data-field-guide-search="${escapeHtml([
                item.ruleId,
                item.domain,
                item.title,
                item.description,
                item.runtimeEffect,
              ].join(" ").toLowerCase())}"
            >
              <header>
                <div>
                  <p class="schema-path">${escapeHtml(item.ruleId)}</p>
                  <h3>${escapeHtml(item.title)}</h3>
                </div>
                <span class="schema-chip">${escapeHtml(item.domain)}</span>
              </header>
              <p class="card-copy">${escapeHtml(item.description)}</p>
              <p class="field-runtime-effect">
                <strong>运行时影响</strong>
                ${escapeHtml(item.runtimeEffect)}
              </p>
            </article>
          `).join("")}
        </div>
      </section>
      <section class="section-stack">
        <div>
          <p class="section-kicker">FIELD DUTIES</p>
          <h3>完整字段职责</h3>
        </div>
        <div class="schema-definition-list field-rule-list">
          ${fields.map(renderAuthoringFieldRule).join("")}
        </div>
      </section>
    `,
  };
}

function diagnosticProfileButton(profile, label) {
  return `
    <button
      class="${state.diagnosticProfile === profile ? "is-active" : ""}"
      type="button"
      data-diagnostic-profile="${escapeHtml(profile)}"
    >${escapeHtml(label)}</button>
  `;
}

function renderAuthoringDiagnostic(item) {
  return `
    <article class="diagnostic-card is-${escapeHtml(item.severity)}">
      <header>
        <span>${escapeHtml(item.severity.toUpperCase())}</span>
        <code>${escapeHtml(item.ruleId)}</code>
      </header>
      <h3>${escapeHtml(item.message)}</h3>
      <code class="diagnostic-path">${escapeHtml(item.path)}</code>
      <p><strong>建议</strong>${escapeHtml(item.suggestion)}</p>
      <p><strong>运行时</strong>${escapeHtml(item.runtimeEffect)}</p>
    </article>
  `;
}

function renderAuthoringFieldRule(item) {
  const example = safeArray(item.examples)[0];
  const searchText = [
    item.ruleId,
    item.domain,
    item.model,
    item.field,
    item.pathPattern,
    item.description,
    item.avoid,
    item.runtimeEffect,
    stringifyCompact(example),
  ].filter(Boolean).join(" ").toLowerCase();
  return `
    <article
      class="schema-card field-rule-card"
      data-field-guide-search="${escapeHtml(searchText)}"
    >
      <header>
        <div>
          <p class="schema-path">${escapeHtml(item.pathPattern)}</p>
          <h3>${escapeHtml(item.model)} · ${escapeHtml(item.field)}</h3>
        </div>
        <span class="schema-chip">${escapeHtml(item.domain)}</span>
      </header>
      <p class="card-copy">${escapeHtml(item.description)}</p>
      <div class="field-rule-detail">
        <p><strong>避免</strong>${escapeHtml(item.avoid)}</p>
        <p><strong>示例</strong><code>${escapeHtml(stringifyCompact(example))}</code></p>
        <p><strong>运行时影响</strong>${escapeHtml(item.runtimeEffect)}</p>
      </div>
      <code class="field-rule-id">${escapeHtml(item.ruleId)}</code>
    </article>
  `;
}

function filterFieldGuideCards(query) {
  const normalized = query.trim().toLowerCase();
  elements.contentStage
    .querySelectorAll("[data-field-guide-search]")
    .forEach((card) => {
      card.hidden =
        normalized.length > 0 &&
        !card.dataset.fieldGuideSearch.includes(normalized);
    });
}

function renderSchemas() {
  const schema = state.schemas[state.schemaKind];
  if (!schema) {
    loadSchema(state.schemaKind).catch(showErrorToast);
    return {
      path: `/schemas/${state.schemaKind}`,
      raw: undefined,
      html: loadingMarkup("正在解析 Schema…"),
    };
  }
  const definitions = schema.$defs || {};
  const cards = [
    ["Root Document", schema],
    ...Object.entries(definitions),
  ];
  return {
    path: `/schemas/${state.schemaKind}`,
    raw: schema,
    html: `
      <div class="schema-toolbar">
        <div class="segmented" aria-label="Schema 类型">
          ${schemaKindButton("story-design", "Story Design")}
          ${schemaKindButton("story-pack", "Story Pack")}
        </div>
        <input
          class="search-input"
          id="schemaSearch"
          type="search"
          placeholder="搜索定义、字段或枚举…"
          autocomplete="off"
          aria-label="搜索 Schema"
        >
      </div>
      <article class="content-card schema-summary">
        <div>
          <p class="card-eyebrow">${escapeHtml(schema.$id || state.schemaKind)}</p>
          <h3>${escapeHtml(schema.title || "Schema")}</h3>
          <p class="card-copy">${escapeHtml(schema.description || "Portable Story schema contract.")}</p>
        </div>
        <div class="tag-row">
          ${tag(`${Object.keys(definitions).length} definitions`, "is-accent")}
          ${tag(schema.type || "object")}
        </div>
      </article>
      <div class="schema-definition-list">
        ${cards.map(([name, definition]) => renderSchemaCard(name, definition)).join("")}
      </div>
    `,
  };
}

async function loadSchema(kind) {
  const requestToken = ++state.schemaRequestToken;
  const schema = await api(`/api/schemas/${encodeURIComponent(kind)}`);
  if (requestToken !== state.schemaRequestToken) {
    return;
  }
  state.schemas[kind] = schema;
  if (state.activeView === "schemas" && state.schemaKind === kind) {
    renderActiveView();
  }
}

function invalidateSchemaCache() {
  state.schemaRequestToken += 1;
  state.schemas = {};
}

function schemaKindButton(kind, label) {
  return `
    <button
      class="${state.schemaKind === kind ? "is-active" : ""}"
      type="button"
      data-schema-kind="${escapeHtml(kind)}"
    >${escapeHtml(label)}</button>
  `;
}

function renderSchemaCard(name, definition) {
  const properties = definition.properties || {};
  const required = new Set(definition.required || []);
  const searchText = [
    name,
    definition.title,
    definition.description,
    ...Object.keys(properties),
    ...Object.values(properties).flatMap((property) => property.enum || []),
  ].filter(Boolean).join(" ").toLowerCase();
  return `
    <article class="schema-card" data-schema-search="${escapeHtml(searchText)}">
      <header>
        <div>
          <p class="schema-path">${escapeHtml(definition.$id || `#/$defs/${name}`)}</p>
          <h3>${escapeHtml(definition.title || name)}</h3>
        </div>
        <span class="schema-chip">${escapeHtml(describeSchemaType(definition))}</span>
      </header>
      ${
        definition.description
          ? `<p class="card-copy">${escapeHtml(definition.description)}</p>`
          : ""
      }
      ${
        Object.keys(properties).length
          ? `<div class="schema-field-list">
              ${Object.entries(properties)
                .map(([field, property]) => renderSchemaField(field, property, required.has(field)))
                .join("")}
            </div>`
          : `<div class="schema-field-list">${renderSchemaConstraints(definition)}</div>`
      }
    </article>
  `;
}

function renderSchemaField(name, property, required) {
  const constraints = schemaConstraints(property);
  return `
    <div class="schema-field">
      <span class="schema-field-name">
        ${escapeHtml(name)}
        ${required ? '<span class="required-star" title="必填">*</span>' : ""}
      </span>
      <span class="schema-field-meta">
        <code>${escapeHtml(describeSchemaType(property))}</code>
        ${constraints.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
      </span>
    </div>
  `;
}

function renderSchemaConstraints(definition) {
  const constraints = schemaConstraints(definition);
  if (!constraints.length) {
    return '<span class="muted">没有额外字段约束。</span>';
  }
  return constraints
    .map((item) => `<span class="schema-field-meta">${escapeHtml(item)}</span>`)
    .join("");
}

function describeSchemaType(schema) {
  if (schema.$ref) {
    return `ref:${schema.$ref.split("/").pop()}`;
  }
  if (schema.type === "array") {
    if (schema.items?.$ref) {
      return `array<${schema.items.$ref.split("/").pop()}>`;
    }
    return `array<${schema.items?.type || "any"}>`;
  }
  if (Array.isArray(schema.anyOf)) {
    return schema.anyOf.map((item) => describeSchemaType(item)).join(" | ");
  }
  if (schema.const !== undefined) {
    return `const`;
  }
  return schema.type || "object";
}

function schemaConstraints(schema) {
  const rows = [];
  if (schema.default !== undefined) {
    rows.push(`默认 ${stringifyCompact(schema.default)}`);
  }
  if (schema.const !== undefined) {
    rows.push(`固定 ${stringifyCompact(schema.const)}`);
  }
  if (schema.enum) {
    rows.push(`枚举 ${schema.enum.join(" · ")}`);
  }
  if (schema.minItems !== undefined) {
    rows.push(`最少 ${schema.minItems} 项`);
  }
  if (schema.maxItems !== undefined) {
    rows.push(`最多 ${schema.maxItems} 项`);
  }
  if (schema.minimum !== undefined) {
    rows.push(`≥ ${schema.minimum}`);
  }
  if (schema.maximum !== undefined) {
    rows.push(`≤ ${schema.maximum}`);
  }
  if (schema.pattern) {
    rows.push(`格式 ${schema.pattern}`);
  }
  if (schema.description) {
    rows.push(schema.description);
  }
  return rows;
}

function filterSchemaCards(query) {
  const normalized = query.trim().toLowerCase();
  elements.contentStage.querySelectorAll(".schema-card").forEach((card) => {
    card.hidden =
      normalized.length > 0 &&
      !card.dataset.schemaSearch.includes(normalized);
  });
}

function renderStoryPacks() {
  if (state.selectedPack) {
    return renderStoryPackDetail(state.selectedPack);
  }
  if (!state.packs.length) {
    return emptyResult(
      "/artifacts/story-packs",
      state.packs,
      "还没有 Story Pack",
      "构建完成的完整包或 section 小包会自动出现在这里。",
    );
  }
  return {
    path: "/artifacts/story-packs",
    raw: state.packs,
    html: `
      <div class="pack-toolbar">
        <div>
          <p class="card-eyebrow">PACK ARCHIVE</p>
          <strong>${state.packs.length} 个不可变产物</strong>
        </div>
        <span class="muted">Story Pack v2 · merge-only</span>
      </div>
      <div class="pack-list">
        ${state.packs.map((pack) => `
          <article class="pack-card">
            <div>
              <p class="card-eyebrow">${escapeHtml(pack.packId || pack.filename)}</p>
              <h3>${escapeHtml(pack.storyTitle || "未命名 Story Pack")}</h3>
              <div class="pack-section-list">
                ${safeArray(pack.includedSections).map((section) => tag(section)).join("")}
              </div>
              ${metaGrid([
                ["来源 Revision", pack.sourceRevision || "—"],
                ["生成时间", formatDate(pack.generatedAt)],
                ["文件", pack.filename],
                ["大小", formatBytes(pack.sizeBytes)],
              ])}
            </div>
            <button
              class="quiet-button"
              type="button"
              data-pack-file="${escapeHtml(pack.filename)}"
            >查看产物</button>
          </article>
        `).join("")}
      </div>
    `,
  };
}

async function loadStoryPack(filename) {
  const requestToken = ++state.packRequestToken;
  setContentLoading();
  const pack = await api(
    `/api/story-packs/${encodeURIComponent(filename)}`,
  );
  if (
    requestToken !== state.packRequestToken
    || state.activeView !== "story-packs"
  ) {
    return;
  }
  state.selectedPack = pack;
  renderActiveView();
}

function renderStoryPackDetail(pack) {
  const story = pack.story || {};
  const resources = pack.resources || {};
  return {
    path: `/artifacts/story-packs/${pack.packId || "pack"}`,
    raw: pack,
    html: `
      <div class="section-stack">
        <button
          class="quiet-button"
          type="button"
          data-viewer-action="back-to-packs"
        >← 返回 Story Pack 列表</button>
        <article class="story-hero">
          <p class="section-kicker">${escapeHtml(pack.packId || "STORY PACK")}</p>
          <h3>${escapeHtml(story.title || "未命名 Story Pack")}</h3>
          <p class="story-logline">${escapeHtml(story.logline || story.summary || "该产物没有故事摘要。")}</p>
          <div class="hero-meta">
            ${tag(pack.sourceRevision || "无来源 revision", "is-accent")}
            ${safeArray(pack.includedSections).map((section) => tag(section)).join("")}
          </div>
        </article>
        <div class="metric-grid">
          ${metricCard("角色", safeArray(resources.characters).length, "pack resources")}
          ${metricCard("世界书", safeArray(resources.lorebook).length, "pack resources")}
          ${metricCard("状态表", safeArray(resources.statusTables).length, "pack resources")}
          ${metricCard("开局", safeArray(resources.openings).length, "pack resources")}
        </div>
        <article class="content-card">
          <p class="card-eyebrow">PACK METADATA</p>
          <h3>产物信息</h3>
          ${metaGrid([
            ["Project ID", pack.projectId || "—"],
            ["Story Stable ID", pack.storyStableId || "—"],
            ["Source Revision", pack.sourceRevision || "—"],
            ["Generated At", formatDate(pack.generatedAt)],
            ["Delete Missing", pack.applyPolicy?.deleteMissing ? "是" : "否"],
            ["Schema", pack.schemaVersion || "—"],
          ])}
        </article>
        ${genericCard("PACK CONTENT", "完整资源结构", resources)}
      </div>
    `,
  };
}

function openRawDialog() {
  if (state.rawValue === undefined) {
    return;
  }
  const definition = VIEW_DEFINITIONS.find(
    (item) => item.id === state.activeView,
  );
  elements.rawDialogTitle.textContent =
    `${definition?.label || "当前视图"} · 原始 JSON`;
  elements.rawDialogPath.textContent = state.rawPath || "/";
  elements.rawJsonContent.textContent = JSON.stringify(
    state.rawValue,
    null,
    2,
  );
  elements.rawDialog.showModal();
}

async function copyRawJson() {
  const text = elements.rawJsonContent.textContent;
  try {
    await navigator.clipboard.writeText(text);
    showToast("已复制", "原始 JSON 已写入剪贴板。");
  } catch {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(elements.rawJsonContent);
    selection.removeAllRanges();
    selection.addRange(range);
    showToast("请手动复制", "当前浏览器未授权剪贴板，JSON 已全选。");
  }
}

function openCompareDialog() {
  const revisions = state.history.revisions || [];
  if (revisions.length < 2) {
    showToast("暂无可比较版本", "至少需要两个 revision。");
    return;
  }
  const selected =
    revisions.find((item) => item.revisionId === state.selectedRevisionId) ||
    revisions[0];
  const parent =
    revisions.find((item) => item.revisionId === selected.parentRevision) ||
    revisions[1];
  const options = revisions
    .map(
      (revision) => `
        <option value="${escapeHtml(revision.revisionId)}">
          ${escapeHtml(revision.revisionId)} · ${escapeHtml(revision.reason || "无说明")}
        </option>
      `,
    )
    .join("");
  elements.compareFrom.innerHTML = options;
  elements.compareTo.innerHTML = options;
  elements.compareFrom.value = parent.revisionId;
  elements.compareTo.value = selected.revisionId;
  elements.compareResult.innerHTML =
    '<div class="empty-inline">选择两个 revision 查看变化。</div>';
  elements.compareDialog.showModal();
}

async function runComparison() {
  const from = elements.compareFrom.value;
  const to = elements.compareTo.value;
  elements.compareResult.innerHTML = loadingMarkup("正在计算 revision 差异…");
  const diff = await api(
    `/api/diff?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
  );
  const lines = diff.unifiedDiff
    ? diff.unifiedDiff.split("\n")
    : [];
  elements.compareResult.innerHTML = `
    <div class="diff-summary">
      ${statusPill(diff.changed ? "有变化" : "完全一致", diff.changed ? "is-accent" : "is-positive")}
      ${safeArray(diff.changedSections)
        .map((item) => tag(item.section))
        .join("")}
    </div>
    ${
      diff.changed
        ? `<pre class="diff-code" tabindex="0">${lines
            .map((line) => {
              let className = "";
              if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@")) {
                className = "is-header";
              } else if (line.startsWith("+")) {
                className = "is-add";
              } else if (line.startsWith("-")) {
                className = "is-remove";
              }
              return `<span class="diff-line ${className}">${escapeHtml(line || " ")}</span>`;
            })
            .join("")}</pre>`
        : emptyInline("两个 revision 的文档内容完全一致。")
    }
  `;
}

function showUpdateBanner() {
  const shouldShow =
    state.pendingHeadId &&
    state.selectedRevisionId !== state.pendingHeadId;
  elements.updateBanner.hidden = !shouldShow;
  if (shouldShow) {
    elements.updateBannerText.textContent =
      `${state.pendingHeadId} 已就绪，当前仍在查看 ${state.selectedRevisionId}`;
  }
}

function setContentLoading() {
  elements.contentStage.innerHTML = loadingMarkup("正在展开 revision…");
}

function loadingMarkup(message) {
  return `
    <div class="loading-state">
      <div class="loading-orbit" aria-hidden="true"></div>
      <p>${escapeHtml(message)}</p>
    </div>
  `;
}

function renderFatalError(error) {
  elements.contentStage.innerHTML = `
    <div class="empty-state error-state">
      <div>
        <strong>无法读取 Story DesignProject</strong>
        <p>${escapeHtml(error?.message || String(error))}</p>
      </div>
    </div>
  `;
}

function showErrorToast(error) {
  showToast("读取失败", error?.message || String(error));
}

function showToast(title, message) {
  window.clearTimeout(state.toastTimer);
  elements.toastTitle.textContent = title;
  elements.toastMessage.textContent = message;
  elements.toast.hidden = false;
  state.toastTimer = window.setTimeout(() => {
    elements.toast.hidden = true;
  }, 4200);
}

function togglePanel(which) {
  const panel =
    which === "sections" ? elements.sectionSidebar : elements.historyRail;
  const other =
    which === "sections" ? elements.historyRail : elements.sectionSidebar;
  const toggle =
    which === "sections" ? elements.sectionToggle : elements.historyToggle;
  const otherToggle =
    which === "sections" ? elements.historyToggle : elements.sectionToggle;
  const nextOpen = !panel.classList.contains("is-open");
  other.classList.remove("is-open");
  otherToggle.setAttribute("aria-expanded", "false");
  panel.classList.toggle("is-open", nextOpen);
  toggle.setAttribute("aria-expanded", String(nextOpen));
  elements.panelBackdrop.hidden = !nextOpen;
}

function closePanels() {
  elements.sectionSidebar.classList.remove("is-open");
  elements.historyRail.classList.remove("is-open");
  elements.sectionToggle.setAttribute("aria-expanded", "false");
  elements.historyToggle.setAttribute("aria-expanded", "false");
  elements.panelBackdrop.hidden = true;
}

function emptyResult(path, raw, title, description) {
  return {
    path,
    raw,
    html: `
      <div class="empty-state${hasViewRevisionChange(state.activeView) ? " is-revision-changed" : ""}">
        <div>
          <strong>${escapeHtml(title)}</strong>
          <p>${escapeHtml(description)}</p>
        </div>
      </div>
    `,
  };
}

function emptyInline(message) {
  return `<div class="empty-inline">${escapeHtml(message)}</div>`;
}

function metricCard(label, value, note, className = "") {
  return `
    <article class="metric-card${className}">
      <span class="metric-label">${escapeHtml(label)}</span>
      <strong class="metric-value">${escapeHtml(value)}</strong>
      <span class="metric-note">${escapeHtml(note)}</span>
    </article>
  `;
}

function proseCard(eyebrow, title, value, fallback, className = "") {
  return `
    <article class="content-card${className}">
      <p class="card-eyebrow">${escapeHtml(eyebrow)}</p>
      <h3>${escapeHtml(title)}</h3>
      <p class="prose-block">${
        value
          ? escapeHtml(value)
          : `<span class="muted">${escapeHtml(fallback)}</span>`
      }</p>
    </article>
  `;
}

function genericCard(eyebrow, title, value, className = "") {
  return `
    <article class="content-card${className}">
      <p class="card-eyebrow">${escapeHtml(eyebrow)}</p>
      <h3>${escapeHtml(title)}</h3>
      <div class="generic-tree">${renderGenericTree(value)}</div>
    </article>
  `;
}

function renderVisualSummary(value) {
  if (!hasKeys(value)) {
    return "";
  }
  return `
    <h4>视觉描述</h4>
    <div class="generic-tree">${renderGenericTree(value)}</div>
  `;
}

function renderDetails(value) {
  return `
    <h4>扩展字段</h4>
    <div class="detail-list">
      ${Object.entries(value)
        .map(([key, item]) => detailRow(key, formatLooseValue(item)))
        .join("")}
    </div>
  `;
}

function renderGenericTree(value, key = null, depth = 0) {
  if (Array.isArray(value)) {
    if (!value.length) {
      return key === null
        ? '<span class="tree-value">[]</span>'
        : treePrimitive(key, "[]");
    }
    return `
      <details ${depth < 1 ? "open" : ""}>
        <summary>
          ${key === null ? "" : `<span class="tree-key">${escapeHtml(key)}</span> `}
          <span class="muted">[${value.length}]</span>
        </summary>
        ${value.map((item, index) => renderGenericTree(item, String(index), depth + 1)).join("")}
      </details>
    `;
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value);
    if (!entries.length) {
      return key === null
        ? '<span class="tree-value">{}</span>'
        : treePrimitive(key, "{}");
    }
    return `
      <details ${depth < 1 ? "open" : ""}>
        <summary>
          ${key === null ? "" : `<span class="tree-key">${escapeHtml(key)}</span> `}
          <span class="muted">{${entries.length}}</span>
        </summary>
        ${entries.map(([childKey, child]) => renderGenericTree(child, childKey, depth + 1)).join("")}
      </details>
    `;
  }
  return treePrimitive(key, value);
}

function treePrimitive(key, value) {
  const isNull = value === null || value === undefined;
  return `
    <div>
      ${key === null ? "" : `<span class="tree-key">${escapeHtml(key)}:</span> `}
      <span class="tree-value ${isNull ? "is-null" : ""}">${escapeHtml(
        isNull ? "null" : stringifyCompact(value),
      )}</span>
    </div>
  `;
}

function detailRow(key, value) {
  return `
    <div class="detail-row">
      <span class="detail-key">${escapeHtml(key)}</span>
      <span class="detail-value">${escapeHtml(value)}</span>
    </div>
  `;
}

function metaGrid(items) {
  const filtered = items.filter((item) => item[1] !== undefined);
  return `
    <div class="meta-grid">
      ${filtered.map(([label, value]) => `
        <div class="meta-item">
          <span class="meta-label">${escapeHtml(label)}</span>
          <span class="meta-value">${escapeHtml(value)}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function tag(value, className = "") {
  return `<span class="tag ${className}">${escapeHtml(value)}</span>`;
}

function statusPill(value, className = "") {
  return `<span class="status-pill ${className}">${escapeHtml(value)}</span>`;
}

function getAtPath(value, path) {
  return path.reduce(
    (current, key) => (current == null ? undefined : current[key]),
    value,
  );
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function sortedResources(value, field = "sortOrder") {
  return safeArray(value).slice().sort((left, right) => {
    const a = Number(left?.[field] ?? 0);
    const b = Number(right?.[field] ?? 0);
    return a - b;
  });
}

function hasKeys(value) {
  return Boolean(
    value &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.keys(value).length,
  );
}

function formatDate(value) {
  if (!value) {
    return "未记录";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatLooseValue(value) {
  if (value === null || value === undefined) {
    return "null";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value, null, 2);
}

function stringifyCompact(value) {
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
