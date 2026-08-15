"use client";

import { useState, useEffect, createContext, useContext } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { logout, subscribe, authState } from "@/lib/auth";

interface User {
  id: string;
  username: string;
}

interface AuthContextType {
  user: User | null;
}

const AuthContext = createContext<AuthContextType>({ user: null });
const useAuth = () => useContext(AuthContext);

const NAV_GROUPS = [
  {
    label: "运营操作",
    items: [
      { href: "/admin/crawl", label: "抓取管理", icon: "\u{1F4E5}" },
      { href: "/admin/process", label: "解析入库", icon: "\u{1F9F9}" },
      { href: "/admin/monitor", label: "系统监控", icon: "\u{1F4CA}" },
    ],
  },
  {
    label: "数据管理",
    items: [
      { href: "/admin/companies", label: "企业管理", icon: "\u{1F3EC}" },
      { href: "/admin/jobs", label: "职位管理", icon: "\u{1F4BC}" },
      { href: "/admin/company-sources", label: "公司来源", icon: "\u{1F517}" },
    ],
  },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const unsubscribe = subscribe((state) => setUser(state.user));
    return unsubscribe;
  }, []);

  const handleLogout = () => {
    logout();
    router.push("/admin/login");
  };

  return (
    <AuthContext.Provider value={{ user }}>
      <div className="flex min-h-[calc(100vh-120px)]">
        <aside
          className={"bg-white border-r border-gray-100 flex-shrink-0 transition-all duration-200 " + (collapsed ? "w-16" : "w-56")}
        >
          <div className="h-14 border-b border-gray-100 flex items-center justify-between px-4">
            {!collapsed && (
              <Link href="/admin" className="text-sm font-semibold text-gray-900 hover:text-blue-600 transition-colors">
                管理后台
              </Link>
            )}
            <button
              onClick={() => setCollapsed(!collapsed)}
              className="text-gray-400 hover:text-gray-600 p-1 rounded transition-colors"
              title={collapsed ? "\u5C55\u5F00" : "\u6536\u8D77"}
            >
              {collapsed ? "\u276F" : "\u276E"}
            </button>
          </div>

          <nav className="p-2 space-y-5">
            {NAV_GROUPS.map((group) => (
              <div key={group.label}>
                {!collapsed && (
                  <div className="px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider text-gray-400">
                    {group.label}
                  </div>
                )}
                <div className="space-y-0.5">
                  {group.items.map((item) => {
                    const active = pathname === item.href || pathname.startsWith(item.href + "/");
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        className={"flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors " + (active ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-600 hover:bg-gray-50 hover:text-gray-900")}
                        title={collapsed ? item.label : undefined}
                      >
                        <span className="text-sm flex-shrink-0">{item.icon}</span>
                        {!collapsed && <span>{item.label}</span>}
                      </Link>
                    );
                  })}
                </div>
              </div>
            ))}
          </nav>
        </aside>

        <div className="flex-1 flex flex-col min-w-0">
          <header className="h-14 bg-white border-b border-gray-100 px-6 flex items-center justify-between flex-shrink-0">
            <nav className="flex items-center gap-1.5 text-sm text-gray-400">
              <Link href="/admin" className="hover:text-gray-600 transition-colors">管理后台</Link>
              {pathname !== "/admin" && (
                <>
                  <span className="mx-1">/</span>
                  <span className="text-gray-700 font-medium">
                    {NAV_GROUPS.flatMap((g) => g.items).find((i) => i.href === pathname)?.label || ""}
                  </span>
                </>
              )}
            </nav>
            <div className="flex items-center gap-4">
              <span className="text-sm text-gray-500">{user ? `欢迎, ${user.username}` : ""}</span>
              <button
                onClick={handleLogout}
                className="text-sm text-gray-400 hover:text-red-600 transition-colors"
              >
                退出登录
              </button>
            </div>
          </header>

          <main className="flex-1 p-6 bg-gray-50/50 overflow-auto">
            {children}
          </main>
        </div>
      </div>
    </AuthContext.Provider>
  );
}