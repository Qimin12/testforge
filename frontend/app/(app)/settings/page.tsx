"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { IconCopy, IconDatabase, IconKey, IconPlus, IconTrash } from "@/components/icons";
import { Dialog } from "@/components/ui/dialog";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Field,
  Input,
  Spinner,
  Textarea,
} from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { API_BASE, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApiKeys, useCreateApiKey, useDeleteApiKey, useUpdateProfile } from "@/lib/queries";
import { formatDateTime } from "@/lib/utils";

interface HealthInfo {
  status: string;
  version?: string;
  env?: string;
  database?: { driver?: string; auto_create_tables?: boolean };
  checkpointer?: { kind?: string };
  llm?: { provider?: string; mock?: boolean; model_large?: string; model_small?: string };
  review_required?: boolean;
}

const HEALTH_URL = API_BASE.replace(/\/api\/v1\/?$/, "") + "/health";

export default function SettingsPage() {
  const { user, refreshUser } = useAuth();
  const toast = useToast();

  const updateProfile = useUpdateProfile();
  const apiKeys = useApiKeys();
  const createKey = useCreateApiKey();
  const deleteKey = useDeleteApiKey();

  const [profile, setProfile] = useState({
    nickname: user?.nickname ?? "",
    bio: user?.bio ?? "",
  });
  const [createOpen, setCreateOpen] = useState(false);
  const [keyName, setKeyName] = useState("ci");
  const [newKey, setNewKey] = useState<string | null>(null);

  // /health 在 API 前缀之外，直接用 fetch，不走 api 客户端
  const health = useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const response = await fetch(HEALTH_URL, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return (await response.json()) as HealthInfo;
    },
    retry: 0,
  });

  async function saveProfile() {
    try {
      await updateProfile.mutateAsync({
        nickname: profile.nickname.trim(),
        bio: profile.bio.trim(),
      });
      await refreshUser();
      toast.success("资料已更新");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "保存失败");
    }
  }

  async function doCreateKey() {
    try {
      const created = await createKey.mutateAsync(keyName.trim() || "default");
      setNewKey(created.full_key);
      setCreateOpen(false);
      toast.success("API Key 已创建，请立即复制");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "创建失败");
    }
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">设置</h1>
        <p className="mt-1 text-sm text-slate-500">个人资料、API Key 与运行环境信息。</p>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="个人资料" description="昵称和简介会显示在侧边栏" />
          <CardBody className="space-y-3">
            <Field label="邮箱">
              <Input value={user?.email ?? ""} disabled />
            </Field>
            <Field label="昵称">
              <Input
                value={profile.nickname}
                maxLength={50}
                onChange={(e) => setProfile({ ...profile, nickname: e.target.value })}
              />
            </Field>
            <Field label="简介">
              <Textarea
                rows={3}
                className="font-sans text-sm"
                value={profile.bio}
                onChange={(e) => setProfile({ ...profile, bio: e.target.value })}
              />
            </Field>
            <div className="flex justify-end">
              <Button variant="primary" loading={updateProfile.isPending} onClick={saveProfile}>
                保存
              </Button>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="API Key"
            description="给 CI/CD 或脚本调用用；完整值只在创建时显示一次"
            actions={
              <Button variant="primary" size="sm" onClick={() => setCreateOpen(true)}>
                <IconPlus size={14} /> 新建
              </Button>
            }
          />
          <CardBody className="space-y-2">
            {newKey && (
              <Alert tone="success">
                <p className="mb-1 font-medium">新 Key（现在复制，关掉就看不到了）</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 break-all rounded bg-white/70 px-2 py-1 text-xs">
                    {newKey}
                  </code>
                  <Button
                    size="sm"
                    onClick={async () => {
                      await navigator.clipboard.writeText(newKey);
                      toast.success("已复制");
                    }}
                  >
                    <IconCopy size={12} /> 复制
                  </Button>
                </div>
                <button
                  type="button"
                  className="mt-2 text-xs underline"
                  onClick={() => setNewKey(null)}
                >
                  我已保存，隐藏
                </button>
              </Alert>
            )}

            {apiKeys.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Spinner size={14} /> 加载中…
              </div>
            ) : (apiKeys.data ?? []).length === 0 ? (
              <p className="py-4 text-center text-xs text-slate-500">还没有 API Key。</p>
            ) : (
              <div className="space-y-1.5">
                {(apiKeys.data ?? []).map((key) => (
                  <div
                    key={key.id}
                    className="flex items-center justify-between rounded border border-slate-200 px-2.5 py-2"
                  >
                    <div className="min-w-0">
                      <p className="flex items-center gap-1.5 text-sm text-slate-800">
                        <IconKey size={13} className="text-slate-400" />
                        {key.name}
                        {!key.is_active && <Badge>已停用</Badge>}
                      </p>
                      <p className="font-mono text-[11px] text-slate-500">{key.prefix}…</p>
                      <p className="text-[11px] text-slate-400">
                        创建 {formatDateTime(key.created_at)}
                        {key.last_used_at ? ` · 最近使用 ${formatDateTime(key.last_used_at)}` : ""}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-red-600 hover:bg-red-50"
                      onClick={async () => {
                        if (!window.confirm(`删除 API Key「${key.name}」？`)) return;
                        try {
                          await deleteKey.mutateAsync(key.id);
                          toast.success("已删除");
                        } catch (err) {
                          toast.error(err instanceof ApiError ? err.detail : "删除失败");
                        }
                      }}
                    >
                      <IconTrash size={13} />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="运行环境"
          description="来自后端 /health，出问题时先看这里"
          actions={
            <Button size="sm" onClick={() => health.refetch()}>
              重新检测
            </Button>
          }
        />
        <CardBody>
          {health.isLoading ? (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Spinner size={14} /> 检测中…
            </div>
          ) : health.isError ? (
            <Alert tone="error">
              连不上后端 {API_BASE}。请确认 `uvicorn app.main:app` 已启动，且 CORS 允许当前地址。
            </Alert>
          ) : (
            <div className="grid gap-2 sm:grid-cols-2">
              <Info
                label="后端版本"
                value={`${health.data?.version ?? "?"} · ${health.data?.env ?? "?"}`}
              />
              <Info label="数据库" value={health.data?.database?.driver ?? "?"} />
              <Info
                label="LangGraph 检查点"
                value={health.data?.checkpointer?.kind ?? "?"}
              />
              <Info
                label="模型"
                value={
                  health.data?.llm?.mock
                    ? "mock（未调用真实模型）"
                    : `${health.data?.llm?.provider ?? "?"} / ${health.data?.llm?.model_large ?? "?"}`
                }
              />
              <Info
                label="小模型"
                value={health.data?.llm?.mock ? "—" : (health.data?.llm?.model_small ?? "?")}
              />
              <Info
                label="用例审核"
                value={health.data?.review_required ? "开启（会中断等确认）" : "关闭（全自动）"}
              />
            </div>
          )}
          <p className="mt-3 flex items-center gap-1 text-[11px] text-slate-400">
            <IconDatabase size={12} /> API 地址：{API_BASE}
          </p>
        </CardBody>
      </Card>

      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="新建 API Key"
        description="名称只是给你自己看的备注，例如 ci、postman"
        footer={
          <>
            <Button onClick={() => setCreateOpen(false)}>取消</Button>
            <Button variant="primary" loading={createKey.isPending} onClick={doCreateKey}>
              创建
            </Button>
          </>
        }
      >
        <Field label="名称">
          <Input
            autoFocus
            value={keyName}
            maxLength={100}
            onChange={(e) => setKeyName(e.target.value)}
            placeholder="ci"
          />
        </Field>
      </Dialog>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-slate-100 py-1.5 last:border-0">
      <span className="text-xs text-slate-500">{label}</span>
      <span className="text-right text-xs font-medium text-slate-800">{value}</span>
    </div>
  );
}
