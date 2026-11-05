import { compile } from "json-schema-to-typescript";
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, "..");

const candidates = [
  process.env.CONTRACTS_DIR,
  resolve(webRoot, "../../contracts"),
  resolve(webRoot, "../../../ContextCon-backend/contracts"),
].filter(Boolean);

const contractsDir = candidates.find((dir) => existsSync(join(dir, "schemas")));
if (!contractsDir) {
  console.error(`No contracts/schemas found. Looked in:\n${candidates.join("\n")}\nSet CONTRACTS_DIR.`);
  process.exit(1);
}

const schemaDir = join(contractsDir, "schemas");
const defs = {};
for (const file of readdirSync(schemaDir).filter((f) => f.endsWith(".json")).sort()) {
  const schema = JSON.parse(readFileSync(join(schemaDir, file), "utf8"));
  const { $defs = {}, ...root } = schema;
  for (const [name, def] of Object.entries($defs)) defs[name] ??= def;
  defs[root.title ?? file.replace(/\.json$/, "")] = root;
}

const merged = {
  title: "OutcomeContracts",
  type: "object",
  additionalProperties: false,
  properties: {},
  $defs: defs,
};

const ts = await compile(merged, "OutcomeContracts", {
  bannerComment: `/* Generated from ${schemaDir.replace(resolve(webRoot, "../../.."), "…")} by scripts/gen-contracts.mjs. Do not edit; run \`pnpm contracts:gen\`. */`,
  unreachableDefinitions: true,
  additionalProperties: false,
  strictIndexSignatures: true,
  format: true,
});

const outDir = join(webRoot, "src/lib/contracts");
mkdirSync(outDir, { recursive: true });
writeFileSync(join(outDir, "generated.ts"), ts.replace(/export interface OutcomeContracts \{\}\n?/, ""));

const fixtureSrc = join(contractsDir, "fixtures");
const fixtureOut = join(webRoot, "src/lib/fixtures/d1");
if (existsSync(fixtureSrc)) {
  mkdirSync(fixtureOut, { recursive: true });
  for (const file of readdirSync(fixtureSrc).filter((f) => f.endsWith(".json"))) {
    copyFileSync(join(fixtureSrc, file), join(fixtureOut, file));
  }
}

console.log(`contracts: ${Object.keys(defs).length} types from ${schemaDir}`);
