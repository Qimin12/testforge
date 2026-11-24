"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState, type ReactNode } from "react";

import {
  IconAlert,
  IconChevronRight,
  IconPlay,
  IconPlus,
  IconTrash,
  IconUpload,
} from "@/components/icons";
import { Dialog } from "@/components/ui/dialog";
import { Tabs } from "@/components/ui/tabs";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Field,
  Input,
  ProgressBar,
  Select,
  Spinner,
  StatCard,
  Textarea,
} from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api";
import {
  useArchiveProject,
  useCoverageHistory,
  useCreateCases,
  useDeleteCase,
  useExecutions,
  useImportOpenapi,
  useLatestCoverage,
  useProject,
  useProjectCases,
  useRunProject,
  useUpdateCase,
  useUpdateProject,
  useUploadCoverage,
} from "@/lib/queries";
import type { CaseCreateInput, ExecutionDetail, TestCase } from "@/lib/types";
import {
  METHOD_STYLES,
  STATUS_STYLES,
  cn,
  formatDateTime,
  formatDuration,
  formatPercent,
} from "@/lib/utils";

const RUN_MODES = [
  { value: "full", label: "完整链路（生成 + 执行 + 分析 + 缺陷 + 报告）" },
  { value: "generate", label: "只生成用例（不执行）" },
  { value: "execute_only", label: "只执行已有用例（不调用模型）" },
];

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const router = useRouter();
  const toast = useToast();

  const project = useProject(projectId);
  const cases = useProjectCases(projectId, { limit: 200 });
  const executions = useExecutions({ project_id: projectId, limit: 20 });
  const coverage = useLatestCoverage(projectId);
  const coverageHistory = useCoverageHistory(projectId, { limit: 10 });
  const importOpenapi = useImportOpenapi(projectId);
  const runProject = useRunProject(projectId);
  const updateProject = useUpdateProject(projectId);
  const archiveProject = useArchiveProject();
  const updateCase = useUpdateCase(projectId);
  const deleteCase = useDeleteCase(projectId);
  const createCases = useCreateCases(projectId);
  const uploadCoverage = useUploadCoverage(projectId);

  const [tab, setTab] = useState("cases");
  const [importOpen, setImportOpen] = useState(false);
  const [specText, setSpecText] = useState("");
  const [runOpen, setRunOpen] = useState(false);
  const [mode, setMode] = useState("full");
  const [asyncMode, setAsyncMode] = useState(false);
  const [lastRun, setLastRun] = useState<ExecutionDetail | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<TestCase | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [coverageOpen, setCoverageOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [coverageForm, setCoverageForm] = useState<{
    lineRate: string;
    branchRate: string;
    source: string;
  }>({ lineRate: "", branchRate: "", source: "web" });
  const [settings, setSettings] = useState({
    name: "",
    target_base_url: "",
    description: "",
    schedule_enabled: false,
    schedule_interval_minutes: 60,
  });

  const data = project.data;
  const caseRows = cases.data?.items ?? [];
  const executionRows = executions.data?.items ?? [];

  const caseStats = useMemo(() => {
    const byCategory: Record<string, number> = {};
    for (const row of caseRows) {
      const key = row.category ?? "未分类";
      byCategory[key] = (byCategory[key] ?? 0) + 1;
    }
    return byCategory;
  }, [caseRows]);

  async function doImport() {
    let parsed: unknown;
    try {
      parsed = JSON.parse(specText);
    } catch {
      toast.error("不是合法 JSON，请检查粘贴内容");
      return;
    }
    try {
      const result = await importOpenapi.mutateAsync(parsed);
      toast.success(`导入成功，识别到 ${result.operation_count} 个接口`);
      setImportOpen(false);
      setSpecText("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "导入失败");
    }
  }

  async function doRun() {
    try {
      const detail = await runProject.mutateAsync({ mode, asyncMode });
      setLastRun(detail);
      if (detail.status === "pending") {
        toast.toast("执行已交给后台队列，稍后刷新执行记录查看结果", "info");
      } else if (detail.status === "interrupted") {
        toast.toast("执行已在用例审核处暂停，去执行详情里确认", "info");
      } else {
        toast.success(`执行完成：${detail.passed_cases}/${detail.total_cases} 通过`);
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "执行失败");
    }
  }

  function openSettings() {
    if (!data) return;
    setSettings({
      name: data.name,
      target_base_url: data.target_base_url ?? "",
      description: data.description ?? "",
      schedule_enabled: data.schedule_enabled,
      schedule_interval_minutes: data.schedule_interval_minutes ?? 60,
    });
    setSettingsOpen(true);
  }

  async function saveSettings() {
    try {
      await updateProject.mutateAsync({
        name: settings.name.trim(),
        target_base_url: settings.target_base_url.trim(),
        description: settings.description.trim(),
        schedule_enabled: settings.schedule_enabled,
        schedule_interval_minutes: Number(settings.schedule_interval_minutes) || 0,
      });
      toast.success("已保存");
      setSettingsOpen(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "保存失败");
    }
  }

  async function doArchive() {
    if (!window.confirm("归档后项目仍可查看，但不再出现在默认列表里。确认归档？")) return;
    try {
      await archiveProject.mutateAsync(projectId);
      toast.success("已归档");
      router.push("/projects");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "归档失败");
    }
  }

  function openCaseEdit(row: TestCase) {
    setEditTarget(row);
    setEditOpen(true);
  }

  async function saveCreatedCase(form: CaseCreateInput) {
    try {
      const result = await createCases.mutateAsync([form]);
      toast.success(`新增用例 ${result.total} 条`);
      setCreateOpen(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "新增失败");
    }
  }

  async function saveCoverage() {
    const lineRate = Number(coverageForm.lineRate);
    const branchRate = Number(coverageForm.branchRate);
    if (coverageForm.lineRate.trim() === "" && coverageForm.branchRate.trim() === "") {
      toast.error("至少填写一项覆盖率");
      return;
    }
    try {
      await uploadCoverage.mutateAsync({
        line_rate: coverageForm.lineRate.trim() ? lineRate : undefined,
        branch_rate: coverageForm.branchRate.trim() ? branchRate : undefined,
        source: coverageForm.source.trim() || "web",
      });
      toast.success("覆盖率已上报");
      setCoverageOpen(false);
      setCoverageForm({ lineRate: "", branchRate: "", source: "web" });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "上报失败");
    }
  }

  async function saveCase(form: CaseEditForm) {
    if (!editTarget) return;
    const base = editTarget.request ?? {};
    try {
      await updateCase.mutateAsync({
        id: editTarget.id,
        body: {
          name: form.name,
          // 带上原有 headers/params/body，只覆盖 method/path/expected_status
          request: {
            ...base,
            method: form.method,
            path: form.path,
            expected_status: Number(form.expected_status),
          },
          assertions: form.assertions,
        },
      });
      toast.success("用例已更新");
      setEditOpen(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "更新失败");
    }
  }

  if (project.isLoading) {
    return (
      <div className="flex items-center gap-2 py-16 text-sm text-slate-500">
        <Spinner /> 加载项目…
      </div>
    );
  }

  if (project.isError || !data) {
    return (
      <div className="space-y-3">
        <Alert tone="error">
          项目不存在或无权访问。
          {project.error instanceof ApiError ? ` ${project.error.detail}` : ""}
        </Alert>
        <Link href="/projects" className="btn-secondary">
          返回项目列表
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Link href="/projects" className="text-xs text-slate-400 hover:text-slate-600">
              项目
            </Link>
            <IconChevronRight size={12} className="text-slate-300" />
            <h1 className="truncate text-xl font-semibold text-slate-900">{data.name}</h1>
            <Badge className={cn(STATUS_STYLES[data.status])}>{data.status}</Badge>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {data.description || "未填写描述"}
            <span className="mx-2 text-slate-300">|</span>
            被测地址：
            <span className="font-mono text-xs">{data.target_base_url || "未设置"}</span>
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setImportOpen(true)}>
            <IconUpload size={14} /> 导入 OpenAPI
          </Button>
          <Button variant="primary" onClick={() => setRunOpen(true)}>
            <IconPlay size={14} /> 运行
          </Button>
          <Button onClick={openSettings}>设置</Button>
          <Button variant="ghost" onClick={doArchive}>
            <IconTrash size={14} /> 归档
          </Button>
        </div>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard label="接口数" value={data.operation_count} hint="来自 OpenAPI 文档" />
        <StatCard label="用例数" value={data.case_count} hint={`已入库 ${caseRows.length} 条`} />
        <StatCard label="执行次数" value={executions.data?.total ?? 0} />
        <StatCard
          label="最近通过率"
          value={executionRows[0] ? formatPercent(executionRows[0].pass_rate) : "—"}
          tone={
            executionRows[0] && executionRows[0].pass_rate >= 80
              ? "good"
              : executionRows[0]
                ? "bad"
                : "default"
          }
        />
        <StatCard
          label="行覆盖率"
          value={coverage.data ? `${coverage.data.line_rate}%` : "—"}
          hint={
            coverage.data
              ? `${coverage.data.source} · 分支 ${coverage.data.branch_rate}%`
              : "CI 里上报后显示"
          }
          tone={
            coverage.data
              ? coverage.data.line_rate >= 80
                ? "good"
                : "bad"
              : "default"
          }
        />
      </div>

      {lastRun && <RunResultBanner detail={lastRun} onClose={() => setLastRun(null)} />}

      <Card>
        <Tabs
          value={tab}
          onChange={setTab}
          className="px-2"
          items={[
            { key: "cases", label: "测试用例", badge: caseRows.length },
            { key: "executions", label: "执行记录", badge: executions.data?.total ?? 0 },
            { key: "overview", label: "项目概览" },
          ]}
        />

        {tab === "cases" && (
          <div>
            {cases.isLoading ? (
              <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500">
                <Spinner /> 加载用例…
              </div>
            ) : caseRows.length === 0 ? (
              <EmptyState
                title="还没有用例"
                description="导入 OpenAPI 文档后点「运行」，AI 生成的用例会自动入库；也可以直接运行一次完整链路。"
                action={
                  <div className="flex items-center gap-2">
                    <Button onClick={() => setCreateOpen(true)}>
                      <IconPlus size={14} /> 新增用例
                    </Button>
                    <Button variant="primary" onClick={() => setRunOpen(true)}>
                      <IconPlay size={14} /> 运行生成用例
                    </Button>
                  </div>
                }
              />
            ) : (
              <div className="overflow-x-auto">
                <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-2 text-xs text-slate-500">
                  <span>分类：</span>
                  {Object.entries(caseStats).map(([key, count]) => (
                    <Badge key={key}>
                      {key} {count}
                    </Badge>
                  ))}
                  <span className="ml-auto">
                    <Button size="sm" variant="ghost" onClick={() => setCreateOpen(true)}>
                      <IconPlus size={14} /> 新增用例
                    </Button>
                  </span>
                </div>
                <table className="table-base">
                  <thead>
                    <tr>
                      <th>用例</th>
                      <th>方法 / 路径</th>
                      <th>期望</th>
                      <th>分类</th>
                      <th>来源</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {caseRows.map((row) => (
                      <tr key={row.id}>
                        <td className="max-w-xs">
                          <span className="block truncate font-medium text-slate-800" title={row.name}>
                            {row.name}
                          </span>
                          {row.description && (
                            <span className="block truncate text-xs text-slate-400">
                              {row.description}
                            </span>
                          )}
                        </td>
                        <td>
                          <div className="flex items-center gap-1.5">
                            <Badge className={cn(METHOD_STYLES[row.method])}>{row.method}</Badge>
                            <span className="font-mono text-xs text-slate-600">{row.path}</span>
                          </div>
                        </td>
                        <td className="tabular-nums text-xs text-slate-600">
                          {row.expected_status}
                        </td>
                        <td>
                          {row.category ? (
                            <Badge
                              className={cn(
                                row.category === "happy" && "border-emerald-200 bg-emerald-50 text-emerald-700",
                                row.category === "negative" && "border-red-200 bg-red-50 text-red-700",
                                row.category === "boundary" && "border-amber-200 bg-amber-50 text-amber-700",
                              )}
                            >
                              {row.category}
                            </Badge>
                          ) : (
                            <span className="text-xs text-slate-400">—</span>
                          )}
                        </td>
                        <td>
                          <Badge>{row.source === "ai" ? "AI 生成" : "手动"}</Badge>
                        </td>
                        <td className="whitespace-nowrap text-right">
                          <Button size="sm" variant="ghost" onClick={() => openCaseEdit(row)}>
                            编辑
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-red-600 hover:bg-red-50"
                            onClick={async () => {
                              if (!window.confirm(`删除用例「${row.name}」？`)) return;
                              try {
                                await deleteCase.mutateAsync(row.id);
                                toast.success("已删除");
                              } catch (err) {
                                toast.error(err instanceof ApiError ? err.detail : "删除失败");
                              }
                            }}
                          >
                            删除
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {tab === "executions" && (
          <div>
            {executionRows.length === 0 ? (
              <EmptyState
                title="还没有执行记录"
                description="点右上角「运行」发起第一次执行。"
                action={
                  <Button variant="primary" onClick={() => setRunOpen(true)}>
                    <IconPlay size={14} /> 运行
                  </Button>
                }
              />
            ) : (
              <table className="table-base">
                <thead>
                  <tr>
                    <th>状态</th>
                    <th>模式</th>
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
                        {row.passed_cases}/{row.total_cases}
                      </td>
                      <td className="text-xs text-slate-500">{formatDuration(row.duration_ms)}</td>
                      <td className="text-xs text-slate-500">{formatDateTime(row.created_at)}</td>
                      <td className="text-right">
                        <Link
                          href={`/executions/${row.id}`}
                          className="text-xs font-medium text-brand-600 hover:underline"
                        >
                          详情
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {tab === "overview" && (
          <div>
            <CardBody className="space-y-2 text-sm">
              <Row label="项目 ID" value={<span className="font-mono text-xs">{data.id}</span>} />
              <Row label="创建时间" value={formatDateTime(data.created_at)} />
              <Row label="代码仓库" value={data.repo_url || "未关联"} />
              <Row label="被测服务" value={data.target_base_url || "未设置"} />
              <Row label="OpenAPI 接口数" value={String(data.operation_count)} />
              <Row label="用例数" value={String(data.case_count)} />
              {data.schedule_enabled && (
                <Row
                  label="定时调度"
                  value={`每 ${data.schedule_interval_minutes ?? 60} 分钟${
                    data.last_scheduled_at ? ` · 上次 ${formatDateTime(data.last_scheduled_at)}` : ""
                  }`}
                />
              )}
              <div className="pt-2">
                <Alert tone="info">
                  接口清单在导入时解析。重新导入会覆盖项目的 api_spec，建议在接口变更后重新导入再运行。
                </Alert>
              </div>
            </CardBody>

            <CardBody className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-slate-800">覆盖率历史</h3>
                <Button size="sm" onClick={() => setCoverageOpen(true)}>
                  <IconUpload size={14} /> 上报覆盖率
                </Button>
              </div>
              {coverageHistory.isLoading ? (
                <p className="text-xs text-slate-500">加载中…</p>
              ) : (coverageHistory.data?.length ?? 0) === 0 ? (
                <p className="text-xs text-slate-500">
                  还没有覆盖率记录。项目测试落地时可通过上报接口回传，例如 CI 里用
                  <code className="mx-1 rounded bg-slate-100 px-1">pytest-cov</code> 的产物。
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="table-base">
                    <thead>
                      <tr>
                        <th>行覆盖率</th>
                        <th>分支覆盖率</th>
                        <th>来源</th>
                        <th>时间</th>
                      </tr>
                    </thead>
                    <tbody>
                      {coverageHistory.data?.map((item) => (
                        <tr key={item.id}>
                          <td>
                            <div className="flex items-center gap-2">
                              <ProgressBar value={item.line_rate} className="w-24" />
                              <span className="text-xs tabular-nums text-slate-600">
                                {item.line_rate}%
                              </span>
                            </div>
                          </td>
                          <td className="tabular-nums text-xs text-slate-600">{item.branch_rate}%</td>
                          <td className="text-xs text-slate-600">{item.source || "—"}</td>
                          <td className="text-xs text-slate-500">{formatDateTime(item.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardBody>
          </div>
        )}
      </Card>

      {/* 新增用例 */}
      {createOpen && (
        <CreateCaseDialog
          open={createOpen}
          busy={createCases.isPending}
          onClose={() => setCreateOpen(false)}
          onSave={saveCreatedCase}
        />
      )}

      {/* 上报覆盖率 */}
      <Dialog
        open={coverageOpen}
        onClose={() => setCoverageOpen(false)}
        title="上报覆盖率"
        description="填写百分比即可；也可以留空让后端用比例字段自动计算"
        footer={
          <>
            <Button onClick={() => setCoverageOpen(false)}>取消</Button>
            <Button variant="primary" loading={uploadCoverage.isPending} onClick={saveCoverage}>
              上报
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="行覆盖率（%）">
              <Input
                type="number"
                value={coverageForm.lineRate}
                placeholder="如 86.5"
                onChange={(e) => setCoverageForm({ ...coverageForm, lineRate: e.target.value })}
              />
            </Field>
            <Field label="分支覆盖率（%）">
              <Input
                type="number"
                value={coverageForm.branchRate}
                placeholder="如 72"
                onChange={(e) => setCoverageForm({ ...coverageForm, branchRate: e.target.value })}
              />
            </Field>
          </div>
          <Field label="来源" hint="默认 web，收到来自 CI 的上报时会覆盖为 pytest-cov 等">
            <Input
              value={coverageForm.source}
              onChange={(e) => setCoverageForm({ ...coverageForm, source: e.target.value })}
            />
          </Field>
        </div>
      </Dialog>

      {/* 导入 OpenAPI */}
      <Dialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        title="导入 OpenAPI / Swagger"
        description="支持 OpenAPI 3.x 与 Swagger 2.0；粘贴 JSON 或选择文件"
        footer={
          <>
            <Button onClick={() => setImportOpen(false)}>取消</Button>
            <Button
              variant="primary"
              loading={importOpenapi.isPending}
              onClick={doImport}
              disabled={!specText.trim()}
            >
              导入
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Field label="选择文件">
            <input
              type="file"
              accept=".json,application/json"
              className="block w-full text-xs text-slate-500 file:mr-3 file:rounded file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-slate-700 hover:file:bg-slate-200"
              onChange={async (event) => {
                const file = event.target.files?.[0];
                if (!file) return;
                setSpecText(await file.text());
              }}
            />
          </Field>
          <Field label="或直接粘贴 JSON" hint={`已输入 ${specText.length} 字符`}>
            <Textarea
              rows={12}
              value={specText}
              placeholder='{"openapi":"3.0.0","info":{...},"paths":{...}}'
              onChange={(e) => setSpecText(e.target.value)}
            />
          </Field>
        </div>
      </Dialog>

      {/* 运行 */}
      <Dialog
        open={runOpen}
        onClose={() => setRunOpen(false)}
        title="运行测试"
        description={
          mode === "execute_only"
            ? "只执行项目里已有的用例，不消耗模型 token"
            : "会调用大模型生成/分析，可能耗时 1~3 分钟，请勿关闭页面"
        }
        footer={
          <>
            <Button onClick={() => setRunOpen(false)}>取消</Button>
            <Button variant="primary" loading={runProject.isPending} onClick={doRun}>
              {runProject.isPending ? "执行中…" : "开始执行"}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Field label="运行模式">
            <Select value={mode} onChange={(e) => setMode(e.target.value)}>
              {RUN_MODES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </Select>
          </Field>

          <label className="flex items-start gap-2 rounded border border-slate-200 px-3 py-2 text-sm">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={asyncMode}
              onChange={(e) => setAsyncMode(e.target.checked)}
            />
            <span>
              后台执行（Celery 队列）
              <span className="mt-0.5 block text-xs text-slate-500">
                开启后接口立即返回，执行在 worker 里跑。开发环境（CELERY_EAGER=true）
                会自动退回同步执行，不会因为没起 Redis 而失败。
              </span>
            </span>
          </label>

          {!data.target_base_url && mode !== "generate" && (
            <Alert tone="warning">
              项目还没设置被测服务地址，执行会失败。请先点「设置」填写。
            </Alert>
          )}
          {data.operation_count === 0 && mode !== "execute_only" && (
            <Alert tone="warning">项目还没导入 OpenAPI 文档，无法生成用例。</Alert>
          )}
          {runProject.isPending && (
            <div className="flex items-center gap-2 text-sm text-slate-600">
              <Spinner size={14} /> 正在执行，请不要关闭页面…
            </div>
          )}
        </div>
      </Dialog>

      {/* 项目设置 */}
      <Dialog
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        title="项目设置"
        footer={
          <>
            <Button onClick={() => setSettingsOpen(false)}>取消</Button>
            <Button variant="primary" loading={updateProject.isPending} onClick={saveSettings}>
              保存
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Field label="名称">
            <Input
              value={settings.name}
              onChange={(e) => setSettings({ ...settings, name: e.target.value })}
            />
          </Field>
          <Field label="被测服务地址">
            <Input
              value={settings.target_base_url}
              placeholder="http://127.0.0.1:8080"
              onChange={(e) => setSettings({ ...settings, target_base_url: e.target.value })}
            />
          </Field>
          <Field label="描述">
            <Input
              value={settings.description}
              onChange={(e) => setSettings({ ...settings, description: e.target.value })}
            />
          </Field>

          <Field
            label="定时执行"
            hint="开启后 Celery beat 每分钟检查一次，到点自动按 full 模式跑一遍"
          >
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={settings.schedule_enabled}
                  onChange={(e) =>
                    setSettings({ ...settings, schedule_enabled: e.target.checked })
                  }
                />
                启用
              </label>
              <span className="text-sm text-slate-500">每隔</span>
              <Input
                type="number"
                min={0}
                max={10080}
                className="w-24"
                value={settings.schedule_interval_minutes}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    schedule_interval_minutes: Number(e.target.value) || 0,
                  })
                }
              />
              <span className="text-sm text-slate-500">分钟</span>
            </div>
          </Field>
        </div>
      </Dialog>

      {/* 编辑用例 */}
      {editTarget && (
        <CaseEditDialog
          open={editOpen}
          row={editTarget}
          busy={updateCase.isPending}
          onClose={() => setEditOpen(false)}
          onSave={saveCase}
        />
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 子组件                                                                      */
/* -------------------------------------------------------------------------- */
function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start gap-3 border-b border-slate-100 py-1.5 last:border-0">
      <span className="w-28 shrink-0 text-xs text-slate-500">{label}</span>
      <span className="min-w-0 flex-1 break-words text-slate-800">{value}</span>
    </div>
  );
}

function RunResultBanner({
  detail,
  onClose,
}: {
  detail: ExecutionDetail;
  onClose: () => void;
}) {
  const failed = detail.failed_cases > 0;
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 rounded-md border px-4 py-3",
        detail.status === "interrupted"
          ? "border-amber-200 bg-amber-50"
          : failed
            ? "border-red-200 bg-red-50"
            : "border-emerald-200 bg-emerald-50",
      )}
    >
      <div className="flex items-center gap-2 text-sm">
        {detail.status === "interrupted" ? (
          <IconAlert size={16} className="text-amber-600" />
        ) : (
          <IconPlay size={16} className={failed ? "text-red-600" : "text-emerald-600"} />
        )}
        <span className="font-medium text-slate-800">
          {detail.status === "interrupted" ? "执行已暂停（等待用例审核）" : "执行完成"}
        </span>
        <span className="text-slate-600">
          {detail.passed_cases}/{detail.total_cases} 通过 · 缺陷 {detail.defects.length}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <Link href={`/executions/${detail.id}`} className="btn-secondary">
          查看详情
        </Link>
        <Button variant="ghost" onClick={onClose}>
          关闭
        </Button>
      </div>
    </div>
  );
}

interface CaseEditForm {
  name: string;
  method: string;
  path: string;
  expected_status: number;
  assertions: { mode: string; target: string; expected: unknown }[];
}

function CaseEditDialog({
  open,
  row,
  busy,
  onClose,
  onSave,
}: {
  open: boolean;
  row: TestCase;
  busy: boolean;
  onClose: () => void;
  onSave: (form: CaseEditForm) => void;
}) {
  const [form, setForm] = useState<CaseEditForm>({
    name: row.name,
    method: row.method,
    path: row.path,
    expected_status: row.expected_status,
    assertions: (row.assertions ?? []).map((a) => ({
      mode: a.mode,
      target: a.target ?? "",
      expected: a.expected,
    })),
  });
  const [assertError, setAssertError] = useState<string | null>(null);
  const [assertText, setAssertText] = useState(JSON.stringify(row.assertions ?? [], null, 2));

  function submit() {
    let assertions: CaseEditForm["assertions"];
    try {
      assertions = JSON.parse(assertText);
      if (!Array.isArray(assertions)) throw new Error("assertions 必须是数组");
      setAssertError(null);
    } catch (err) {
      setAssertError(err instanceof Error ? err.message : "断言 JSON 不合法");
      return;
    }
    onSave({ ...form, assertions });
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="编辑用例"
      description="保存后版本号 +1"
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" loading={busy} onClick={submit}>
            保存
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="用例名称">
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="方法">
            <Select
              value={form.method}
              onChange={(e) => setForm({ ...form, method: e.target.value })}
            >
              {["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="路径" className="sm:col-span-2">
            <Input value={form.path} onChange={(e) => setForm({ ...form, path: e.target.value })} />
          </Field>
        </div>
        <Field label="期望状态码">
          <Input
            type="number"
            value={form.expected_status}
            onChange={(e) => setForm({ ...form, expected_status: Number(e.target.value) })}
          />
        </Field>
        <Field label="断言（JSON 数组）" error={assertError ?? undefined}>
          <Textarea
            rows={6}
            value={assertText}
            onChange={(e) => setAssertText(e.target.value)}
            placeholder={'[{"mode":"json_path","target":"data.id","expected":1}]'}
          />
        </Field>
      </div>
    </Dialog>
  );
}

interface CreateCaseForm {
  name: string;
  method: string;
  path: string;
  expected_status: number;
  category: string;
}

function CreateCaseDialog({
  open,
  busy,
  onClose,
  onSave,
}: {
  open: boolean;
  busy: boolean;
  onClose: () => void;
  onSave: (form: CaseCreateInput) => void;
}) {
  const [form, setForm] = useState<CreateCaseForm>({
    name: "",
    method: "GET",
    path: "/",
    expected_status: 200,
    category: "",
  });

  function submit() {
    if (!form.name.trim() || !form.path.trim()) return;
    onSave({
      name: form.name.trim(),
      method: form.method,
      path: form.path.trim(),
      expected_status: Number(form.expected_status) || 200,
      category: form.category ? (form.category as CaseCreateInput["category"]) : null,
    });
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="新增用例"
      description="手动创建一条用例；名称相同的用例会自动去重"
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button
            variant="primary"
            loading={busy}
            onClick={submit}
            disabled={!form.name.trim() || !form.path.trim()}
          >
            新增
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="用例名称">
          <Input
            value={form.name}
            placeholder="如：登录接口返回 token"
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="方法">
            <Select
              value={form.method}
              onChange={(e) => setForm({ ...form, method: e.target.value })}
            >
              {["GET", "POST", "PUT", "PATCH", "DELETE"].map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="路径" className="sm:col-span-2">
            <Input
              value={form.path}
              placeholder="/api/login"
              onChange={(e) => setForm({ ...form, path: e.target.value })}
            />
          </Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="期望状态码">
            <Input
              type="number"
              value={form.expected_status}
              onChange={(e) => setForm({ ...form, expected_status: Number(e.target.value) })}
            />
          </Field>
          <Field label="分类">
            <Select
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
            >
              <option value="">不分类</option>
              <option value="happy">happy（正常路径）</option>
              <option value="boundary">boundary（边界值）</option>
              <option value="negative">negative（异常输入）</option>
            </Select>
          </Field>
        </div>
      </div>
    </Dialog>
  );
}