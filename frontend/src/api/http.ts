// Fetch helper dùng chung cho mọi module trong api/ — không export ra ngoài
// api/, mỗi resource (graph.ts, impact.ts, ...) tự bọc lại theo domain của nó.

const BASE = "/api/v1";

export function selectedDatabaseId(): number | null {
  const raw = localStorage.getItem("data_lineage_database_id");
  const value = raw ? Number(raw) : NaN;
  return Number.isInteger(value) && value > 0 ? value : null;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem("data_lineage_token");
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers as Record<string, string> | undefined),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // response không phải JSON (vd lỗi hạ tầng) — giữ statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function requestMultipart<T>(path: string, form: FormData): Promise<T> {
  const token = localStorage.getItem("data_lineage_token");
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // giữ statusText nếu response không phải JSON
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}
