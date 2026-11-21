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
  pending_promise?: {
    promise_id: string;
    entity_name: string;
    promised_amount?: number | null;
    expected_date: string;
    description: string;
    status: string;
    days_overdue?: number;
  } | null;
  promise_warning?: boolean;
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

const SILENCE_MS = 1800; // 1.8s pause to allow natural conversational dialogue cadence
const MAX_UTTERANCE_MS = 30000;

function playChime(freq = 587.33, duration = 0.15) {
  try {
    const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
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

/**
 * Resamples a Float32Array from inputSampleRate (typically 44100 or 48000 Hz)
 * to 16000 Hz mono Int16 PCM for high-accuracy backend STT.
 */
function downsampleTo16k(buffer: Float32Array, inputSampleRate: number): Int16Array {
  if (inputSampleRate === 16000) {
    const pcm = new Int16Array(buffer.length);
    for (let i = 0; i < buffer.length; i++) {
      pcm[i] = Math.max(-32768, Math.min(32767, Math.round(buffer[i] * 32767)));
    }
    return pcm;
  }
  const ratio = inputSampleRate / 16000;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Int16Array(newLength);
  let offsetResult = 0;
  let offsetBuffer = 0;
  while (offsetResult < newLength) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
    let accum = 0;
    let count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
      accum += buffer[i];
      count++;
    }
    const sample = count > 0 ? accum / count : 0;
    result[offsetResult] = Math.max(-32768, Math.min(32767, Math.round(sample * 32767)));
    offsetResult++;
    offsetBuffer = nextOffsetBuffer;
  }
  return result;
}

