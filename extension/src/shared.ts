import type { SubtitleTranslationContext } from "./subtitle_context";

export const DEFAULT_PORT = 17890;
export const NATIVE_HOST_NAME = "com.clipboard_translator.bridge";
export const STORAGE_KEYS = {
  token: "bridgeToken",
  port: "bridgePort",
  enabled: "extensionEnabled",
  targetLang: "targetLang",
  pairSource: "pairSource",
} as const;

export type PairSource = "native" | "code" | "";

export type BridgeSettings = {
  token: string;
  port: number;
  enabled: boolean;
  targetLang: string;
  pairSource: PairSource;
};

export type LookupRequest = {
  type: "LOOKUP";
  word: string;
  context: string;
  requestId: string;
};

export type LookupResponse = {
  type: "LOOKUP_RESULT";
  requestId: string;
  ok: boolean;
  error?: string;
  word?: string;
  lemma?: string;
  pos?: string;
  gloss?: string;
  meaning_in_context?: string;
};

export type HealthRequest = { type: "HEALTH" };
export type HealthResponse = {
  type: "HEALTH_RESULT";
  ok: boolean;
  paired: boolean;
  online: boolean;
  error?: string;
  port?: number;
  pairSource?: PairSource;
  nmAvailable?: boolean;
};

export type AutoPairRequest = { type: "AUTO_PAIR" };
export type AutoPairResponse = {
  type: "AUTO_PAIR_RESULT";
  ok: boolean;
  error?: string;
  port?: number;
  pairSource?: PairSource;
};

export type PairRequest = { type: "PAIR"; code: string; port?: number };
export type PairResponse = {
  type: "PAIR_RESULT";
  ok: boolean;
  error?: string;
  port?: number;
};

export type TranslateRequest = {
  type: "TRANSLATE";
  text: string;
  context?: SubtitleTranslationContext;
  requestId: string;
};

export type TranslateResponse = {
  type: "TRANSLATE_RESULT";
  requestId: string;
  ok: boolean;
  error?: string;
  contextSession?: string;
};

export type ExtensionMessage =
  | LookupRequest
  | LookupResponse
  | HealthRequest
  | HealthResponse
  | PairRequest
  | PairResponse
  | AutoPairRequest
  | AutoPairResponse
  | TranslateRequest
  | TranslateResponse;

export async function loadSettings(): Promise<BridgeSettings> {
  const data = await chrome.storage.local.get([
    STORAGE_KEYS.token,
    STORAGE_KEYS.port,
    STORAGE_KEYS.enabled,
    STORAGE_KEYS.targetLang,
    STORAGE_KEYS.pairSource,
  ]);
  const pairSourceRaw = String(data[STORAGE_KEYS.pairSource] || "");
  const pairSource: PairSource =
    pairSourceRaw === "native" || pairSourceRaw === "code" ? pairSourceRaw : "";
  return {
    token: String(data[STORAGE_KEYS.token] || ""),
    port: Number(data[STORAGE_KEYS.port] || DEFAULT_PORT) || DEFAULT_PORT,
    enabled: data[STORAGE_KEYS.enabled] !== false,
    targetLang: String(data[STORAGE_KEYS.targetLang] || "zh"),
    pairSource,
  };
}

export function bridgeBase(port: number): string {
  return `http://127.0.0.1:${port}`;
}
