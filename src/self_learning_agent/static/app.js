const state = {
  userId: localStorage.getItem("recall-user-id") || "demo-user",
  conversationId: null,
  finalized: false,
  sending: false,
};

const elements = {
  chatForm: document.querySelector("#chat-form"),
  messageInput: document.querySelector("#message-input"),
  sendButton: document.querySelector("#send-message"),
  messageList: document.querySelector("#message-list"),
  messageScroller: document.querySelector("#message-scroller"),
  emptyState: document.querySelector("#empty-state"),
  userId: document.querySelector("#user-id"),
  newConversation: document.querySelector("#new-conversation"),
  finalize: document.querySelector("#finalize-conversation"),
  conversationTitle: document.querySelector("#conversation-title"),
  sessionLabel: document.querySelector("#session-label"),
  memoryList: document.querySelector("#memory-list"),
  memoryCount: document.querySelector("#memory-count"),
  refreshMemories: document.querySelector("#refresh-memories"),
  connectionStatus: document.querySelector("#connection-status"),
  connectionLabel: document.querySelector("#connection-label"),
  toastRegion: document.querySelector("#toast-region"),
  sidebar: document.querySelector("#memory-sidebar"),
  sidebarScrim: document.querySelector("#sidebar-scrim"),
  openSidebar: document.querySelector("#open-sidebar"),
  closeSidebar: document.querySelector("#close-sidebar"),
};

elements.userId.value = state.userId;

async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch (_) {
      // The status code still gives the user a useful failure message.
    }
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
}

async function checkHealth() {
  try {
    await apiRequest("/health");
    setConnection(true, "Local services online");
  } catch (_) {
    setConnection(false, "Local services unavailable");
  }
}

function currentUserId() {
  const value = elements.userId.value.trim();
  if (!value) throw new Error("Enter a memory identity before starting a conversation.");
  return value;
}

function resetConversation() {
  state.conversationId = null;
  state.finalized = false;
  state.sending = false;
  elements.messageList.replaceChildren();
  elements.emptyState.classList.remove("hidden");
  elements.conversationTitle.textContent = "New conversation";
  elements.sessionLabel.textContent = "No conversation started";
  elements.finalize.textContent = "Finalize & learn";
  elements.finalize.disabled = true;
  elements.messageInput.disabled = false;
  elements.messageInput.placeholder = "Message your local agent…";
  elements.sendButton.disabled = false;
  elements.messageInput.focus();
}

async function createConversation() {
  const userId = currentUserId();
  const conversation = await apiRequest("/v1/conversations", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
  state.userId = userId;
  state.conversationId = conversation.id;
  state.finalized = false;
  localStorage.setItem("recall-user-id", userId);
  elements.conversationTitle.textContent = `Conversation · ${conversation.id.slice(0, 8)}`;
  elements.sessionLabel.textContent = `Session ${conversation.id.slice(0, 8)}`;
  return conversation;
}

function createMessage(role, content, memories = []) {
  elements.emptyState.classList.add("hidden");
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = role === "user" ? "U" : "R";
  const body = document.createElement("div");
  body.className = "message-body";
  const label = document.createElement("div");
  label.className = "message-role";
  label.textContent = role === "user" ? "You" : "Recall agent";
  const bubble = document.createElement("div");
  bubble.className = "message-content";
  bubble.textContent = content;
  body.append(label, bubble);
  if (memories.length) body.append(createMemoryRecall(memories));
  article.append(avatar, body);
  elements.messageList.append(article);
  scrollToLatest();
  return article;
}

function createMemoryRecall(memories) {
  const details = document.createElement("details");
  details.className = "memory-recall";
  const summary = document.createElement("summary");
  summary.textContent = `${memories.length} ${memories.length === 1 ? "memory" : "memories"} recalled`;
  const list = document.createElement("div");
  list.className = "recall-items";
  memories.forEach((memory) => {
    const item = document.createElement("div");
    item.className = "recall-item";
    const content = document.createElement("span");
    content.textContent = memory.content;
    const score = document.createElement("span");
    score.className = "recall-score";
    score.textContent = Number(memory.score || 0).toFixed(2);
    score.title = "Similarity score";
    item.append(content, score);
    list.append(item);
  });
  details.append(summary, list);
  return details;
}

function createTypingMessage() {
  const article = createMessage("assistant", "");
  const bubble = article.querySelector(".message-content");
  bubble.setAttribute("aria-label", "Agent is thinking");
  bubble.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
  return article;
}

function appendSystemMessage(content) {
  elements.emptyState.classList.add("hidden");
  const message = document.createElement("div");
  message.className = "system-message";
  message.textContent = content;
  elements.messageList.append(message);
  scrollToLatest();
}

function scrollToLatest() {
  window.requestAnimationFrame(() => {
    elements.messageScroller.scrollTop = elements.messageScroller.scrollHeight;
  });
}

function setSending(isSending) {
  state.sending = isSending;
  elements.messageInput.disabled = isSending || state.finalized;
  elements.sendButton.disabled = isSending || state.finalized;
  elements.finalize.disabled = isSending || state.finalized || !state.conversationId;
}

async function sendMessage(content) {
  const cleanContent = content.trim();
  if (!cleanContent || state.sending || state.finalized) return;
  setSending(true);
  createMessage("user", cleanContent);
  elements.messageInput.value = "";
  resizeComposer();
  let typingMessage;
  try {
    if (!state.conversationId) await createConversation();
    typingMessage = createTypingMessage();
    const response = await apiRequest(`/v1/conversations/${state.conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content: cleanContent }),
    });
    typingMessage.remove();
    createMessage("assistant", response.content, response.recalled_memories || []);
  } catch (error) {
    typingMessage?.remove();
    appendSystemMessage(`Message failed: ${error.message}`);
    showToast(error.message, "error");
  } finally {
    setSending(false);
    if (!state.finalized) elements.messageInput.focus();
  }
}

async function finalizeConversation() {
  if (!state.conversationId || state.sending || state.finalized) return;
  setSending(true);
  elements.finalize.textContent = "Summarizing…";
  try {
    const response = await apiRequest(`/v1/conversations/${state.conversationId}/finalize`, {
      method: "POST",
    });
    state.finalized = true;
    const learned = Object.values(response.memory_actions || {}).reduce(
      (total, value) => total + Number(value || 0),
      0,
    );
    appendSystemMessage(
      `Conversation finalized. Summary: ${response.summary.synopsis} (${learned} memory operations)`,
    );
    elements.messageInput.placeholder = "Start a new conversation to continue";
    showToast("Summary stored and long-term memory updated.");
    await loadMemories();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    elements.finalize.textContent = state.finalized ? "Memory updated" : "Finalize & learn";
    setSending(false);
  }
}

function renderMemoryState(title, message, className = "memory-empty") {
  elements.memoryList.replaceChildren();
  const empty = document.createElement("div");
  empty.className = className;
  const icon = document.createElement("span");
  icon.className = "memory-empty-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = className === "memory-error" ? "!" : "◇";
  const heading = document.createElement("strong");
  heading.textContent = title;
  const detail = document.createElement("p");
  detail.textContent = message;
  empty.append(icon, heading, detail);
  elements.memoryList.append(empty);
}

function renderMemories(memories) {
  elements.memoryList.replaceChildren();
  elements.memoryCount.textContent = String(memories.length);
  if (!memories.length) {
    renderMemoryState("No memories yet", "Finalize a conversation to create durable memories.");
    return;
  }
  memories.forEach((memory) => {
    const card = document.createElement("article");
    card.className = "memory-card";
    const content = document.createElement("p");
    content.textContent = memory.content;
    const time = document.createElement("time");
    const timestamp = memory.updated_at || memory.created_at;
    time.textContent = timestamp ? new Date(timestamp).toLocaleString() : "Stored by Mem0";
    const remove = document.createElement("button");
    remove.className = "delete-memory";
    remove.type = "button";
    remove.title = "Delete this memory";
    remove.setAttribute("aria-label", `Delete memory: ${memory.content}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => deleteMemory(memory));
    card.append(content, time, remove);
    elements.memoryList.append(card);
  });
}

