import type { Account, Composition, Page, Prediction, SavedPlacement } from "../types";

const PAGE_SIZE = 12;

/** An error from the backend, keeping the HTTP status so the UI can react (401 -> login, 402 -> recharge). */
export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

/** FastAPI sends `detail` as a string, or as a list of field errors for 422 validation failures. */
function readableDetail(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = Array.isArray(item?.loc) ? item.loc[item.loc.length - 1] : undefined;
        const message = typeof item?.msg === "string" ? item.msg : "is invalid";
        return field ? `${field}: ${message}` : message;
      })
      .join(" ");
  }
  return `Request failed (${status}).`;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  // Same origin in development (Vite proxy) and production (FastAPI serves the app), so the cookie is sent automatically.
  const response = await fetch(path, { credentials: "same-origin", ...options });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new ApiError(readableDetail(payload?.detail, response.status), response.status);
  }
  if (response.status === 204) return undefined as T; // e.g. logout has no body
  return response.json() as Promise<T>;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

export const api = {
  me: () => request<Account>("/api/auth/me"),
  login: (email: string, password: string) => postJson<Account>("/api/auth/login", { email, password }),
  register: (email: string, password: string) => postJson<Account>("/api/auth/register", { email, password }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  recharge: () => request<Account>("/api/auth/recharge", { method: "POST" }),
  verifyEmail: (token: string) => postJson<void>("/api/auth/verify-email", { token }),
  resendVerification: () => request<void>("/api/auth/resend-verification", { method: "POST" }),
  forgotPassword: (email: string) => postJson<{ detail: string }>("/api/auth/forgot-password", { email }),
  resetPassword: (token: string, password: string) => postJson<void>("/api/auth/reset-password", { token, password }),
  segment: (image: File) => {
    const body = new FormData();
    body.append("image", image);
    return request<Prediction>("/api/predictions", { method: "POST", body });
  },
  compose: (person: File, background: File) => {
    const body = new FormData();
    body.append("person_image", person);
    body.append("background_image", background);
    return request<Composition>("/api/compositions", { method: "POST", body });
  },
  // History (newest first, PAGE_SIZE items per call)
  listPredictions: (offset = 0) => request<Page<Prediction>>(`/api/predictions?limit=${PAGE_SIZE}&offset=${offset}`),
  listCompositions: (offset = 0) => request<Page<Composition>>(`/api/compositions?limit=${PAGE_SIZE}&offset=${offset}`),
  deletePrediction: (id: string) => request<void>(`/api/predictions/${id}`, { method: "DELETE" }),
  deleteComposition: (id: string) => request<void>(`/api/compositions/${id}`, { method: "DELETE" }),
  // keepalive lets a save that starts while the page is being left still reach the server.
  savePlacement: (id: string, placement: SavedPlacement) =>
    request<void>(`/api/compositions/${id}/placement`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(placement),
      keepalive: true,
    }),
  deleteAccount: (password: string) =>
    request<void>("/api/auth/account", { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) }),
};
