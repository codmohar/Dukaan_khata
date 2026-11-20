"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getWsUrl } from "./api";

export type Msg = { role: "you" | "ai"; text: string; audio?: string; silent?: boolean };
export type Draft = {
  draft_id: string;
  customer: string;
  customer_id?: string;
  customer_phone?: string | null;
  member_id?: string | null;
  member_name?: string | null;
  relationship?: string | null;
  item_note?: string | null;
  rule_warnings?: Array<{ rule_category: string; message: string; [key: string]: any }>;
  requires_override?: boolean;
  type: "credit" | "payment" | "adjustment";
  amount: number;
  payment_mode?: "cash" | "upi" | "credit" | "other" | null;
  adjustment_reason?: "discount" | "return" | "write_off" | "correction" | null;
  due_date?: string | null;
  backdated_to?: string | null;
  items?: { name?: string; qty?: string; amount?: number }[] | null;
  note?: string;
  current_balance?: number;
  projected_balance?: number;
  is_advance?: boolean;
  anomaly_warning?: boolean;
  warning_message?: string | null;
};
export type Reminder = {
  customer: string;
  phone?: string | null;
  balance: number;
  reminder_text: string;
  whatsapp_url: string;
};
export type Status =
  | "connecting"
  | "idle"
  | "monitoring"
  | "listening"
  | "thinking"
  | "speaking"
  | "offline";

const SILENCE_MS = 750; // 0.75s pause to auto-submit brisk kirana speech
const MAX_UTTERANCE_MS = 25000;

function playChime(freq = 587.33, duration = 0.15) {
  try {
    const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(freq, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + duration);
    gain.gain.setValueAtTime(0.18, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + duration);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + duration);
  } catch {}
}

