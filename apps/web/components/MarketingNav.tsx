"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowRight, Menu, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

type Props = {
  variant?: "landing" | "default";
};

type NavItem = {
  href: string;
  label: string;
  kind: "route" | "anchor";
};

const LANDING_ITEMS: NavItem[] = [
  { href: "#product", label: "Produto", kind: "anchor" },
  { href: "#how", label: "Como funciona", kind: "anchor" },
  { href: "#sdk", label: "SDK", kind: "anchor" },
  { href: "/docs", label: "Documentação", kind: "route" },
  { href: "/changelog", label: "Changelog", kind: "route" },
];

const DEFAULT_ITEMS: NavItem[] = [
  { href: "/docs", label: "Documentação", kind: "route" },
  { href: "/changelog", label: "Changelog", kind: "route" },
];

const GOOEY_PARTICLE_COUNT = 7;
const GOOEY_OUTER_DISTANCE = 38;
const GOOEY_INNER_DISTANCE = 9;
const GOOEY_ANIMATION_TIME = 520;
const GOOEY_TIME_VARIANCE = 160;
const GOOEY_COLORS = ["#29DFFF", "#5B7CFF", "#48FCA5", "#7E87FF"];

function isActive(item: NavItem, pathname: string, hash: string) {
  if (item.kind === "anchor") {
    return pathname === "/" && hash === item.href;
  }

  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

function randomNoise(amount = 1) {
  return amount / 2 - Math.random() * amount;
}

function polar(distance: number, index: number, total: number) {
  const angle = ((360 + randomNoise(8)) / total) * index * (Math.PI / 180);
  return [distance * Math.cos(angle), distance * Math.sin(angle)];
}

export function MarketingNav({ variant = "default" }: Props) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [hash, setHash] = useState("");
  const [visualIndex, setVisualIndex] = useState(0);
  const [canAnimateGooey, setCanAnimateGooey] = useState(false);

  const navItems = useMemo(() => {
    return variant === "landing" ? LANDING_ITEMS : DEFAULT_ITEMS;
  }, [variant]);

  const desktopNavRef = useRef<HTMLElement | null>(null);
  const gooeyPillRef = useRef<HTMLSpanElement | null>(null);
  const linkRefs = useRef<(HTMLAnchorElement | null)[]>([]);
  const particleTimersRef = useRef<number[]>([]);

  const clearParticleTimers = () => {
    for (const timerId of particleTimersRef.current) {
      window.clearTimeout(timerId);
    }
    particleTimersRef.current = [];
  };

  const clearParticles = () => {
    if (!gooeyPillRef.current) return;
    const particles = gooeyPillRef.current.querySelectorAll(".mk-gooey__particle");
    particles.forEach((particle) => particle.remove());
    clearParticleTimers();
  };

  const spawnParticles = () => {
    if (!gooeyPillRef.current || !canAnimateGooey) return;

    clearParticles();

    for (let i = 0; i < GOOEY_PARTICLE_COUNT; i += 1) {
      const [startX, startY] = polar(GOOEY_OUTER_DISTANCE, GOOEY_PARTICLE_COUNT - i, GOOEY_PARTICLE_COUNT);
      const [endX, endY] = polar(
        GOOEY_INNER_DISTANCE + randomNoise(4),
        GOOEY_PARTICLE_COUNT - i,
        GOOEY_PARTICLE_COUNT
      );
      const duration = GOOEY_ANIMATION_TIME + randomNoise(GOOEY_TIME_VARIANCE * 2);
      const scale = 0.6 + Math.random() * 0.55;
      const size = 4 + Math.random() * 3;
      const color = GOOEY_COLORS[Math.floor(Math.random() * GOOEY_COLORS.length)];
      const rotate = randomNoise(20);

      const particle = document.createElement("span");
      const point = document.createElement("span");
      particle.className = "mk-gooey__particle";
      point.className = "mk-gooey__point";
      particle.style.setProperty("--start-x", `${startX}px`);
      particle.style.setProperty("--start-y", `${startY}px`);
      particle.style.setProperty("--end-x", `${endX}px`);
      particle.style.setProperty("--end-y", `${endY}px`);
      particle.style.setProperty("--duration", `${Math.max(320, duration)}ms`);
      particle.style.setProperty("--scale", `${scale}`);
      particle.style.setProperty("--size", `${size}px`);
      particle.style.setProperty("--color", color);
      particle.style.setProperty("--rotate", `${rotate}deg`);

      particle.appendChild(point);
      gooeyPillRef.current.appendChild(particle);

      const timerId = window.setTimeout(() => {
        particle.remove();
      }, Math.max(320, duration));
      particleTimersRef.current.push(timerId);
    }
  };

  const updatePillPosition = (index: number, withParticles: boolean) => {
    const linkEl = linkRefs.current[index];
    if (!desktopNavRef.current || !gooeyPillRef.current || !linkEl) return;

    const navRect = desktopNavRef.current.getBoundingClientRect();
    const linkRect = linkEl.getBoundingClientRect();

    const left = linkRect.left - navRect.left;
    const top = linkRect.top - navRect.top;
    const width = linkRect.width;
    const height = linkRect.height;

    gooeyPillRef.current.style.setProperty("--x", `${left}px`);
    gooeyPillRef.current.style.setProperty("--y", `${top}px`);
    gooeyPillRef.current.style.setProperty("--w", `${width}px`);
    gooeyPillRef.current.style.setProperty("--h", `${height}px`);
    gooeyPillRef.current.classList.add("is-ready");

    if (withParticles) {
      spawnParticles();
    }
  };

  useEffect(() => {
    const syncHash = () => {
      setHash(window.location.hash || "");
    };

    syncHash();
    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, []);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname, hash]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [menuOpen]);

  useEffect(() => {
    const activeIndex = navItems.findIndex((item) => isActive(item, pathname, hash));
    setVisualIndex(activeIndex >= 0 ? activeIndex : 0);
  }, [hash, navItems, pathname]);

  useEffect(() => {
    const desktopMedia = window.matchMedia("(min-width: 881px)");
    const reducedMotionMedia = window.matchMedia("(prefers-reduced-motion: reduce)");

    const syncFlags = () => {
      setCanAnimateGooey(desktopMedia.matches && !reducedMotionMedia.matches);
    };

    syncFlags();
    desktopMedia.addEventListener("change", syncFlags);
    reducedMotionMedia.addEventListener("change", syncFlags);

    return () => {
      desktopMedia.removeEventListener("change", syncFlags);
      reducedMotionMedia.removeEventListener("change", syncFlags);
    };
  }, []);

  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => {
      updatePillPosition(visualIndex, false);
    });

    return () => window.cancelAnimationFrame(frameId);
  }, [visualIndex, canAnimateGooey]);

  useEffect(() => {
    if (!desktopNavRef.current) return;

    const observer = new ResizeObserver(() => {
      updatePillPosition(visualIndex, false);
    });
    observer.observe(desktopNavRef.current);

    return () => observer.disconnect();
  }, [visualIndex]);

  useEffect(() => {
    return () => {
      clearParticles();
    };
  }, []);

  const onDesktopItemClick = (index: number, onNavigate?: () => void) => {
    setVisualIndex(index);
    window.requestAnimationFrame(() => {
      updatePillPosition(index, true);
    });

    if (onNavigate) {
      onNavigate();
    }
  };

  const renderDesktopItem = (item: NavItem, index: number) => {
    const active = isActive(item, pathname, hash);
    const className = active ? "is-active" : undefined;
    const ariaCurrent = active ? "page" : undefined;

    if (item.kind === "route") {
      return (
        <Link
          key={item.href}
          href={item.href}
          className={className}
          aria-current={ariaCurrent}
          ref={(el) => {
            linkRefs.current[index] = el;
          }}
          onClick={() => onDesktopItemClick(index)}
        >
          {item.label}
        </Link>
      );
    }

    return (
      <a
        key={item.href}
        href={item.href}
        className={className}
        aria-current={ariaCurrent}
        ref={(el) => {
          linkRefs.current[index] = el;
        }}
        onClick={() => onDesktopItemClick(index)}
      >
        {item.label}
      </a>
    );
  };

  const renderMobileItem = (item: NavItem, onNavigate: () => void) => {
    const active = isActive(item, pathname, hash);
    const className = active ? "is-active" : undefined;
    const ariaCurrent = active ? "page" : undefined;

    if (item.kind === "route") {
      return (
        <Link key={item.href} href={item.href} className={className} aria-current={ariaCurrent} onClick={onNavigate}>
          {item.label}
        </Link>
      );
    }

    return (
      <a key={item.href} href={item.href} className={className} aria-current={ariaCurrent} onClick={onNavigate}>
        {item.label}
      </a>
    );
  };

  return (
    <header className={`mk-nav${menuOpen ? " is-open" : ""}`}>
      <div className="mk-nav__row">
        <Link href="/" className="mk-brand">
          <img src="/brand/mark-evalops.svg" alt="" />
          <span>
            EvalOps<span className="sub">Studio</span>
          </span>
        </Link>

        <nav className="mk-nav__links mk-gooey" aria-label="Navegação principal" ref={desktopNavRef}>
          <span className={`mk-gooey__pill${canAnimateGooey ? " is-gooey" : ""}`} ref={gooeyPillRef} aria-hidden="true">
            <span className="mk-gooey__core" />
          </span>
          {navItems.map((item, index) => renderDesktopItem(item, index))}
        </nav>

        <span className="mk-nav__spacer" />

        <div className="mk-nav__actions">
          <Link className="mk-btn mk-btn--ghost" href="/login">
            Entrar
          </Link>
          <Link className="mk-btn mk-btn--primary" href="/register">
            Abrir dashboard
            <ArrowRight />
          </Link>
        </div>

        <button
          type="button"
          className="mk-nav__menu-btn"
          onClick={() => setMenuOpen((open) => !open)}
          aria-expanded={menuOpen}
          aria-controls="mk-mobile-menu"
          aria-label={menuOpen ? "Fechar menu" : "Abrir menu"}
        >
          {menuOpen ? <X /> : <Menu />}
        </button>
      </div>

      <div className="mk-nav__mobile" id="mk-mobile-menu" aria-hidden={!menuOpen}>
        <nav className="mk-nav__mobile-links" aria-label="Navegação mobile">
          {navItems.map((item) => renderMobileItem(item, () => setMenuOpen(false)))}
        </nav>
        <div className="mk-nav__mobile-actions">
          <Link className="mk-btn mk-btn--ghost mk-btn--block" href="/login" onClick={() => setMenuOpen(false)}>
            Entrar
          </Link>
          <Link className="mk-btn mk-btn--primary mk-btn--block" href="/register" onClick={() => setMenuOpen(false)}>
            Abrir dashboard
            <ArrowRight />
          </Link>
        </div>
      </div>
    </header>
  );
}
