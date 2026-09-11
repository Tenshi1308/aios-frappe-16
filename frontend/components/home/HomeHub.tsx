"use client";

import { useEffect, useRef, useState } from "react";
import { BRANCHES, type Branch, accentOf, rgbaOf, getWorkerSkills, getSkillTools } from "@/lib/branches";
import ChatDock from "@/components/chat/ChatDock";
import type { WorkerInfo } from "@/lib/types";

import ParticleBg from "./ParticleBg";
import NeuralBall from "./NeuralBall";
import QuickInsightsPanel from "./QuickInsightsPanel";
import LeadModal from "@/components/lead/LeadModal";
// Chatbot dibekukan (frozen) atas instruksi user
// import ChatbotMonitoringWidget from "@/components/chatbot/ChatbotMonitoringWidget";
import { getSortedLeads } from "@/lib/mock-leads";
import { ChevronLeft, ChevronRight, Plus, Minus, Home, UserSearch } from "lucide-react";

// Port dari mockup-v2/home.html — AI network hub (Google-Maps-style zoom + chat dock)

// Monogram singkatan per bidang (visual)
const MONOGRAMS: Record<string, string> = {
  planning: "SOP",
  finance: "FIN",
  hr: "HR",
  logistics: "LOG",
  maintenance: "MNT",
  sales: "SAL",
  quality: "QLT",
  material: "MAT",
  manufacturing: "MFG",
};

// Aksen warna per AI Manager mengikuti warna identitas bidangnya
// (BRANCH_GLOW di lib/branches.ts — satu sumber untuk seluruh app).

