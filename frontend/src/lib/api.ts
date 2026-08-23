import { client } from "@/client/client.gen";

export class ApiError extends Error {
  status?: number;
  data?: unknown;
  retryAfter?: number;

  constructor(message: string, status?: number, data?: unknown, retryAfter?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
    this.retryAfter = retryAfter;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

/**
 * Parses raw error and response objects from backend / fetch into user-friendly ApiError.
 */
export function parseApiError(error: unknown, response?: Response): ApiError {
  // 1. Network / Connection Refused (no response produced)
  if (!response) {
    return new ApiError(
      "Unable to connect to the backend server. Please check your network connection.",
      0,
      error
    );
  }

  const status = response.status;
  const rawData: Record<string, unknown> =
    error && typeof error === "object" ? (error as Record<string, unknown>) : {};

  // 2. 401 Unauthorized
  if (status === 401) {
    return new ApiError(
      "Incorrect email or password. Please verify your credentials and try again.",
      401,
      error
    );
  }

  // 3. 429 Too Many Requests (extract retry_after from header or response body)
  if (status === 429) {
    let retryAfter: number | undefined;

    // Check Retry-After header
    const headerVal = response.headers?.get("Retry-After");
    if (headerVal) {
      const parsed = parseInt(headerVal, 10);
      if (!isNaN(parsed) && parsed > 0) {
        retryAfter = parsed;
      }
    }

    // Check JSON body retry_after / retryAfter
    if (retryAfter === undefined && rawData) {
      if (typeof rawData.retry_after === "number") {
        retryAfter = rawData.retry_after;
      } else if (typeof rawData.retryAfter === "number") {
        retryAfter = rawData.retryAfter;
      } else if (typeof rawData.retry_after === "string") {
        const parsed = parseInt(rawData.retry_after, 10);
        if (!isNaN(parsed)) retryAfter = parsed;
      }
    }

    const message =
      retryAfter !== undefined
        ? `Too many attempts. Please wait ${retryAfter} seconds before trying again.`
        : "Too many attempts. Please wait a few seconds before trying again.";

    return new ApiError(message, 429, error, retryAfter);
  }

  // 4. 500 / 502 / 503 / 504 Server Error
  if (status >= 500 && status <= 599) {
    return new ApiError(
      "The platform service is currently unavailable. Please try again shortly.",
      status,
      error
    );
  }

  // 5. Generic / Structured error extracting from { detail, error, message }
  let extractedMessage: string | null = null;
  if (rawData) {
    if (typeof rawData.detail === "string" && rawData.detail.trim()) {
      extractedMessage = rawData.detail.trim();
    } else if (Array.isArray(rawData.detail) && rawData.detail.length > 0) {
      extractedMessage = rawData.detail
        .map((d: unknown) =>
          typeof d === "string"
            ? d
            : (d as Record<string, unknown>)?.msg ||
              (d as Record<string, unknown>)?.message ||
              JSON.stringify(d)
        )
        .join("; ");
    } else if (typeof rawData.error === "string" && rawData.error.trim()) {
      extractedMessage = rawData.error.trim();
    } else if (typeof rawData.message === "string" && rawData.message.trim()) {
      extractedMessage = rawData.message.trim();
    }
  }

  if (typeof error === "string" && error.trim()) {
    extractedMessage = error.trim();
  }

  const finalMessage = extractedMessage || response.statusText || "An unexpected error occurred.";
  return new ApiError(finalMessage, status, error);
}

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

// Register global error interceptor
client.interceptors.error.use((error, response, request, options) => {
  const parsedError = parseApiError(error, response);

  if (import.meta.env.DEV) {
    console.warn(`[API Error ${response?.status ?? "Network"}]:`, {
      message: parsedError.message,
      status: parsedError.status,
      retryAfter: parsedError.retryAfter,
      url: request?.url || (options as { url?: string })?.url,
      data: parsedError.data,
    });
  }

  return parsedError;
});

export { client };

