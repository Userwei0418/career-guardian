"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/stores/auth";

const navItems = [
  { href: "/opportunity", label: "机会守护" },
  { href: "/decision", label: "决策守护" },
  { href: "/rights", label: "权益守护" },
  { href: "/income", label: "收支守护" },
  { href: "/growth", label: "成长守护" },
];

const growthNavItems = [
  { href: "/growth", label: "成长总览", shortLabel: "总览", description: "查看当下、资产与方向的整体轨迹" },
  { href: "/growth/work", label: "当下的事", shortLabel: "当下的事", description: "跟进长期事项、会议和下一步" },
  { href: "/growth/assets", label: "过去的果", shortLabel: "过去的果", description: "沉淀作品、证据、能力与反思" },
  { href: "/growth/direction", label: "未来的路", shortLabel: "未来的路", description: "核对目标、市场温差与里程碑" },
];

function isGrowthItemActive(pathname: string | null, href: string) {
  if (href === "/growth") return pathname === href;
  return pathname === href || Boolean(pathname?.startsWith(`${href}/`));
}

function GuardianMenu({ pathname, onNavigate }: { pathname: string | null; onNavigate: () => void }) {
  return (
    <div
      role="menu"
      aria-label="切换守护模块"
      className="absolute left-0 top-full mt-2 w-56 overflow-hidden rounded-2xl border border-[var(--color-border-light)] bg-white p-2 shadow-xl"
    >
      <div className="px-3 pb-2 pt-1">
        <p className="text-[11px] font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">切换守护模块</p>
      </div>
      {navItems.map((item) => {
        const active = pathname === item.href || Boolean(pathname?.startsWith(`${item.href}/`));
        return (
          <Link
            key={item.href}
            href={item.href}
            role="menuitem"
            aria-current={active ? "page" : undefined}
            onClick={onNavigate}
            className={`group flex min-h-11 items-center gap-3 rounded-xl px-3 py-2.5 transition-colors ${active ? "bg-[var(--color-primary-light)]" : "hover:bg-[var(--color-bg-warm)]"}`}
          >
            <span className={`h-2 w-2 shrink-0 rounded-full ${active ? "bg-[var(--color-primary)]" : "bg-[var(--color-border)] group-hover:bg-[var(--color-primary)]"}`} />
            <span className={`min-w-0 flex-1 text-sm font-semibold ${active ? "text-[var(--color-primary-dark)]" : "text-[var(--color-text)]"}`}>{item.label}</span>
            {active && <span className="text-xs text-[var(--color-primary)]">当前</span>}
          </Link>
        );
      })}
    </div>
  );
}

function MobileGrowthMenu({ pathname, onNavigate }: { pathname: string | null; onNavigate: () => void }) {
  return (
    <div role="menu" aria-label="成长守护导航" className="absolute left-1/2 top-full mt-3 w-[min(22rem,calc(100vw-2rem))] -translate-x-1/2 rounded-2xl border border-[var(--color-border-light)] bg-white p-2 shadow-xl">
      <div className="px-3 pb-2 pt-1">
        <p className="text-[11px] font-semibold tracking-[0.16em] text-[var(--color-primary-dark)]">成长守护工作区</p>
        <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">当下的事，过去的果，未来的路</p>
      </div>
      {growthNavItems.map((item) => {
        const active = isGrowthItemActive(pathname, item.href);
        return (
          <Link key={item.href} href={item.href} role="menuitem" aria-current={active ? "page" : undefined} onClick={onNavigate} className={`flex min-h-12 items-center gap-3 rounded-xl px-3 py-2.5 ${active ? "bg-[var(--color-primary-light)]" : "hover:bg-[var(--color-bg-warm)]"}`}>
            <span className={`h-2 w-2 shrink-0 rounded-full ${active ? "bg-[var(--color-primary)]" : "bg-[var(--color-border)]"}`} />
            <span className="min-w-0 flex-1"><span className={`block text-sm font-semibold ${active ? "text-[var(--color-primary-dark)]" : "text-[var(--color-text)]"}`}>{item.label}</span><span className="block truncate text-xs text-[var(--color-text-muted)]">{item.description}</span></span>
          </Link>
        );
      })}
      <div className="my-2 border-t border-[var(--color-border-light)]" />
      <p className="px-3 pb-1 text-[11px] text-[var(--color-text-muted)]">切换其他守护</p>
      <div className="grid grid-cols-2 gap-1">
        {navItems.filter((item) => item.href !== "/growth").map((item) => <Link key={item.href} href={item.href} role="menuitem" onClick={onNavigate} className="rounded-xl px-3 py-2.5 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]">{item.label}</Link>)}
      </div>
    </div>
  );
}

