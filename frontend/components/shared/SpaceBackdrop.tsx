"use client";

// Backdrop deep-space untuk halaman non-home: bintang berkelip + web
// konstelasi tipis di belakang konten. Versi ringan dari scene HomeHub —
// deterministik, hormat prefers-reduced-motion, tanpa dependency baru.
import { useEffect, useRef } from "react";

const SEED = 20260813;
const STAR_COLOR = "#9adfff";

// Generator acak deterministik (sama dengan HomeHub) supaya pola langit stabil.
function mulberry32(seed: number) {
  let t = seed >>> 0;
  return function () {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

interface Star {
  x: number;
  y: number;
  r: number;
  a: number;
  tw: number;
}

export default function SpaceBackdrop() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvasEl = canvasRef.current;
    if (!canvasEl) return;
    const ctx = canvasEl.getContext("2d");
    if (!ctx) return;
    const canvas: HTMLCanvasElement = canvasEl;

    const DPR = Math.min(window.devicePixelRatio || 1, 2);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let W = 0;
    let H = 0;
    let stars: Star[] = [];
    let links: [Star, Star][] = [];
    let raf = 0;

    function build() {
      W = canvas.clientWidth;
      H = canvas.clientHeight;
      canvas.width = W * DPR;
      canvas.height = H * DPR;
      ctx!.setTransform(DPR, 0, 0, DPR, 0, 0);

      const rng = mulberry32(SEED);
      const count = Math.min(80, Math.floor((W * H) / 16000));
      stars = [];
      for (let i = 0; i < count; i++) {
        stars.push({
          x: rng() * W,
          y: rng() * H,
          r: 0.7 + rng() * 1.4,
          a: 0.18 + rng() * 0.45,
          tw: 0.0008 + rng() * 0.0022,
        });
      }

      // Web konstelasi tipis: hubungkan pasangan bintang yang berdekatan.
      links = [];
      const MAX_D = Math.min(150, Math.max(90, Math.min(W, H) * 0.16));
      for (let i = 0; i < stars.length; i++) {
        for (let j = i + 1; j < stars.length; j++) {
          const d = Math.hypot(stars[i].x - stars[j].x, stars[i].y - stars[j].y);
          if (d < MAX_D) links.push([stars[i], stars[j]]);
        }
      }
    }

    function draw(now: number) {
      if (!ctx) return;
      ctx.clearRect(0, 0, W, H);

      ctx.strokeStyle = "rgba(34, 211, 238, 0.07)";
      ctx.lineWidth = 0.7;
      ctx.beginPath();
      for (const [a, b] of links) {
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
      }
      ctx.stroke();

      for (const s of stars) {
        const alpha = reduced ? s.a : s.a * (0.55 + Math.sin(now * s.tw + s.x * 0.01) * 0.45);
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fillStyle = STAR_COLOR;
        ctx.globalAlpha = alpha;
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    }

    function frame(now: number) {
      draw(now);
      if (!document.hidden) raf = requestAnimationFrame(frame);
    }

    function start() {
      build();
      if (reduced) {
        draw(performance.now());
      } else {
        raf = requestAnimationFrame(frame);
      }
    }

    start();
    window.addEventListener("resize", start);
    return () => {
      window.removeEventListener("resize", start);
      cancelAnimationFrame(raf);
    };
  }, []);

  return <canvas className="space-backdrop" ref={canvasRef} aria-hidden="true" />;
}
