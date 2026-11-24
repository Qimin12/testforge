"use client";

import Link from "next/link";

import { IconChevronRight, IconFolder, IconPlay, IconPlus } from "@/components/icons";
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ProgressBar,
  Spinner,
  StatCard,
} from "@/components/ui/primitives";
import { useDefects, useExecutions, useProjects, useUsage } from "@/lib/queries";
import {
  STATUS_STYLES,
  cn,
  formatDateTime,
  formatDuration,
  formatPercent,
} from "@/lib/utils";

export default function DashboardPage() {
  const projects = useProjects({ limit: 100 });
  const executions = useExecutions({ limit: 8 });
  const openDefects = useDefects({ status: "open", limit: 1 });
  const usage = useUsage();

  const loading = projects.isLoading || executions.isLoading;
  const projectRows = projects.data?.items ?? [];
  const executionRows = executions.data?.items ?? [];

  const totalRuns = executions.data?.total ?? 0;
  const finished = executionRows.filter((row) => row.status !== "running" && row.status !== "pending");
  const avgPassRate =
    finished.length > 0
      ? finished.reduce((sum, row) => sum + (row.pass_rate || 0), 0) / finished.length
      : 0;
  const lastRun = executionRows[0];

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">概览</h1>
          <p className="mt-1 text-sm text-slate-500">
            AI 生成用例 → 执行 → 分析 → 缺陷 → 报告，一条链路看质量。
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/projects" className="btn-secondary">
            <IconFolder size={14} /> 全部项目
          </Link>
          <Link href="/projects" className="btn-primary">
            <IconPlus size={14} /> 新建项目
          </Link>
        </div>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="项目数" value={projects.data?.total ?? "—"} hint="进行中 + 归档" />
        <StatCard label="执行次数" value={totalRuns} hint="全部历史" />
        <StatCard
          label="近 8 次平均通过率"
          value={finished.length ? formatPercent(avgPassRate) : "—"}
          tone={avgPassRate >= 80 ? "good" : avgPassRate > 0 ? "bad" : "default"}
        />
        <StatCard
          label="未修复缺陷"
          value={openDefects.data?.total ?? "—"}
          tone={(openDefects.data?.total ?? 0) > 0 ? "bad" : "good"}
          hint="状态为 open"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="最近执行"
            description="点击查看每条用例的结果与缺陷"
            actions={
              <Link href="/executions" className="text-xs font-medium text-brand-600 hover:underline">
                全部记录
              </Link>
            }
          />
          {executions.isLoading ? (
            <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
              <Spinner /> 加载中…
            </div>
          ) : executionRows.length === 0 ? (
            <EmptyState
              title="还没有执行记录"
              description="去项目页导入 OpenAPI 文档，然后点「运行」就会产生第一条记录。"
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
                    <th>通过率</th>
                    <th>用例</th>
                    <th>耗时</th>
                    <th>时间</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {executionRows.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <Badge className={cn(STATUS_STYLES[row.status])}>{row.status}</Badge>
                      </td>
                      <td className="w-32">
                        <div className="flex items-center gap-2">
                          <ProgressBar value={row.pass_rate} className="w-16" />
                          <span className="tabular-nums text-xs text-slate-600">
                            {formatPercent(row.pass_rate)}
                          </span>
                        </div>
                      </td>
                      <td className="tabular-nums text-xs text-slate-600">
                        {row.passed_cases}/{row.total_cases}
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

        <div className="space-y-4">
          <Card>
            <CardHeader
              title="本月 Token 消耗"
              description={
                usage.data
                  ? `${usage.data.period} · ${usage.data.executions} 次执行`
                  : "统计中…"
              }
            />
            <CardBody>
              {usage.data ? (
                <>
                  <p className="text-lg font-semibold tabular-nums text-slate-900">
                    {usage.data.total_tokens.toLocaleString()}
                  </p>
                  <ProgressBar value={usage.data.used_ratio} className="mt-2" />
                  <p className="mt-1 text-xs text-slate-500">
                    预算 {usage.data.budget.toLocaleString()} · 已用 {usage.data.used_ratio}%
                  </p>
                  {usage.data.warning && (
                    <p className="mt-2 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">
                      {usage.data.warning}
                    </p>
                  )}
                </>
              ) : (
                <p className="text-xs text-slate-500">暂无数据。</p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="项目" description={`共 ${projects.data?.total ?? 0} 个`} />
            <CardBody className="space-y-2">
              {loading ? (
                <div className="flex items-center gap-2 text-sm text-slate-500">
                  <Spinner size={14} /> 加载中…
                </div>
              ) : projectRows.length === 0 ? (
                <p className="text-xs text-slate-500">还没有项目。</p>
              ) : (
                projectRows.slice(0, 5).map((project) => (
                  <Link
                    key={project.id}
                    href={`/projects/${project.id}`}
                    className="flex items-center justify-between rounded-md border border-slate-200 px-2.5 py-2 text-sm hover:border-brand-500/40 hover:bg-brand-50/40"
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-medium text-slate-800">
                        {project.name}
                      </span>
                      <span className="block truncate text-xs text-slate-400">
                        {project.operation_count} 接口 · {project.case_count} 用例
                      </span>
                    </span>
                    <IconChevronRight size={14} className="shrink-0 text-slate-300" />
                  </Link>
                ))
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="最近一次执行" />
            <CardBody>
              {lastRun ? (
                <div className="space-y-2 text-sm">
                  <div className="flex items-center justify-between">
                    <Badge className={cn(STATUS_STYLES[lastRun.status])}>{lastRun.status}</Badge>
                    <span className="text-xs text-slate-500">
                      {formatDateTime(lastRun.created_at)}
                    </span>
                  </div>
                  <p className="text-slate-700">
                    通过 {lastRun.passed_cases} / {lastRun.total_cases}，失败{" "}
                    <span className={lastRun.failed_cases > 0 ? "text-red-600" : "text-slate-700"}>
                      {lastRun.failed_cases}
                    </span>
                  </p>
                  <Link
                    href={`/executions/${lastRun.id}`}
                    className="inline-flex items-center gap-1 text-xs font-medium text-brand-600 hover:underline"
                  >
                    <IconPlay size={12} /> 查看报告
                  </Link>
                </div>
              ) : (
                <p className="text-xs text-slate-500">暂无执行。</p>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
