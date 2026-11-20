export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";
export const WS_URL = API_URL.replace(/^http/, "ws") + "/ws/voice";
export const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL;
export const SUPABASE_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;
export const PICOVOICE_KEY = process.env.EXPO_PUBLIC_PICOVOICE_KEY ?? "";
export const WAKE_KEYWORD_PATH = "hey_dukaan_android.ppn"; // Android asset path; iOS: add hey_dukaan_ios.ppn to the Xcode bundle
