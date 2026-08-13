import { DEFAULT_PORT, STORAGE_KEYS, loadSettings } from "./shared";
import type { AutoPairResponse, HealthResponse, PairResponse } from "./shared";

const statusEl = document.getElementById("status") as HTMLDivElement;
const enabledEl = document.getElementById("enabled") as HTMLInputElement;
const targetLangEl = document.getElementById("targetLang") as HTMLSelectElement;
const portEl = document.getElementById("port") as HTMLInputElement;
const codeEl = document.getElementById("code") as HTMLInputElement;
const pairBtn = document.getElementById("pairBtn") as HTMLButtonElement;
const autoPairBtn = document.getElementById("autoPairBtn") as HTMLButtonElement;
const refreshBtn = document.getElementById("refreshBtn") as HTMLButtonElement;
const hintEl = document.getElementById("hint") as HTMLParagraphElement;

async function init(): Promise<void> {
  const settings = await loadSettings();
  enabledEl.checked = settings.enabled;
  targetLangEl.value = settings.targetLang || "zh";
  portEl.value = String(settings.port || DEFAULT_PORT);
  await refreshStatus();
}

function setHint(mode: "offline" | "unpaired" | "auto" | "code" | "nm-missing"): void {
  if (mode === "offline") {
    hintEl.innerHTML =
      "请先启动 Clipboard Translator，并在设置中启用「本机桥接」。";
    return;
  }
  if (mode === "auto") {
    hintEl.innerHTML = "已自动连接桌面端。网页双击英文词，或打开 YouTube 字幕即可使用。";
    return;
  }
  if (mode === "code") {
    hintEl.innerHTML = "已通过短码配对连接。网页双击英文词，或打开 YouTube 字幕即可使用。";
    return;
  }
  if (mode === "nm-missing") {
    hintEl.innerHTML =
      "自动连接失败。请确认桌面端已启动并启用本机桥接，或在桌面端点「开始配对」后在此输入 6 位码。";
    return;
  }
  hintEl.innerHTML =
    "桌面在线但尚未配对：可点「自动连接」，或在桌面端「开始配对」后输入 6 位码。";
}

async function refreshStatus(): Promise<void> {
  statusEl.textContent = "检查桌面端…";
  statusEl.className = "status";
  const resp = (await chrome.runtime.sendMessage({ type: "HEALTH" })) as HealthResponse;
  if (!resp?.online) {
    statusEl.innerHTML = `<span class="bad">桌面端离线</span><br>${resp?.error || "请启动 Clipboard Translator"}`;
    setHint("offline");
    return;
  }
  if (resp.paired) {
    const via =
      resp.pairSource === "native" || resp.pairSource === "http"
        ? "自动连接"
        : resp.pairSource === "code"
          ? "短码配对"
          : "已连接";
    statusEl.innerHTML = `<span class="ok">${via}</span> · 端口 ${resp.port ?? portEl.value}`;
    setHint(resp.pairSource === "code" ? "code" : "auto");
    return;
  }
  statusEl.innerHTML = `<span class="bad">桌面在线，尚未配对</span> · 端口 ${resp.port ?? portEl.value}`;
  setHint(resp.nmAvailable === false ? "nm-missing" : "unpaired");
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

autoPairBtn.addEventListener("click", async () => {
  autoPairBtn.disabled = true;
  statusEl.textContent = "自动连接中…";
  try {
    // Clear token so AUTO_PAIR actually retries NM.
    await chrome.storage.local.remove([STORAGE_KEYS.token, STORAGE_KEYS.pairSource]);
    const resp = (await chrome.runtime.sendMessage({ type: "AUTO_PAIR" })) as AutoPairResponse;
    if (!resp?.ok) {
      statusEl.innerHTML = `<span class="bad">${resp?.error || "自动连接失败"}</span>`;
      setHint("nm-missing");
      return;
    }
    statusEl.innerHTML = `<span class="ok">已自动连接</span> · 端口 ${resp.port ?? portEl.value}`;
    setHint("auto");
  } finally {
    autoPairBtn.disabled = false;
  }
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
    statusEl.innerHTML = `<span class="ok">短码配对成功</span> · 端口 ${resp.port ?? port}`;
    setHint("code");
  } finally {
    pairBtn.disabled = false;
  }
});

void init();
