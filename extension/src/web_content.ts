import { SubtitleOverlay } from "./overlay";
import type { LookupResponse } from "./shared";
import {
  contextForSelection,
  extractCurrentSentence,
  isEditableTarget,
  normalizeLookupWord,
} from "./web_lookup";

const overlay = new SubtitleOverlay();
let requestSeq = 0;
let activeRequestId = "";

overlay.onCloseTip = () => {
  activeRequestId = "";
};

document.addEventListener("dblclick", (event) => {
  if (event.button !== 0 || isEditableTarget(event.target)) return;
  const selection = window.getSelection();
  const word = normalizeLookupWord(selection?.toString() || "");
  if (!selection || !word || selection.rangeCount === 0) return;

  const range = selection.getRangeAt(0);
  const anchor = range.getBoundingClientRect();
  if (!anchor.width && !anchor.height) return;
  const selectionContext = contextForSelection(selection, event.target);
  const context = extractCurrentSentence(
    selectionContext.text,
    word,
    selectionContext.offset,
  );

  requestSeq += 1;
  const requestId = `web-${requestSeq}`;
  activeRequestId = requestId;
  overlay.showLoading(anchor, word);
  chrome.runtime.sendMessage(
    { type: "LOOKUP", word, context, requestId, source: "web" },
    (response: LookupResponse | undefined) => {
      if (activeRequestId !== requestId) return;
      if (chrome.runtime.lastError) {
        overlay.showError(anchor, word, chrome.runtime.lastError.message || "扩展通信失败");
        return;
      }
      if (!response?.ok) {
        overlay.showError(anchor, word, response?.error || "查词失败");
        return;
      }
      overlay.showResult(anchor, word, response);
    },
  );
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  activeRequestId = "";
  overlay.hideTip();
});

document.addEventListener("pointerdown", (event) => {
  if (!overlay.isTipVisible()) return;
  const path = event.composedPath();
  if (path.some((item) => item instanceof HTMLElement && item.id === "ct-subtitle-host")) {
    return;
  }
  activeRequestId = "";
  overlay.hideTip();
}, true);
