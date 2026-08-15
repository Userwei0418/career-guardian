const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

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
    throw new Error(err.error?.message || err.detail || "请求失败");
  }
  return res.json();
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
      throw new Error(err.error?.message || err.detail || "请求失败");
    }
    return res.json();
  },
};
