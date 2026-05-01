"use client";

// Fallback to the public HuggingFace Space backend so the deployed Vercel
// site keeps working even if NEXT_PUBLIC_API_URL hasn't been set in the
// dashboard yet. Override at build time with NEXT_PUBLIC_API_URL.
const DEFAULT_API_BASE = "https://rah7809-clipgenius-api.hf.space";
const API_BASE = process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_BASE;
const TOKEN_KEY = "clipgenius_token";

export class ApiError extends Error {
  status: number;
  data: unknown;
  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

function buildUrl(path: string) {
  if (!API_BASE || API_BASE === "/") return path;
  if (path.startsWith("http")) return path;
  return `${API_BASE.replace(/\/$/, "")}${path}`;
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let body: BodyInit | undefined = options.body as BodyInit | undefined;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }

  const res = await fetch(buildUrl(path), { ...options, headers, body });
  const text = await res.text();
  let data: unknown = undefined;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    data = text;
  }
  if (!res.ok) {
    type ErrorBody = { detail?: string };
    const errBody = (typeof data === "object" && data !== null ? (data as ErrorBody) : null);
    const detail = errBody?.detail || res.statusText;
    throw new ApiError(detail, res.status, data);
  }
  return data as T;
}

export const swrFetcher = <T = unknown>(path: string) => api<T>(path);
