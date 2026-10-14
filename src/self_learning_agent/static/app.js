const MODEL_META = {
  "qwen3-local:4b": { label: "Qwen3 4B", note: "适合即时回答和轻量工具调用。" },
  "qwen3-local:8b": { label: "Qwen3 8B", note: "适合 K3 上的速度与质量平衡。" },
  "qwen3-local:14b": { label: "Qwen3 14B", note: "适合复杂分析和更长上下文。" },
};
const EFFORT_META = {
  fast: { label: "快速", description: "优先响应速度 · 最多 2 步工具调用" },
  balanced: { label: "平衡", description: "速度和质量平衡 · 最多 4 步工具调用" },
  deep: { label: "深度", description: "允许更多推理 · 最多 6 步工具调用" },
};

const state = {
  userId: localStorage.getItem("recall-user-id") || "demo-user",
  conversationId: null,
  finalized: false,
  sending: false,
  modelSwitching: false,
  webEnabled: false,
  model: "qwen3-local:8b",
  reasoningEffort: "balanced",
  runtimeModels: [],
  contextChars: 0,
  activeView: "chat",
  conversations: [],
  memories: [],
  pendingUploads: [],
};

const elements = {
  chatForm: document.querySelector("#chat-form"),
  messageInput: document.querySelector("#message-input"),
  sendButton: document.querySelector("#send-message"),
  uploadInput: document.querySelector("#upload-input"),
  uploadsStrip: document.querySelector("#uploads-strip"),
  messageList: document.querySelector("#message-list"),
  messageScroller: document.querySelector("#message-scroller"),
  emptyState: document.querySelector("#empty-state"),
  userId: document.querySelector("#user-id"),
  newConversation: document.querySelector("#new-conversation"),
  finalize: document.querySelector("#finalize-conversation"),
  conversationTitle: document.querySelector("#conversation-title"),
  sessionLabel: document.querySelector("#session-label"),
  memoryCount: document.querySelector("#memory-count"),
  refreshMemories: document.querySelector("#refresh-memories"),
  connectionStatus: document.querySelector("#connection-status"),
  connectionLabel: document.querySelector("#connection-label"),
  sidebarStatus: document.querySelector("#sidebar-status"),
  sidebarStatusLight: document.querySelector("#sidebar-status-light"),
  webToggle: document.querySelector("#web-toggle"),
  webToggleLabel: document.querySelector("#web-toggle-label"),
  networkCard: document.querySelector("#network-card"),
  networkDescription: document.querySelector("#network-description"),
  webStateNote: document.querySelector("#web-state-note"),
  resumeCard: document.querySelector("#resume-card"),
  resumeDescription: document.querySelector("#resume-description"),
  resumeHint: document.querySelector("#resume-hint"),
  shutdownButton: document.querySelector("#shutdown-button"),
  modelOptions: document.querySelector("#model-options"),
  modelNote: document.querySelector("#model-note"),
  latencyBadge: document.querySelector("#latency-badge"),
  effortRange: document.querySelector("#effort-range"),
  effortValue: document.querySelector("#effort-value"),
  effortNote: document.querySelector("#effort-note"),
  contextSize: document.querySelector("#context-size"),
  contextMeterFill: document.querySelector("#context-meter-fill"),
  memoryMode: document.querySelector("#memory-mode"),
  toastRegion: document.querySelector("#toast-region"),
  sidebar: document.querySelector("#memory-sidebar"),
  sidebarScrim: document.querySelector("#sidebar-scrim"),
  openSidebar: document.querySelector("#open-sidebar"),
  closeSidebar: document.querySelector("#close-sidebar"),
  conversationList: document.querySelector("#conversation-list"),
  navItems: document.querySelectorAll("[data-view]"),
  workspaceGrid: document.querySelector(".workspace-grid"),
  memoryView: document.querySelector("#memory-view"),
  toolsView: document.querySelector("#tools-view"),
  memoryGrid: document.querySelector("#memory-grid"),
  memoryViewRefresh: document.querySelector("#memory-view-refresh"),
  toolGrid: document.querySelector("#tool-grid"),
  workflowGrid: document.querySelector("#workflow-grid"),
  toolsViewRefresh: document.querySelector("#tools-view-refresh"),
  hardwareMessage: document.querySelector("#hardware-message"),
  hardwareCamera: document.querySelector("#hardware-camera"),
  hardwareActuators: document.querySelector("#hardware-actuators"),
  hardwareVision: document.querySelector("#hardware-vision"),
  toolTestName: document.querySelector("#tool-test-name"),
  toolTestArguments: document.querySelector("#tool-test-arguments"),
  toolTestRun: document.querySelector("#tool-test-run"),
  toolTestResult: document.querySelector("#tool-test-result"),
};

