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

export default function Navbar() {
  const pathname = usePathname();
  const { username, isAdmin, logout, restore } = useAuth();
  const [userDropdownOpen, setUserDropdownOpen] = useState(false);
  const userDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    restore();
  }, [restore]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (userDropdownRef.current && !userDropdownRef.current.contains(event.target as Node)) {
        setUserDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <header className="sticky top-0 z-50 border-b border-[var(--color-border-light)] bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-5 px-5 sm:px-6 lg:px-8">
        <Link href="/today" className="flex shrink-0 items-center gap-2" aria-label="职护首页">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-[var(--color-primary)] text-sm font-semibold text-white">护</span>
          <span className="text-lg font-semibold tracking-tight text-[var(--color-primary-dark)]">职护</span>
        </Link>

        <nav className="hidden min-w-0 flex-1 items-center justify-center gap-1 md:flex" aria-label="主导航">
          {navItems.map((item) => {
            const isActive = pathname === item.href || pathname?.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive ? "page" : undefined}
                className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]"
                    : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)] hover:text-[var(--color-text)]"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2" ref={userDropdownRef}>
          <Link href="/knowledge" className="hidden rounded-lg px-3 py-2 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)] lg:block">
            知识
          </Link>
          <button
            type="button"
            onClick={() => setUserDropdownOpen((open) => !open)}
            className="flex items-center gap-2 rounded-lg px-3 py-2 transition-colors hover:bg-[var(--color-bg-warm)]"
            aria-expanded={userDropdownOpen}
            aria-haspopup="menu"
          >
            <span className="max-w-28 truncate text-sm font-medium text-[var(--color-text-secondary)]">{username || "我的职护"}</span>
            {isAdmin && <span className="rounded-full bg-[var(--color-primary)] px-1.5 py-0.5 text-xs text-white">管理员</span>}
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

      <nav className="flex gap-1 overflow-x-auto border-t border-[var(--color-border-light)] px-4 py-2 md:hidden" aria-label="移动端主导航">
        {navItems.map((item) => {
          const isActive = pathname === item.href || pathname?.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium ${isActive ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]" : "text-[var(--color-text-secondary)]"}`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
