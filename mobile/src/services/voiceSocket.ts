import { Audio } from "expo-av";
import * as FileSystem from "expo-file-system";
import { WS_URL } from "../config";

export type Draft = {
  draft_id: string;
  customer: string;
  type: "credit" | "payment" | "adjustment";
  amount: number;
  payment_mode?: "cash" | "upi" | "other" | null;
  adjustment_reason?: "discount" | "return" | "write_off" | "correction" | null;
  due_date?: string | null;
  backdated_to?: string | null;
  projected_balance?: number;
  is_advance?: boolean;
  anomaly_warning?: boolean;
  warning_message?: string | null;
  member_name?: string | null;
  relationship?: string | null;
  item_note?: string | null;
  rule_warnings?: Array<{ rule_category: string; message: string }>;
  requires_override?: boolean;
  note?: string;
};

export type Reminder = {
  customer: string;
  phone?: string | null;
  balance: number;
  reminder_text: string;
  whatsapp_url: string;
};

export type Status = "connecting" | "idle" | "listening" | "thinking" | "speaking" | "offline";

export type Handlers = {
  onStatus: (s: Status) => void;
  onMessage: (role: "you" | "ai", text: string) => void;
  onDraft: (d: Draft | null) => void;
  onPromiseCard?: (p: any | null) => void;
  onRuleCard?: (r: any | null) => void;
  onReconcileResult?: (r: any | null) => void;
  onReminder?: (r: Reminder | null) => void;
  onError: (m: string) => void;
  onTurnEnd: (followUp: boolean) => void;
};

const SILENCE_MS = 1400;
const NO_SPEECH_MS = 7000;
const MAX_MS = 25000;

export class VoiceClient {
  private ws: WebSocket | null = null;
  private disposed = false;
  private retry?: ReturnType<typeof setTimeout>;
  private pingTimer?: ReturnType<typeof setInterval>;
  private meterTimer?: ReturnType<typeof setInterval>;
  private listening = false;
  private hasDraft = false;
  private lastReply = "";
  private sound: Audio.Sound | null = null;
  private recording: Audio.Recording | null = null;

  constructor(private language: string, private h: Handlers) {}