elements.userId.value = state.userId;

async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
  });
  if (!response.ok) {
    let message = `请求失败 (${response.status})`;
    try { message = (await response.json()).detail || message; } catch (_) { /* status is enough */ }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast ${type === "error" ? "error" : ""}`;
  toast.textContent = message;
  elements.toastRegion.append(toast);
  window.setTimeout(() => toast.remove(), 4300);
}

function setConnection(online, label) {
  elements.connectionStatus.classList.toggle("online", online);
  elements.connectionStatus.classList.toggle("offline", !online);
  elements.connectionLabel.textContent = label;
  elements.sidebarStatus.textContent = online ? "本地服务在线" : "本地服务不可用";
  elements.sidebarStatusLight.style.background = online ? "#6fc58a" : "#eb8c81";
}

async function checkHealth() {
  try { await apiRequest("/health"); setConnection(true, "本地服务在线"); }
  catch (_) { setConnection(false, "本地服务不可用"); }
}

function renderRuntime(runtime) {
  const fileAccess = document.querySelector("#file-access-mode");
  if (fileAccess) {
    fileAccess.textContent = runtime.filesystem?.mode === "local" ? "本机文件可读" : "项目文件可读";
    fileAccess.title = runtime.filesystem?.mode === "local"
      ? "可按绝对路径浏览和读取本机文件，使用当前系统账户权限"
      : "文件访问范围限制在项目目录";
  }
  if (runtime.latency_target_seconds) {
    elements.latencyBadge.textContent = `目标 <${runtime.latency_target_seconds}s`;
  }
  state.runtimeModels = runtime.models || [];
  if (runtime.model_switching && !state.modelSwitching) {
    showToast("K3 正在加载模型，请等待右侧状态恢复后再发送消息。");
  }
  if (elements.memoryMode) {
    const mode = runtime.memory?.embedding_mode || (runtime.memory?.embedding_available ? "semantic" : "lexical");
    elements.memoryMode.textContent = mode === "semantic" ? "语义记忆" : "词法记忆";
    elements.memoryMode.title = mode === "semantic"
      ? "已启用 Ollama 嵌入检索"
      : "嵌入模型未就绪，使用本地词法回退";
  }
  const available = new Set(state.runtimeModels.filter((model) => model.registered).map((model) => model.id));
  elements.modelOptions.querySelectorAll("[data-model]").forEach((button) => {
    const model = button.dataset.model;
    const modelInfo = state.runtimeModels.find((item) => item.id === model);
    const ready = modelInfo ? modelInfo.registered : false;
    button.classList.toggle("unavailable", !ready);
    button.title = ready
      ? "模型当前已加载"
      : modelInfo?.file_available
        ? "模型文件已部署，点击后切换 K3 模型服务"
        : "模型文件尚未部署到当前运行环境";
    const status = button.querySelector("[data-model-status]");
    if (status) status.textContent = ready
      ? "当前加载"
      : modelInfo?.file_available ? "已部署，点击切换" : "未部署";
  });
  if (!available.has(state.model) && available.has(runtime.default_model)) state.model = runtime.default_model;
  updateModelSelection();
}

async function loadRuntime() {
  try { renderRuntime(await apiRequest("/v1/runtime")); }
  catch (_) { updateModelSelection(); }
}

function updateModelSelection() {
  elements.modelOptions.querySelectorAll("[data-model]").forEach((button) => {
    button.classList.toggle("selected", button.dataset.model === state.model);
  });
  const meta = MODEL_META[state.model] || MODEL_META["qwen3-local:8b"];
  elements.modelNote.textContent = `当前使用 ${meta.label}，${meta.note}`;
}

async function setModel(model) {
  if (!MODEL_META[model]) return;
  const profile = state.runtimeModels.find((item) => item.id === model);
  if (profile && !profile.registered) {
    if (!profile.file_available) {
      showToast("该模型文件尚未部署到当前运行环境。", "error");
      return;
    }
    if (!window.confirm(`切换到 ${MODEL_META[model].label} 会重启 K3 模型服务，切换期间当前请求会暂停，是否继续？`)) return;
    state.modelSwitching = true;
    setSending(false);
    elements.modelOptions.querySelectorAll("[data-model]").forEach((button) => { button.disabled = true; });
    showToast(`正在切换到 ${MODEL_META[model].label}，大模型可能需要较长加载时间…`);
    try {
      const runtime = await apiRequest("/v1/runtime/model", {
        method: "POST",
        body: JSON.stringify({ model }),
      });
      renderRuntime(runtime);
      if (!runtime.models?.some((item) => item.id === model && item.registered)) {
        throw new Error("模型服务已返回，但目标模型尚未就绪");
      }
      state.model = model;
      updateModelSelection();
      showToast(`已切换到 ${MODEL_META[model].label}。`);
    } catch (error) {
      showToast(`模型切换失败：${error.message}`, "error");
      await loadRuntime();
    } finally {
      state.modelSwitching = false;
      setSending(false);
      elements.modelOptions.querySelectorAll("[data-model]").forEach((button) => { button.disabled = false; });
    }
    return;
  }
  state.model = model;
  updateModelSelection();
  showToast(`已切换到 ${MODEL_META[model].label}。`);
}

function updateEffort() {
  const values = ["fast", "balanced", "deep"];
  state.reasoningEffort = values[Number(elements.effortRange.value) - 1] || "balanced";
  const meta = EFFORT_META[state.reasoningEffort];
  elements.effortValue.textContent = meta.label;
  elements.effortNote.textContent = meta.description;
}

function updateWebToggle() {
  const enabled = state.webEnabled;
  elements.webToggle.classList.toggle("enabled", enabled);
  elements.webToggle.setAttribute("aria-pressed", String(enabled));
  elements.webToggleLabel.textContent = enabled ? "外网开启" : "外网关闭";
  elements.networkCard.classList.toggle("enabled", enabled);
  elements.webStateNote.textContent = enabled ? "已允许" : "默认关闭";
  elements.networkDescription.textContent = enabled ? "当前消息允许发送到外部搜索" : "仅在确认后搜索外部信息";
}

function toggleWebAccess() {
  if (state.webEnabled) {
    state.webEnabled = false;
    updateWebToggle();
    showToast("外网已关闭，后续消息不会主动搜索外网。");
    return;
  }
  const confirmed = window.confirm("开启外网后，当前消息可能会发送到外部搜索服务。请确认你了解这一点，并确定要开启吗？");
  if (!confirmed) return;
  state.webEnabled = true;
  updateWebToggle();
  showToast("外网已开启。发送消息时将允许 Agent 使用外部搜索。");
}

function currentUserId() {
  const value = elements.userId.value.trim();
  if (!value) throw new Error("开始任务前请输入记忆身份。");
  return value;
}

function updateContextMeter(extra = "") {
  state.contextChars = elements.messageList.textContent.length + elements.messageInput.value.length + extra.length;
  elements.contextSize.textContent = `${state.contextChars.toLocaleString()} 字符`;
  elements.contextMeterFill.style.width = `${Math.min(100, Math.max(2, (state.contextChars / 18000) * 100))}%`;
}

function resetConversation() {
  state.conversationId = null;
  state.finalized = false;
  state.sending = false;
  elements.messageList.replaceChildren();
  elements.emptyState.classList.remove("hidden");
  elements.conversationTitle.textContent = "新建任务";
  elements.sessionLabel.textContent = "尚未开始任务";
  elements.finalize.textContent = "完成并学习";
  elements.finalize.disabled = true;
  elements.messageInput.disabled = false;
  elements.messageInput.placeholder = "描述任务，Agent 会在本地完成…";
  elements.sendButton.disabled = false;
  updateContextMeter();
  showView("chat");
  renderConversationList();
  elements.messageInput.focus();
}

async function createConversation() {
  const conversation = await apiRequest("/v1/conversations", { method: "POST", body: JSON.stringify({ user_id: currentUserId() }) });
  state.userId = elements.userId.value.trim();
  state.conversationId = conversation.id;
  state.finalized = false;
  localStorage.setItem("recall-user-id", state.userId);
  elements.conversationTitle.textContent = `任务 · ${conversation.id.slice(0, 8)}`;
  elements.sessionLabel.textContent = `会话 ${conversation.id.slice(0, 8)}`;
  await loadConversations();
  return conversation;
}

function conversationStatusLabel(status) {
  return status === "finalized" ? "已完成" : "进行中";
}

function renderConversationList() {
  if (!elements.conversationList) return;
  elements.conversationList.replaceChildren();
  if (!state.conversations.length) {
    const empty = document.createElement("div");
    empty.className = "conversation-empty";
    empty.textContent = "还没有任务记录";
    elements.conversationList.append(empty);
    return;
  }
  state.conversations.forEach((conversation) => {
    const button = document.createElement("button");
    button.className = `conversation-item${conversation.id === state.conversationId ? " active" : ""}`;
    button.type = "button";
    button.dataset.conversationId = conversation.id;
    const dot = document.createElement("span"); dot.className = "conversation-dot";
    const copy = document.createElement("span");
    const title = document.createElement("strong"); title.textContent = conversation.title || "新建任务";
    const meta = document.createElement("small"); meta.textContent = `${conversationStatusLabel(conversation.status)} · ${conversation.message_count} 条消息`;
    copy.append(title, meta); button.append(dot, copy); elements.conversationList.append(button);
  });
}

async function loadConversations() {
  try {
    state.conversations = await apiRequest(`/v1/users/${encodeURIComponent(currentUserId())}/conversations?limit=30`);
    renderConversationList();
  } catch (_) {
    state.conversations = [];
    renderConversationList();
  }
}

async function openConversation(conversationId) {
  try {
    const conversation = await apiRequest(`/v1/conversations/${conversationId}`);
    state.conversationId = conversation.id;
    state.finalized = conversation.status === "finalized";
    elements.messageList.replaceChildren();
    elements.emptyState.classList.toggle("hidden", conversation.messages.length > 0);
    conversation.messages.forEach((message) => createMessage(message.role, message.content));
    elements.conversationTitle.textContent = `任务 · ${conversation.id.slice(0, 8)}`;
    elements.sessionLabel.textContent = `会话 ${conversation.id.slice(0, 8)}`;
    elements.finalize.textContent = state.finalized ? "记忆已更新" : "完成并学习";
    elements.finalize.disabled = state.finalized;
    elements.messageInput.disabled = state.finalized;
    elements.sendButton.disabled = state.finalized;
    showView("chat");
    renderConversationList();
    scrollToLatest();
  } catch (error) { showToast(`无法打开任务：${error.message}`, "error"); }
}

function scrollToLatest() { window.requestAnimationFrame(() => { elements.messageScroller.scrollTop = elements.messageScroller.scrollHeight; }); }

function createMemoryRecall(memories) {
  const details = document.createElement("details");
  details.className = "memory-recall";
  const summary = document.createElement("summary");
  summary.textContent = `已召回 ${memories.length} 条记忆`;
  const list = document.createElement("div"); list.className = "recall-items";
  memories.forEach((memory) => {
    const item = document.createElement("div"); item.className = "recall-item";
    const content = document.createElement("span"); content.textContent = memory.content;
    const score = document.createElement("span"); score.className = "recall-score"; score.textContent = Number(memory.score || 0).toFixed(2);
    item.append(content, score); list.append(item);
  });
  details.append(summary, list); return details;
}

function createMessage(role, content, memories = []) {
  elements.emptyState.classList.add("hidden");
  const article = document.createElement("article"); article.className = `message ${role}`;
  const avatar = document.createElement("div"); avatar.className = "message-avatar"; avatar.setAttribute("aria-hidden", "true"); avatar.textContent = role === "user" ? "我" : "AI";
  const body = document.createElement("div"); body.className = "message-body";
  const label = document.createElement("div"); label.className = "message-role"; label.textContent = role === "user" ? "用户" : "K3 Agent";
  const bubble = document.createElement("div"); bubble.className = "message-content"; bubble.textContent = content;
  body.append(label, bubble); if (memories.length) body.append(createMemoryRecall(memories)); article.append(avatar, body); elements.messageList.append(article); scrollToLatest(); updateContextMeter(); return article;
}

function createTypingMessage() {
  const article = createMessage("assistant", "");
  const bubble = article.querySelector(".message-content"); bubble.setAttribute("aria-label", "Agent 正在思考"); bubble.innerHTML = "<div class=\"typing-dots\"><span></span><span></span><span></span></div>"; return article;
}

function appendSystemMessage(content) { elements.emptyState.classList.add("hidden"); const message = document.createElement("div"); message.className = "system-message"; message.textContent = content; elements.messageList.append(message); scrollToLatest(); updateContextMeter(); }

function maybePromptToFinalize(answer) {
  // Surface a hint when the assistant claims to remember something: until
  // the operator clicks "完成并学习", the fact only lives in this turn's
  // context and a fresh tab will not see it.
  if (!answer || state.finalized) return;
  const triggers = ["我记住了", "记住了您", "记住了你的", "已记住", "已记录"];
  if (!triggers.some((needle) => answer.includes(needle))) return;
  appendSystemMessage(
    "提示：这条记忆只在本次对话里。要让新窗口/下次也能记住，请点右上角「完成并学习」。"
  );
}

function setSending(isSending) {
  state.sending = isSending;
  const blocked = isSending || state.modelSwitching;
  elements.messageInput.disabled = blocked || state.finalized;
  elements.sendButton.disabled = blocked || state.finalized;
  elements.finalize.disabled = blocked || state.finalized || !state.conversationId;
}

async function sendMessage(content) {
  const cleanContent = content.trim();
  if (!cleanContent || state.sending || state.finalized) return;
  setSending(true); createMessage("user", cleanContent); elements.messageInput.value = ""; updateContextMeter(); resizeComposer();
  // Attach a one-line list of pending uploads so the agent knows there are
  // files it can ``workspace_read`` this turn. The chips remain visible
  // until the user removes them so a follow-up question can also reference
  // them.
  const uploads = state.pendingUploads.filter((u) => !u.error);
  let body = { content: cleanContent, use_web: state.webEnabled, model: state.model, reasoning_effort: state.reasoningEffort };
  if (uploads.length) {
    body.content = `${cleanContent}\n\n[本轮已上传到 workspace/uploads/：${uploads.map((u) => u.path).join("、")}]`;
  }
  let typingMessage;
  try {
    if (!state.conversationId) await createConversation();
    typingMessage = createTypingMessage();
    const response = await apiRequest(`/v1/conversations/${state.conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    typingMessage.remove();
    if (response.web_status) appendSystemMessage(response.web_status);
    createMessage("assistant", response.content, response.recalled_memories || []);
    maybePromptToFinalize(response.content);
  } catch (error) { typingMessage?.remove(); appendSystemMessage(`消息发送失败：${error.message}`); showToast(error.message, "error"); }
  finally { setSending(false); if (!state.finalized) elements.messageInput.focus(); }
}

