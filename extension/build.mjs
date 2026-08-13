import * as esbuild from "esbuild";
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const dist = join(root, "dist");
const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));

// Keep in sync with distribution.py
const EXTENSION_PUBLIC_KEY_B64 =
  "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAr7KUU3FDDEtfi3HuU/2jqSjlp3tfl0L+" +
  "y1OIBCG19NuAZ/WCpIZKc4JZSn9Bgd2YGmPRD046Quzz8rCN5yMNmuQisBEl3FXDRGj8Wk/HPDVI" +
  "OtMlhw5Z96YDtqFGn0U5Ma5atzXduv6EAH8g3R54JvMwNd6a9/aBXmkhQD4qLZ/0C414134iAi/" +
  "zevMAJpcXQnqFn5vc3L0Rr1HzZAWG+UN9ajzKaHejknaSy8zuhqJ7zVB/vG8PH/LTeyxVj2JBfa" +
  "4AJuKyVUVxDv+kln/6FNHZDNfPB1pucw1Ii1pB2GPM1iUfMTTzcM2qAixNADlt4Sxa03q91ICsj" +
  "WrPPXwBsQIDAQAB";
const ONBOARDING_URL = "https://zhuji423.github.io/clipboard-translator/onboarding/";

rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });

await esbuild.build({
  entryPoints: {
    background: join(root, "src/background.ts"),
    content: join(root, "src/content.ts"),
    web_content: join(root, "src/web_content.ts"),
    popup: join(root, "src/popup.ts"),
  },
  outdir: dist,
  bundle: true,
  format: "iife",
  target: ["chrome114"],
  sourcemap: true,
  logLevel: "info",
  define: {
    __ONBOARDING_URL__: JSON.stringify(ONBOARDING_URL),
  },
});

const manifest = {
  manifest_version: 3,
  name: "Clipboard Translator Subtitles",
  version: pkg.version,
  description:
    "Look up English words on web pages and YouTube subtitles via the local Clipboard Translator desktop app.",
  // Pins extension ID for unpacked / pre-store builds (must match distribution.py).
  key: EXTENSION_PUBLIC_KEY_B64,
  action: {
    default_title: "Clipboard Translator",
    default_popup: "popup.html",
  },
  background: {
    service_worker: "background.js",
  },
  permissions: ["storage", "nativeMessaging"],
  host_permissions: ["http://127.0.0.1/*", "http://*/*", "https://*/*"],
  externally_connectable: {
    matches: ["https://zhuji423.github.io/*"],
  },
  content_scripts: [
    {
      matches: ["https://www.youtube.com/*", "https://youtube.com/*"],
      js: ["content.js"],
      css: ["content.css"],
      run_at: "document_idle",
    },
    {
      matches: ["http://*/*", "https://*/*"],
      exclude_matches: ["https://www.youtube.com/*", "https://youtube.com/*"],
      js: ["web_content.js"],
      run_at: "document_idle",
    },
  ],
  icons: {
    16: "icons/icon16.png",
    48: "icons/icon48.png",
    128: "icons/icon128.png",
  },
};

writeFileSync(
  join(dist, "manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  "utf8",
);
cpSync(join(root, "src/popup.html"), join(dist, "popup.html"));
cpSync(join(root, "src/content.css"), join(dist, "content.css"));
mkdirSync(join(dist, "icons"), { recursive: true });
cpSync(join(root, "icons"), join(dist, "icons"), { recursive: true });

console.log("Built extension -> extension/dist");
