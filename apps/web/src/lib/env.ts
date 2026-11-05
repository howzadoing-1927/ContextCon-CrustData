export type ApiMode = "fixture" | "live";

export const env = {
  apiMode: (process.env.NEXT_PUBLIC_OUTCOME_API_MODE === "live" ? "live" : "fixture") as ApiMode,
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  supabaseAnonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "",
};

export const supabaseConfigured = Boolean(env.supabaseUrl && env.supabaseAnonKey);
