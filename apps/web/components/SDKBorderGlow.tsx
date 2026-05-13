"use client";

import type { CSSProperties, PointerEvent, ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import styles from "./SDKBorderGlow.module.css";

type SDKBorderGlowProps = {
  children: ReactNode;
  className?: string;
  edgeSensitivity?: number;
  glowColor?: string;
  backgroundColor?: string;
  borderRadius?: number;
  glowRadius?: number;
  glowIntensity?: number;
  coneSpread?: number;
  animated?: boolean;
  colors?: string[];
  fillOpacity?: number;
};

function parseHSL(hsl: string) {
  const match = hsl.match(/([\d.]+)\s*([\d.]+)%?\s*([\d.]+)%?/);
  if (!match) return { h: 192, s: 86, l: 76 };
  return { h: Number(match[1]), s: Number(match[2]), l: Number(match[3]) };
}

function buildGlowVars(glowColor: string, intensity: number) {
  const { h, s, l } = parseHSL(glowColor);
  const base = `${h}deg ${s}% ${l}%`;
  const opacities = [100, 60, 50, 40, 30, 20, 10];
  const keys = ["", "-60", "-50", "-40", "-30", "-20", "-10"];
  const vars: Record<string, string> = {};

  for (let i = 0; i < opacities.length; i += 1) {
    vars[`--sdk-glow-color${keys[i]}`] = `hsl(${base} / ${Math.min(opacities[i] * intensity, 100)}%)`;
  }

  return vars;
}

const GRADIENT_POSITIONS = ["80% 55%", "69% 34%", "8% 6%", "41% 38%", "86% 85%", "82% 18%", "51% 4%"];
const GRADIENT_KEYS = [
  "--sdk-gradient-one",
  "--sdk-gradient-two",
  "--sdk-gradient-three",
  "--sdk-gradient-four",
  "--sdk-gradient-five",
  "--sdk-gradient-six",
  "--sdk-gradient-seven",
];
const COLOR_MAP = [0, 1, 2, 0, 1, 2, 1];

function buildGradientVars(colors: string[]) {
  const vars: Record<string, string> = {};
  for (let i = 0; i < 7; i += 1) {
    const c = colors[Math.min(COLOR_MAP[i], colors.length - 1)];
    vars[GRADIENT_KEYS[i]] = `radial-gradient(at ${GRADIENT_POSITIONS[i]}, ${c} 0px, transparent 50%)`;
  }
  vars["--sdk-gradient-base"] = `linear-gradient(${colors[0]} 0 100%)`;
  return vars;
}

function easeOutCubic(x: number) {
  return 1 - (1 - x) ** 3;
}

function easeInCubic(x: number) {
  return x ** 3;
}

function animateValue(options: {
  start?: number;
  end?: number;
  duration?: number;
  delay?: number;
  ease?: (x: number) => number;
  onUpdate: (value: number) => void;
  onEnd?: () => void;
}) {
  const {
    start = 0,
    end = 100,
    duration = 1000,
    delay = 0,
    ease = easeOutCubic,
    onUpdate,
    onEnd,
  } = options;

  const t0 = performance.now() + delay;

  function tick() {
    const elapsed = performance.now() - t0;
    const t = Math.min(Math.max(elapsed, 0) / duration, 1);
    onUpdate(start + (end - start) * ease(t));
    if (t < 1) {
      requestAnimationFrame(tick);
    } else if (onEnd) {
      onEnd();
    }
  }

  window.setTimeout(() => requestAnimationFrame(tick), delay);
}

function usePrefersReducedMotion() {
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReducedMotion(query.matches);
    onChange();
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return reducedMotion;
}

export function SDKBorderGlow({
  children,
  className = "",
  edgeSensitivity = 30,
  glowColor = "192 86 76",
  backgroundColor = "#0B1220",
  borderRadius = 26,
  glowRadius = 36,
  glowIntensity = 0.72,
  coneSpread = 22,
  animated = true,
  colors = ["#29DFFF", "#5B7CFF", "#48FCA5"],
  fillOpacity = 0.18,
}: SDKBorderGlowProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const reducedMotion = usePrefersReducedMotion();
  const [sweepActive, setSweepActive] = useState(false);

  const cardStyle = useMemo(
    () =>
      ({
        "--sdk-card-bg": backgroundColor,
        "--sdk-edge-sensitivity": edgeSensitivity,
        "--sdk-border-radius": `${borderRadius}px`,
        "--sdk-glow-padding": `${glowRadius}px`,
        "--sdk-cone-spread": coneSpread,
        "--sdk-fill-opacity": fillOpacity,
        ...buildGlowVars(glowColor, glowIntensity),
        ...buildGradientVars(colors),
      }) as CSSProperties,
    [backgroundColor, edgeSensitivity, borderRadius, glowRadius, coneSpread, fillOpacity, glowColor, glowIntensity, colors]
  );

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const card = cardRef.current;
    if (!card) return;

    const rect = card.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;

    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const dx = x - cx;
    const dy = y - cy;

    let kx = Number.POSITIVE_INFINITY;
    let ky = Number.POSITIVE_INFINITY;
    if (dx !== 0) kx = cx / Math.abs(dx);
    if (dy !== 0) ky = cy / Math.abs(dy);
    const edge = Math.min(Math.max(1 / Math.min(kx, ky), 0), 1);

    const radians = Math.atan2(dy, dx);
    let degrees = radians * (180 / Math.PI) + 90;
    if (degrees < 0) degrees += 360;

    card.style.setProperty("--sdk-edge-proximity", `${(edge * 100).toFixed(3)}`);
    card.style.setProperty("--sdk-cursor-angle", `${degrees.toFixed(3)}deg`);
  };

  useEffect(() => {
    if (reducedMotion || !animated || !cardRef.current) return;

    const card = cardRef.current;
    const angleStart = 110;
    const angleEnd = 465;

    setSweepActive(true);
    card.style.setProperty("--sdk-cursor-angle", `${angleStart}deg`);

    animateValue({
      duration: 450,
      onUpdate: (v) => card.style.setProperty("--sdk-edge-proximity", `${v}`),
    });
    animateValue({
      ease: easeInCubic,
      duration: 1200,
      end: 50,
      onUpdate: (v) => {
        card.style.setProperty("--sdk-cursor-angle", `${((angleEnd - angleStart) * v) / 100 + angleStart}deg`);
      },
    });
    animateValue({
      ease: easeOutCubic,
      delay: 1200,
      duration: 1600,
      start: 50,
      end: 100,
      onUpdate: (v) => {
        card.style.setProperty("--sdk-cursor-angle", `${((angleEnd - angleStart) * v) / 100 + angleStart}deg`);
      },
    });
    animateValue({
      ease: easeInCubic,
      delay: 2200,
      duration: 1200,
      start: 100,
      end: 0,
      onUpdate: (v) => card.style.setProperty("--sdk-edge-proximity", `${v}`),
      onEnd: () => setSweepActive(false),
    });
  }, [animated, reducedMotion]);

  return (
    <div
      ref={cardRef}
      onPointerMove={onPointerMove}
      className={`${styles.sdkBorderGlowCard} ${sweepActive ? styles.sdkBorderGlowSweepActive : ""} ${className}`.trim()}
      style={cardStyle}
    >
      <span className={styles.sdkBorderGlowEdgeLight} />
      <div className={styles.sdkBorderGlowInner}>{children}</div>
    </div>
  );
}