async function finalizeConversation() {
  if (!state.conversationId || state.sending || state.finalized) return;
  setSending(true); elements.finalize.textContent = "正在总结…";
  try {
    const response = await apiRequest(`/v1/conversations/${state.conversationId}/finalize`, { method: "POST" });
    state.finalized = true;
    const learned = Object.values(response.memory_actions || {}).reduce((total, value) => total + Number(value || 0), 0);
    appendSystemMessage(`任务已完成。总结：${response.summary.synopsis}（${learned} 个记忆操作）`);
    elements.messageInput.placeholder = "请新建任务继续"; showToast("总结已保存，长期记忆已更新。"); await loadMemories();
  } catch (error) { showToast(error.message, "error"); }
  finally { elements.finalize.textContent = state.finalized ? "记忆已更新" : "完成并学习"; setSending(false); }
}

async function loadMemories() {
  try {
    state.memories = await apiRequest(`/v1/users/${encodeURIComponent(currentUserId())}/memories`);
    elements.memoryCount.textContent = String(state.memories.length);
    renderMemoryView();
  } catch (_) { elements.memoryCount.textContent = "–"; }
}

function renderMemoryView() {
  if (!elements.memoryGrid) return;
  elements.memoryGrid.replaceChildren();
  if (!state.memories.length) {
    const empty = document.createElement("div"); empty.className = "panel-empty"; empty.textContent = "还没有长期记忆。完成一个任务后，Agent 会从已验证内容中学习。"; elements.memoryGrid.append(empty); return;
  }
  state.memories.forEach((memory) => {
    const card = document.createElement("article"); card.className = "memory-card";
    const content = document.createElement("p"); content.textContent = memory.content;
    const meta = document.createElement("small"); meta.textContent = `${memory.metadata?.source ? "已验证" : "本地记录"} · ${memory.created_at ? new Date(memory.created_at).toLocaleString() : ""}`;
    const remove = document.createElement("button"); remove.type = "button"; remove.className = "card-delete"; remove.textContent = "删除"; remove.dataset.memoryId = memory.id;
    card.append(content, meta, remove); elements.memoryGrid.append(card);
  });
}

