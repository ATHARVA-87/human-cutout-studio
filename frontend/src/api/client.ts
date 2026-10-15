import type { Account, Capability, Composition, Prediction } from "../types";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, { credentials: "include", ...options });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  capabilities: async (): Promise<Capability[]> => (await request<{ operations: Capability[] }>("/api/capabilities")).operations,
  history: async (): Promise<Prediction[]> => (await request<{ items: Prediction[] }>("/api/predictions")).items,
  segment: async (file: File): Promise<Prediction> => {
    const body = new FormData();
    body.append("image", file);
    return request<Prediction>("/api/predictions", { method: "POST", body });
  },
  me: () => request<Account>("/api/auth/me"),
  auth: (path: "register" | "login", email: string, password: string) => request<Account>(`/api/auth/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) }),
  recharge: () => request<Account>("/api/auth/recharge", { method: "POST" }),
  compose: async (person: File, background: File): Promise<Composition> => { const body = new FormData(); body.append("person_image", person); body.append("background_image", background); return request<Composition>("/api/compositions", { method: "POST", body }); },
  assetUrl: (path: string): string => `${baseUrl}${path}`,
};
