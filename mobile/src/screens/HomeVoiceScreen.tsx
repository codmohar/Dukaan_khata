import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Linking, Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { inr } from "../services/api";
import { pauseWakeWord, resumeWakeWord, startAlwaysListening, stopAlwaysListening } from "../services/wakeWordService";
import { Draft, Reminder, Status, VoiceClient } from "../services/voiceSocket";
import { C } from "../theme";

const LANGS = [
  ["kn-IN", "ಕನ್ನಡ"],
  ["hi-IN", "हिन्दी"],
  ["en-IN", "English"],
  ["ta-IN", "தமிழ்"],
  ["te-IN", "తెలుగు"],
  ["mr-IN", "मराठी"],
] as const;

const LABEL: Record<Status, string> = {
  connecting: "Connecting to server…",
  offline: "Server offline. Retrying…",
  idle: "Tap the mic and speak",
  listening: "Listening… (auto-stops on pause)",
  thinking: "Processing khata…",
  speaking: "Speaking reply…",
};

export default function HomeVoiceScreen() {
  const [lang, setLang] = useState("kn-IN");
  const [status, setStatus] = useState<Status>("connecting");
  const [msgs, setMsgs] = useState<{ role: "you" | "ai"; text: string }[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [promiseCard, setPromiseCard] = useState<any | null>(null);
  const [ruleCard, setRuleCard] = useState<any | null>(null);
  const [reconcileResult, setReconcileResult] = useState<any | null>(null);
  const [reminder, setReminder] = useState<Reminder | null>(null);
  const [error, setError] = useState("");
  const [always, setAlways] = useState(false);
  const alwaysRef = useRef(false);
  const client = useRef<VoiceClient | null>(null);
  const scroll = useRef<ScrollView>(null);

  const listen = useCallback(async () => {
    if (alwaysRef.current) await pauseWakeWord(); // temporarily release mic
    client.current?.startListening();
  }, []);

  useEffect(() => {
    const c = new VoiceClient(lang, {
      onStatus: setStatus,
      onMessage: (role, text) => setMsgs((m) => [...m, { role, text }]),
      onDraft: setDraft,
      onPromiseCard: setPromiseCard,
      onRuleCard: setRuleCard,
      onReconcileResult: setReconcileResult,
      onReminder: setReminder,
      onError: (m) => {
        setError(m);
        if (alwaysRef.current) resumeWakeWord();
      },
      onTurnEnd: (followUp) => {
        if (followUp) listen();
        else if (alwaysRef.current) resumeWakeWord();
      },
    });
    client.current = c;
    c.connect();
    return () => c.dispose();
  }, [lang, listen]);

  useEffect(() => () => { stopAlwaysListening(); }, []);

  async function toggleAlways(on: boolean) {
    setError("");
    try {
      if (on) {
        await startAlwaysListening(() => {
          pauseWakeWord().then(() => client.current?.startListening());
        });
      } else {
        await stopAlwaysListening();
      }
      alwaysRef.current = on;
      setAlways(on);
    } catch (e) {
      Alert.alert("Always-Listening Setup", String((e as Error).message ?? e));
    }
  }

  const listening = status === "listening";
  const busy =
    status === "thinking" ||
    status === "speaking" ||
    status === "connecting" ||
    status === "offline";

  return (
    <View style={s.wrap}>
      {/* Top Header: Languages + Wake-Word Switch */}
      <View style={s.top}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.langs}>
          {LANGS.map(([code, label]) => (
            <Pressable
              key={code}
              onPress={() => setLang(code)}
              style={[s.chip, lang === code && s.chipOn]}
            >
              <Text style={[s.chipTxt, lang === code && { color: "#fff" }]}>{label}</Text>
            </Pressable>
          ))}
        </ScrollView>
        <View style={s.alwaysRow}>
          <Text style={s.alwaysTxt}>Hi Khata</Text>
          <Switch
            value={always}
            onValueChange={toggleAlways}
            trackColor={{ false: "#cbd5e1", true: C.brand }}
            thumbColor={always ? "#ffffff" : "#f1f5f9"}
          />
        </View>
      </View>

      {/* Live Chat & Transcript ScrollView */}
      <ScrollView
        ref={scroll}
        style={s.chat}
        contentContainerStyle={{ padding: 16, gap: 10 }}
        onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: true })}
      >
        {msgs.length === 0 && (
          <View style={s.emptyBox}>
            <Text style={s.emptyIcon}>🎙️</Text>
            <Text style={s.emptyTitle}>Speak Any Kirana Ledger Command</Text>
            <Text style={s.emptySubtitle}>Udhar • UPI/Cash Jama • Returns • Settlements • Balance</Text>
            <Text style={s.exampleQuote}>Speak in Kannada, Hindi, Hinglish, English, Tamil, Telugu, or Marathi</Text>
          </View>
        )}
        {msgs.map((m, i) => (
          <View key={i} style={[s.bubble, m.role === "you" ? s.you : s.ai]}>
            <Text style={s.roleTag}>{m.role === "you" ? "You" : "DukaanAI"}</Text>
            <Text style={{ color: m.role === "you" ? "#fff" : C.text, fontSize: 15, lineHeight: 20 }}>
              {m.text}
            </Text>
          </View>
        ))}
      </ScrollView>

      {/* Floating Action Draft Confirmation Card */}
      {draft && (
        <View style={[s.draft, draft.anomaly_warning && { borderColor: C.red, backgroundColor: "#fef2f2" }]}>
          <View style={s.draftHeader}>
            <Text style={[s.draftTag, draft.anomaly_warning && { color: C.red }]}>
              {draft.anomaly_warning ? "⚠️ HIGH AMOUNT — DOUBLE CHECK" : "PLEASE CONFIRM TRANSACTION"}
            </Text>
            <Text style={s.guardTag}>
              {draft.payment_mode ? draft.payment_mode.toUpperCase() : "Guardrail"}
            </Text>
          </View>
          {draft.anomaly_warning && draft.warning_message ? (
            <Text style={{ fontSize: 12, color: C.red, fontWeight: "700", marginBottom: 4 }}>
              {draft.warning_message}
            </Text>
          ) : null}
          {draft.member_name ? (
            <Text style={{ fontSize: 12, fontWeight: "700", color: "#b45309", marginBottom: 2 }}>
              👤 {draft.relationship ? `${draft.relationship}: ` : ""}{draft.member_name}
            </Text>
          ) : null}
          {draft.rule_warnings && draft.rule_warnings.length > 0 ? (
            <View style={{ backgroundColor: "#fee2e2", padding: 8, borderRadius: 8, marginVertical: 4, borderWidth: 1, borderColor: "#f87171" }}>
              <Text style={{ fontSize: 11, fontWeight: "800", color: "#991b1b" }}>🚨 Dukaan Rule Alert:</Text>
              {draft.rule_warnings.map((rw: any, idx: number) => (
                <View key={idx} style={{ marginTop: 2 }}>
                  <Text style={{ fontSize: 11, fontWeight: "700", color: "#7f1d1d" }}>
                    📜 Rule: &quot;{rw.rule_text || rw.message}&quot;
                  </Text>
                  {rw.rule_text && rw.message ? (
                    <Text style={{ fontSize: 10, color: C.red, marginTop: 1 }}>• {rw.message}</Text>
                  ) : null}
                </View>
              ))}
            </View>
          ) : null}
          <Text style={s.draftMain}>
            {draft.customer}{" "}
            <Text
              style={{
                color:
                  draft.type === "credit"
                    ? C.red
                    : draft.type === "adjustment"
                    ? "#7e22ce"
                    : C.brand,
              }}
            >
              {draft.type === "credit"
                ? "Udhar"
                : draft.type === "adjustment"
                ? `Adjust (${draft.adjustment_reason || "discount"})`
                : "Paid"}{" "}
              {inr(draft.amount)}
            </Text>
          </Text>
          {draft.item_note ? (
            <Text style={[s.draftNote, { color: C.text, fontWeight: "600" }]}>📦 {draft.item_note}</Text>
          ) : null}
          {(draft.due_date || draft.backdated_to || typeof draft.projected_balance === "number") && (
            <Text style={s.draftNote}>
              {draft.due_date ? `Due: ${draft.due_date}  ` : ""}
              {draft.backdated_to ? `Dated: ${draft.backdated_to}  ` : ""}
              {typeof draft.projected_balance === "number"
                ? draft.projected_balance < 0
                  ? `Advance: ${inr(Math.abs(draft.projected_balance))}`
                  : `New Bal: ${inr(draft.projected_balance)}`
                : ""}
            </Text>
          )}
          {draft.note && <Text style={s.draftNote}>Note: {draft.note}</Text>}
          <View style={s.row}>
            {draft.requires_override ? (
              <>
                <Pressable
                  style={[s.btn, { backgroundColor: C.red }]}
                  onPress={() => client.current?.sendText("Continue anyway")}
                >
                  <Text style={s.btnTxt}>⚠️ Continue anyway</Text>
                </Pressable>
                <Pressable
                  style={[s.btn, s.btnOutline]}
                  onPress={() => client.current?.sendText("No, cancel this")}
                >
                  <Text style={[s.btnTxt, { color: C.text }]}>✕ Cancel</Text>
                </Pressable>
              </>
            ) : (
              <>
                <Pressable
                  style={[s.btn, { backgroundColor: C.brand }]}
                  onPress={() => client.current?.sendText("Yes, confirm")}
                >
                  <Text style={s.btnTxt}>✓ Confirm</Text>
                </Pressable>
                <Pressable
                  style={[s.btn, s.btnOutline]}
                  onPress={() => client.current?.sendText("No, cancel this")}
                >
                  <Text style={[s.btnTxt, { color: C.red }]}>✕ Cancel</Text>
                </Pressable>
              </>
            )}
          </View>
        </View>
      )}

      {/* Blue Promise Card */}
      {promiseCard && (
        <View style={[s.draft, { borderColor: "#60a5fa", backgroundColor: "#eff6ff" }]}>
          <View style={s.draftHeader}>
            <Text style={[s.draftTag, { color: "#2563eb" }]}>🤝 PROMISE RECORDED</Text>
            <Pressable onPress={() => setPromiseCard(null)}>
              <Text style={{ fontSize: 12, color: C.muted, fontWeight: "700" }}>Dismiss</Text>
            </Pressable>
          </View>
          <Text style={s.draftMain}>
            {promiseCard.entity_name} • {promiseCard.amount ? inr(promiseCard.amount) : promiseCard.description}
          </Text>
          <Text style={[s.draftNote, { color: "#1d4ed8" }]}>📅 Expected: {promiseCard.expected_date}</Text>
          <Text style={{ fontSize: 10, color: C.muted, marginTop: 2 }}>
            Ledger balance remains unchanged until payment is confirmed.
          </Text>
        </View>
      )}

      {/* Purple Rule Card */}
      {ruleCard && (
        <View style={[s.draft, { borderColor: "#c084fc", backgroundColor: "#faf5ff" }]}>
          <View style={s.draftHeader}>
            <Text style={[s.draftTag, { color: "#9333ea" }]}>📜 DUKAAN RULE SAVED</Text>
            <Pressable onPress={() => setRuleCard(null)}>
              <Text style={{ fontSize: 12, color: C.muted, fontWeight: "700" }}>Dismiss</Text>
            </Pressable>
          </View>
          <Text style={[s.draftMain, { fontSize: 14 }]}>&quot;{ruleCard.rule_text}&quot;</Text>
          <Text style={[s.draftNote, { color: "#7e22ce" }]}>Category: {ruleCard.rule_category}</Text>
        </View>
      )}

      {/* Green/Orange Reconciliation Card */}
      {reconcileResult && (
        <View
          style={[
            s.draft,
            {
              borderColor: reconcileResult.status === "MATCHED" ? C.brand : "#f59e0b",
              backgroundColor: reconcileResult.status === "MATCHED" ? "#ecfdf5" : "#fffbeb",
            },
          ]}
        >
          <View style={s.draftHeader}>
            <Text
              style={[
                s.draftTag,
                { color: reconcileResult.status === "MATCHED" ? C.brand : "#b45309" },
              ]}
            >
              {reconcileResult.status === "MATCHED" ? "✓ KHATA MATCHED" : "⚠️ NEEDS INVESTIGATION"}
            </Text>
            <Pressable onPress={() => setReconcileResult(null)}>
              <Text style={{ fontSize: 12, color: C.muted, fontWeight: "700" }}>Dismiss</Text>
            </Pressable>
          </View>
          <Text style={[s.draftNote, { color: C.text, fontWeight: "700" }]}>
            Cash Diff: {inr(reconcileResult.cash_difference ?? 0)} | UPI Diff:{" "}
            {inr(reconcileResult.upi_difference ?? 0)}
          </Text>
          {reconcileResult.findings?.map((f: any, i: number) => (
            <Text key={i} style={{ fontSize: 11, color: C.red, marginTop: 2 }}>• {f.message}</Text>
          ))}
        </View>
      )}

      {/* WhatsApp Payment Reminder Card */}
      {reminder && (
        <View style={[s.draft, { borderColor: C.brand, backgroundColor: "#ecfdf5" }]}>
          <View style={s.draftHeader}>
            <Text style={[s.draftTag, { color: C.brand }]}>📲 PAYMENT REMINDER READY</Text>
            <Pressable onPress={() => setReminder(null)}>
              <Text style={{ fontSize: 12, color: C.muted, fontWeight: "700" }}>Dismiss</Text>
            </Pressable>
          </View>
          <Text style={s.draftMain}>
            {reminder.customer} — {inr(reminder.balance)}
          </Text>
          <Pressable
            style={[s.btn, { backgroundColor: C.brand, marginTop: 6 }]}
            onPress={() => Linking.openURL(reminder.whatsapp_url)}
          >
            <Text style={s.btnTxt}>💬 Send on WhatsApp</Text>
          </Pressable>
        </View>
      )}

      {/* Microphone & Status Bottom Station */}
      <View style={s.micArea}>
        {!!error && <Text style={s.err}>{error}</Text>}
        <Text style={s.status}>{LABEL[status]}</Text>
        <Pressable
          disabled={busy}
          onPress={() => (listening ? client.current?.stopListening() : listen())}
          style={[
            s.mic,
            listening && { backgroundColor: C.red, transform: [{ scale: 1.05 }] },
            busy && { opacity: 0.5 },
          ]}
        >
          <Text style={{ fontSize: 44 }}>{listening ? "⏹" : "🎙️"}</Text>
        </Pressable>
        <Pressable
          onPress={() => {
            client.current?.reset();
            setMsgs([]);
            setError("");
          }}
        >
          <Text style={s.link}>Reset conversation</Text>
        </Pressable>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: "#f8fafc" },
  top: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderColor: "#e2e8f0",
    backgroundColor: "#ffffff",
  },
  langs: { flexDirection: "row", gap: 6 },
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: "#f1f5f9",
    borderWidth: 1,
    borderColor: "#e2e8f0",
  },
  chipOn: { backgroundColor: C.brand, borderColor: C.brand },
  chipTxt: { fontSize: 13, fontWeight: "700", color: C.muted },
  alwaysRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  alwaysTxt: { fontSize: 12, color: C.muted, fontWeight: "700" },
  chat: { flex: 1 },
  emptyBox: { alignItems: "center", justifyContent: "center", marginTop: 40, paddingHorizontal: 20 },
  emptyIcon: { fontSize: 36, marginBottom: 8 },
  emptyTitle: { fontSize: 16, fontWeight: "700", color: C.text, marginBottom: 4 },
  emptySubtitle: { fontSize: 13, color: C.muted, marginBottom: 8 },
  exampleQuote: { fontSize: 14, fontStyle: "italic", color: C.brand, marginVertical: 2 },
  bubble: { maxWidth: "84%", paddingHorizontal: 14, paddingVertical: 10, borderRadius: 16 },
  roleTag: { fontSize: 10, fontWeight: "700", opacity: 0.7, marginBottom: 2 },
  you: { alignSelf: "flex-end", backgroundColor: C.brand, borderBottomRightRadius: 4 },
  ai: { alignSelf: "flex-start", backgroundColor: "#ffffff", borderWidth: 1, borderColor: "#e2e8f0", borderBottomLeftRadius: 4 },
  draft: {
    margin: 12,
    padding: 16,
    borderRadius: 18,
    backgroundColor: "#fef3c7",
    borderWidth: 2,
    borderColor: "#f59e0b",
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 3,
  },
  draftHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  draftTag: { fontSize: 11, fontWeight: "800", color: "#b45309" },
  guardTag: { fontSize: 10, color: "#92400e", fontWeight: "600" },
  draftMain: { fontSize: 20, fontWeight: "800", marginTop: 6, color: C.text },
  draftNote: { fontSize: 12, color: "#78350f", marginTop: 2 },
  row: { flexDirection: "row", gap: 10, marginTop: 14 },
  btn: { flex: 1, paddingVertical: 12, borderRadius: 12, alignItems: "center", elevation: 1 },
  btnOutline: { backgroundColor: "#fff", borderWidth: 1, borderColor: "#fecaca" },
  btnTxt: { color: "#fff", fontWeight: "700", fontSize: 15 },
  micArea: { alignItems: "center", paddingBottom: 20, paddingTop: 10, backgroundColor: "#ffffff", borderTopWidth: 1, borderColor: "#e2e8f0" },
  status: { color: C.muted, marginBottom: 10, fontWeight: "600", fontSize: 13 },
  err: { color: C.red, marginBottom: 6, fontSize: 12, fontWeight: "600" },
  mic: {
    width: 90,
    height: 90,
    borderRadius: 45,
    backgroundColor: C.brand,
    alignItems: "center",
    justifyContent: "center",
    elevation: 6,
    shadowColor: "#16a34a",
    shadowOpacity: 0.35,
    shadowRadius: 8,
  },
  link: { color: C.muted, marginTop: 12, fontSize: 13, textDecorationLine: "underline" },
});
