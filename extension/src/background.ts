import {
  BridgeSettings,
  ExtensionMessage,
  HealthResponse,
  LookupResponse,
  PairResponse,
  STORAGE_KEYS,
  bridgeBase,
  loadSettings,
} from "./shared";

chrome.runtime.onMessage.addListener((message: ExtensionMessage, _sender, sendResponse) => {
  void handleMessage(message).then(sendResponse);
  return true;
});

async function handleMessage(message: ExtensionMessage): Promise<ExtensionMessage> {
  if (message.type === "HEALTH") {
    return health();
  }
  if (message.type === "PAIR") {
    return pair(message.code, message.port);
  }
  if (message.type === "LOOKUP") {
    return lookup(message.word, message.context, message.requestId);
  }
  return { type: "HEALTH_RESULT", ok: false, paired: false, online: false, error: "unknown message" };
}

async function health(): Promise<HealthResponse> {
  const settings = await loadSettings();
  try {
    const resp = await fetch(`${bridgeBase(settings.port)}/health`, {
      method: "GET",
      signal: AbortSignal.timeout(2000),
    });
    if (!resp.ok) {
      return {
        type: "HEALTH_RESULT",
        ok: false,
        paired: Boolean(settings.token),
        online: false,
        error: `桌面端返回 HTTP ${resp.status}`,
        port: settings.port,
      };
    }
    const data = (await resp.json()) as { ok?: boolean; paired?: boolean; enabled?: boolean };
    return {
      type: "HEALTH_RESULT",
      ok: Boolean(data.ok),
      paired: Boolean(settings.token) && Boolean(data.paired),
      online: true,
      port: settings.port,
    };
  } catch {
    return {
      type: "HEALTH_RESULT",
      ok: false,
      paired: Boolean(settings.token),
      online: false,
      error: "无法连接桌面端：请启动 Clipboard Translator 并启用浏览器集成",
      port: settings.port,
    };
  }
}

async function pair(code: string, port?: number): Promise<PairResponse> {
  const settings = await loadSettings();
  const usePort = port && port > 0 ? port : settings.port;
  try {
    const resp = await fetch(`${bridgeBase(usePort)}/v1/pair`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: code.trim() }),
      signal: AbortSignal.timeout(5000),
    });
    const data = (await resp.json()) as { ok?: boolean; token?: string; error?: string; port?: number };
    if (!resp.ok || !data.ok || !data.token) {
      return {
        type: "PAIR_RESULT",
        ok: false,
        error: data.error || `配对失败（HTTP ${resp.status}）`,
      };
    }
    await chrome.storage.local.set({
      [STORAGE_KEYS.token]: data.token,
      [STORAGE_KEYS.port]: data.port || usePort,
    });
    return { type: "PAIR_RESULT", ok: true, port: data.port || usePort };
  } catch {
    return {
      type: "PAIR_RESULT",
      ok: false,
      error: "无法连接桌面端：请确认已启动并点击「开始配对」",
    };
  }
}

async function lookup(
  word: string,
  context: string,
  requestId: string,
): Promise<LookupResponse> {
  const settings = await loadSettings();
  if (!settings.enabled) {
    return {
      type: "LOOKUP_RESULT",
      requestId,
      ok: false,
      error: "扩展已暂停（可在弹窗中重新启用）",
    };
  }
  if (!settings.token) {
    return {
      type: "LOOKUP_RESULT",
      requestId,
      ok: false,
      error: "尚未配对桌面端",
    };
  }
  try {
    const resp = await fetch(`${bridgeBase(settings.port)}/v1/lookup`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${settings.token}`,
      },
      body: JSON.stringify({
        word,
        context,
        target_lang: settings.targetLang,
      }),
      signal: AbortSignal.timeout(45000),
    });
    const data = (await resp.json()) as Record<string, unknown>;
    if (!resp.ok || !data.ok) {
      return {
        type: "LOOKUP_RESULT",
        requestId,
        ok: false,
        error: String(data.error || `查词失败（HTTP ${resp.status}）`),
      };
    }
    return {
      type: "LOOKUP_RESULT",
      requestId,
      ok: true,
      word: String(data.word || word),
      lemma: String(data.lemma || ""),
      pos: String(data.pos || ""),
      gloss: String(data.gloss || ""),
      meaning_in_context: String(data.meaning_in_context || ""),
    };
  } catch {
    return {
      type: "LOOKUP_RESULT",
      requestId,
      ok: false,
      error: "桌面端离线或请求超时",
    };
  }
}

// Keep typed unused import for future settings sync helpers.
void (0 as unknown as BridgeSettings);
