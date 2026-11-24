"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  IconBug,
  IconDashboard,
  IconFolder,
  IconList,
  IconLogout,
  IconSettings,
} from "@/components/icons";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "概览", icon: IconDashboard },
  { href: "/projects", label: "项目", icon: IconFolder },
  { href: "/executions", label: "执行记录", icon: IconList },
  { href: "/defects", label: "缺陷", icon: IconBug },
  { href: "/settings", label: "设置", icon: IconSettings },
];

export function Sidebar({ currentPath }: { currentPath: string }) {
  const { user, logout } = useAuth();

  return (
    <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="flex items-center gap-2 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-brand-600 text-sm font-bold text-white">
          TF
        </div>
        <div className="leading-tight">
          <p className="text-sm font-semibold text-slate-800">TestForge</p>
          <p className="text-[11px] text-slate-400">AI 自动化测试平台</p>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 px-2">
        {NAV.map((item) => {
          const active = currentPath === item.href || currentPath.startsWith(`${item.href}/`);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2 rounded-md px-2.5 py-2 text-sm transition",
                active
                  ? "bg-brand-50 font-medium text-brand-700"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
              )}
            >
              <Icon size={16} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-slate-200 p-3">
        <div className="mb-2 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-200 text-xs font-semibold text-slate-600">
            {(user?.nickname || user?.email || "?").slice(0, 1).toUpperCase()}
          </div>
          <div className="min-w-0 leading-tight">
            <p className="truncate text-xs font-medium text-slate-700">
              {user?.nickname || "未命名"}
            </p>
            <p className="truncate text-[11px] text-slate-400" title={user?.email}>
              {user?.email}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={logout}
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs text-slate-500 hover:bg-slate-100 hover:text-slate-700"
        >
          <IconLogout size={14} />
          退出登录
        </button>
      </div>
    </aside>
  );
}
