"use client";

import {
  type CSSProperties,
  type Key,
  type ReactNode,
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import styles from "./LogoLoop.module.css";

type Direction = "left" | "right" | "up" | "down";

type LogoNodeItem = {
  node: ReactNode;
  title?: string;
  ariaLabel?: string;
  href?: string;
};

type LogoImageItem = {
  src: string;
  alt?: string;
  title?: string;
  href?: string;
  srcSet?: string;
  sizes?: string;
  width?: number;
  height?: number;
};

export type LogoItem = LogoNodeItem | LogoImageItem;

type LogoLoopProps = {
  logos: LogoItem[];
  speed?: number;
  direction?: Direction;
  width?: number | string;
  logoHeight?: number;
  gap?: number;
  pauseOnHover?: boolean;
  hoverSpeed?: number;
  fadeOut?: boolean;
  fadeOutColor?: string;
  scaleOnHover?: boolean;
  renderItem?: (item: LogoItem, key: Key) => ReactNode;
  ariaLabel?: string;
  className?: string;
  style?: CSSProperties;
};

function toCssLength(value: number | string | undefined): string | undefined {
  if (typeof value === "number") return `${value}px`;
  return value ?? undefined;
}

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(media.matches);
    onChange();
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  return reduced;
}

export const LogoLoop = memo(function LogoLoop({
  logos,
  speed = 120,
  direction = "left",
  width = "100%",
  logoHeight = 28,
  gap = 32,
  pauseOnHover,
  hoverSpeed,
  fadeOut = false,
  fadeOutColor,
  scaleOnHover = false,
  renderItem,
  ariaLabel = "Partner logos",
  className,
  style,
}: LogoLoopProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const seqRef = useRef<HTMLUListElement>(null);

  const [isHovered, setIsHovered] = useState(false);
  const [seqWidth, setSeqWidth] = useState(0);
  const [containerWidth, setContainerWidth] = useState(0);
  const prefersReducedMotion = usePrefersReducedMotion();

  useEffect(() => {
    const updateLayout = () => {
      const cWidth = Math.ceil(containerRef.current?.clientWidth ?? 0);
      const sWidth = Math.ceil(seqRef.current?.getBoundingClientRect().width ?? 0);
      if (cWidth > 0) setContainerWidth(cWidth);
      if (sWidth > 0) setSeqWidth(sWidth);
    };

    updateLayout();

    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", updateLayout);
      return () => window.removeEventListener("resize", updateLayout);
    }

    const observer = new ResizeObserver(updateLayout);
    if (containerRef.current) observer.observe(containerRef.current);
    if (seqRef.current) observer.observe(seqRef.current);
    return () => observer.disconnect();
  }, [logos, gap, logoHeight]);

  const effectiveHoverSpeed = useMemo(() => {
    if (hoverSpeed !== undefined) return hoverSpeed;
    if (pauseOnHover) return 0;
    return undefined;
  }, [hoverSpeed, pauseOnHover]);

  const hoverActive = isHovered && effectiveHoverSpeed !== undefined;
  const activeSpeedRaw = hoverActive ? effectiveHoverSpeed! : speed;
  const activeSpeed = Math.max(1, Math.abs(activeSpeedRaw));

  const moveLeft = useMemo(() => {
    if (direction === "up" || direction === "down") return true;
    const baseLeft = direction === "left";
    return speed < 0 ? !baseLeft : baseLeft;
  }, [direction, speed]);

  const durationSeconds = useMemo(() => {
    if (!seqWidth) return 24;
    return Math.max(8, seqWidth / activeSpeed);
  }, [seqWidth, activeSpeed]);

  const paused = prefersReducedMotion || (hoverActive && effectiveHoverSpeed === 0);

  const baseCopies = useMemo(() => {
    if (prefersReducedMotion) return 1;
    if (!seqWidth || !containerWidth) return 3;
    return Math.max(3, Math.ceil(containerWidth / seqWidth) + 2);
  }, [prefersReducedMotion, seqWidth, containerWidth]);

  const cssVariables = useMemo(
    () =>
      ({
        "--logoloop-gap": `${gap}px`,
        "--logoloop-logo-height": `${logoHeight}px`,
        "--logoloop-distance": `${Math.max(seqWidth, 1)}px`,
        "--logoloop-duration": `${durationSeconds}s`,
        ...(fadeOutColor ? { "--logoloop-fade-color": fadeOutColor } : {}),
      }) as CSSProperties,
    [gap, logoHeight, seqWidth, durationSeconds, fadeOutColor]
  );

  const rootClassName = useMemo(
    () =>
      [
        styles.logoloop,
        fadeOut ? styles.logoloopFade : "",
        scaleOnHover ? styles.logoloopScaleHover : "",
        !moveLeft ? styles.reverse : "",
        paused ? styles.paused : "",
        className ?? "",
      ]
        .filter(Boolean)
        .join(" "),
    [fadeOut, scaleOnHover, moveLeft, paused, className]
  );

  const renderLogoItem = useCallback(
    (item: LogoItem, key: Key) => {
      if (renderItem) {
        return (
          <li className={styles.logoItem} key={key} role="listitem">
            {renderItem(item, key)}
          </li>
        );
      }

      const isNodeItem = "node" in item;
      const content = isNodeItem ? (
        <span className={styles.logoNode} aria-hidden={!!item.href && !item.ariaLabel}>
          {item.node}
        </span>
      ) : (
        <img
          src={item.src}
          srcSet={item.srcSet}
          sizes={item.sizes}
          width={item.width}
          height={item.height}
          alt={item.alt ?? ""}
          title={item.title}
          loading="lazy"
          decoding="async"
          draggable={false}
        />
      );

      const itemAriaLabel = isNodeItem ? item.ariaLabel ?? item.title : item.alt ?? item.title;
      const itemContent = item.href ? (
        <a
          className={styles.logoLink}
          href={item.href}
          aria-label={itemAriaLabel || "Logo link"}
          target="_blank"
          rel="noreferrer noopener"
        >
          {content}
        </a>
      ) : (
        content
      );

      return (
        <li className={styles.logoItem} key={key} role="listitem">
          {itemContent}
        </li>
      );
    },
    [renderItem]
  );

  const lists = useMemo(
    () =>
      Array.from({ length: baseCopies }, (_, copyIndex) => (
        <ul
          className={styles.logoList}
          key={`copy-${copyIndex}`}
          role="list"
          aria-hidden={copyIndex > 0}
          ref={copyIndex === 0 ? seqRef : undefined}
        >
          {logos.map((item, itemIndex) => renderLogoItem(item, `${copyIndex}-${itemIndex}`))}
        </ul>
      )),
    [baseCopies, logos, renderLogoItem]
  );

  const containerStyle = useMemo(() => {
    const resolvedWidth = toCssLength(width);
    return {
      width: resolvedWidth ?? "100%",
      ...cssVariables,
      ...style,
    } as CSSProperties;
  }, [width, cssVariables, style]);

  return (
    <div ref={containerRef} className={rootClassName} style={containerStyle} role="region" aria-label={ariaLabel}>
      <div
        className={styles.logoTrack}
        onMouseEnter={() => {
          if (effectiveHoverSpeed !== undefined) setIsHovered(true);
        }}
        onMouseLeave={() => {
          if (effectiveHoverSpeed !== undefined) setIsHovered(false);
        }}
      >
        {lists}
      </div>
    </div>
  );
});