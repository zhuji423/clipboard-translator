import * as esbuild from "esbuild";
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const dist = join(root, "dist");
const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));

rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });

await esbuild.build({
  entryPoints: {
    background: join(root, "src/background.ts"),
    content: join(root, "src/content.ts"),
    popup: join(root, "src/popup.ts"),
  },
  outdir: dist,
  bundle: true,
  format: "iife",
  target: ["chrome114"],
  sourcemap: true,
  logLevel: "info",
});

const manifest = {
  manifest_version: 3,
  name: "Clipboard Translator Subtitles",
  version: pkg.version,
  description:
    "Click YouTube subtitle words to look them up via the local Clipboard Translator desktop app.",
  action: {
    default_title: "Clipboard Translator",
    default_popup: "popup.html",
  },
  background: {
    service_worker: "background.js",
  },
  permissions: ["storage"],
  host_permissions: ["http://127.0.0.1/*", "https://www.youtube.com/*"],
  content_scripts: [
    {
      matches: ["https://www.youtube.com/*", "https://youtube.com/*"],
      js: ["content.js"],
      css: ["content.css"],
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
