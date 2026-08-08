import { DEFAULT_PORT, STORAGE_KEYS, loadSettings } from "./shared";
import type { HealthResponse, PairResponse } from "./shared";

const statusEl = document.getElementById("status") as HTMLDivElement;
const enabledEl = document.getElementById("enabled") as HTMLInputElement;
const targetLangEl = document.getElementById("targetLang") as HTMLSelectElement;
const portEl = document.getElementById("port") as HTMLInputElement;
const codeEl = document.getElementById("code") as HTMLInputElement;
const pairBtn = document.getElementById("pairBtn") as HTMLButtonElement;
const refreshBtn = document.getElementById("refreshBtn") as HTMLButtonElement;

async function init(): Promise<void> {
  const settings = await loadSettings();
  enabledEl.checked = settings.enabled;
  targetLangEl.value = settings.targetLang || "zh";
  portEl.value = String(settings.port || DEFAULT_PORT);
  await refreshStatus();
}

async function refreshStatus(): Promise<void> {
  statusEl.textContent = "检查桌面端…";
  statusEl.className = "status";
  const resp = (await chrome.runtime.sendMessage({ type: "HEALTH" })) as HealthResponse;
  if (!resp?.online) {
    statusEl.innerHTML = `<span class="bad">桌面端离线</span><br>${resp?.error || "请启动 Clipboard Translator"}`;
    return;
  }
  if (resp.paired) {
    statusEl.innerHTML = `<span class="ok">已连接</span> · 端口 ${resp.port ?? portEl.value}`;
  } else {
    statusEl.innerHTML = `<span class="bad">桌面在线，尚未配对</span> · 端口 ${resp.port ?? portEl.value}`;
  }
}

enabledEl.addEventListener("change", () => {
  void chrome.storage.local.set({ [STORAGE_KEYS.enabled]: enabledEl.checked });
});

targetLangEl.addEventListener("change", () => {
  void chrome.storage.local.set({ [STORAGE_KEYS.targetLang]: targetLangEl.value });
});

portEl.addEventListener("change", () => {
  const port = Number(portEl.value) || DEFAULT_PORT;
  void chrome.storage.local.set({ [STORAGE_KEYS.port]: port });
});

refreshBtn.addEventListener("click", () => {
  void refreshStatus();
});

pairBtn.addEventListener("click", async () => {
  const code = codeEl.value.trim();
  if (!code) {
    statusEl.innerHTML = `<span class="bad">请输入配对码</span>`;
    return;
  }
  const port = Number(portEl.value) || DEFAULT_PORT;
  await chrome.storage.local.set({ [STORAGE_KEYS.port]: port });
  pairBtn.disabled = true;
  statusEl.textContent = "配对中…";
  try {
    const resp = (await chrome.runtime.sendMessage({
      type: "PAIR",
      code,
      port,
    })) as PairResponse;
    if (!resp?.ok) {
      statusEl.innerHTML = `<span class="bad">${resp?.error || "配对失败"}</span>`;
      return;
    }
    codeEl.value = "";
    statusEl.innerHTML = `<span class="ok">配对成功</span> · 端口 ${resp.port ?? port}`;
  } finally {
    pairBtn.disabled = false;
  }
});

void init();
