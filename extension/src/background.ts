import {
  AutoPairResponse,
  BridgeSettings,
  DEFAULT_PORT,
  ExtensionMessage,
  HealthResponse,
  LookupResponse,
  NATIVE_HOST_NAME,
  PairResponse,
  STORAGE_KEYS,
  TranslateRequest,
  TranslateResponse,
  bridgeBase,
  loadSettings,
} from "./shared";

declare const __ONBOARDING_URL__: string;

chrome.runtime.onMessage.addListener((message: ExtensionMessage, _sender, sendResponse) => {
  void handleMessage(message).then(sendResponse);
  return true;
});

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install") {
    void openOnboardingIfStoreInstall();
  }
  void tryAutoPair();
});

/** Sideload / unpacked 不打开远程引导页（GitHub Pages 未部署时会 404）。 */
async function openOnboardingIfStoreInstall(): Promise<void> {
  try {
    const self = await chrome.management.getSelf();
    if (self.installType === "development") {
      return;
    }
  } catch {
    // getSelf 不可用时仍尝试打开（商店包）
  }
  const base =
    typeof __ONBOARDING_URL__ === "string" && __ONBOARDING_URL__
      ? __ONBOARDING_URL__
      : "https://zhuji423.github.io/clipboard-translator/onboarding/";
  const url = `${base}${base.includes("#") ? "" : "#installed"}`;
  void chrome.tabs.create({ url });
}

chrome.runtime.onStartup.addListener(() => {
  void tryAutoPair();
});

async function handleMessage(message: ExtensionMessage): Promise<ExtensionMessage> {
  if (message.type === "HEALTH") {
    return health();
  }
  if (message.type === "PAIR") {
    return pair(message.code, message.port);
  }
  if (message.type === "AUTO_PAIR") {
    return tryAutoPair();
  }
  if (message.type === "LOOKUP") {
    return lookup(message.word, message.context, message.requestId);
  }
  if (message.type === "TRANSLATE") {
    return translate(
      message.text,
      message.context,
      message.requestId,
      Boolean(message.inline),
    );
  }
  return { type: "HEALTH_RESULT", ok: false, paired: false, online: false, error: "unknown message" };
}

async function sendNativeCredentials(): Promise<{
  ok: boolean;
  port?: number;
  token?: string;
  error?: string;
}> {
  try {
    const resp = (await chrome.runtime.sendNativeMessage(NATIVE_HOST_NAME, {
      type: "get_bridge_credentials",
    })) as { ok?: boolean; port?: number; token?: string; error?: string };
    if (!resp?.ok || !resp.token) {
      return { ok: false, error: resp?.error || "Native Messaging 未返回令牌" };
    }
    return {
      ok: true,
      port: Number(resp.port) || undefined,
      token: String(resp.token),
    };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { ok: false, error: msg || "Native Messaging 不可用" };
  }
}

async function sendHttpAutoPair(port: number): Promise<{
  ok: boolean;
  port?: number;
  token?: string;
  error?: string;
}> {
  try {
    const resp = await fetch(`${bridgeBase(port)}/v1/auto_pair`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      signal: AbortSignal.timeout(3000),
    });
    const data = (await resp.json()) as {
      ok?: boolean;
      token?: string;
      port?: number;
      error?: string;
    };
    if (!resp.ok || !data?.ok || !data.token) {
      return { ok: false, error: data?.error || `自动配对失败（HTTP ${resp.status}）` };
    }
    return {
      ok: true,
      port: Number(data.port) || port,
      token: String(data.token),
    };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { ok: false, error: msg || "无法连接桌面端自动配对接口" };
  }
}

async function tryAutoPair(): Promise<AutoPairResponse> {
  const settings = await loadSettings();
  if (settings.token) {
    return {
      type: "AUTO_PAIR_RESULT",
      ok: true,
      port: settings.port,
      pairSource: settings.pairSource || "http",
    };
  }

  const http = await sendHttpAutoPair(settings.port || DEFAULT_PORT);
  if (http.ok && http.token) {
    const port = http.port && http.port > 0 ? http.port : settings.port;
    await chrome.storage.local.set({
      [STORAGE_KEYS.token]: http.token,
      [STORAGE_KEYS.port]: port,
      [STORAGE_KEYS.pairSource]: "http",
    });
    return { type: "AUTO_PAIR_RESULT", ok: true, port, pairSource: "http" };
  }

  const nm = await sendNativeCredentials();
  if (!nm.ok || !nm.token) {
    return {
      type: "AUTO_PAIR_RESULT",
      ok: false,
      error: http.error || nm.error || "自动配对失败，请使用短码配对",
    };
  }
  const port = nm.port && nm.port > 0 ? nm.port : settings.port;
  await chrome.storage.local.set({
    [STORAGE_KEYS.token]: nm.token,
    [STORAGE_KEYS.port]: port,
    [STORAGE_KEYS.pairSource]: "native",
  });
  return { type: "AUTO_PAIR_RESULT", ok: true, port, pairSource: "native" };
}

