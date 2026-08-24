const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

function responseErrorMessage(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== "object") return fallback;
  const error = "error" in payload ? payload.error : null;
  if (error && typeof error === "object" && "message" in error && typeof error.message === "string") return error.message;
  const detail = "detail" in payload ? payload.detail : null;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string") return detail.message;
  return fallback;
}

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("zhihu_token") : null;
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });
  if (res.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("zhihu_token");
      localStorage.removeItem("zhihu-auth");
      window.location.assign(new URL("/welcome", window.location.origin));
    }
    throw new Error("未登录");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(responseErrorMessage(err, "请求失败"));
  }
  return res.json();
}

async function fetchBlob(path: string, options?: RequestInit): Promise<Blob> {
  const token = typeof window !== "undefined" ? localStorage.getItem("zhihu_token") : null;
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options?.headers },
  });
  if (res.status === 401) {
    if (typeof window !== "undefined") window.location.assign(new URL("/welcome", window.location.origin));
    throw new Error("未登录");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(responseErrorMessage(err, "文件读取失败"));
  }
  return res.blob();
}

async function postStream<T>(
  path: string,
  data: unknown,
  onEvent: (event: T) => void | Promise<void>,
  options?: { signal?: AbortSignal },
): Promise<void> {
  const token = typeof window !== "undefined" ? localStorage.getItem("zhihu_token") : null;
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/x-ndjson",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(data),
    signal: options?.signal,
  });
  if (res.status === 401) {
    if (typeof window !== "undefined") {
      localStorage.removeItem("zhihu_token");
      localStorage.removeItem("zhihu-auth");
      window.location.assign(new URL("/welcome", window.location.origin));
    }
    throw new Error("未登录");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(responseErrorMessage(err, "请求失败"));
  }
  if (!res.body) throw new Error("服务没有返回可读取的流");
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/x-ndjson")) throw new Error("服务返回了无法识别的流格式");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        await onEvent(JSON.parse(line) as T);
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) await onEvent(JSON.parse(buffer) as T);
  } catch (error) {
    try {
      await reader.cancel(error);
    } catch {
      // The browser may already have closed the stream after AbortController.abort().
    }
    throw error;
  } finally {
    reader.releaseLock();
  }
}

export const api = {
  get: <T>(path: string) => fetchAPI<T>(path),
  post: <T>(path: string, data?: unknown) =>
    fetchAPI<T>(path, { method: "POST", body: JSON.stringify(data) }),
  put: <T>(path: string, data?: unknown) =>
    fetchAPI<T>(path, { method: "PUT", body: JSON.stringify(data) }),
  patch: <T>(path: string, data?: unknown) =>
    fetchAPI<T>(path, { method: "PATCH", body: JSON.stringify(data) }),
  delete: <T>(path: string) => fetchAPI<T>(path, { method: "DELETE" }),
  upload: async <T>(path: string, formData: FormData): Promise<T> => {
    const token = typeof window !== "undefined" ? localStorage.getItem("zhihu_token") : null;
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: formData,
    });
    if (res.status === 401) {
      if (typeof window !== "undefined") {
        localStorage.removeItem("zhihu_token");
        localStorage.removeItem("zhihu-auth");
        window.location.assign(new URL("/welcome", window.location.origin));
      }
      throw new Error("未登录");
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(responseErrorMessage(err, "请求失败"));
    }
    return res.json();
  },
  blob: (path: string) => fetchBlob(path),
  postBlob: (path: string) => fetchBlob(path, { method: "POST" }),
  postStream,
};
