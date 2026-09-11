"use client";

import { useEffect, useRef } from "react";

export default function ParticleBg() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvasEl = canvasRef.current;
    if (!canvasEl) return;
    const ctxEl = canvasEl.getContext("2d");
    if (!ctxEl) return;
    const canvas = canvasEl;
    const ctx = ctxEl;
    const DPR = Math.min(window.devicePixelRatio || 1, 2);
    let W = 0,
      H = 0,
      parts: { x: number; y: number; r: number; vx: number; vy: number; a: number; tw: number }[] = [];
    const COUNT = Math.min(90, Math.floor((canvas.offsetWidth * canvas.offsetHeight) / 14000));

    function resize() {
      W = canvas.clientWidth;
      H = canvas.clientHeight;
      canvas.width = W * DPR;
      canvas.height = H * DPR;
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      parts = [];
      for (let i = 0; i < COUNT; i++) {
        parts.push({
          x: Math.random() * W,
          y: Math.random() * H,
          r: 0.6 + Math.random() * 1.5,
          vx: (Math.random() - 0.5) * 0.16,
          vy: (Math.random() - 0.5) * 0.16,
          a: 0.12 + Math.random() * 0.4,
          tw: Math.random() * 0.004 + 0.001,
        });
      }
    }

    const ACENT = "#22d3ee";
    let raf = 0;

    function step() {
      ctx.clearRect(0, 0, W, H);
      for (const p of parts) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < -5) p.x = W + 5;
        if (p.x > W + 5) p.x = -5;
        if (p.y < -5) p.y = H + 5;
        if (p.y > H + 5) p.y = -5;
        const alpha = p.a * (0.6 + Math.sin(performance.now() * p.tw + p.x * 0.01) * 0.4);
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = ACENT;
        ctx.globalAlpha = alpha;
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      if (!document.hidden) raf = requestAnimationFrame(step);
    }

    resize();
    window.addEventListener("resize", resize);
    step();
    return () => {
      window.removeEventListener("resize", resize);
      cancelAnimationFrame(raf);
    };
  }, []);

  return <canvas className="hub-particles" ref={canvasRef} />;
}