async function health(): Promise<HealthResponse> {
  let settings = await loadSettings();
  let nmAvailable = settings.pairSource === "native";
  if (!settings.token) {
    const auto = await tryAutoPair();
    if (auto.ok) {
      settings = await loadSettings();
      nmAvailable = true;
    } else {
      const err = auto.error || "";
      nmAvailable = Boolean(err) && !/native messaging host not found|forbidden/i.test(err);
    }
  }
  return probeHealth(settings, nmAvailable);
}

async function probeHealth(settings: BridgeSettings, nmAvailable: boolean): Promise<HealthResponse> {
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
        pairSource: settings.pairSource,
        nmAvailable,
      };
    }
    const data = (await resp.json()) as { ok?: boolean; paired?: boolean; enabled?: boolean };
    return {
      type: "HEALTH_RESULT",
      ok: Boolean(data.ok),
      paired: Boolean(settings.token) && Boolean(data.paired),
      online: true,
      port: settings.port,
      pairSource: settings.pairSource,
      nmAvailable,
    };
  } catch {
    return {
      type: "HEALTH_RESULT",
      ok: false,
      paired: Boolean(settings.token),
      online: false,
      error: "无法连接桌面端：请启动 Clipboard Translator 并启用浏览器集成",
      port: settings.port,
      pairSource: settings.pairSource,
      nmAvailable,
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
      [STORAGE_KEYS.pairSource]: "code",
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
    const auto = await tryAutoPair();
    if (!auto.ok) {
      return {
        type: "LOOKUP_RESULT",
        requestId,
        ok: false,
        error: "尚未配对桌面端",
      };
    }
  }
  const latest = await loadSettings();
  if (!latest.token) {
    return {
      type: "LOOKUP_RESULT",
      requestId,
      ok: false,
      error: "尚未配对桌面端",
    };
  }
  try {
    const resp = await fetch(`${bridgeBase(latest.port)}/v1/lookup`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${latest.token}`,
      },
      body: JSON.stringify({
        word,
        context,
        target_lang: latest.targetLang,
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

async function translate(
  text: string,
  context: TranslateRequest["context"],
  requestId: string,
  inline = false,
): Promise<TranslateResponse> {
  const settings = await loadSettings();
  if (!settings.enabled) {
    return {
      type: "TRANSLATE_RESULT",
      requestId,
      ok: false,
      error: "扩展已暂停（可在弹窗中重新启用）",
    };
  }
  if (!settings.token) {
    const auto = await tryAutoPair();
    if (!auto.ok) {
      return {
        type: "TRANSLATE_RESULT",
        requestId,
        ok: false,
        error: "尚未配对桌面端",
      };
    }
  }
  const latest = await loadSettings();
  if (!latest.token) {
    return {
      type: "TRANSLATE_RESULT",
      requestId,
      ok: false,
      error: "尚未配对桌面端",
    };
  }
  const timeoutMs = inline ? 60_000 : 10_000;
  try {
    const resp = await fetch(`${bridgeBase(latest.port)}/v1/translate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${latest.token}`,
      },
      body: JSON.stringify({ text, context, inline: inline || undefined }),
      signal: AbortSignal.timeout(timeoutMs),
    });
    const data = (await resp.json()) as {
      ok?: boolean;
      error?: string;
      context_session?: string;
      translation?: string;
    };
    if (!resp.ok || !data.ok) {
      return {
        type: "TRANSLATE_RESULT",
        requestId,
        ok: false,
        error: String(data.error || `翻译请求失败（HTTP ${resp.status}）`),
      };
    }
    if (inline) {
      const translation = String(data.translation || "").trim();
      if (!translation) {
        return {
          type: "TRANSLATE_RESULT",
          requestId,
          ok: false,
          error: "译文为空",
        };
      }
      return {
        type: "TRANSLATE_RESULT",
        requestId,
        ok: true,
        translation,
        contextSession: data.context_session,
      };
    }
    return {
      type: "TRANSLATE_RESULT",
      requestId,
      ok: true,
      contextSession: data.context_session,
    };
  } catch {
    return {
      type: "TRANSLATE_RESULT",
      requestId,
      ok: false,
      error: "桌面端离线或请求超时",
    };
  }
}

// Keep typed unused import for future settings sync helpers.
void (0 as unknown as BridgeSettings);