export function useVoice(language: string) {
  const [status, setStatus] = useState<Status>("connecting");
  const statusRef = useRef<Status>("connecting");

  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [cashInCard, setCashInCard] = useState<any | null>(null);
  const [reminder, setReminder] = useState<Reminder | null>(null);
  const [promiseCard, setPromiseCard] = useState<any | null>(null);
  const [ruleCard, setRuleCard] = useState<any | null>(null);
  const [reconcileResult, setReconcileResult] = useState<any | null>(null);
  const draftRef = useRef<Draft | null>(null);

  const [error, setError] = useState("");
  const [interimText, setInterimText] = useState("");
  const [audioLevel, setAudioLevel] = useState(0); // 0-100 for soundwave visualizer
  const [handsFree, setHandsFree] = useState(true);
  const handsFreeRef = useRef(true);

  const [wakeWordActive, setWakeWordActive] = useState(true);
  const [wakeDetected, setWakeDetected] = useState(false);
  const [micActive, setMicActive] = useState(false);
  const micActiveRef = useRef(false);

  const isSpokenRef = useRef(false);
  const lastSubmittedTextRef = useRef("");
  const currentTranscriptRef = useRef("");
  const accumulatedTranscriptRef = useRef("");
  const debounceSubmitRef = useRef<any>(null);

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

  const sendText = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!trimmed || ws.current?.readyState !== WebSocket.OPEN) return;
    if (trimmed === lastSubmittedTextRef.current) return;
    lastSubmittedTextRef.current = trimmed;
    setTimeout(() => {
      lastSubmittedTextRef.current = "";
    }, 2000);

    setStatus("thinking");
    setInterimText("");
    ws.current.send(JSON.stringify({ type: "text", text: trimmed }));
  }, []);

  // WebSocket Connection Lifecycle (single stable connection per language)
  useEffect(() => {
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;
    let pingTimer: ReturnType<typeof setInterval>;

    const connect = () => {
      if (closed) return;
      setStatus("connecting");
      try {
        const s = new WebSocket(getWsUrl(language));
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
              setInterimText("");
            } else if (m.type === "reply") {
              setMsgs((x) => [...x, { role: "ai", text: m.text }]);
              // If no audio event accompanies reply, return to monitoring
              if (statusRef.current === "thinking") {
                setStatus(micActiveRef.current && handsFreeRef.current ? "monitoring" : "idle");
              }
            } else if (m.type === "draft") {
              const d = { ...m, type: m.tx_type || m.type };
              setDrafts((prev) => {
                const filtered = prev.filter((x) => x.draft_id !== d.draft_id);
                return [...filtered, d];
              });
              setDraft(d);
            } else if (m.type === "cash_in") {
              setCashInCard(m);
            } else if (m.type === "promise_card") {
              setPromiseCard(m);
            } else if (m.type === "rule_card") {
              setRuleCard(m);
            } else if (m.type === "reconciliation_result") {
              setReconcileResult(m);
            } else if (m.type === "reminder") {
              setReminder(m);
            } else if (m.type === "confirmed" || m.type === "cancelled") {
              if (m.draft_id) {
                setDrafts((prev) => {
                  const next = prev.filter((x) => x.draft_id !== m.draft_id);
                  setDraft(next.length > 0 ? next[next.length - 1] : null);
                  return next;
                });
              } else {
                setDrafts([]);
                setDraft(null);
              }
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
        retry = setTimeout(connect, 1000);
      }
    };

    connect();

    return () => {
      closed = true;
      clearTimeout(retry);
      clearInterval(pingTimer);
      try {
        ws.current?.close();
      } catch {}
    };
  }, [language]);

  // Stop current active utterance and submit to backend wholly
  const stopUtterance = useCallback(() => {
    clearTimeout(debounceSubmitRef.current);
    const accumulated = accumulatedTranscriptRef.current.trim();
    const current = currentTranscriptRef.current.trim();
    const textToSend = (accumulated ? (accumulated + " " + current) : current).trim();
    accumulatedTranscriptRef.current = "";
    currentTranscriptRef.current = "";

    if (textToSend) {
      let cleanText = textToSend
        .replace(/^(hi|hey|hello|hai|namaste)?\s*khata\s*/i, "")
        .trim();
      if (cleanText) {
        sendText(cleanText);
      }
    } else if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type: "end_utterance", text: "" }));
    }
    setStatus("thinking");
    setWakeDetected(false);
    isSpokenRef.current = false;
  }, [sendText]);

  // Initialize Persistent Microphone Stream with Continuous Web Audio VAD & Resampling
  const startContinuousVAD = useCallback(async () => {
    setError("");
    if (rec.current) {
      setMicActive(true);
      if (rec.current.ctx.state === "suspended") {
        try {
          await rec.current.ctx.resume();
        } catch {}
      }
      if (statusRef.current === "idle" || statusRef.current === "connecting") {
        setStatus("monitoring");
      }
      return;
    }

    try {
      if (typeof window === "undefined" || !navigator.mediaDevices?.getUserMedia) {
        throw new Error("Microphone API not supported by this browser");
      }

      // Safe constraints without hardcoded sampleRate (prevents NotSupportedError on phones/desktops)
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      const ctx = new AudioCtx();
      if (ctx.state === "suspended") {
        await ctx.resume();
      }

      const inputSampleRate = ctx.sampleRate || 44100;
      const src = ctx.createMediaStreamSource(stream);
      const node = ctx.createScriptProcessor(4096, 1, 1);

      // Pre-roll buffer to preserve first syllables
      const preRollChunks: ArrayBufferLike[] = [];
      let noiseFloor = 0.008;
      let lastVoice = Date.now();
      let utteranceStart = 0;
      let consecutiveSpeechFrames = 0;

      node.onaudioprocess = (ev) => {
        const inputData = ev.inputBuffer.getChannelData(0);
        let sum = 0;
        for (let i = 0; i < inputData.length; i++) {
          sum += inputData[i] * inputData[i];
        }
        const rms = Math.sqrt(sum / inputData.length);
        const lvl = Math.min(100, Math.round(rms * 900));
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
          consecutiveSpeechFrames = 0;
          return;
        }

        // Downsample input audio stream to 16kHz mono PCM16
        const pcm = downsampleTo16k(inputData, inputSampleRate);

        // Monitoring State: Mic is live, waiting for intentional human voice
        if (curStatus === "monitoring" || curStatus === "idle") {
          noiseFloor = 0.95 * noiseFloor + 0.05 * rms;
          preRollChunks.push(pcm.buffer.slice(0));
          if (preRollChunks.length > 3) {
            preRollChunks.shift();
          }

          // Less Sensitive Noise Gate: Ignores fan hum, breathing, table bumps, distant background noise
          const vadThreshold = Math.max(0.022, noiseFloor * 2.2);

          if (isHF && rms > vadThreshold) {
            consecutiveSpeechFrames++;
            // Require sustained speech (at least 2 consecutive voice frames ~180ms)
            if (consecutiveSpeechFrames >= 2) {
              isSpokenRef.current = true;
              utteranceStart = Date.now();
              lastVoice = Date.now();
              setStatus("listening");

              // Flush pre-roll chunks so first syllable is never lost
              if (ws.current?.readyState === WebSocket.OPEN) {
                for (const chunk of preRollChunks) {
                  ws.current.send(chunk);
                }
              }
              preRollChunks.length = 0;
              consecutiveSpeechFrames = 0;
              return;
            }
          } else {
            consecutiveSpeechFrames = Math.max(0, consecutiveSpeechFrames - 1);
          }
        }

        // Listening State: Actively streaming audio
        if (curStatus === "listening") {
          if (ws.current?.readyState === WebSocket.OPEN) {
            ws.current.send(pcm.buffer);
          }

          const vadHoldThreshold = Math.max(0.016, noiseFloor * 1.6);
          if (rms > vadHoldThreshold) {
            lastVoice = Date.now();
            isSpokenRef.current = true;
          }

          const now = Date.now();
          // Pause detected for SILENCE_MS (1.2s) -> Auto-submit!
          if (
            (isSpokenRef.current && now - lastVoice > SILENCE_MS) ||
            (utteranceStart > 0 && now - utteranceStart > MAX_UTTERANCE_MS)
          ) {
            const utteranceDuration = Date.now() - utteranceStart;
            const textToSend = currentTranscriptRef.current.trim();

            // Guard against accidental short noises (< 350ms)
            if (utteranceDuration > 350 || textToSend.length > 0) {
              if (ws.current?.readyState === WebSocket.OPEN) {
                ws.current.send(JSON.stringify({ type: "end_utterance", text: textToSend }));
              }
              setStatus("thinking");
            } else {
              // Return to monitoring without submitting empty noise
              setStatus(micActiveRef.current && handsFreeRef.current ? "monitoring" : "idle");
            }
            isSpokenRef.current = false;
            currentTranscriptRef.current = "";
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
    } catch (e: any) {
      console.warn("Microphone access prompt:", e);
      setError("Please allow microphone access to enable voice intake.");
      setMicActive(false);
    }
  }, []);

  // Web Speech API for Instant Real-Time Transcripts & Wake-Word
  useEffect(() => {
    if (typeof window === "undefined") return;
    const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRec) return;

    let active = true;
    let sr: any = null;

    try {
      sr = new SpeechRec();
      sr.continuous = true;
      sr.interimResults = true;
      sr.lang = language || "hi-IN";

      sr.onresult = (ev: any) => {
        let finalStr = "";
        let interimStr = "";

        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          const res = ev.results[i];
          const transcript = res[0]?.transcript || "";
          if (res.isFinal) {
            finalStr += transcript;
          } else {
            interimStr += transcript;
          }
        }

        if (finalStr.trim()) {
          accumulatedTranscriptRef.current = (
            (accumulatedTranscriptRef.current ? accumulatedTranscriptRef.current + " " : "") + finalStr.trim()
          ).trim();
        }

        const composite = (
          (accumulatedTranscriptRef.current ? accumulatedTranscriptRef.current + " " : "") + interimStr.trim()
        ).trim();

        if (composite) {
          setInterimText(composite);
          currentTranscriptRef.current = composite;
        }

        const lower = composite.toLowerCase();

        // Check for wake words
        if (
          wakeWordActive &&
          (lower.includes("hi khata") ||
            lower.includes("hey khata") ||
            lower.includes("hello khata") ||
            lower.includes("hai khata") ||
            lower.includes("namaste khata") ||
            lower.includes("khata"))
        ) {
          if (statusRef.current === "monitoring" || statusRef.current === "idle") {
            playChime(659.25, 0.12);
            setWakeDetected(true);
            setStatus("listening");
            isSpokenRef.current = true;
            return;
          }
        }

        // Debounced submission: allows whole conversational dialogue (multi-turn exchange)
        // to be taken wholly before sending to backend
        clearTimeout(debounceSubmitRef.current);
        if (accumulatedTranscriptRef.current.trim()) {
          debounceSubmitRef.current = setTimeout(() => {
            const wholeText = accumulatedTranscriptRef.current.trim();
            accumulatedTranscriptRef.current = "";
            currentTranscriptRef.current = "";
            if (wholeText && statusRef.current !== "speaking" && statusRef.current !== "offline") {
              let cleanText = wholeText
                .replace(/^(hi|hey|hello|hai|namaste)?\s*khata\s*/i, "")
                .trim();
              if (cleanText) {
                sendText(cleanText);
                setInterimText("");
                setWakeDetected(false);
              }
            }
          }, 1500); // 1.5s natural pause captures the complete command wholly
        }
      };

      sr.onerror = (e: any) => {
        if (e.error !== "no-speech" && e.error !== "aborted") {
          console.warn("SpeechRecognition notice:", e.error);
        }
        if (active && (statusRef.current === "monitoring" || statusRef.current === "idle")) {
          setTimeout(() => {
            try {
              if (active) sr.start();
            } catch {}
          }, 1200);
        }
      };

      sr.onend = () => {
        if (active && (statusRef.current === "monitoring" || statusRef.current === "idle" || statusRef.current === "listening")) {
          try {
            sr.start();
          } catch {}
        }
      };

      try {
        sr.start();
      } catch {}
    } catch {}

    wakeRec.current = sr;

    return () => {
      active = false;
      try {
        sr?.abort();
      } catch {}
    };
  }, [language, wakeWordActive, sendText]);

  // Auto-attempt mic activation on mount
  useEffect(() => {
    if (typeof window !== "undefined" && navigator.mediaDevices) {
      navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then(() => {
          startContinuousVAD();
        })
        .catch(() => {
          // Normal: requires user click/gesture
        });
    }
  }, [startContinuousVAD]);

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
    setInterimText("");
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
    setError("");
    if (!rec.current) {
      await startContinuousVAD();
    } else if (rec.current.ctx.state === "suspended") {
      try {
        await rec.current.ctx.resume();
      } catch {}
    }
    playChime(587.33, 0.12);
    isSpokenRef.current = true;
    setStatus("listening");

    try {
      if (wakeRec.current && typeof wakeRec.current.start === "function") {
        wakeRec.current.start();
      }
    } catch {}
  }, [startContinuousVAD]);

  const stop = useCallback(() => {
    stopUtterance();
  }, [stopUtterance]);

  const clearCashInCard = useCallback(() => setCashInCard(null), []);
  const clearReminder = useCallback(() => setReminder(null), []);
  const clearPromiseCard = useCallback(() => setPromiseCard(null), []);
  const clearRuleCard = useCallback(() => setRuleCard(null), []);
  const clearReconcileResult = useCallback(() => setReconcileResult(null), []);
  const confirmAllDrafts = useCallback(() => sendText("Haan confirm kar do"), [sendText]);
  const cancelAllDrafts = useCallback(() => sendText("Cancel kar do"), [sendText]);

  return {
    status,
    msgs,
    draft,
    drafts,
    cashInCard,
    clearCashInCard,
    reminder,
    clearReminder,
    promiseCard,
    clearPromiseCard,
    ruleCard,
    clearRuleCard,
    reconcileResult,
    clearReconcileResult,
    confirmAllDrafts,
    cancelAllDrafts,
    error,
    interimText,
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