async function deleteMemory(memoryId) {
  if (!window.confirm("删除这条长期记忆？此操作会立即写入本地数据库。")) return;
  try { await apiRequest(`/v1/users/${encodeURIComponent(currentUserId())}/memories/${memoryId}`, { method: "DELETE" }); await loadMemories(); showToast("记忆已删除。"); }
  catch (error) { showToast(error.message, "error"); }
}

async function loadToolsView() {
  try {
    const [catalog, hardware, workflows] = await Promise.all([apiRequest("/v1/tools"), apiRequest("/v1/hardware/status"), apiRequest("/v1/workflows")]);
    elements.toolGrid.replaceChildren();
    catalog.tools.forEach((tool) => {
      const card = document.createElement("article"); card.className = "tool-card";
      const name = document.createElement("strong"); name.textContent = tool.name;
      const description = document.createElement("p"); description.textContent = tool.description;
      const badge = document.createElement("span"); badge.className = `tool-badge${tool.safe_for_ui ? " safe" : ""}`; badge.textContent = tool.safe_for_ui ? "可测试" : "仅 Agent";
      card.append(name, description, badge); elements.toolGrid.append(card);
    });
    elements.hardwareMessage.textContent = hardware.message;
    elements.hardwareCamera.textContent = hardware.camera?.available ? "已连接" : "未连接";
    elements.hardwareActuators.textContent = hardware.actuators?.length ? `${hardware.actuators.length} 个` : "未连接";
    elements.hardwareVision.textContent = hardware.vision?.available ? "已连接" : "占位模式";
    elements.workflowGrid.replaceChildren();
    workflows.workflows.forEach((workflow) => {
      const card = document.createElement("article"); card.className = "workflow-card";
      const title = document.createElement("strong"); title.textContent = workflow.name;
      const description = document.createElement("p"); description.textContent = workflow.description;
      const steps = document.createElement("small"); steps.textContent = `${workflow.steps.length} 个步骤 · ${workflow.steps.map((step) => step.tool).join(" → ")}`;
      const run = document.createElement("button"); run.type = "button"; run.className = "panel-action workflow-run"; run.textContent = "运行预检"; run.dataset.workflowId = workflow.id;
      card.append(title, description, steps, run); elements.workflowGrid.append(card);
    });
  } catch (error) { showToast(`工具状态读取失败：${error.message}`, "error"); }
}

