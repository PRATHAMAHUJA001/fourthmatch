// Copies the scenario videos from samples/scenarios into public/demo so the
// frontend-only demo (MSW) can play real dock footage. public/demo is gitignored.
import { copyFileSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const src = join(root, "samples", "scenarios");
const dest = join(root, "frontend", "public", "demo");
if (!existsSync(src)) process.exit(0);
mkdirSync(dest, { recursive: true });
for (const f of readdirSync(src)) {
  if (f.endsWith(".mp4")) copyFileSync(join(src, f), join(dest, f));
}
console.log(`demo assets -> ${dest}`);
