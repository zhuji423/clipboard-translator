import "./src/tokenize_node_test.mjs";
import * as esbuild from "esbuild";

async function runBundledTest(entryPoint) {
  const result = await esbuild.build({
    entryPoints: [entryPoint],
    absWorkingDir: import.meta.dirname,
    bundle: true,
    format: "esm",
    platform: "node",
    write: false,
  });
  const code = Buffer.from(result.outputFiles[0].text).toString("base64");
  await import(`data:text/javascript;base64,${code}`);
}

await runBundledTest("src/subtitle_context.test.ts");
await runBundledTest("src/word_selection.test.ts");