async function runWorkflow(workflowId, button) {
  button.disabled = true; button.textContent = "运行中…";
  try {
    const result = await apiRequest(`/v1/workflows/${workflowId}/run`, { method: "POST" });
    elements.toolTestResult.textContent = result.steps.map((step) => `[${step.tool}] ${step.result}`).join("\n");
    showToast(`${result.name} 已完成。`);
  } catch (error) { showToast(error.message, "error"); }
  finally { button.disabled = false; button.textContent = "运行预检"; }
}

async function runToolTest() {
  const name = elements.toolTestName.value;
  let argumentsPayload = {};
  try { argumentsPayload = JSON.parse(elements.toolTestArguments.value || "{}"); }
  catch (_) { showToast("工具参数必须是 JSON。", "error"); return; }
  elements.toolTestRun.disabled = true;
  try {
    const response = await apiRequest("/v1/tools/execute", { method: "POST", body: JSON.stringify({ name, arguments: argumentsPayload }) });
    elements.toolTestResult.textContent = response.result;
  } catch (error) { elements.toolTestResult.textContent = error.message; showToast(error.message, "error"); }
  finally { elements.toolTestRun.disabled = false; }
}

function showView(view) {
  state.activeView = view;
  elements.workspaceGrid.classList.toggle("hidden", view !== "chat");
  elements.memoryView.classList.toggle("hidden", view !== "memory");
  elements.toolsView.classList.toggle("hidden", view !== "tools");
  elements.navItems.forEach((item) => item.classList.toggle("active", item.dataset.view === view));
  if (view === "memory") loadMemories();
  if (view === "tools") loadToolsView();
}

