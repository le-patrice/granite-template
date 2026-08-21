import { client } from "@/client/client.gen";

/**
 * Configure @hey-api/client-fetch base instance.
 * Automatically injects the stored JWT Bearer token into Authorization headers.
 * Strips any redundant '/api/v1' from VITE_API_URL to prevent duplicate '/api/v1/api/v1' routing errors.
 */
const rawUrl = (import.meta.env.VITE_API_URL || "").trim();
const sanitizedBase = rawUrl ? rawUrl.replace(/\/api\/v1\/?$/, "").replace(/\/$/, "") : "";

client.setConfig({
  baseUrl: sanitizedBase,
  auth: () => {
    const token = localStorage.getItem("access_token");
    return token ? token : "";
  },
});

export { client };
