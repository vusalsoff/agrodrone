export const appEnv = {
  appName: process.env.NEXT_PUBLIC_APP_NAME || "AgroDrone",
  get apiBaseUrl(): string {
    const explicit = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "";
    if (
      typeof window !== "undefined" &&
      window.location.hostname !== "localhost" &&
      window.location.hostname !== "127.0.0.1" &&
      (!explicit || explicit.includes("127.0.0.1") || explicit.includes("localhost"))
    ) {
      return "";
    }
    return explicit || "http://127.0.0.1:8000";
  },
  environment: process.env.NEXT_PUBLIC_ENVIRONMENT || "development",
  mapStyleUrl: process.env.NEXT_PUBLIC_MAP_STYLE_URL || "",
} as const;