function resizeComposer() { elements.messageInput.style.height = "auto"; elements.messageInput.style.height = `${Math.min(elements.messageInput.scrollHeight, 140)}px`; }
function openSidebar() { elements.sidebar.classList.add("open"); elements.sidebarScrim.classList.add("visible"); elements.sidebarScrim.setAttribute("aria-hidden", "false"); }
function closeSidebar() { elements.sidebar.classList.remove("open"); elements.sidebarScrim.classList.remove("visible"); elements.sidebarScrim.setAttribute("aria-hidden", "true"); }

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function renderUploadChips() {
  if (!elements.uploadsStrip) return;
  elements.uploadsStrip.replaceChildren();
  for (const item of state.pendingUploads) {
    const chip = document.createElement("span");
    chip.className = `upload-chip${item.error ? " error" : ""}`;
    const label = document.createElement("span");
    label.textContent = item.error
      ? `✗ ${item.filename}：${item.error}`
      : `📎 ${item.filename} · ${formatBytes(item.bytes)}`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove";
    remove.textContent = "×";
    remove.setAttribute("aria-label", `移除 ${item.filename}`);
    remove.addEventListener("click", () => {
      state.pendingUploads = state.pendingUploads.filter((u) => u !== item);
      renderUploadChips();
    });
    chip.append(label, remove);
    elements.uploadsStrip.append(chip);
  }
}

