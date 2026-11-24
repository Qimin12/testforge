"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type ReactNode } from "react";

import { IconAlert, IconArrowLeft, IconRefresh } from "@/components/icons";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Select,
  Spinner,
  StatCard,
} from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { ApiError, downloadFile } from "@/lib/api";
import { useExecution, useResumeExecution, useUpdateDefect } from "@/lib/queries";
import type { ReportSummary, TestResult } from "@/lib/types";
import {
  RISK_LABELS,
  SEVERITY_STYLES,
  STATUS_STYLES,
  cn,
  formatDateTime,
  formatDuration,
  formatPercent,
  truncate,
} from "@/lib/utils";

export default function ExecutionDetailPage() {
  const params = useParams<{ id: string }>();
  const executionId = params.id;
  const toast = useToast();

  const execution = useExecution(executionId);
  const resume = useResumeExecution(executionId);
  const updateDefect = useUpdateDefect();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [exportFormat, setExportFormat] = useState("json");
  const [exporting, setExporting] = useState(false);

  const data = execution.data;
  const report: ReportSummary | null = data?.report ?? null;

  async function doResume(approved: boolean) {
    try {
      await resume.mutateAsync(approved);
      toast.success(approved ? "已确认，执行继续" : "已驳回，执行终止");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "恢复失败");
    }
  }

  async function exportReport() {
    if (!data) return;
    const ext =
      exportFormat === "markdown" ? "md" : exportFormat === "xlsx" ? "xlsx" : exportFormat;
    setExporting(true);
    try {
      await downloadFile(
        `/executions/${data.id}/export?format=${exportFormat}`,
        `testforge-${data.id.slice(0, 8)}.${ext}`,
      );
      toast.success("已开始下载");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "导出失败");
    } finally {
      setExporting(false);
    }
  }

  if (execution.isLoading) {
    return (
      <div className="flex items-center gap-2 py-16 text-sm text-slate-500">
        <Spinner /> 加载执行详情…
      </div>
    );
  }

  if (execution.isError || !data) {
    return (
      <div className="space-y-3">
        <Alert tone="error">执行记录不存在或无权访问。</Alert>
        <Link href="/executions" className="btn-secondary">
          返回列表
        </Link>
      </div>
    );
  }

  const tokenEntries = Object.entries(data.token_usage ?? {}).filter(([, value]) => value > 0);
  const failedResults = data.results.filter((row) => row.status !== "passed");

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-xs text-slate-400">
        <Link href="/executions" className="inline-flex items-center gap-1 hover:text-slate-600">
          <IconArrowLeft size={12} /> 执行记录
        </Link>
        <span>/</span>
        <span className="font-mono">{data.id.slice(0, 8)}</span>
      </div>

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-slate-900">执行详情</h1>
            <Badge className={cn(STATUS_STYLES[data.status])}>{data.status}</Badge>
            <Badge>{data.graph_mode || "—"}</Badge>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            项目：
            <Link href={`/projects/${data.project_id}`} className="text-brand-600 hover:underline">
              {data.project_id.slice(0, 8)}
            </Link>
            <span className="mx-2 text-slate-300">|</span>
            开始 {formatDateTime(data.started_at ?? data.created_at)}
            <span className="mx-2 text-slate-300">|</span>
            耗时 {formatDuration(data.duration_ms)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            className="w-28"
            value={exportFormat}
            onChange={(event) => setExportFormat(event.target.value)}
          >
            <option value="json">JSON</option>
            <option value="markdown">Markdown</option>
            <option value="csv">CSV</option>
            <option value="xlsx">Excel</option>
          </Select>
          <Button variant="secondary" loading={exporting} onClick={exportReport}>
            导出
          </Button>
          <Button variant="ghost" onClick={() => execution.refetch()}>
            <IconRefresh size={14} /> 刷新
          </Button>
        </div>
      </header>

      {data.status === "interrupted" && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-amber-200 bg-amber-50 px-4 py-3">
          <div className="flex items-start gap-2 text-sm text-amber-900">
            <IconAlert size={16} className="mt-0.5" />
            <div>
              <p className="font-medium">执行在「用例审核」处暂停</p>
              <p className="text-xs text-amber-800">
                确认用例质量后点继续，图会从断点恢复执行，不会重跑前面的节点。
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              variant="primary"
              loading={resume.isPending}
              onClick={() => doResume(true)}
            >
              确认并继续
            </Button>
            <Button onClick={() => doResume(false)}>驳回</Button>
          </div>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-4">
        <StatCard label="用例总数" value={data.total_cases} />
        <StatCard label="通过" value={data.passed_cases} tone="good" />
        <StatCard label="失败" value={data.failed_cases} tone={data.failed_cases ? "bad" : "default"} />
        <StatCard
          label="通过率"
          value={formatPercent(data.pass_rate)}
          tone={data.pass_rate >= 80 ? "good" : "bad"}
        />
      </div>

      {/* 报告 */}
      <Card>
        <CardHeader
          title="测试报告"
          description={report?.generated_at ? `生成于 ${formatDateTime(report.generated_at)}` : undefined}
          actions={
            report?.risk_level ? (
              <Badge
                className={cn(
                  report.risk_level === "low" && "border-emerald-200 bg-emerald-50 text-emerald-700",
                  report.risk_level === "medium" && "border-amber-200 bg-amber-50 text-amber-800",
                  report.risk_level === "high" && "border-red-200 bg-red-50 text-red-700",
                )}
              >
                {RISK_LABELS[report.risk_level] ?? report.risk_level}
              </Badge>
            ) : undefined
          }
        />
        <CardBody className="space-y-3">
          {report?.summary ? (
            <p className="text-sm leading-relaxed text-slate-700">{report.summary}</p>
          ) : (
            <p className="text-sm text-slate-500">这次执行还没有报告（可能被中断或未走到报告节点）。</p>
          )}

          {report?.highlights && report.highlights.length > 0 && (
            <ul className="list-inside list-disc space-y-1 text-xs text-slate-600">
              {report.highlights.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}

          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            {report?.defect_count !== undefined && <Badge>缺陷 {report.defect_count}</Badge>}
            {report?.avg_duration_ms !== undefined && (
              <Badge>平均 {formatDuration(report.avg_duration_ms)}</Badge>
            )}
            {Object.entries(report?.defects_by_severity ?? {}).map(([key, count]) => (
              <Badge key={key} className={cn(SEVERITY_STYLES[key])}>
                {key} {count}
              </Badge>
            ))}
            {Object.entries(report?.defects_by_category ?? {}).map(([key, count]) => (
              <Badge key={key}>
                {key} {count}
              </Badge>
            ))}
          </div>

          {tokenEntries.length > 0 && (
            <details className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
              <summary className="cursor-pointer text-xs font-medium text-slate-600">
                Token 用量（{tokenEntries.reduce((sum, [, value]) => sum + value, 0)} 总计）
              </summary>
              <div className="mt-2 grid gap-1 sm:grid-cols-2">
                {tokenEntries.map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-2 text-xs text-slate-600">
                    <span className="font-mono">{key}</span>
                    <span className="tabular-nums">{value}</span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </CardBody>
      </Card>

      {/* 逐条结果 */}
      <Card>
        <CardHeader
          title="用例执行结果"
          description={`${data.results.length} 条，失败 ${failedResults.length} 条`}
        />
        {data.results.length === 0 ? (
          <EmptyState title="没有结果" description="执行可能还没开始、被中断，或没有可执行的用例。" />
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>用例</th>
                  <th>状态</th>
                  <th>期望 / 实际</th>
                  <th>耗时</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.results.map((row) => (
                  <ResultRow
                    key={row.id}
                    row={row}
                    expanded={expanded === row.id}
                    onToggle={() => setExpanded(expanded === row.id ? null : row.id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* 缺陷 */}
      <Card>
        <CardHeader
          title="缺陷"
          description="AI 归类的结果，可在这里直接改状态"
          actions={
            <Link href={`/defects?project_id=${data.project_id}`} className="text-xs text-brand-600 hover:underline">
              查看项目全部缺陷
            </Link>
          }
        />
        {data.defects.length === 0 ? (
          <EmptyState title="没有缺陷" description="所有用例都通过，或者失败结论未归类为缺陷。" />
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>缺陷</th>
                  <th>等级</th>
                  <th>分类</th>
                  <th>根因 / 建议</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {data.defects.map((defect) => (
                  <tr key={defect.id}>
                    <td className="max-w-xs">
                      <p className="font-medium text-slate-800">{defect.title}</p>
                      <p className="mt-0.5 text-xs text-slate-500" title={defect.description}>
                        {truncate(defect.description, 100)}
                      </p>
                    </td>
                    <td>
                      <Badge className={cn(SEVERITY_STYLES[defect.severity])}>
                        {defect.severity}
                      </Badge>
                    </td>
                    <td>
                      <Badge>{defect.category}</Badge>
                    </td>
                    <td className="max-w-sm text-xs text-slate-600">
                      {defect.root_cause && <p>根因：{truncate(defect.root_cause, 90)}</p>}
                      {defect.fix_suggestion && (
                        <p className="mt-0.5 text-slate-500">建议：{truncate(defect.fix_suggestion, 90)}</p>
                      )}
                    </td>
                    <td>
                      <select
                        className="input px-1.5 py-1 text-xs"
                        value={defect.status}
                        onChange={async (event) => {
                          try {
                            await updateDefect.mutateAsync({
                              id: defect.id,
                              status: event.target.value,
                            });
                            toast.success("缺陷状态已更新");
                            void execution.refetch();
                          } catch (err) {
                            toast.error(err instanceof ApiError ? err.detail : "更新失败");
                          }
                        }}
                      >
                        {["open", "fixed", "closed", "wontfix"].map((value) => (
                          <option key={value} value={value}>
                            {value}
                          </option>
                        ))}
                      </select>
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

function ResultRow({
  row,
  expanded,
  onToggle,
}: {
  row: TestResult;
  expanded: boolean;
  onToggle: () => void;
}) {
  const hasDetail = Boolean(row.error_message || row.expected_output || row.actual_output);
  return (
    <>
      <tr className={cn(expanded && "bg-slate-50")}>
        <td className="max-w-xs">
          <button
            type="button"
            onClick={onToggle}
            className="block max-w-full truncate text-left font-medium text-slate-800 hover:text-brand-700"
            title={row.case_name}
          >
            {row.case_name}
          </button>
        </td>
        <td>
          <Badge className={cn(STATUS_STYLES[row.status])}>{row.status}</Badge>
        </td>
        <td className="max-w-md text-xs text-slate-600">
          {row.error_message ? truncate(row.error_message, 80) : "—"}
        </td>
        <td className="text-xs text-slate-500">{formatDuration(row.duration_ms)}</td>
        <td className="text-right">
          {hasDetail && (
            <Button size="sm" variant="ghost" onClick={onToggle}>
              {expanded ? "收起" : "详情"}
            </Button>
          )}
        </td>
      </tr>
      {expanded && hasDetail && (
        <tr>
          <td colSpan={5} className="bg-slate-50">
            <div className="space-y-2 py-1 text-xs">
              {row.expected_output && (
                <Kv label="期望">
                  <code className="break-all">{row.expected_output}</code>
                </Kv>
              )}
              {row.actual_output && (
                <Kv label="实际">
                  <code className="break-all">{row.actual_output}</code>
                </Kv>
              )}
              {row.error_message && (
                <Kv label="错误">
                  <code className="break-all text-red-700">{row.error_message}</code>
                </Kv>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function Kv({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-2">
      <span className="w-12 shrink-0 text-slate-500">{label}</span>
      <span className="min-w-0 flex-1 text-slate-700">{children}</span>
    </div>
  );
}