export function useVoice(language: string) {
  const [status, setStatus] = useState<Status>("connecting");
  const statusRef = useRef<Status>("connecting");

  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [reminder, setReminder] = useState<Reminder | null>(null);
  const [promiseCard, setPromiseCard] = useState<any | null>(null);
  const [ruleCard, setRuleCard] = useState<any | null>(null);
  const [reconcileResult, setReconcileResult] = useState<any | null>(null);
  const draftRef = useRef<Draft | null>(null);

  const [error, setError] = useState("");
  const [audioLevel, setAudioLevel] = useState(0); // 0-100 for soundwave visualizer
  const [handsFree, setHandsFree] = useState(true);
  const handsFreeRef = useRef(true);

  const [wakeWordActive, setWakeWordActive] = useState(true);
  const [wakeDetected, setWakeDetected] = useState(false);
  const [micActive, setMicActive] = useState(false);
  const micActiveRef = useRef(false);

  const ws = useRef<WebSocket | null>(null);
  const rec = useRef<{
    ctx: AudioContext;
    stream: MediaStream;
    node: ScriptProcessorNode;
    src: MediaStreamAudioSourceNode;
  } | null>(null);
  const wakeRec = useRef<any>(null);

  // Keep refs in sync
  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    handsFreeRef.current = handsFree;
  }, [handsFree]);

  useEffect(() => {
    micActiveRef.current = micActive;
  }, [micActive]);

  // WebSocket Connection Lifecycle (single stable connection per language)
  useEffect(() => {
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;
    let pingTimer: ReturnType<typeof setInterval>;

    const connect = () => {
      if (closed) return;
      setStatus("connecting");
      try {
        const s = new WebSocket(`${getWsUrl()}?language=${language}`);
        ws.current = s;

        s.onopen = () => {
          setStatus(micActiveRef.current ? "monitoring" : "idle");
          setError("");
          clearInterval(pingTimer);
          pingTimer = setInterval(() => {
            if (s.readyState === WebSocket.OPEN) {
              try {
                s.send(JSON.stringify({ type: "ping" }));
              } catch {}
            }
          }, 25000);
        };

        s.onclose = () => {
          clearInterval(pingTimer);
          if (!closed) {
            setStatus("offline");
            retry = setTimeout(connect, 1000);
          }
        };

        s.onerror = () => {
          setStatus("offline");
        };

        s.onmessage = (e) => {
          try {
            const m = JSON.parse(e.data);
            if (m.type === "pong") return;
            if (m.type === "noop") {
              setStatus(micActiveRef.current && handsFreeRef.current ? "monitoring" : "idle");
              return;
            }
            if (m.type === "silent_context") {
              setMsgs((prev) => {
                if (prev.length === 0) return prev;
                const next = [...prev];
                const last = next[next.length - 1];
                if (last.role === "you") {
                  next[next.length - 1] = { ...last, silent: true };
                }
                return next;
              });
              setStatus(micActiveRef.current && handsFreeRef.current ? "monitoring" : "idle");
              return;
            }
            if (m.type === "transcript") {
              setMsgs((x) => [...x, { role: "you", text: m.text }]);
            } else if (m.type === "reply") {
              setMsgs((x) => [...x, { role: "ai", text: m.text }]);
              // If no audio event accompanies reply, return to monitoring
              if (statusRef.current === "thinking") {
                setStatus(micActiveRef.current && handsFreeRef.current ? "monitoring" : "idle");
              }
            } else if (m.type === "draft") {
              setDraft({ ...m, type: m.tx_type || m.type });
            } else if (m.type === "promise_card") {
              setPromiseCard(m);
            } else if (m.type === "rule_card") {
              setRuleCard(m);
            } else if (m.type === "reconciliation_result") {
              setReconcileResult(m);
            } else if (m.type === "reminder") {
              setReminder(m);
            } else if (m.type === "confirmed" || m.type === "cancelled") {
              setDraft(null);
            } else if (m.type === "error") {
              setError(m.message);
              setStatus(micActiveRef.current && handsFreeRef.current ? "monitoring" : "idle");
            } else if (m.type === "audio") {
              // Attach audio to the last AI message
              setMsgs((prev) => {
                const next = [...prev];
                for (let i = next.length - 1; i >= 0; i--) {
                  if (next[i].role === "ai" && !next[i].audio) {
                    next[i] = { ...next[i], audio: m.data };
                    break;
                  }
                }
                return next;
              });

              try {
                const a = new Audio("data:audio/wav;base64," + m.data);
                setStatus("speaking");
                a.onended = a.onerror = () => {
                  // After speaking, immediately resume hands-free monitoring!
                  setStatus(micActiveRef.current && handsFreeRef.current ? "monitoring" : "idle");
                };
                a.play().catch(() => {
                  setStatus(micActiveRef.current && handsFreeRef.current ? "monitoring" : "idle");
                });
              } catch {
                setStatus(micActiveRef.current && handsFreeRef.current ? "monitoring" : "idle");
              }
            }
          } catch {
            // ignore malformed frame
          }
        };
      } catch {
        setStatus("offline");
        retry = setTimeout(connect, 1200);
      }
    };

    connect();

    return () => {
      closed = true;
      clearTimeout(retry);
      clearInterval(pingTimer);
      ws.current?.close();
    };
  }, [language]);

  // Stop current active utterance and submit to backend
  const stopUtterance = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type: "end_utterance" }));
    }
    setStatus("thinking");
    setWakeDetected(false);
  }, []);

  // Initialize Persistent Microphone Stream with Continuous Web Audio VAD
  const startContinuousVAD = useCallback(async () => {
    setError("");
    if (rec.current) {
      // Already running
      setMicActive(true);
      if (statusRef.current === "idle" || statusRef.current === "connecting") {
        setStatus("monitoring");
      }
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 16000,
        },
      });

      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)({
        sampleRate: 16000,
      });
      if (ctx.state === "suspended") {
        await ctx.resume();
      }

      const src = ctx.createMediaStreamSource(stream);
      const node = ctx.createScriptProcessor(4096, 1, 1);

      // ~400ms circular pre-roll buffer to preserve beginning of words
      const preRollChunks: ArrayBuffer[] = [];
      let noiseFloor = 0.008;
      let isSpoken = false;
      let lastVoice = Date.now();
      let utteranceStart = 0;

      node.onaudioprocess = (ev) => {
        const f = ev.inputBuffer.getChannelData(0);
        let sum = 0;
        const pcm = new Int16Array(f.length);
        for (let i = 0; i < f.length; i++) {
          sum += f[i] * f[i];
          pcm[i] = Math.max(-1, Math.min(1, f[i])) * 0x7fff;
        }

        const rms = Math.sqrt(sum / f.length);
        // Level for visual soundwave (0-100)
        const lvl = Math.min(100, Math.round(rms * 450));
        setAudioLevel(lvl);

        const curStatus = statusRef.current;
        const isHF = handsFreeRef.current;

        // Software Gate: Ignore audio while DukaanAI is speaking, thinking, or offline
        if (
          curStatus === "speaking" ||
          curStatus === "thinking" ||
          curStatus === "offline" ||
          curStatus === "connecting"
        ) {
          preRollChunks.length = 0;
          return;
        }

        // Monitoring State: Mic is live, waiting for voice
        if (curStatus === "monitoring" || curStatus === "idle") {
          noiseFloor = 0.96 * noiseFloor + 0.04 * rms;
          preRollChunks.push(pcm.buffer.slice(0));
          if (preRollChunks.length > 2) {
            preRollChunks.shift();
          }

          // Dukaan Ambient Noise Immunity: Filter distant background customer chatter
          const vadThreshold = Math.max(0.024, noiseFloor * 2.5);

          if (isHF && rms > vadThreshold) {
            // Speech detected hands-free!
            isSpoken = true;
            utteranceStart = Date.now();
            lastVoice = Date.now();
            setStatus("listening");

            // Flush pre-roll chunks so first syllable is never clipped
            if (ws.current?.readyState === WebSocket.OPEN) {
              for (const chunk of preRollChunks) {
                ws.current.send(chunk);
              }
            }
            preRollChunks.length = 0;
            return;
          }
        }

        // Listening State: Actively streaming audio
        if (curStatus === "listening") {
          if (ws.current?.readyState === WebSocket.OPEN) {
            ws.current.send(pcm.buffer);
          }

          const vadThreshold = Math.max(0.018, noiseFloor * 1.8);
          if (rms > vadThreshold) {
            lastVoice = Date.now();
          }

          const now = Date.now();
          // Pause detected for SILENCE_MS (1.4s) -> Auto-submit!
          if (
            (isSpoken && now - lastVoice > SILENCE_MS) ||
            now - utteranceStart > MAX_UTTERANCE_MS
          ) {
            if (ws.current?.readyState === WebSocket.OPEN) {
              ws.current.send(JSON.stringify({ type: "end_utterance" }));
            }
            setStatus("thinking");
            isSpoken = false;
            preRollChunks.length = 0;
          }
        }
      };

      src.connect(node);
      node.connect(ctx.destination);
      rec.current = { ctx, stream, node, src };
      setMicActive(true);

      if (statusRef.current === "idle" || statusRef.current === "connecting") {
        setStatus("monitoring");
      }
    } catch (e) {
      console.warn("Microphone access prompt:", e);
      setError("Please allow microphone access to enable Hands-Free voice intake.");
      setMicActive(false);
    }
  }, []);

  // Attempt auto-activation of mic on mount if browser already has permission
  useEffect(() => {
    if (typeof window !== "undefined" && navigator.mediaDevices) {
      navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then(() => {
          startContinuousVAD();
        })
        .catch(() => {
          // Needs initial user gesture (normal browser security policy)
        });
    }
  }, [startContinuousVAD]);

  // "Hi Khata" Web Speech wake-word recognizer running alongside VAD
  useEffect(() => {
    if (!wakeWordActive || typeof window === "undefined") return;
    const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRec) return;

    let active = true;
    let sr: any = null;

    try {
      sr = new SpeechRec();
      sr.continuous = true;
      sr.interimResults = true;
      sr.lang = "en-IN";

      sr.onresult = (ev: any) => {
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          const text = ev.results[i][0].transcript.toLowerCase();
          if (
            text.includes("hi khata") ||
            text.includes("hey khata") ||
            text.includes("hello khata") ||
            text.includes("hai khata") ||
            text.includes("khata")
          ) {
            if (statusRef.current === "monitoring" || statusRef.current === "idle") {
              playChime(659.25, 0.12);
              setWakeDetected(true);
              setStatus("listening");
            }
            break;
          }
        }
      };

      sr.onerror = () => {
        if (active && (statusRef.current === "monitoring" || statusRef.current === "idle")) {
          setTimeout(() => {
            try {
              if (active) sr.start();
            } catch {}
          }, 1500);
        }
      };

      sr.onend = () => {
        if (active && (statusRef.current === "monitoring" || statusRef.current === "idle")) {
          try {
            sr.start();
          } catch {}
        }
      };

      if (statusRef.current === "monitoring" || statusRef.current === "idle") {
        try {
          sr.start();
        } catch {}
      }
    } catch {}

    wakeRec.current = sr;

    return () => {
      active = false;
      try {
        sr?.stop();
      } catch {}
    };
  }, [wakeWordActive]);

  const sendText = useCallback((text: string) => {
    if (!text.trim() || ws.current?.readyState !== WebSocket.OPEN) return;
    setStatus("thinking");
    ws.current.send(JSON.stringify({ type: "text", text }));
  }, []);

  const playAudio = useCallback((base64Data: string) => {
    try {
      const a = new Audio("data:audio/wav;base64," + base64Data);
      setStatus("speaking");
      a.onended = a.onerror = () => {
        setStatus(micActive && handsFreeRef.current ? "monitoring" : "idle");
      };
      a.play().catch(() => {
        setStatus(micActive && handsFreeRef.current ? "monitoring" : "idle");
      });
    } catch {}
  }, [micActive]);

  const reset = useCallback(() => {
    ws.current?.send(JSON.stringify({ type: "reset" }));
    setMsgs([]);
    setDraft(null);
    setError("");
    setStatus(micActive && handsFreeRef.current ? "monitoring" : "idle");
    setWakeDetected(false);
  }, [micActive]);

  // Clean up mic on unmount
  useEffect(() => {
    return () => {
      const r = rec.current;
      if (r) {
        try {
          r.node.disconnect();
          r.src.disconnect();
          r.stream.getTracks().forEach((t) => t.stop());
          r.ctx.close();
        } catch {}
      }
    };
  }, []);

  const start = useCallback(async () => {
    if (!rec.current) {
      await startContinuousVAD();
    }
    if (statusRef.current === "monitoring" || statusRef.current === "idle") {
      playChime(587.33, 0.12);
      setStatus("listening");
    }
  }, [startContinuousVAD]);

  const stop = useCallback(() => {
    stopUtterance();
  }, [stopUtterance]);

  const clearReminder = useCallback(() => setReminder(null), []);
  const clearPromiseCard = useCallback(() => setPromiseCard(null), []);
  const clearRuleCard = useCallback(() => setRuleCard(null), []);
  const clearReconcileResult = useCallback(() => setReconcileResult(null), []);

  return {
    status,
    msgs,
    draft,
    reminder,
    clearReminder,
    promiseCard,
    clearPromiseCard,
    ruleCard,
    clearRuleCard,
    reconcileResult,
    clearReconcileResult,
    error,
    audioLevel,
    handsFree,
    setHandsFree,
    wakeWordActive,
    setWakeWordActive,
    wakeDetected,
    micActive,
    startContinuousVAD,
    stopUtterance,
    start,
    stop,
    sendText,
    playAudio,
    reset,
  };
}