async function uploadOneFile(file) {
  const form = new FormData();
  form.append("file", file);
  try {
    const response = await fetch("/v1/uploads", { method: "POST", body: form });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || `上传失败（${response.status}）`);
    }
    state.pendingUploads.push({
      filename: data.filename,
      path: data.path,
      bytes: Number(data.bytes || file.size),
    });
    showToast(`已上传 ${data.filename}，下次工具调用时可读`);
  } catch (error) {
    state.pendingUploads.push({
      filename: file.name,
      bytes: file.size,
      error: error.message,
    });
    showToast(`上传失败：${error.message}`, "error");
  }
  renderUploadChips();
}

async function handleUploadSelection(event) {
  const files = Array.from(event.target.files || []);
  event.target.value = ""; // allow re-selecting the same file
  for (const file of files) await uploadOneFile(file);
}

function showShutdownOverlay(message) {
  // Hide everything else and show a full-page notice so the operator knows
  // the agent is down and how to restart it.
  let overlay = document.querySelector("#shutdown-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "shutdown-overlay";
    overlay.className = "shutdown-overlay";
    overlay.innerHTML = `
      <div class="shutdown-card" role="alert">
        <div class="shutdown-glyph" aria-hidden="true">⏻</div>
        <h2>本地 Agent 已停止</h2>
        <p id="shutdown-message"></p>
        <button type="button" id="shutdown-reload">关闭此网页</button>
      </div>`;
    document.body.append(overlay);
    overlay.querySelector("#shutdown-reload").addEventListener("click", () => {
      window.close();
      // window.close() is a no-op for windows the script did not open; fall
      // back to navigating to a blank page so the operator can close the tab.
      setTimeout(() => { window.location.href = "about:blank"; }, 200);
    });
  }
  overlay.querySelector("#shutdown-message").textContent = message;
  overlay.hidden = false;
}