  connect() {
    if (this.disposed) return;
    this.h.onStatus("connecting");
    try {
      const ws = new WebSocket(`${WS_URL}?language=${this.language}`);
      this.ws = ws;
      ws.onopen = () => {
        this.h.onStatus("idle");
        clearInterval(this.pingTimer);
        this.pingTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            try {
              ws.send(JSON.stringify({ type: "ping" }));
            } catch {}
          }
        }, 25000);
      };
      ws.onclose = () => {
        clearInterval(this.pingTimer);
        if (!this.disposed) {
          this.h.onStatus("offline");
          this.retry = setTimeout(() => this.connect(), 1500);
        }
      };
      ws.onerror = () => {
        this.h.onStatus("offline");
      };
      ws.onmessage = (e) => {
        try {
          this.onMsg(JSON.parse(String(e.data)));
        } catch {}
      };
    } catch {
      this.h.onStatus("offline");
      this.retry = setTimeout(() => this.connect(), 2000);
    }
  }

  private onMsg(m: any) {
    switch (m.type) {
      case "pong":
        break;
      case "noop":
      case "silent_context":
        this.h.onStatus("idle");
        this.h.onTurnEnd(false);
        break;
      case "transcript":
        this.h.onMessage("you", m.text);
        break;
      case "draft":
        this.hasDraft = true;
        this.h.onDraft({ ...m, type: m.tx_type || m.type });
        break;
      case "promise_card":
        this.h.onPromiseCard?.(m);
        break;
      case "rule_card":
        this.h.onRuleCard?.(m);
        break;
      case "reconciliation_result":
        this.h.onReconcileResult?.(m);
        break;
      case "reminder":
        this.h.onReminder?.(m);
        break;
      case "confirmed":
      case "cancelled":
        this.hasDraft = false;
        this.h.onDraft(null);
        break;
      case "reply":
        this.lastReply = m.text;
        this.h.onMessage("ai", m.text);
        this.h.onStatus("idle");
        break;
      case "audio":
        this.play(m.data);
        break;
      case "error":
        this.h.onError(m.message);
        this.h.onStatus("idle");
        this.h.onTurnEnd(false);
        break;
    }
  }

  private async play(b64: string) {
    const followUp = this.hasDraft || /[?？]\s*$/.test(this.lastReply);
    try {
      this.h.onStatus("speaking");
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false, playsInSilentModeIOS: true });
      const uri = FileSystem.cacheDirectory + "dukaan_reply.wav";
      await FileSystem.writeAsStringAsync(uri, b64, { encoding: FileSystem.EncodingType.Base64 });
      await this.sound?.unloadAsync();
      const { sound } = await Audio.Sound.createAsync({ uri }, { shouldPlay: true });
      this.sound = sound;
      sound.setOnPlaybackStatusUpdate((s) => {
        if (s.isLoaded && s.didJustFinish) {
          this.h.onStatus("idle");
          this.h.onTurnEnd(followUp);
        }
      });
    } catch {
      this.h.onStatus("idle");
      this.h.onTurnEnd(followUp);
    }
  }

  /** Native Expo Go compatible recording with automatic pause detection (VAD via metering). */
  async startListening() {
    if (this.listening || this.ws?.readyState !== WebSocket.OPEN) return;
    try {
      const perm = await Audio.requestPermissionsAsync();
      if (!perm.granted) {
        this.h.onError("Please allow microphone permission for DukaanAI.");
        return;
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      this.listening = true;
      this.h.onStatus("listening");

      const rec = new Audio.Recording();
      await rec.prepareToRecordAsync({
        ...Audio.RecordingOptionsPresets.HIGH_QUALITY,
        isMeteringEnabled: true,
      });
      await rec.startAsync();
      this.recording = rec;

      const t0 = Date.now();
      let spoke = false;
      let lastVoice = t0;

      clearInterval(this.meterTimer);
      this.meterTimer = setInterval(async () => {
        if (!this.listening || !this.recording) return;
        try {
          const st = await this.recording.getStatusAsync();
          const now = Date.now();
          // Metering is in dBFS (approx -160 silence to 0 loud; speech is typically > -38 dB)
          const db = typeof st.metering === "number" ? st.metering : -160;
          if (db > -38) {
            spoke = true;
            lastVoice = now;
          }

          if (spoke && now - lastVoice > SILENCE_MS) {
            this.stopListening();
          } else if (!spoke && now - t0 > NO_SPEECH_MS) {
            this.cancelListening();
          } else if (now - t0 > MAX_MS) {
            this.stopListening();
          }
        } catch {}
      }, 200);
    } catch (e) {
      this.listening = false;
      this.h.onError("Could not start microphone: " + String((e as Error).message ?? e));
      this.h.onStatus("idle");
    }
  }

  private async cancelListening() {
    if (!this.listening) return;
    this.listening = false;
    clearInterval(this.meterTimer);
    try {
      await this.recording?.stopAndUnloadAsync();
    } catch {}
    this.recording = null;
    this.h.onStatus("idle");
    this.h.onTurnEnd(false);
  }

  async stopListening() {
    if (!this.listening) return;
    this.listening = false;
    clearInterval(this.meterTimer);

    const rec = this.recording;
    this.recording = null;
    if (!rec) {
      this.h.onStatus("idle");
      return;
    }

    this.h.onStatus("thinking");
    try {
      await rec.stopAndUnloadAsync();
      const uri = rec.getURI();
      if (!uri || this.ws?.readyState !== WebSocket.OPEN) {
        this.h.onStatus("idle");
        return;
      }
      const b64 = await FileSystem.readAsStringAsync(uri, {
        encoding: FileSystem.EncodingType.Base64,
      });
      this.ws.send(JSON.stringify({ type: "audio_file", data: b64 }));
    } catch (e) {
      this.h.onError("Audio upload error: " + String((e as Error).message ?? e));
      this.h.onStatus("idle");
    }
  }

  sendText(text: string) {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    this.h.onStatus("thinking");
    this.ws.send(JSON.stringify({ type: "text", text }));
  }

  reset() {
    this.ws?.send(JSON.stringify({ type: "reset" }));
    this.hasDraft = false;
    this.h.onDraft(null);
  }

  dispose() {
    this.disposed = true;
    clearTimeout(this.retry);
    clearInterval(this.pingTimer);
    clearInterval(this.meterTimer);
    try {
      this.recording?.stopAndUnloadAsync();
      this.ws?.close();
      this.sound?.unloadAsync();
    } catch {}
  }
}
