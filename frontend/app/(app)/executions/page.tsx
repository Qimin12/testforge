"use client";

import Link from "next/link";
import { useState } from "react";

import { IconChevronRight } from "@/components/icons";
import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  ProgressBar,
  Select,
  Spinner,
} from "@/components/ui/primitives";
import { useExecutions, useProjects } from "@/lib/queries";
import {
  STATUS_STYLES,
  cn,
  formatDateTime,
  formatDuration,
  formatPercent,
} from "@/lib/utils";

const STATUS_OPTIONS = [
  { value: "", label: "全部状态" },
  { value: "success", label: "success" },
  { value: "failed", label: "failed" },
  { value: "interrupted", label: "interrupted" },
  { value: "running", label: "running" },
];

export default function ExecutionsPage() {
  const [status, setStatus] = useState("");
  const [projectId, setProjectId] = useState("");

  const projects = useProjects({ limit: 100 });
  const executions = useExecutions({
    status: status || undefined,
    project_id: projectId || undefined,
    limit: 50,
  });

  const projectName = (id: string) =>
    projects.data?.items.find((item) => item.id === id)?.name ?? id.slice(0, 8);

  const rows = executions.data?.items ?? [];

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">执行记录</h1>
        <p className="mt-1 text-sm text-slate-500">
          每次运行都会留下完整结果：通过率、逐条结果、缺陷与报告。
        </p>
      </header>

      <Card>
        <CardHeader
          title={`共 ${executions.data?.total ?? 0} 次执行`}
          actions={
            <div className="flex items-center gap-2">
              <Select
                className="w-40"
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
              >
                <option value="">全部项目</option>
                {(projects.data?.items ?? []).map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </Select>
              <Select
                className="w-32"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                {STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
              {executions.isFetching && <Spinner size={14} className="text-slate-400" />}
            </div>
          }
        />

        {executions.isLoading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500">
            <Spinner /> 加载中…
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            title="没有符合条件的执行"
            description="去项目页发起一次运行，或在右上角调整筛选条件。"
            action={
              <Link href="/projects" className="btn-primary">
                去项目页
              </Link>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>状态</th>
                  <th>项目</th>
                  <th>模式</th>
                  <th>通过率</th>
                  <th>用例（过/总）</th>
                  <th>耗时</th>
                  <th>时间</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <Badge className={cn(STATUS_STYLES[row.status])}>{row.status}</Badge>
                    </td>
                    <td className="max-w-[180px]">
                      <Link
                        href={`/projects/${row.project_id}`}
                        className="block truncate text-sm text-slate-700 hover:text-brand-700"
                      >
                        {projectName(row.project_id)}
                      </Link>
                    </td>
                    <td className="text-xs text-slate-600">{row.graph_mode || "—"}</td>
                    <td className="w-28">
                      <div className="flex items-center gap-2">
                        <ProgressBar value={row.pass_rate} className="w-14" />
                        <span className="text-xs tabular-nums text-slate-600">
                          {formatPercent(row.pass_rate)}
                        </span>
                      </div>
                    </td>
                    <td className="tabular-nums text-xs text-slate-600">
                      <span className="text-emerald-600">{row.passed_cases}</span>
                      <span className="text-slate-400"> / </span>
                      {row.total_cases}
                    </td>
                    <td className="text-xs text-slate-500">{formatDuration(row.duration_ms)}</td>
                    <td className="text-xs text-slate-500">{formatDateTime(row.created_at)}</td>
                    <td className="text-right">
                      <Link
                        href={`/executions/${row.id}`}
                        className="inline-flex items-center gap-0.5 text-xs font-medium text-brand-600 hover:underline"
                      >
                        详情 <IconChevronRight size={12} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
