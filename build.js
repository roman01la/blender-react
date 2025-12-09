#!/usr/bin/env node
import * as esbuild from "esbuild";
import { mkdirSync } from "fs";
import { dirname } from "path";

// Example: node build.js src/index.jsx bundle.js development

const entryPoint = process.argv[2];
const outfile = process.argv[3];
const nodeEnv = process.argv[4] || "production";

// Ensure output directory exists
mkdirSync(dirname(outfile), { recursive: true });

await esbuild.build({
  entryPoints: [entryPoint],
  bundle: true,
  outfile: outfile,
  platform: "neutral",
  format: "iife",
  target: "es2020",
  minify: nodeEnv === "production",
  sourcemap: false,
  jsx: "automatic",
  // Define NODE_ENV for dead code elimination
  define: {
    "process.env.NODE_ENV": JSON.stringify(nodeEnv),
  },
});

console.log(`Built ${outfile} (${nodeEnv})`);