async function loadMemories() {
  let userId;
  try {
    userId = currentUserId();
  } catch (error) {
    renderMemoryState("Identity required", error.message, "memory-error");
    return;
  }
  elements.refreshMemories.classList.add("refreshing");
  renderMemoryState("Reading memory", "Searching the local Mem0 store…", "memory-loading");
  try {
    const memories = await apiRequest(`/v1/users/${encodeURIComponent(userId)}/memories`);
    renderMemories(memories);
  } catch (error) {
    elements.memoryCount.textContent = "–";
    renderMemoryState("Memory unavailable", error.message, "memory-error");
  } finally {
    elements.refreshMemories.classList.remove("refreshing");
  }
}

async function deleteMemory(memory) {
  const confirmed = window.confirm(`Delete this memory?\n\n${memory.content}`);
  if (!confirmed) return;
  try {
    await apiRequest(
      `/v1/users/${encodeURIComponent(currentUserId())}/memories/${encodeURIComponent(memory.id)}`,
      { method: "DELETE" },
    );
    showToast("Memory deleted.");
    await loadMemories();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function resizeComposer() {
  elements.messageInput.style.height = "auto";
  elements.messageInput.style.height = `${Math.min(elements.messageInput.scrollHeight, 150)}px`;
}

function openSidebar() {
  elements.sidebar.classList.add("open");
  elements.sidebarScrim.classList.add("visible");
  elements.sidebarScrim.setAttribute("aria-hidden", "false");
}

function closeSidebar() {
  elements.sidebar.classList.remove("open");
  elements.sidebarScrim.classList.remove("visible");
  elements.sidebarScrim.setAttribute("aria-hidden", "true");
}

elements.chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(elements.messageInput.value);
});
elements.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.chatForm.requestSubmit();
  }
});
elements.messageInput.addEventListener("input", resizeComposer);
elements.finalize.addEventListener("click", finalizeConversation);
elements.refreshMemories.addEventListener("click", loadMemories);
elements.openSidebar.addEventListener("click", openSidebar);
elements.closeSidebar.addEventListener("click", closeSidebar);
elements.sidebarScrim.addEventListener("click", closeSidebar);
elements.newConversation.addEventListener("click", () => {
  resetConversation();
  closeSidebar();
  showToast("Ready for a new conversation.");
});
elements.userId.addEventListener("change", async () => {
  try {
    const userId = currentUserId();
    if (userId !== state.userId) {
      state.userId = userId;
      localStorage.setItem("recall-user-id", userId);
      resetConversation();
      await loadMemories();
      showToast(`Switched memory identity to ${userId}.`);
    }
  } catch (error) {
    showToast(error.message, "error");
  }
});
document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    elements.messageInput.value = button.dataset.prompt;
    resizeComposer();
    elements.messageInput.focus();
  });
});
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "n") {
    event.preventDefault();
    resetConversation();
  }
  if (event.key === "Escape") closeSidebar();
});

checkHealth();
loadMemories();
elements.messageInput.focus();