export default function Navbar() {
  const pathname = usePathname();
  const { username, isAdmin, logout, restore } = useAuth();
  const [userDropdownOpen, setUserDropdownOpen] = useState(false);
  const [growthMenuOpen, setGrowthMenuOpen] = useState(false);
  const userDropdownRef = useRef<HTMLDivElement>(null);
  const growthDesktopRef = useRef<HTMLDivElement>(null);
  const growthMobileRef = useRef<HTMLDivElement>(null);
  const isGrowthRoute = pathname === "/growth" || Boolean(pathname?.startsWith("/growth/"));
  const currentGrowthItem = growthNavItems.find((item) => isGrowthItemActive(pathname, item.href)) || growthNavItems[0];

  useEffect(() => {
    restore();
  }, [restore]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (userDropdownRef.current && !userDropdownRef.current.contains(event.target as Node)) {
        setUserDropdownOpen(false);
      }
      const target = event.target as Node;
      if (
        !growthDesktopRef.current?.contains(target)
        && !growthMobileRef.current?.contains(target)
      ) {
        setGrowthMenuOpen(false);
      }
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setUserDropdownOpen(false);
        setGrowthMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  return (
    <header className="sticky top-0 z-50 border-b border-[var(--color-border-light)] bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-5 px-5 sm:px-6 lg:px-8">
        <Link href="/today" className="flex shrink-0 items-center gap-2" aria-label="职护首页">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-[var(--color-primary)] text-sm font-semibold text-white">护</span>
          <span className="hidden text-lg font-semibold tracking-tight text-[var(--color-primary-dark)] sm:inline">职护</span>
        </Link>

        <nav className="hidden min-w-0 flex-1 items-center justify-center gap-1 md:flex" aria-label="主导航">
          {isGrowthRoute ? <>
            <div ref={growthDesktopRef} className="relative mr-1">
              <button
                type="button"
                onClick={() => { setUserDropdownOpen(false); setGrowthMenuOpen((open) => !open); }}
                aria-expanded={growthMenuOpen}
                aria-haspopup="menu"
                className="flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-sm font-semibold text-[var(--color-primary-dark)] hover:bg-[var(--color-primary-light)]"
              >
                <span>成长守护</span>
                <span aria-hidden="true" className={`text-[10px] transition-transform ${growthMenuOpen ? "rotate-180" : ""}`}>▾</span>
              </button>
              {growthMenuOpen && <GuardianMenu pathname={pathname} onNavigate={() => setGrowthMenuOpen(false)} />}
            </div>
            <span className="mx-1 h-5 w-px bg-[var(--color-border)]" aria-hidden="true" />
            {growthNavItems.map((item) => {
              const active = isGrowthItemActive(pathname, item.href);
              return <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} className={`rounded-lg px-2.5 py-2 text-sm font-medium transition-colors ${active ? "bg-[var(--color-bg-warm)] text-[var(--color-primary-dark)]" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)] hover:text-[var(--color-text)]"}`}>{item.shortLabel}</Link>;
            })}
          </> : navItems.map((item) => {
            const isActive = pathname === item.href || pathname?.startsWith(`${item.href}/`);
            return <Link key={item.href} href={item.href} aria-current={isActive ? "page" : undefined} className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]" : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)] hover:text-[var(--color-text)]"}`}>{item.label}</Link>;
          })}
        </nav>

        {isGrowthRoute && <div ref={growthMobileRef} className="relative flex min-w-0 flex-1 justify-center md:hidden">
          <button
            type="button"
            onClick={() => { setUserDropdownOpen(false); setGrowthMenuOpen((open) => !open); }}
            aria-expanded={growthMenuOpen}
            aria-haspopup="menu"
            aria-label={`成长守护，当前：${currentGrowthItem.label}`}
            className="flex max-w-full items-center gap-1.5 rounded-xl bg-[var(--color-primary-light)] px-3 py-2 text-sm font-semibold text-[var(--color-primary-dark)]"
          >
            <span className="shrink-0">成长守护</span><span className="text-[var(--color-primary)]">·</span><span className="truncate">{currentGrowthItem.shortLabel}</span><span aria-hidden="true" className={`shrink-0 text-[9px] transition-transform ${growthMenuOpen ? "rotate-180" : ""}`}>▾</span>
          </button>
          {growthMenuOpen && <MobileGrowthMenu pathname={pathname} onNavigate={() => setGrowthMenuOpen(false)} />}
        </div>}

        <div className="ml-auto flex items-center gap-2" ref={userDropdownRef}>
          <Link href="/knowledge" className="hidden rounded-lg px-3 py-2 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)] lg:block">
            知识
          </Link>
          <button
            type="button"
            onClick={() => { setGrowthMenuOpen(false); setUserDropdownOpen((open) => !open); }}
            className="flex items-center gap-1.5 rounded-lg px-2 py-2 transition-colors hover:bg-[var(--color-bg-warm)] sm:px-3"
            aria-expanded={userDropdownOpen}
            aria-haspopup="menu"
          >
            <span className="text-sm font-medium text-[var(--color-text-secondary)] lg:hidden">我的</span>
            <span className="hidden max-w-28 truncate text-sm font-medium text-[var(--color-text-secondary)] lg:inline">{username || "我的职护"}</span>
            {isAdmin && <span className="hidden rounded-full bg-[var(--color-primary)] px-1.5 py-0.5 text-xs text-white xl:inline-flex">管理员</span>}
            <span className={`text-xs text-[var(--color-text-muted)] transition-transform ${userDropdownOpen ? "rotate-180" : ""}`} aria-hidden="true">▾</span>
          </button>

          {userDropdownOpen && (
            <div className="absolute right-5 top-full mt-1 w-48 rounded-xl border border-[var(--color-border-light)] bg-white py-1 shadow-lg sm:right-6 lg:right-8" role="menu">
              <Link href="/profile" onClick={() => setUserDropdownOpen(false)} className="block px-4 py-2.5 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]" role="menuitem">个人中心</Link>
              {isAdmin && <Link href="/admin" onClick={() => setUserDropdownOpen(false)} className="block px-4 py-2.5 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]" role="menuitem">管理后台</Link>}
              <div className="my-1 border-t border-[var(--color-border-light)]" />
              <button
                type="button"
                onClick={() => { setUserDropdownOpen(false); logout(); }}
                className="w-full px-4 py-2.5 text-left text-sm text-[var(--color-text-muted)] hover:bg-[var(--color-bg-warm)] hover:text-[var(--color-danger)]"
                role="menuitem"
              >
                退出登录
              </button>
            </div>
          )}
        </div>
      </div>

      {!isGrowthRoute && <nav className="flex gap-1 overflow-x-auto border-t border-[var(--color-border-light)] px-4 py-2 md:hidden" aria-label="移动端主导航">
        {navItems.map((item) => {
          const isActive = pathname === item.href || pathname?.startsWith(`${item.href}/`);
          return <Link key={item.href} href={item.href} aria-current={isActive ? "page" : undefined} className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium ${isActive ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]" : "text-[var(--color-text-secondary)]"}`}>{item.label}</Link>;
        })}
      </nav>}
    </header>
  );
}
