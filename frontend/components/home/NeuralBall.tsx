"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

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

export default function NeuralBall() {
  const coreNetRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvasEl = coreNetRef.current;
    if (!canvasEl) return;
    const canvas = canvasEl;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 20);
    camera.position.set(0, 0, 3.3);
    const renderer = new THREE.WebGLRenderer({ canvas: canvasEl, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    // Titik neuron tersebar merata di permukaan bola (distribusi fibonacci).
    const N = 92;
    const GOLD = Math.PI * (3 - Math.sqrt(5));
    const rngCore = mulberry32(SEED + 7);
    const nodes: { v: THREE.Vector3; bright: boolean }[] = [];
    for (let i = 0; i < N; i++) {
      const y = 1 - (i / (N - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const th = GOLD * i;
      nodes.push({ v: new THREE.Vector3(Math.cos(th) * r, y, Math.sin(th) * r), bright: rngCore() < 0.16 });
    }
    // Pasangan sinaps: neuron bertetangga (jarak chord < ambang).
    const links: [number, number][] = [];
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        if (nodes[i].v.distanceTo(nodes[j].v) < 0.58) links.push([i, j]);
      }
    }

    // Tekstur titik bercahaya (glow radial) — dapatkan efek bloom tanpa postprocessing.
    const spriteCanvas = document.createElement("canvas");
    spriteCanvas.width = spriteCanvas.height = 64;
    const sctx = spriteCanvas.getContext("2d");
    if (sctx) {
      const grad = sctx.createRadialGradient(32, 32, 0, 32, 32, 32);
      grad.addColorStop(0, "rgba(255,255,255,1)");
      grad.addColorStop(0.35, "rgba(255,255,255,0.55)");
      grad.addColorStop(1, "rgba(255,255,255,0)");
      sctx.fillStyle = grad;
      sctx.fillRect(0, 0, 64, 64);
    }
    const spriteTex = new THREE.CanvasTexture(spriteCanvas);

    const ball = new THREE.Group();
    scene.add(ball);

    // Neuron
    const nodeGeo = new THREE.BufferGeometry();
    const nodePos = new Float32Array(N * 3);
    const nodeCol = new Float32Array(N * 3);
    nodes.forEach((n, i) => n.v.toArray(nodePos, i * 3));
    nodeGeo.setAttribute("position", new THREE.BufferAttribute(nodePos, 3));
    nodeGeo.setAttribute("color", new THREE.BufferAttribute(nodeCol, 3));
    const nodeMat = new THREE.PointsMaterial({
      size: 0.085,
      map: spriteTex,
      vertexColors: true,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true,
    });
    const nodeObj = new THREE.Points(nodeGeo, nodeMat);
    ball.add(nodeObj);

    // Sinaps
    const lineGeo = new THREE.BufferGeometry();
    const linePos = new Float32Array(links.length * 6);
    const lineCol = new Float32Array(links.length * 6);
    links.forEach(([i, j], k) => {
      nodes[i].v.toArray(linePos, k * 6);
      nodes[j].v.toArray(linePos, k * 6 + 3);
    });
    lineGeo.setAttribute("position", new THREE.BufferAttribute(linePos, 3));
    lineGeo.setAttribute("color", new THREE.BufferAttribute(lineCol, 3));
    const lineMat = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const lineObj = new THREE.LineSegments(lineGeo, lineMat);
    ball.add(lineObj);

    const tmp = new THREE.Vector3();
    const worldZ = new Float64Array(N);
    function paint() {
      ball.updateMatrix();
      for (let i = 0; i < N; i++) {
        tmp.copy(nodes[i].v).applyMatrix4(ball.matrix);
        worldZ[i] = tmp.z; 
        const front = Math.max(0, tmp.z);
        const k = 0.18 + front * (nodes[i].bright ? 0.95 : 0.62);
        if (nodes[i].bright) {
          nodeCol[i * 3] = 0.92 * k; nodeCol[i * 3 + 1] = 0.98 * k; nodeCol[i * 3 + 2] = 1.0 * k;
        } else {
          nodeCol[i * 3] = 0.4 * k; nodeCol[i * 3 + 1] = 0.91 * k; nodeCol[i * 3 + 2] = 0.98 * k;
        }
      }
      links.forEach(([i, j], k2) => {
        const front = Math.max(0, (worldZ[i] + worldZ[j]) / 2);
        const c = 0.05 + front * 0.42;
        lineCol[k2 * 6] = 0.4 * c; lineCol[k2 * 6 + 1] = 0.91 * c; lineCol[k2 * 6 + 2] = 0.98 * c;
        lineCol[k2 * 6 + 3] = lineCol[k2 * 6];
        lineCol[k2 * 6 + 4] = lineCol[k2 * 6 + 1];
        lineCol[k2 * 6 + 5] = lineCol[k2 * 6 + 2];
      });
      nodeGeo.attributes.color.needsUpdate = true;
      lineGeo.attributes.color.needsUpdate = true;
    }

    let rotY = 0.6, rotX = 0.12;
    let targetRotY = rotY, targetRotX = rotX;
    let dragging = false, lastX = 0, lastY = 0;
    
    const onDown = (e: PointerEvent) => {
      dragging = true;
      lastX = e.clientX;
      lastY = e.clientY;
      canvas.setPointerCapture(e.pointerId);
      canvas.style.cursor = "grabbing";
      e.stopPropagation(); 
    };
    const onMove = (e: PointerEvent) => {
      if (!dragging) return;
      targetRotY += (e.clientX - lastX) * 0.006;
      targetRotX = Math.max(-1.1, Math.min(1.1, targetRotX + (e.clientY - lastY) * 0.006));
      lastX = e.clientX;
      lastY = e.clientY;
    };
    const onUp = () => {
      dragging = false;
      canvas.style.cursor = "grab";
    };
    
    canvasEl.addEventListener("pointerdown", onDown);
    canvasEl.addEventListener("pointermove", onMove);
    canvasEl.addEventListener("pointerup", onUp);
    canvasEl.addEventListener("pointercancel", onUp);

    function resize() {
      const w = canvas.clientWidth || 200;
      const h = canvas.clientHeight || 200;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }

    let raf = 0;
    function frame() {
      if (!dragging && !reduced) targetRotY += 0.0016;
      rotY += (targetRotY - rotY) * 0.12;
      rotX += (targetRotX - rotX) * 0.12;
      ball.rotation.set(rotX, rotY, 0);
      paint();
      renderer.render(scene, camera);
      if (!document.hidden) raf = requestAnimationFrame(frame);
    }

    resize();
    window.addEventListener("resize", resize);
    raf = requestAnimationFrame(frame);
    
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      canvasEl.removeEventListener("pointerdown", onDown);
      canvasEl.removeEventListener("pointermove", onMove);
      canvasEl.removeEventListener("pointerup", onUp);
      canvasEl.removeEventListener("pointercancel", onUp);
      nodeGeo.dispose();
      lineGeo.dispose();
      nodeMat.dispose();
      lineMat.dispose();
      spriteTex.dispose();
      renderer.dispose();
    };
  }, []);

  return <canvas className="core-net" ref={coreNetRef} aria-hidden="true" />;
}
