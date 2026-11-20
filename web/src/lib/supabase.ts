"use client";
import { createClient } from "@supabase/supabase-js";
import { useEffect, useRef, useState } from "react";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const supabase = url && key ? createClient(url, key) : null;

/** Runs `load` now and again whenever customers/transactions change (Supabase Realtime), or polls every 5 s if without Supabase. */
export function useLive(load: () => void, deps: unknown[] = []) {
  const ref = useRef(load);
  ref.current = load;

  useEffect(() => {
    const run = () => ref.current();
    run();

    if (!supabase) {
      const t = setInterval(run, 5000);
      return () => clearInterval(t);
    }

    const ch = supabase
      .channel("live-" + Math.random().toString(36).slice(2))
      .on("postgres_changes", { event: "*", schema: "public", table: "transactions" }, run)
      .on("postgres_changes", { event: "*", schema: "public", table: "customers" }, run)
      .subscribe();

    return () => {
      supabase.removeChannel(ch);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

/** Hook to check if Supabase Realtime is currently connected. */
export function useRealtimeStatus() {
  const [isLive, setIsLive] = useState<boolean>(!!supabase);

  useEffect(() => {
    if (!supabase) {
      setIsLive(false);
      return;
    }
    setIsLive(true);
  }, []);

  return isLive;
}
