import type {
  CurrentUser,
  DataSource,
  Execution,
  Preview,
  ReportAdmin,
  ReportSummary,
  ReportWrite,
} from "./types";

const TOKEN_KEYS = ["identity_access_token", "access_token"];

export function getToken(): string | null {
  return TOKEN_KEYS.map((key) => localStorage.getItem(key)).find(Boolean) || null;
}

export function clearToken(): void {
  TOKEN_KEYS.forEach((key) => localStorage.removeItem(key));
}

export async function login(email: string, password: string): Promise<void> {
  const response = await fetch("/identity-api/auth/login", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.detail || `HTTP ${response.status}`);
  localStorage.setItem(TOKEN_KEYS[0], data.access_token);
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401) clearToken();
    throw new Error(data?.detail || data?.message || `HTTP ${response.status}`);
  }
  return data as T;
}

export const fetchMe = () => requestJson<CurrentUser>("/api/v1/me");
export const fetchReports = (search = "") =>
  requestJson<ReportSummary[]>(`/api/v1/reports${search ? `?search=${encodeURIComponent(search)}` : ""}`);
export const fetchAdminReport = (id: number) => requestJson<ReportAdmin>(`/api/v1/admin/reports/${id}`);
export const fetchSources = () => requestJson<DataSource[]>("/api/v1/admin/sources");
export const fetchExecutions = () => requestJson<Execution[]>("/api/v1/admin/executions");

export function previewReport(id: number, parameters: Record<string, unknown>, rowLimit?: number): Promise<Preview> {
  return requestJson<Preview>(`/api/v1/reports/${id}/preview`, {
    method: "POST",
    body: JSON.stringify({ parameters, row_limit: rowLimit }),
  });
}

export async function exportReport(
  report: ReportSummary,
  parameters: Record<string, unknown>,
  format: "csv" | "xlsx",
  rowLimit?: number,
): Promise<void> {
  const token = getToken();
  const response = await fetch(`/api/v1/reports/${report.id}/export?format=${format}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ parameters, row_limit: rowLimit }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    if (response.status === 401) clearToken();
    throw new Error(data?.detail || `HTTP ${response.status}`);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] || `${report.slug}.${format}`;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function saveReport(payload: ReportWrite, id?: number): Promise<ReportAdmin> {
  return requestJson<ReportAdmin>(id ? `/api/v1/admin/reports/${id}` : "/api/v1/admin/reports", {
    method: id ? "PATCH" : "POST",
    body: JSON.stringify(payload),
  });
}

export function createSource(payload: {
  name: string;
  engine: "mssql" | "postgresql";
  dsn: string;
  allowed_schemas: string[];
  is_active: boolean;
}): Promise<DataSource> {
  return requestJson<DataSource>("/api/v1/admin/sources", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function testSource(id: number): Promise<{ status: string; message: string }> {
  return requestJson(`/api/v1/admin/sources/${id}/test`, { method: "POST" });
}
