import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webDir = path.resolve(__dirname, "..");
const outDir = path.join(webDir, "out");

// Possible targets depending on environment (Windows UNC or Linux WSL)
const targets = [
  "\\\\wsl.localhost\\Ubuntu\\home\\samue\\mybench\\apps\\aios_v1\\aios_v1\\public\\frontend",
  "\\\\wsl$\\Ubuntu\\home\\samue\\mybench\\apps\\aios_v1\\aios_v1\\public\\frontend",
  path.join(process.env.HOME || "", "mybench/apps/aios_v1/aios_v1/public/frontend")
];

const siteAssetTargets = [
  "\\\\wsl.localhost\\Ubuntu\\home\\samue\\mybench\\sites\\assets\\aios_v1\\frontend",
  "\\\\wsl$\\Ubuntu\\home\\samue\\mybench\\sites\\assets\\aios_v1\\frontend",
  path.join(process.env.HOME || "", "mybench/sites/assets/aios_v1/frontend")
];

console.log("🚀 Building Next.js for Frappe static export...");
execSync("npx next build", { cwd: webDir, stdio: "inherit" });

if (fs.existsSync(outDir)) {
  console.log("📦 Syncing build assets to Frappe via WSL and Windows repo...");
  try {
    // Copy to Windows repo target
    const winPublicFrontend = path.resolve(__dirname, "../../../../apps/aios_v1/aios_v1/public/frontend");
    if (fs.existsSync(winPublicFrontend)) {
      fs.cpSync(outDir, winPublicFrontend, { recursive: true });
    }

    const wslSyncCmd = [
      "mkdir -p ~/mybench-v16/apps/aios_v1/aios_v1/public/frontend",
      "cp -rf /mnt/g/AI-Agents/Eksperiment-AIOS-by-GLM/aios/apps/web/out/* ~/mybench-v16/apps/aios_v1/aios_v1/public/frontend/",
      "if [ -d ~/mybench/apps/aios_v1 ]; then mkdir -p ~/mybench/apps/aios_v1/aios_v1/public/frontend && cp -rf /mnt/g/AI-Agents/Eksperiment-AIOS-by-GLM/aios/apps/web/out/* ~/mybench/apps/aios_v1/aios_v1/public/frontend/; fi",
      "cd ~/mybench-v16 && ~/.local/bin/bench --site all clear-cache 2>/dev/null || true"
    ].join(" && ");

    execSync(`wsl -d Ubuntu -- bash -c "${wslSyncCmd}"`, { stdio: "inherit" });
    console.log("✨ Done! Next.js frontend is now updated in Frappe (mybench-v16).");
  } catch (err) {
    console.error("Failed to sync via WSL:", err);
  }
} else {
  console.log(`⚠️ Build output ${outDir} not found.`);
}
