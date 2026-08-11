import "./src/tokenize_node_test.mjs";
import * as esbuild from "esbuild";

const result = await esbuild.build({
  entryPoints: ["src/subtitle_context.test.ts"],
  absWorkingDir: import.meta.dirname,
  bundle: true,
  format: "esm",
  platform: "node",
  write: false,
});
const code = Buffer.from(result.outputFiles[0].text).toString("base64");
await import(`data:text/javascript;base64,${code}`);