// Generator acak deterministik (topologi jaringan stabil saat resize)
function mulberry32(seed: number) {
  let t = seed >>> 0;
  return function () {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}
const SEED = 20260813;
const SVG_NS = "http://www.w3.org/2000/svg";
const NODE_CORE = 34;

interface Pos {
  x: number;
  y: number;
  angle: number;
  a: number;
  outX: number;
  outY: number;
  tx: number;
  ty: number;
  R: number;
  accent: string;
}
interface Geo {
  W: number;
  H: number;
  POS: Pos[];
  WORKER_R: number;
}

export default function HomeHub({ workersByBranch }: { workersByBranch: Record<string, WorkerInfo[]> }) {
  const stageRef = useRef<HTMLDivElement>(null);
  const worldRef = useRef<HTMLDivElement>(null);
  const nodesRef = useRef<HTMLDivElement>(null);
  const linesRef = useRef<SVGSVGElement>(null);
  const workersByBranchRef = useRef(workersByBranch);
  
  useEffect(() => {
    workersByBranchRef.current = workersByBranch;
  }, [workersByBranch]);


  // zoomedIndex dipakai utk render ChatDock & callback stabil
  const [zoomedIndex, setZoomedIndex] = useState(-1);
  const [isClosingDock, setIsClosingDock] = useState(false);
  const [isLeadModalOpen, setIsLeadModalOpen] = useState(false);
  const zoomedRef = useRef(-1);
  const pendingWorkerRef = useRef<string>("manager");
  const setZ = (i: number) => {
    zoomedRef.current = i;
    setZoomedIndex(i);
  };

  useEffect(() => {
    const onOpenLead = () => setIsLeadModalOpen(true);
    window.addEventListener("aios:open-lead-modal", onOpenLead);
    return () => window.removeEventListener("aios:open-lead-modal", onOpenLead);
  }, []);

  // Sub-tahap 1c: Auto-show pop-up Lead AI Generator saat pertama kali masuk ke Home Hub
  useEffect(() => {
    if (typeof window === "undefined") return;

    const leads = getSortedLeads();
    if (leads.length === 0) return;

    const hasShown = sessionStorage.getItem("aios:lead_auto_shown");
    if (!hasShown) {
      const timer = setTimeout(() => {
        setIsLeadModalOpen(true);
        sessionStorage.setItem("aios:lead_auto_shown", "true");
      }, 700); // Jeda 700ms agar scene neural ball & 3D network siap
      return () => clearTimeout(timer);
    }
  }, []);

  useEffect(() => {
    const handleNodePointerUp = (e: PointerEvent) => {
      const target = e.target as HTMLElement;
      if (!target) return;

      // 1. Klik pada Sub-Agent dot (di sekeliling node)
      const wd = target.closest(".worker-dot") as HTMLElement;
      if (wd) {
        const wKey = wd.dataset.wkey;
        const bIdx = wd.dataset.bidx ? parseInt(wd.dataset.bidx) : -1;
        if (wKey && bIdx >= 0 && zoomedRef.current === bIdx) {
          e.preventDefault();
          e.stopPropagation();
          pendingWorkerRef.current = wKey;
          window.dispatchEvent(new CustomEvent("aios:select-worker", { detail: wKey }));
        }
        return;
      }

      // Jangan proses jika klik berasal dari dalam Chatdock, modal lead, UI zoom kontrol, atau widget chatbot
      if (target.closest(".chat-dock, .zoom-ui, .dock-head, .dock-worker, .quick-insights-panel, .lead-modal-backdrop, .lead-modal-dialog, .chatbot-monitoring-popup, .chatbot-widget-btn")) return;

      // 2. Klik pada Node AI Manager Pusat (Lingkaran FIN, HR, dll)
      if (zoomedRef.current >= 0 && stageRef.current) {
        const stage = stageRef.current;
        const selectedNode = stage.querySelectorAll(".branch-node")[zoomedRef.current] as HTMLElement;
        const socket = (selectedNode?.querySelector(".b-socket") || selectedNode) as HTMLElement;

        let dist = 9999;
        if (socket) {
          const socketRect = socket.getBoundingClientRect();
          const cx = socketRect.left + socketRect.width / 2;
          const cy = socketRect.top + socketRect.height / 2;
          dist = Math.hypot(e.clientX - cx, e.clientY - cy);
        }

        // Hitbox luas & nyaman (radius 180px dari pusat lingkaran FIN) atau klik pada elemen socket
        const isDomCenter = target.closest(".manager-hit, .branch-hit, .b-socket, .b-ring, .b-aura, .b-code, .branch-node");
        if (dist < 180 || isDomCenter) {
          e.preventDefault();
          e.stopPropagation();
          pendingWorkerRef.current = "manager";
          window.dispatchEvent(new CustomEvent("aios:select-worker", { detail: "manager" }));

          if (socket) {
            socket.style.transform = "translate(-50%, -50%) scale(1.25)";
            socket.style.borderColor = "#38bdf8";
            socket.style.boxShadow = "0 0 35px rgba(56, 189, 248, 0.95)";
            setTimeout(() => {
              socket.style.transform = "";
              socket.style.borderColor = "";
              socket.style.boxShadow = "";
            }, 350);
          }
        }
      }
    };
    document.addEventListener("pointerup", handleNodePointerUp, true);
    return () => document.removeEventListener("pointerup", handleNodePointerUp, true);
  }, []);

  // view transform dunia + geometry terakhir
  const view = useRef({ s: 1, tx: 0, ty: 0 });
  const lastGeo = useRef<Geo | null>(null);
  const lineEls = useRef<SVGPathElement[]>([]);
  const pulseEls = useRef<SVGCircleElement[]>([]);
  const dockWidth = useRef(400);

  const activeBranch: Branch | undefined =
    zoomedIndex >= 0 ? BRANCHES[zoomedIndex] : undefined;

  function applyTransform() {
    if (!worldRef.current) return;
    const v = view.current;
    worldRef.current.style.transform = `translate(${v.tx}px, ${v.ty}px) scale(${v.s})`;
  }

  function targetScreenPos(W: number, H: number) {
    return { x: (W - dockWidth.current) / 2, y: H / 2 };
  }

  function useZoomClasses(on: boolean) {
    const stage = stageRef.current;
    const nodes = nodesRef.current;
    if (!stage || !nodes) return;
    if (on) {
      stage.classList.add("zoomed");
      nodes.querySelectorAll(".branch-node").forEach((n) => n.classList.remove("selected"));
      nodes.querySelectorAll(".branch-name").forEach((n) => n.classList.remove("selected"));
      const ns = nodes.querySelectorAll(".branch-node");
      if (ns[zoomedRef.current]) ns[zoomedRef.current].classList.add("selected");
      const chips = nodes.querySelectorAll(".branch-name");
      if (chips[zoomedRef.current]) chips[zoomedRef.current].classList.add("selected");
    }
  }

  function zoomTo(i: number) {
    if (isClosingDock) return;
    const geo = lastGeo.current;
    const stage = stageRef.current;
    if (!geo || !stage) return;
    pendingWorkerRef.current = "manager";
    const { W, H, POS } = geo;
    dockWidth.current = Math.min(580, Math.max(280, W * 0.38));
    const p = POS[i];
    const base = Math.max(1.15, Math.min(1.48, Math.min(W * 0.24, H * 0.32) / 180));
    view.current.s = base;
    const c = targetScreenPos(W, H);
    view.current.tx = c.x - p.x * view.current.s;
    view.current.ty = c.y - p.y * view.current.s;
    setIsClosingDock(false);
    setZ(i);
    applyTransform();
    useZoomClasses(true);
    stage.classList.remove("dock-closing");
    stage.classList.add("dock-open");
  }

  function zoomReset() {
    if (isClosingDock) return;
    const stage = stageRef.current;
    if (!stage) return;

    setIsClosingDock(true);
    stage.classList.remove("zoomed", "dock-open");
    stage.classList.add("dock-closing");

    // Sinkronisasi: Mulai zoom out panggung seketika di t = 0ms bersamaan dengan 4 komponen UI
    stage.querySelectorAll(".branch-node.selected").forEach((n) => n.classList.remove("selected"));
    stage.querySelectorAll(".branch-name.selected").forEach((n) => n.classList.remove("selected"));
    view.current = { s: 1, tx: 0, ty: 0 };
    applyTransform();

    setTimeout(() => {
      pendingWorkerRef.current = "manager";
      setZ(-1);
      setIsClosingDock(false);
      stage.classList.remove("dock-closing");
    }, 300);
  }

  function zoomByFactor(f: number) {
    const stage = stageRef.current;
    const geo = lastGeo.current;
    if (!stage || !geo) return;
    const c = { x: stage.clientWidth / 2, y: stage.clientHeight / 2 };
    view.current.s = Math.min(6, Math.max(0.85, view.current.s * f));
    view.current.tx = c.x - (c.x - view.current.tx) * f;
    view.current.ty = c.y - (c.y - view.current.ty) * f;
    clampView();
    applyTransform();
  }

  function clampView() {
    const geo = lastGeo.current;
    if (zoomedRef.current < 0 || !geo) return;
    const { W, H, POS } = geo;
    const p = POS[zoomedRef.current];
    const m = 60;
    const minTx = m - p.x * view.current.s;
    const maxTx = W - m - p.x * view.current.s;
    const minTy = m - p.y * view.current.s;
    const maxTy = H - m - p.y * view.current.s;
    view.current.tx = Math.max(minTx, Math.min(maxTx, view.current.tx));
    view.current.ty = Math.max(minTy, Math.min(maxTy, view.current.ty));
  }

  // ---------- Particles dipindah ke ParticleBg.tsx ----------
  // ---------- Render jaringan ----------
  function render() {
    const stage = stageRef.current;
    const world = worldRef.current;
    const nodes = nodesRef.current;
    const lines = linesRef.current;
    if (!stage || !world || !nodes || !lines) return;

    nodes.innerHTML = "";
    const W = stage.clientWidth;
    const H = stage.clientHeight;
    const hubX = W / 2;
    const hubY = H / 2;
    const rng = mulberry32(SEED);

    const WORKER_R = Math.min(74, Math.min(W, H) * 0.115);
    const isCompact = W < 700;

    const rx = Math.max(130, (W / 2 - (WORKER_R + 50)) * (isCompact ? 0.65 : 0.82));
    const ry = Math.max(105, (H / 2 - (WORKER_R + 60)) * (isCompact ? 0.72 : 0.82));

    const RF = [0.92, 1.0, 0.86, 0.97, 1.0, 0.88, 0.98, 0.9, 1.02];

    const POS: Pos[] = [];
    BRANCHES.forEach((b, i) => {
      const angleDeg = -90 + i * 40;
      const a = (angleDeg * Math.PI) / 180;
      const eR = (rx * ry) / Math.sqrt(Math.pow(ry * Math.cos(a), 2) + Math.pow(rx * Math.sin(a), 2));
      const R = Math.min(eR, W / 2 - NODE_CORE - 12) * RF[i];
      const x = hubX + R * Math.cos(a);
      const y = hubY + R * Math.sin(a);
      const outX = Math.cos(a);
      const outY = Math.sin(a);
      const tx = -Math.sin(a);
      const ty = Math.cos(a);
      POS.push({ x, y, angle: angleDeg, a, outX, outY, tx, ty, R, accent: accentOf(b.id) });
    });

    lastGeo.current = { W, H, POS, WORKER_R };

    lines.setAttribute("viewBox", `0 0 ${W} ${H}`);
    lines.setAttribute("width", String(W));
    lines.setAttribute("height", String(H));
    lines.innerHTML = "";
    lineEls.current = [];
    pulseEls.current = [];

    // Worker network per branch
    function buildWorkerNet(branch: Branch, index: number) {
      const cluster = document.createElement("div");
      cluster.className = "branch-cluster";
      const p = POS[index];
      const center = p.angle;
      const n = branch.workers.length;
      // Jarak worker diperlebar (tanpa mengubah posisi AI Manager/AIOS).
      const dist = WORKER_R * 1.4 + n * 4 + (rng() - 0.5) * 8;
      // Canvas cluster diperluas agar muat hingga ke cabang tools (level 4 tree).
      const S = WORKER_R + 320;
      const off = S;

      const svg = document.createElementNS(SVG_NS, "svg");
      svg.setAttribute("class", "cluster-svg");
      svg.setAttribute("width", String(S * 2));
      svg.setAttribute("height", String(S * 2));
      svg.setAttribute("viewBox", `0 0 ${S * 2} ${S * 2}`);
      svg.style.left = -off + "px";
      svg.style.top = -off + "px";

      const spread = n >= 6 ? 84 : n >= 5 ? 78 : n >= 4 ? 68 : 54;
      const dAngle = n <= 1 ? 0 : (spread * 2) / (n - 1);
      const pts: { x: number; y: number; name: string; ang: number }[] = [];
      branch.workers.forEach((w, k) => {
        const tt = n === 1 ? 0 : (k / (n - 1)) * 2 - 1;
        const aOff = tt * spread;
        const ang = ((center + aOff) * Math.PI) / 180;
        // Level 1: Jarak seragam & simetris untuk seluruh sub-agent
        const rad = WORKER_R * 1.48;
        pts.push({ x: Math.cos(ang) * rad, y: Math.sin(ang) * rad, name: w, ang });
      });

      const lnColor = p.accent;

      pts.forEach((pt, pk) => {
        const L = Math.hypot(pt.x, pt.y) || 1;
        const ux = pt.x / L,
          uy = pt.y / L;
        const line = document.createElementNS(SVG_NS, "line");
        line.setAttribute("class", "worker-line");
        line.setAttribute("x1", String(off + ux * (NODE_CORE + 8)));
        line.setAttribute("y1", String(off + uy * (NODE_CORE + 8)));
        line.setAttribute("x2", String(off + pt.x));
        line.setAttribute("y2", String(off + pt.y));
        line.style.color = lnColor;
        svg.appendChild(line);

        // SKILL BRANCHES (Tree level 3: Sub-Agent -> Skills dengan Jarak Selaras)
        const skills = getWorkerSkills(pt.name);
        const sCount = skills.length;
        // Batasi sudut mekar skill agar tidak pernah menyeberang ke sektor worker tetangga
        const maxSkillSpread = n <= 1 ? 26 : Math.min(18, dAngle * 0.42);

        skills.forEach((skName, skIdx) => {
          const sTt = sCount === 1 ? 0 : (skIdx / (sCount - 1)) * 2 - 1;
          const sAng = pt.ang + (sTt * maxSkillSpread * Math.PI) / 180;
          
          // Level 2: Jarak cabang skill 100% seragam dan selaras
          const sDist = 84;

          const skX = pt.x + Math.cos(sAng) * sDist;
          const skY = pt.y + Math.sin(sAng) * sDist;

          // Garis dari Sub-Agent ke Skill
          const sLine = document.createElementNS(SVG_NS, "line");
          sLine.setAttribute("class", "skill-line");
          sLine.setAttribute("x1", String(off + pt.x));
          sLine.setAttribute("y1", String(off + pt.y));
          sLine.setAttribute("x2", String(off + skX));
          sLine.setAttribute("y2", String(off + skY));
          sLine.style.color = lnColor;
          svg.appendChild(sLine);

          // Dot skill HTML
          const skDiv = document.createElement("div");
          skDiv.className = "skill-dot";
          skDiv.style.left = skX + "px";
          skDiv.style.top = skY + "px";
          skDiv.style.setProperty("--glow", lnColor);
          skDiv.style.setProperty("--glow-mid", rgbaOf(lnColor, 0.4));
          skDiv.innerHTML = `<span class="sk-dot"></span><span class="sk-name">${skName}</span>`;
          skDiv.title = `SOP: ${skName}`;
          skDiv.dataset.parentWorker = pt.name;
          skDiv.addEventListener("click", (e) => {
            e.stopPropagation();
            // Pilih sub-agent parent saat skill diklik
            const fallbackKey = pt.name.toLowerCase().replace(/\s+/g, "-");
            const wKey = workersByBranchRef.current[branch.id]?.find(w => w.jobRole === pt.name)?.key || fallbackKey;
            pendingWorkerRef.current = wKey;
            window.dispatchEvent(new CustomEvent("aios:select-worker", { detail: wKey }));
          });
          cluster.appendChild(skDiv);

          // TOOL BRANCHES (Tree level 4: Skill -> Tools Python dengan Jarak Selaras)
          const tools = getSkillTools(skName);
          const tCount = tools.length;
          const tSpread = tCount <= 1 ? 0 : 15;

          tools.forEach((tName, tIdx) => {
            const tTt = tCount === 1 ? 0 : (tIdx / (tCount - 1)) * 2 - 1;
            const tAng = sAng + (tTt * tSpread * Math.PI) / 180;
            // Level 3: Jarak ranting tool 100% seragam dan selaras
            const tDist = 42;
            const tX = skX + Math.cos(tAng) * tDist;
            const tY = skY + Math.sin(tAng) * tDist;

            // Garis dari Skill ke Tool
            const tLine = document.createElementNS(SVG_NS, "line");
            tLine.setAttribute("class", "tool-line");
            tLine.setAttribute("x1", String(off + skX));
            tLine.setAttribute("y1", String(off + skY));
            tLine.setAttribute("x2", String(off + tX));
            tLine.setAttribute("y2", String(off + tY));
            tLine.style.color = lnColor;
            svg.appendChild(tLine);

            // Dot Tool HTML
            const tlDiv = document.createElement("div");
            tlDiv.className = "tool-dot";
            tlDiv.style.left = tX + "px";
            tlDiv.style.top = tY + "px";
            tlDiv.style.setProperty("--glow", lnColor);
            tlDiv.style.setProperty("--glow-mid", rgbaOf(lnColor, 0.35));
            tlDiv.innerHTML = `<span class="tl-dot"></span><span class="tl-name">⚙ ${tName}</span>`;
            tlDiv.title = `Python Tool: ${tName}()`;
            tlDiv.addEventListener("click", (e) => {
              e.stopPropagation();
              const fallbackKey = pt.name.toLowerCase().replace(/\s+/g, "-");
              const wKey = workersByBranchRef.current[branch.id]?.find(w => w.jobRole === pt.name)?.key || fallbackKey;
              pendingWorkerRef.current = wKey;
              window.dispatchEvent(new CustomEvent("aios:select-worker", { detail: wKey }));
            });
            cluster.appendChild(tlDiv);
          });
        });
      });

      for (let k = 0; k < 3; k++) {
        const aOff = (k === 0 ? -1 : 1) * (30 + rng() * 32);
        const ang = ((center + aOff) * Math.PI) / 180;
        const rad = Math.max(46, dist - 18);
        const ax = Math.cos(ang) * rad,
          ay = Math.sin(ang) * rad;
        const line = document.createElementNS(SVG_NS, "line");
        line.setAttribute("class", "amb-line");
        line.setAttribute("x1", String(off + Math.cos(ang) * (NODE_CORE + 8)));
        line.setAttribute("y1", String(off + Math.sin(ang) * (NODE_CORE + 8)));
        line.setAttribute("x2", String(off + ax));
        line.setAttribute("y2", String(off + ay));
        svg.appendChild(line);
        const dot = document.createElementNS(SVG_NS, "circle");
        dot.setAttribute("class", "amb-dot");
        dot.setAttribute("cx", String(off + ax));
        dot.setAttribute("cy", String(off + ay));
        dot.setAttribute("r", "1.6");
        svg.appendChild(dot);
      }

      cluster.appendChild(svg);

      pts.forEach((pt, pk) => {
        // Satu bidang = satu warna identitas untuk semua worker-nya.
        const c = accentOf(branch.id);
        const wd = document.createElement("div");
        wd.className = "worker-dot";
        wd.style.left = pt.x + "px";
        wd.style.top = pt.y + "px";
        wd.style.setProperty("--glow", c);
        wd.style.setProperty("--glow-strong", rgbaOf(c, 0.8));
        wd.style.setProperty("--glow-mid", rgbaOf(c, 0.35));
        wd.style.setProperty("--glow-soft", rgbaOf(c, 0.12));
        // Kelap-kelip organik: kecepatan & jeda berbeda tiap titik.
        wd.style.setProperty("--glow-dur", `${(2.6 + ((pk * 37 + index * 13) % 20) / 10).toFixed(2)}s`);
        wd.style.setProperty("--glow-delay", `${((pk * 53 + index * 29) % 30) / 10}s`);
        // id ternormalisasi buat mencocokkan event "worker dipakai" dari chat.
        wd.dataset.wid = pt.name.toLowerCase().replace(/[^a-z0-9]/g, "");
        const fallbackKey = pt.name.toLowerCase().replace(/\s+/g, "-");
        const wKey = workersByBranchRef.current[branch.id]?.find(w => w.jobRole === pt.name)?.key || fallbackKey;
        wd.dataset.wkey = wKey;
        wd.dataset.bidx = index.toString();
        wd.innerHTML = `<span class="wd-dot"></span><span class="wd-name">${pt.name}</span>`;
        wd.style.cursor = "pointer";
        cluster.appendChild(wd);
      });

      cluster.setAttribute("aria-hidden", "true");
      return cluster;
    }

    // text width estimator
    function textWidth(txt: string) {
      const c = document.createElement("canvas");
      const m = c.getContext("2d");
      if (!m) return 100;
      m.font = '600 11px "Segoe UI", system-ui, sans-serif';
      return m.measureText(txt).width;
    }

    // ---- Web global ----
    const webNodes: { x: number; y: number }[] = [];
    const want = Math.round(Math.min(250, Math.max(90, (W * H) / 6200)));
    let made = 0,
      safety = 0;
    while (made < want && safety < want * 22) {
      safety++;
      const a = rng() * Math.PI * 2;
      const rr = Math.pow(rng(), 2.1);
      const x = hubX + Math.cos(a) * rr * (rx * 1.05);
      const y = hubY + Math.sin(a) * rr * (ry * 1.05);
      if (x < 12 || x > W - 12 || y < 12 || y > H - 12) continue;
      if (Math.hypot(x - hubX, y - hubY) < 64) continue;
      let near = false;
      for (const pp of POS) {
        if (Math.hypot(x - pp.x, y - pp.y) < NODE_CORE + 14) {
          near = true;
          break;
        }
      }
      if (near) continue;
      webNodes.push({ x, y });
      made++;
    }

    const webLinks = new Map<string, number>();
    for (let i = 0; i < webNodes.length; i++) {
      const hits: [number, number][] = [];
      for (let j = 0; j < webNodes.length; j++) {
        if (i === j) continue;
        const dx = webNodes[i].x - webNodes[j].x;
        const dy = webNodes[i].y - webNodes[j].y;
        hits.push([dx * dx + dy * dy, j]);
      }
      hits.sort((a, b) => a[0] - b[0]);
      const take = Math.min(2 + (i % 2), hits.length);
      for (let k = 0; k < take; k++) {
        const j = hits[k][1];
        const key = i < j ? i + "_" + j : j + "_" + i;
        if (!webLinks.has(key)) webLinks.set(key, Math.sqrt(hits[k][0]));
      }
    }

    const maxLink = Math.min(W, H) * 0.3;
    webLinks.forEach((dlen, key) => {
      if (dlen > maxLink) return;
      const ids = key.split("_");
      const A = webNodes[Number(ids[0])],
        B = webNodes[Number(ids[1])];
      const ln = document.createElementNS(SVG_NS, "line");
      ln.setAttribute("class", "web-link");
      ln.setAttribute("x1", String(A.x));
      ln.setAttribute("y1", String(A.y));
      ln.setAttribute("x2", String(B.x));
      ln.setAttribute("y2", String(B.y));
      lines.appendChild(ln);
    });

    webNodes.forEach((nn, i) => {
      const dot = document.createElementNS(SVG_NS, "circle");
      dot.setAttribute("class", "web-node" + (i % 7 === 0 ? " web-node-bright" : ""));
      dot.setAttribute("cx", String(nn.x));
      dot.setAttribute("cy", String(nn.y));
      dot.setAttribute("r", (1 + (i % 3) * 0.7).toFixed(2));
      lines.appendChild(dot);
    });

    const byCore = webNodes
      .map((n, i) => ({ n, i, d: Math.hypot(n.x - hubX, n.y - hubY) }))
      .filter((o) => o.d < Math.min(W, H) * 0.3)
      .sort((a, b) => a.d - b.d)
      .slice(0, 16);
    byCore.forEach((o) => {
      const dx = o.n.x - hubX,
        dy = o.n.y - hubY;
      const L = Math.hypot(dx, dy) || 1;
      const ln = document.createElementNS(SVG_NS, "line");
      ln.setAttribute("class", "core-web");
      ln.setAttribute("x1", String(hubX + (dx / L) * 52));
      ln.setAttribute("y1", String(hubY + (dy / L) * 52));
      ln.setAttribute("x2", String(o.n.x));
      ln.setAttribute("y2", String(o.n.y));
      lines.appendChild(ln);
    });

    // ---- Jalur data inti -> manager ----
    POS.forEach((p, i) => {
      const startX = hubX + p.outX * 52;
      const startY = hubY + p.outY * 52;
      const endX = p.x - p.outX * NODE_CORE;
      const endY = p.y - p.outY * NODE_CORE;
      // Agar garis terlihat "tepat membidik" titik tengah meskipun jalurnya melengkung,
      // gunakan kurva Bezier Kubik (C) di mana control point ditarik searah vektor radial.
      const dist = Math.hypot(endX - startX, endY - startY);
      const cpDist = Math.min(dist * 0.4, 80); // Seberapa kuat "dorongan" kurvanya
      
      // Sedikit twisting biar organik (selang-seling kiri/kanan)
      const twist = (i % 2 === 0 ? 1 : -1) * cpDist * 0.3;
      
      const cp1x = startX + p.outX * cpDist + p.tx * twist;
      const cp1y = startY + p.outY * cpDist + p.ty * twist;
      const cp2x = endX - p.outX * cpDist + p.tx * twist;
      const cp2y = endY - p.outY * cpDist + p.ty * twist;
      
      const d = `M ${startX} ${startY} C ${cp1x} ${cp1y} ${cp2x} ${cp2y} ${endX} ${endY}`;

      const pathEl = document.createElementNS(SVG_NS, "path");
      pathEl.setAttribute("class", "man-link");
      pathEl.setAttribute("d", d);
      pathEl.style.color = p.accent;
      lines.appendChild(pathEl);
      lineEls.current.push(pathEl);

      const pulse = document.createElementNS(SVG_NS, "circle");
      pulse.setAttribute("class", "pulse-dot");
      pulse.setAttribute("r", "2.6");
      pulse.style.color = p.accent;
      lines.appendChild(pulse);
      pulseEls.current.push(pulse);

      // Titik tengah bezier kubik (t = 0.5)
      const mx = 0.125 * startX + 0.375 * cp1x + 0.375 * cp2x + 0.125 * endX;
      const my = 0.125 * startY + 0.375 * cp1y + 0.375 * cp2y + 0.125 * endY;
      const relay = document.createElementNS(SVG_NS, "circle");
      relay.setAttribute("class", "relay-dot");
      relay.setAttribute("cx", String(mx));
      relay.setAttribute("cy", String(my));
      relay.setAttribute("r", "2");
      lines.appendChild(relay);
    });

    // ---- Label chip + anti-tabrakan ----
    const chips: {
      i: number;
      cx: number;
      cy: number;
      estW: number;
      estH: number;
      outX: number;
      outY: number;
      tx: number;
      ty: number;
    }[] = [];
    POS.forEach((p, i) => {
      const nameW = textWidth(BRANCHES[i].name) + 24;
      const estW = Math.min(nameW, 172);
      const wrap = nameW > 172;
      const estH = (wrap ? 31 : 16) + 13 + 12 + 2;
      const gap = NODE_CORE + 24;
      const cx = p.x + p.outX * gap;
      const cy = p.y + p.outY * gap;
      chips.push({ i, cx, cy, estW, estH, outX: p.outX, outY: p.outY, tx: p.tx, ty: p.ty });
    });

    for (let pass = 0; pass < 60; pass++) {
      let movedChip = false;
      let movedSocket = false;
      for (let a = 0; a < chips.length; a++) {
        for (let b = a + 1; b < chips.length; b++) {
          const A = chips[a],
            B = chips[b];
          const ox = B.cx - A.cx,
            oy = B.cy - A.cy;
          const overlapX = (A.estW + B.estW) / 2 - Math.abs(ox);
          const overlapY = (A.estH + B.estH) / 2 - Math.abs(oy);
          if (overlapX > 0 && overlapY > 0) {
            const push = Math.min(overlapX, overlapY) + 8;
            const sgnX = ox >= 0 ? 1 : -1;
            const sgnY = oy >= 0 ? 1 : -1;
            if (overlapX <= overlapY) {
              A.cx -= (sgnX * push) / 2;
              B.cx += (sgnX * push) / 2;
            } else {
              A.cy -= (sgnY * push) / 2;
              B.cy += (sgnY * push) / 2;
            }
            movedChip = true;
          }
        }
      }
      for (let c = 0; c < chips.length; c++) {
        const C = chips[c];
        const cr = { l: C.cx - C.estW / 2, t: C.cy - C.estH / 2, r: C.cx + C.estW / 2, b: C.cy + C.estH / 2 };
        for (let n = 0; n < POS.length; n++) {
          if (n === C.i) continue;
          const p = POS[n];
          const cx = Math.max(cr.l, Math.min(p.x, cr.r));
          const cy = Math.max(cr.t, Math.min(p.y, cr.b));
          let dx = p.x - cx,
            dy = p.y - cy;
          const distSq = dx * dx + dy * dy;
          const socR = NODE_CORE * 0.85 + 2;
          if (distSq < socR * socR) {
            const dist = Math.sqrt(distSq) || 0.001;
            const push = socR - dist + 5;
            dx /= dist;
            dy /= dist;
            C.cx -= dx * push * 0.5;
            C.cy -= dy * push * 0.5;
            movedSocket = true;
          }
        }
      }
      for (let c = 0; c < chips.length; c++) {
        const C = chips[c];
        const margin = 8;
        let nx = C.cx,
          ny = C.cy;
        nx = Math.max(margin + C.estW / 2, Math.min(W - margin - C.estW / 2, nx));
        ny = Math.max(margin + C.estH / 2, Math.min(H - margin - C.estH / 2, ny));
        if (Math.abs(nx - C.cx) > 0.1 || Math.abs(ny - C.cy) > 0.1) {
          C.cx = nx;
          C.cy = ny;
          movedSocket = true;
        }
      }
      if (!movedChip && !movedSocket) break;
    }

    // ---- Render 9 node AI Manager ----
    BRANCHES.forEach((b, i) => {
      const p = POS[i];
      const node = document.createElement("div");
      node.className = "branch-node";
      node.style.left = p.x + "px";
      node.style.top = p.y + "px";
      node.style.setProperty("--acc", p.accent);
      node.style.setProperty("--acc-soft", rgbaOf(p.accent, 0.28));
      node.style.setProperty("--acc-line", rgbaOf(p.accent, 0.55));
      node.style.setProperty("--acc-glow", rgbaOf(p.accent, 0.85));
      node.setAttribute("role", "button");
      node.setAttribute("tabindex", "0");
      node.setAttribute("aria-label", `${b.name} — AI Manager, zoom ke bidang & buka chat`);

      node.innerHTML =
        `<span class="b-aura"></span>` +
        `<span class="b-ring"></span>` +
        `<span class="b-socket" data-bidx="${i}" data-wkey="manager"><span class="b-code">${MONOGRAMS[b.id] || b.id.slice(0, 3).toUpperCase()}</span></span>`;

      node.addEventListener("click", (e) => {
        // Kalau klik berasal dari worker-dot, jangan override — biar global handler yg urus
        if ((e.target as HTMLElement).closest(".worker-dot")) return;
        pendingWorkerRef.current = "manager";
        if (zoomedRef.current !== i) zoomTo(i);
        else window.dispatchEvent(new CustomEvent("aios:select-worker", { detail: "manager" }));
      });
      node.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          pendingWorkerRef.current = "manager";
          if (zoomedRef.current !== i) zoomTo(i);
          else window.dispatchEvent(new CustomEvent("aios:select-worker", { detail: "manager" }));
        }
      });
      node.addEventListener("mouseenter", () => setActive(i, true));
      node.addEventListener("mouseleave", () => setActive(i, false));
      node.addEventListener("focus", () => setActive(i, true));
      node.addEventListener("blur", () => setActive(i, false));

      const cluster = buildWorkerNet(b, i);
      node.appendChild(cluster);

      const hs = 72; // Ukuran pas mengikuti lingkaran socket AI Manager
      const hit = document.createElement("div");
      hit.className = "branch-hit manager-hit";
      hit.dataset.bidx = i.toString();
      hit.dataset.wkey = "manager";
      hit.style.width = hs + "px";
      hit.style.height = hs + "px";
      hit.style.left = "0px";
      hit.style.top = "0px";
      hit.style.position = "absolute";
      hit.style.transform = "translate(-50%, -50%)";
      hit.style.borderRadius = "50%";
      hit.style.zIndex = "10";
      hit.style.cursor = "pointer";
      hit.style.pointerEvents = "auto";
      node.appendChild(hit);

      nodes.appendChild(node);
    });

    // chip label
    chips.forEach((c) => {
      const el = document.createElement("div");
      el.className = "branch-name";
      el.setAttribute("inert", "");
      el.style.left = c.cx + "px";
      el.style.top = c.cy + "px";
      el.innerHTML =
        `<span class="bn-title">${BRANCHES[c.i].name}</span>` +
        `<span class="bn-meta">${BRANCHES[c.i].workers.length} worker</span>`;
      nodes.appendChild(el);
    });

    chips.forEach((c) => {
      const p = POS[c.i];
      const ln = document.createElementNS(SVG_NS, "line");
      ln.setAttribute("class", "label-link");
      ln.setAttribute("x1", String(p.x + p.outX * NODE_CORE));
      ln.setAttribute("y1", String(p.y + p.outY * NODE_CORE));
      ln.setAttribute("x2", String(c.cx - p.outX * 8));
      ln.setAttribute("y2", String(c.cy - p.outY * 8));
      lines.appendChild(ln);
    });

    if (zoomedRef.current >= 0) useZoomClasses(true);
  }

  // highlight koneksi inti -> manager
  function setActive(i: number, on: boolean) {
    const stage = stageRef.current;
    if (!stage) return;
    if (zoomedRef.current >= 0) on = i === zoomedRef.current;
    stage.classList.toggle("hub-hover", on);
    if (lineEls.current[i]) lineEls.current[i].classList.toggle("active", on);
    if (pulseEls.current[i]) pulseEls.current[i].classList.toggle("active", on);
  }

  // ---------- Inti AIOS (Neural Ball) dipindah ke NeuralBall.tsx ----------

  // ---------- Mount: init particles + render + listeners ----------
  useEffect(() => {
    render();

    const stage = stageRef.current;
    if (!stage) return;

    let pan: { x0: number; y0: number; tx0: number; ty0: number } | null = null;

    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Element | null;
      if (zoomedRef.current < 0 || (target && (target.closest(".chat-dock") || target.closest(".zoom-ui") || target.closest(".lead-modal-backdrop") || target.closest(".lead-modal-dialog") || target.closest(".chatbot-monitoring-popup") || target.closest(".chatbot-widget-btn")))) return;
      // Jangan hijack pointer kalau user klik worker-dot atau node AI Manager pusat
      if (target && (target.closest(".worker-dot") || target.closest(".manager-hit") || target.closest(".branch-hit") || target.closest(".branch-node") || target.closest(".b-socket"))) return;
      pan = { x0: e.clientX, y0: e.clientY, tx0: view.current.tx, ty0: view.current.ty };
      stage.setPointerCapture(e.pointerId);
      stage.classList.add("panning");
    };
    const onPointerMove = (e: PointerEvent) => {
      if (!pan) return;
      const dx = e.clientX - pan.x0;
      const dy = e.clientY - pan.y0;
      view.current.tx = pan.tx0 + dx;
      view.current.ty = pan.ty0 + dy;
      clampView();
      applyTransform();
    };
    const endPan = () => {
      if (pan) {
        pan = null;
        stage.classList.remove("panning");
      }
    };
    const onWheel = (e: WheelEvent) => {
      if (zoomedRef.current < 0) return;
      // Scroll di dalam chat dock / tombol zoom biarkan normal (scroll daftar
      // pesan), jangan diubah jadi zoom peta.
      const target = e.target as Element | null;
      if (
        target &&
        (target.closest(".chat-dock") ||
          target.closest(".zoom-ui") ||
          target.closest(".lead-modal-backdrop") ||
          target.closest(".lead-modal-dialog") ||
          target.closest(".chatbot-monitoring-popup") ||
          target.closest(".chatbot-widget-btn"))
      )
        return;
      e.preventDefault();
      zoomByFactor(e.deltaY < 0 ? 1.12 : 1 / 1.12);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && zoomedRef.current >= 0) zoomReset();
    };
    const onResize = () => {
      render();
    };

    stage.addEventListener("pointerdown", onPointerDown);
    stage.addEventListener("pointermove", onPointerMove);
    stage.addEventListener("pointerup", endPan);
    stage.addEventListener("pointercancel", endPan);
    stage.addEventListener("wheel", onWheel, { passive: false });
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", onResize);

    return () => {
      stage.removeEventListener("pointerdown", onPointerDown);
      stage.removeEventListener("pointermove", onPointerMove);
      stage.removeEventListener("pointerup", endPan);
      stage.removeEventListener("pointercancel", endPan);
      stage.removeEventListener("wheel", onWheel);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  // ---------- Sub-agent menyala terang saat benar-benar dipakai menjawab ----------
  // ChatDock mengirim event "aios:worker-used" saat backend mendelegasikan
  // jawaban ke worker; titik worker terkait di peta di-flare 4 detik.
  useEffect(() => {
    let timers: number[] = [];
    const onWorkerUsed = (e: Event) => {
      const key = String((e as CustomEvent).detail?.workerId || "")
        .toLowerCase()
        .replace(/[\s-]/g, "");
      if (!key || !nodesRef.current) return;
      const dot = nodesRef.current.querySelector(
        `.worker-dot[data-wid="${CSS.escape(key)}"] .wd-dot`
      );
      if (!dot) return;
      dot.classList.remove("wd-active");
      void (dot as HTMLElement).offsetWidth; // paksa restart animasi flare
      dot.classList.add("wd-active");
      const t = window.setTimeout(() => dot.classList.remove("wd-active"), 4000);
      timers.push(t);
    };
    window.addEventListener("aios:worker-used", onWorkerUsed);
    return () => {
      window.removeEventListener("aios:worker-used", onWorkerUsed);
      timers.forEach((t) => clearTimeout(t));
    };
  }, []);

  // ---------- Re-apply zoom class saat zoomedIndex berubah ----------
  useEffect(() => {
    if (zoomedIndex >= 0) useZoomClasses(true);
  }, [zoomedIndex]);

  // Navbar ngambang sembunyi saat masuk chat (biar tidak menghalangi),
  // muncul lagi saat kembali ke home.
  useEffect(() => {
    document.body.classList.toggle("chat-open", zoomedIndex >= 0);
    return () => document.body.classList.remove("chat-open");
  }, [zoomedIndex]);

  return (
    <div className="home-body">
      <div className="hub-stage" ref={stageRef}>
        <div className="hub-world" ref={worldRef}>
          <ParticleBg />
          <svg className="hub-lines" ref={linesRef} />

          <div className="hub-core">
            <NeuralBall />
            <div className="core-body">
              <span className="core-name">AIOS</span>
              <span className="core-caption">AI CORE</span>
            </div>
          </div>
          <div ref={nodesRef} />
        </div>

        <div className="zoom-ui">
          <div className="zoom-group">
            <button
              type="button"
              className="zoom-btn zoom-btn-lead"
              onClick={() => setIsLeadModalOpen(true)}
              title="Lead AI Generator"
              aria-label="Lead AI Generator"
            >
              <UserSearch size={16} />
            </button>
          </div>

          <div className="zoom-divider" />

          <div className="zoom-group">
            <button
              type="button"
              className="zoom-btn"
              onClick={() => zoomedRef.current >= 0 && zoomTo((zoomedRef.current + 8) % 9)}
              title="AI Manager Sebelumnya"
              aria-label="AI Manager sebelumnya"
            >
              <ChevronLeft size={16} />
            </button>
            <button
              type="button"
              className="zoom-btn"
              onClick={() => zoomedRef.current >= 0 && zoomTo((zoomedRef.current + 1) % 9)}
              title="AI Manager Berikutnya"
              aria-label="AI Manager berikutnya"
            >
              <ChevronRight size={16} />
            </button>
          </div>

          <div className="zoom-divider" />

          <div className="zoom-group">
            <button
              type="button"
              className="zoom-btn"
              onClick={() => zoomedRef.current >= 0 && zoomByFactor(1.35)}
              title="Perbesar (Zoom In)"
              aria-label="Perbesar"
            >
              <Plus size={16} />
            </button>
            <button
              type="button"
              className="zoom-btn"
              onClick={() => zoomedRef.current >= 0 && zoomByFactor(1 / 1.35)}
              title="Perkecil (Zoom Out)"
              aria-label="Perkecil"
            >
              <Minus size={16} />
            </button>
          </div>

          <div className="zoom-divider" />

          <div className="zoom-group">
            <button
              type="button"
              className="zoom-btn"
              onClick={zoomReset}
              title="Kembali ke Jaringan Penuh"
              aria-label="Kembali ke jaringan penuh"
            >
              <Home size={15} />
            </button>
          </div>
        </div>

        {activeBranch && (
          <>
            <QuickInsightsPanel branch={activeBranch} />
            <ChatDock
              branch={activeBranch}
              workers={workersByBranch[activeBranch.id] ?? []}
              initialWorkerKey={pendingWorkerRef.current}
              onClose={zoomReset}
            />
          </>
        )}

        <LeadModal
          isOpen={isLeadModalOpen}
          onClose={() => setIsLeadModalOpen(false)}
        />

        {/* Fitur Chatbot dibekukan (frozen) atas instruksi user */}
      </div>
    </div>
  );
}