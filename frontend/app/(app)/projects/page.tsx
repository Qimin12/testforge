"use client";

import Link from "next/link";
import { useState } from "react";

import { IconChevronRight, IconPlus, IconSearch } from "@/components/icons";
import { Dialog } from "@/components/ui/dialog";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Spinner,
} from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api";
import { useCreateProject, useProjects } from "@/lib/queries";
import { STATUS_STYLES, cn, formatDateTime } from "@/lib/utils";

export default function ProjectsPage() {
  const toast = useToast();
  const [keyword, setKeyword] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", target_base_url: "" });

  const projects = useProjects({ keyword: keyword || undefined, limit: 50 });
  const createProject = useCreateProject();

  async function submit() {
    if (!form.name.trim()) {
      toast.error("项目名称不能为空");
      return;
    }
    try {
      await createProject.mutateAsync({
        name: form.name.trim(),
        description: form.description.trim() || undefined,
        target_base_url: form.target_base_url.trim() || undefined,
      });
      toast.success("项目已创建");
      setOpen(false);
      setForm({ name: "", description: "", target_base_url: "" });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "创建失败");
    }
  }

  const rows = projects.data?.items ?? [];

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">项目</h1>
          <p className="mt-1 text-sm text-slate-500">
            每个项目对应一个被测服务，导入 OpenAPI 文档后即可生成用例。
          </p>
        </div>
        <Button variant="primary" onClick={() => setOpen(true)}>
          <IconPlus size={14} /> 新建项目
        </Button>
      </header>

      <div className="flex items-center gap-2">
        <div className="relative w-72">
          <span className="pointer-events-none absolute left-2.5 top-2.5 text-slate-400">
            <IconSearch size={14} />
          </span>
          <Input
            className="pl-8"
            placeholder="搜索项目名称或描述"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </div>
        {projects.isFetching && <Spinner size={14} className="text-slate-400" />}
        <span className="text-xs text-slate-500">共 {projects.data?.total ?? 0} 个</span>
      </div>

      <Card>
        {projects.isLoading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500">
            <Spinner /> 加载中…
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            title="还没有项目"
            description="建一个项目，填上被测服务的地址，再导入 OpenAPI 文档。"
            action={
              <Button variant="primary" onClick={() => setOpen(true)}>
                新建第一个项目
              </Button>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>名称</th>
                  <th>状态</th>
                  <th>接口</th>
                  <th>用例</th>
                  <th>被测地址</th>
                  <th>创建时间</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((project) => (
                  <tr key={project.id}>
                    <td>
                      <Link
                        href={`/projects/${project.id}`}
                        className="font-medium text-slate-800 hover:text-brand-700"
                      >
                        {project.name}
                      </Link>
                      {project.description && (
                        <p className="mt-0.5 max-w-md truncate text-xs text-slate-400">
                          {project.description}
                        </p>
                      )}
                    </td>
                    <td>
                      <Badge className={cn(STATUS_STYLES[project.status])}>{project.status}</Badge>
                    </td>
                    <td className="tabular-nums text-xs text-slate-600">
                      {project.operation_count}
                    </td>
                    <td className="tabular-nums text-xs text-slate-600">{project.case_count}</td>
                    <td className="font-mono text-xs text-slate-500">
                      {project.target_base_url || "—"}
                    </td>
                    <td className="text-xs text-slate-500">{formatDateTime(project.created_at)}</td>
                    <td className="text-right">
                      <Link
                        href={`/projects/${project.id}`}
                        className="inline-flex items-center gap-0.5 text-xs font-medium text-brand-600 hover:underline"
                      >
                        打开 <IconChevronRight size={12} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="新建项目"
        description="被测服务地址可以稍后在项目详情里改"
        footer={
          <>
            <Button onClick={() => setOpen(false)}>取消</Button>
            <Button variant="primary" loading={createProject.isPending} onClick={submit}>
              创建
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Field label="项目名称">
            <Input
              autoFocus
              value={form.name}
              maxLength={100}
              placeholder="例如：订单服务 API"
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="描述" hint="可选">
            <Input
              value={form.description}
              placeholder="这个项目测什么"
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </Field>
          <Field
            label="被测服务地址"
            hint="例如 http://localhost:8080；也可从 OpenAPI 的 servers 自动读取"
          >
            <Input
              value={form.target_base_url}
              placeholder="http://127.0.0.1:8080"
              onChange={(e) => setForm({ ...form, target_base_url: e.target.value })}
            />
          </Field>
        </div>
      </Dialog>
    </div>
  );
}
