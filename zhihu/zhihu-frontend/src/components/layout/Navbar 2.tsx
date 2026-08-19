"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/stores/auth";
import { PERSONAS } from "@/lib/personas";

const navItems = [
  { href: "/knowledge", label: "知识学堂", icon: "📚" },
  { href: "/journey", label: "我的旅程", icon: "🗺️" },
  { href: "/profile", label: "我的档案", icon: "👤" },
];

export default function Navbar() {
  const pathname = usePathname();
  const { username, isAdmin, logout } = useAuth();
  const [userDropdownOpen, setUserDropdownOpen] = useState(false);
  const [personaDropdownOpen, setPersonaDropdownOpen] = useState(false);
  const userDropdownRef = useRef<HTMLDivElement>(null);
  const personaDropdownRef = useRef<HTMLDivElement>(null);

  const isPersonaActive = pathname?.startsWith("/persona");

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (userDropdownRef.current && !userDropdownRef.current.contains(e.target as Node)) {
        setUserDropdownOpen(false);
      }
      if (personaDropdownRef.current && !personaDropdownRef.current.contains(e.target as Node)) {
        setPersonaDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <header className="bg-white border-b border-[var(--color-border-light)] sticky top-0 z-50">
      <div className="max-w-5xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link href="/today" className="flex items-center gap-2">
          <span className="text-xl">🛡️</span>
          <span className="text-lg font-semibold text-[var(--color-primary)]">职护</span>
        </Link>

        <nav className="flex items-center gap-0.5">
          {/* 专场下拉 */}
          <div className="relative" ref={personaDropdownRef}>
            <button
              onClick={() => setPersonaDropdownOpen(!personaDropdownOpen)}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-1 ${
                isPersonaActive
                  ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]"
              }`}
            >
              <span>🎯</span>
              专场
              <span className={`text-[10px] transition-transform ${personaDropdownOpen ? "rotate-180" : ""}`}>▼</span>
            </button>

            {personaDropdownOpen && (
              <div className="absolute left-0 top-full mt-1 w-56 bg-white rounded-xl shadow-lg border border-[var(--color-border-light)] py-1 z-50">
                {PERSONAS.map((p) => (
                  <Link
                    key={p.id}
                    href={`/persona/${p.id}`}
                    onClick={() => setPersonaDropdownOpen(false)}
                    className={`flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                      pathname === `/persona/${p.id}`
                        ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]"
                        : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]"
                    }`}
                  >
                    <span className="text-lg">{p.icon}</span>
                    <div>
                      <p className="font-medium">{p.title}</p>
                      <p className="text-xs text-[var(--color-text-muted)]">{p.subtitle}</p>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>

          {/* 固定导航项 */}
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                pathname === item.href || pathname?.startsWith(item.href + "/")
                  ? "bg-[var(--color-primary-light)] text-[var(--color-primary-dark)]"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)]"
              }`}
            >
              <span className="mr-1">{item.icon}</span>
              {item.label}
            </Link>
          ))}
        </nav>

        {/* 用户下拉 */}
        <div className="relative" ref={userDropdownRef}>
          <button
            onClick={() => setUserDropdownOpen(!userDropdownOpen)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-[var(--color-bg-warm)] transition-colors"
          >
            <span className="text-sm font-medium text-[var(--color-text-secondary)]">{username}</span>
            {isAdmin && <span className="text-xs bg-[var(--color-primary)] text-white px-1.5 py-0.5 rounded-full">管理员</span>}
            <span className={`text-xs text-[var(--color-text-muted)] transition-transform ${userDropdownOpen ? "rotate-180" : ""}`}>▼</span>
          </button>

          {userDropdownOpen && (
            <div className="absolute right-0 top-full mt-1 w-48 bg-white rounded-xl shadow-lg border border-[var(--color-border-light)] py-1 z-50">
              <Link
                href="/dashboard"
                onClick={() => setUserDropdownOpen(false)}
                className="flex items-center gap-2 px-4 py-2.5 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)] transition-colors"
              >
                <span>📊</span> 管理中心
              </Link>
              {isAdmin && (
                <Link
                  href="/admin"
                  onClick={() => setUserDropdownOpen(false)}
                  className="flex items-center gap-2 px-4 py-2.5 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-warm)] transition-colors"
                >
                  <span>⚙️</span> 管理后台
                </Link>
              )}
              <div className="border-t border-[var(--color-border-light)] my-1" />
              <button
                onClick={() => { setUserDropdownOpen(false); logout(); }}
                className="flex items-center gap-2 w-full px-4 py-2.5 text-sm text-[var(--color-text-muted)] hover:bg-[var(--color-bg-warm)] hover:text-[var(--color-danger)] transition-colors"
              >
                <span>🚪</span> 退出登录
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
