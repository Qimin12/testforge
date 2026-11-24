"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { Alert, Button, Field, Input } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** 与后端 validate_password_strength 保持一致的提示 */
function passwordHint(password: string): string | null {
  if (!password) return null;
  if (password.length < 8) return "密码至少 8 位";
  const classes =
    Number(/[A-Za-z]/.test(password)) +
    Number(/\d/.test(password)) +
    Number(/[^A-Za-z0-9]/.test(password));
  if (classes < 2) return "需包含字母、数字、特殊字符中至少两种";
  return null;
}

export default function RegisterPage() {
  const { register, user, loading } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [nickname, setNickname] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  const hint = useMemo(() => passwordHint(password), [password]);
  const mismatch = confirm.length > 0 && confirm !== password;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (hint) {
      setError(hint);
      return;
    }
    if (password !== confirm) {
      setError("两次输入的密码不一致");
      return;
    }
    setSubmitting(true);
    try {
      await register(email.trim(), password, nickname.trim());
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "注册失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <h1 className="text-lg font-semibold text-slate-900">注册 TestForge</h1>
          <p className="mt-1 text-xs text-slate-500">创建账号后即可导入 API 文档并自动生成用例</p>
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

            <Field label="昵称" hint="可留空，默认取邮箱前缀">
              <Input value={nickname} onChange={(e) => setNickname(e.target.value)} maxLength={50} />
            </Field>

            <Field label="密码" error={hint ?? undefined} hint="至少 8 位，含字母/数字/特殊字符中两种">
              <Input
                type="password"
                required
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>

            <Field label="确认密码" error={mismatch ? "两次输入不一致" : undefined}>
              <Input
                type="password"
                required
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </Field>

            <Button type="submit" variant="primary" className="w-full" loading={submitting}>
              注册并登录
            </Button>
          </form>

          <p className="mt-4 text-center text-xs text-slate-500">
            已有账号？
            <Link href="/login" className="ml-1 font-medium text-brand-600 hover:underline">
              去登录
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