async function shutdownAgent() {
  if (!window.confirm("确定要关闭本地 Agent 服务吗？\n\n这会停止本地推理和 API，关闭后网页无法继续使用，需要重新启动。")) return;
  elements.shutdownButton.disabled = true;
  try {
    const response = await apiRequest("/v1/shutdown", { method: "POST" });
    // The server schedules its own exit ~300 ms after the response is sent.
    // Show the overlay immediately so the operator sees the final message
    // even if the next fetch fails because the process is already gone.
    showShutdownOverlay(response.message || "Agent 已停止。");
    // Mark the connection offline so the header reflects the state.
    setConnection(false, "本地服务已关闭");
  } catch (error) {
    // Even if the call failed, the server may still be tearing down; show the
    // overlay with the error text rather than leaving the operator guessing.
    showShutdownOverlay(`关闭请求已完成（${error.message}）。如果服务还在，请重新启动。`);
  }
}

elements.chatForm.addEventListener("submit", (event) => { event.preventDefault(); sendMessage(elements.messageInput.value); });
elements.messageInput.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); elements.chatForm.requestSubmit(); } });
elements.messageInput.addEventListener("input", () => { resizeComposer(); updateContextMeter(); });
if (elements.uploadInput) elements.uploadInput.addEventListener("change", handleUploadSelection);
elements.finalize.addEventListener("click", finalizeConversation);
elements.refreshMemories.addEventListener("click", loadMemories);
elements.memoryViewRefresh.addEventListener("click", loadMemories);
elements.toolsViewRefresh.addEventListener("click", loadToolsView);
elements.toolTestRun.addEventListener("click", runToolTest);
elements.toolTestName.addEventListener("change", () => {
  const examples = {
    workspace_list: { subpath: "D:\\mc" },
    workspace_read: { path: "D:\\mc\\README.txt" },
    calculator: { expression: "1 + 2 * 3" },
    get_time: {}, hardware_status: {}, camera_capture: { camera: "main" },
  };
  elements.toolTestArguments.value = JSON.stringify(examples[elements.toolTestName.value] || {});
});
elements.workflowGrid.addEventListener("click", (event) => { const button = event.target.closest("[data-workflow-id]"); if (button) runWorkflow(button.dataset.workflowId, button); });
elements.webToggle.addEventListener("click", toggleWebAccess);
elements.networkCard.addEventListener("click", toggleWebAccess);
elements.shutdownButton.addEventListener("click", shutdownAgent);
elements.effortRange.addEventListener("input", updateEffort);
elements.modelOptions.addEventListener("click", (event) => { const button = event.target.closest("[data-model]"); if (button) setModel(button.dataset.model); });
elements.openSidebar.addEventListener("click", openSidebar); elements.closeSidebar.addEventListener("click", closeSidebar); elements.sidebarScrim.addEventListener("click", closeSidebar);
elements.newConversation.addEventListener("click", () => { resetConversation(); closeSidebar(); showToast("可以开始新任务了。"); });
elements.navItems.forEach((item) => item.addEventListener("click", () => showView(item.dataset.view)));
elements.conversationList.addEventListener("click", (event) => { const item = event.target.closest("[data-conversation-id]"); if (item) openConversation(item.dataset.conversationId); });
elements.memoryGrid.addEventListener("click", (event) => { const button = event.target.closest("[data-memory-id]"); if (button) deleteMemory(button.dataset.memoryId); });
elements.userId.addEventListener("change", async () => { try { const userId = currentUserId(); if (userId !== state.userId) { state.userId = userId; localStorage.setItem("recall-user-id", userId); resetConversation(); await loadMemories(); showToast(`已切换记忆身份：${userId}`); } } catch (error) { showToast(error.message, "error"); } });
document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => { elements.messageInput.value = button.dataset.prompt; resizeComposer(); updateContextMeter(); elements.messageInput.focus(); }));
document.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "n") { event.preventDefault(); resetConversation(); } if (event.key === "Escape") closeSidebar(); });

async function resumeLastConversation() {
  // When the page loads (including a freshly opened tab) try to drop the
  // operator back into their most recent non-finalized conversation so the
  // previous chat history is visible without any extra clicks.
  if (!state.conversations.length) return;
  const sorted = [...state.conversations].sort((a, b) => {
    const ta = new Date(a.created_at || 0).getTime();
    const tb = new Date(b.created_at || 0).getTime();
    return tb - ta;
  });
  const target = sorted.find((c) => c.status !== "finalized") || sorted[0];
  if (target) await openConversation(target.id);
}

updateEffort(); updateWebToggle(); updateModelSelection(); checkHealth(); loadRuntime(); loadMemories();
loadConversations().then(resumeLastConversation);
