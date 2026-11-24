"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  Select,
  Spinner,
} from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api";
import { useDefects, useProjects, useUpdateDefect } from "@/lib/queries";
import { SEVERITY_STYLES, cn, formatDateTime, truncate } from "@/lib/utils";

function DefectsContent() {
  const search = useSearchParams();
  const toast = useToast();

  const [projectId, setProjectId] = useState(search.get("project_id") ?? "");
  const [status, setStatus] = useState("");

  const projects = useProjects({ limit: 100 });
  const defects = useDefects({
    project_id: projectId || undefined,
    status: status || undefined,
    limit: 100,
  });
  const updateDefect = useUpdateDefect();

  const rows = defects.data?.items ?? [];

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">缺陷</h1>
        <p className="mt-1 text-sm text-slate-500">
          AI 分析失败用例后自动归类；修完把状态改成 fixed，还能看根因与修复建议。
        </p>
      </header>

      <Card>
        <CardHeader
          title={`共 ${defects.data?.total ?? 0} 条`}
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
              <Select className="w-32" value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">全部状态</option>
                {["open", "fixed", "closed", "wontfix"].map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </Select>
              {defects.isFetching && <Spinner size={14} className="text-slate-400" />}
            </div>
          }
        />

        {defects.isLoading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500">
            <Spinner /> 加载中…
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            title="没有缺陷"
            description="有失败用例时，分析节点会自动产出缺陷条目。"
            action={
              <Link href="/executions" className="btn-secondary">
                看执行记录
              </Link>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>缺陷</th>
                  <th>等级</th>
                  <th>分类</th>
                  <th>根因 / 建议</th>
                  <th>时间</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((defect) => (
                  <tr key={defect.id}>
                    <td className="max-w-xs">
                      <p className="font-medium text-slate-800">{defect.title}</p>
                      <p className="mt-0.5 text-xs text-slate-500" title={defect.description}>
                        {truncate(defect.description, 90)}
                      </p>
                      <Link
                        href={`/executions/${defect.execution_id}`}
                        className="mt-1 inline-block text-[11px] text-brand-600 hover:underline"
                      >
                        查看所属执行
                      </Link>
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
                      {defect.root_cause ? (
                        <p>根因：{truncate(defect.root_cause, 80)}</p>
                      ) : (
                        <p className="text-slate-400">—</p>
                      )}
                      {defect.fix_suggestion && (
                        <p className="mt-0.5 text-slate-500">
                          建议：{truncate(defect.fix_suggestion, 80)}
                        </p>
                      )}
                    </td>
                    <td className="whitespace-nowrap text-xs text-slate-500">
                      {formatDateTime(defect.created_at)}
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
                            toast.success("状态已更新");
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

export default function DefectsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center gap-2 py-16 text-sm text-slate-500">
          <Spinner /> 加载中…
        </div>
      }
    >
      <DefectsContent />
    </Suspense>
  );
}
