"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";

import { Sidebar } from "@/components/layout/sidebar";
import { Spinner } from "@/components/ui/primitives";
import { useAuth } from "@/lib/auth";

export default function AppLayout({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center gap-2 text-sm text-slate-500">
        <Spinner /> 正在加载…
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex h-screen items-center justify-center gap-2 text-sm text-slate-500">
        <Spinner /> 正在跳转登录…
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar currentPath={pathname} />
      <main className="min-w-0 flex-1">
        <div className="mx-auto max-w-7xl px-6 py-6">{children}</div>
      </main>
    </div>
  );
}
