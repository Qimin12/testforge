"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Alert, Button, Field, Input } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login, user, loading } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "登录失败，请检查后端是否已启动");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-lg bg-brand-600 text-lg font-bold text-white">
            TF
          </div>
          <h1 className="text-lg font-semibold text-slate-900">登录 TestForge</h1>
          <p className="mt-1 text-xs text-slate-500">AI 驱动的全链路自动化测试平台</p>
        </div>

        <div className="card p-5">
          <form onSubmit={onSubmit} className="space-y-3">
            {error && <Alert tone="error">{error}</Alert>}

            <Field label="邮箱">
              <Input
                type="email"
                required
                autoComplete="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>

            <Field label="密码">
              <Input
                type="password"
                required
                autoComplete="current-password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>

            <Button type="submit" variant="primary" className="w-full" loading={submitting}>
              登录
            </Button>
          </form>

          <p className="mt-4 text-center text-xs text-slate-500">
            还没有账号？
            <Link href="/register" className="ml-1 font-medium text-brand-600 hover:underline">
              立即注册
            </Link>
          </p>
        </div>

        <p className="mt-4 text-center text-[11px] text-slate-400">
          后端地址：{process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1"}
        </p>
      </div>
    </div>
  );
}
