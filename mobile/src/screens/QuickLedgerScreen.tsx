import { useState } from "react";
import {
  FlatList,
  Linking,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { api, Customer, inr, Stats, Txn, useLive, when, whatsAppReminderUrl } from "../services/api";
import { C } from "../theme";

export default function QuickLedgerScreen() {
  const [tab, setTab] = useState<"customers" | "recent">("customers");
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [shopName, setShopName] = useState("Kirana Store");
  const [txns, setTxns] = useState<Txn[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [q, setQ] = useState("");
  const [err, setErr] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [waEditId, setWaEditId] = useState<string | null>(null);
  const [waInput, setWaInput] = useState("");

  const load = () =>
    Promise.all([api.customers(), api.txns(), api.stats(), api.shop().catch(() => null)])
      .then(([c, t, st, sh]) => {
        setCustomers(c);
        setTxns(t);
        setStats(st);
        if (sh?.name) setShopName(sh.name);
        setErr(false);
      })
      .catch(() => setErr(true));

  const saveWhatsApp = async (customerId: string) => {
    const cleaned = waInput.trim();
    if (!cleaned) return;
    try {
      await api.updateCustomer(customerId, { phone: cleaned });
      setWaEditId(null);
      setWaInput("");
      load();
    } catch {
      setErr(true);
    }
  };

  useLive(load);

  const shown = customers.filter(
    (c) =>
      c.name.toLowerCase().includes(q.toLowerCase()) ||
      (c.landmark && c.landmark.toLowerCase().includes(q.toLowerCase()))
  );

  return (
    <View style={{ flex: 1, backgroundColor: "#f8fafc" }}>
      {/* Hero Stats Card */}
      <View style={s.hero}>
        <Text style={s.heroLbl}>TOTAL UDHAR OUTSTANDING</Text>
        <Text style={s.heroVal}>{inr(stats?.total_outstanding ?? 0)}</Text>
        <View style={s.heroSubRow}>
          <Text style={s.heroSub}>
            Today: <Text style={{ color: "#f87171" }}>+{inr(stats?.credit_today ?? 0)}</Text> udhar ·{" "}
            <Text style={{ color: "#4ade80" }}>{inr(stats?.payments_today ?? 0)}</Text> received
          </Text>
        </View>
      </View>

      {err && <Text style={s.err}>Could not reach backend API server</Text>}

      {/* Segmented Tab Bar */}
      <View style={s.seg}>
        {(["customers", "recent"] as const).map((t) => (
          <Pressable
            key={t}
            onPress={() => setTab(t)}
            style={[s.segBtn, tab === t && s.segOn]}
          >
            <Text style={[s.segTxt, tab === t && { color: "#fff" }]}>
              {t === "customers" ? "Customers Ledger" : "Recent Entries"}
            </Text>
          </Pressable>
        ))}
      </View>

      {tab === "customers" ? (
        <FlatList
          data={shown}
          keyExtractor={(c) => c.id}
          ListHeaderComponent={
            <TextInput
              style={s.search}
              placeholder="🔍 Search customer or landmark…"
              placeholderTextColor="#94a3b8"
              value={q}
              onChangeText={setQ}
            />
          }
          ListEmptyComponent={
            <Text style={s.empty}>No customers found</Text>
          }
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={async () => {
                setRefreshing(true);
                await load();
                setRefreshing(false);
              }}
            />
          }
          renderItem={({ item: c }) => {
            const b = Number(c.balance);
            const hasDue = b > 0;
            const hasWa = Boolean(c.phone && c.phone.trim());
            const waUrl = whatsAppReminderUrl(c.phone, c.name, b, shopName);

            return (
              <View style={s.item}>
                <View style={{ flex: 1, paddingRight: 8 }}>
                  <Text style={s.name}>{c.name}</Text>
                  {hasWa ? (
                    <Text style={s.sub}>
                      {[c.landmark, c.phone].filter(Boolean).join(" · ")}
                    </Text>
                  ) : (
                    <View style={{ marginTop: 4 }}>
                      {c.landmark ? <Text style={s.sub}>{c.landmark}</Text> : null}
                      {waEditId === c.id ? (
                        <View style={s.waFormRow}>
                          <TextInput
                            style={s.waInput}
                            placeholder="10-digit WhatsApp #"
                            placeholderTextColor="#94a3b8"
                            keyboardType="phone-pad"
                            value={waInput}
                            onChangeText={setWaInput}
                            autoFocus
                          />
                          <Pressable style={s.waSaveBtn} onPress={() => saveWhatsApp(c.id)}>
                            <Text style={s.waSaveTxt}>Save</Text>
                          </Pressable>
                          <Pressable
                            style={s.waCancelBtn}
                            onPress={() => {
                              setWaEditId(null);
                              setWaInput("");
                            }}
                          >
                            <Text style={s.waCancelTxt}>✕</Text>
                          </Pressable>
                        </View>
                      ) : (
                        <Pressable
                          style={s.addWaBtn}
                          onPress={() => {
                            setWaEditId(c.id);
                            setWaInput("");
                          }}
                        >
                          <Text style={s.addWaTxt}>📱 + Add WhatsApp Number</Text>
                        </Pressable>
                      )}
                    </View>
                  )}
                </View>

                <View style={{ alignItems: "flex-end", gap: 4 }}>
                  <Text style={[s.amt, { color: hasDue ? C.red : C.brand }]}>
                    {hasDue ? inr(b) : b < 0 ? `${inr(-b)} adv` : "Clear"}
                  </Text>
                  {hasDue && hasWa && (
                    <Pressable
                      style={s.waBtn}
                      onPress={() => Linking.openURL(waUrl).catch(() => { })}
                    >
                      <Text style={s.waTxt}>💬 Remind</Text>
                    </Pressable>
                  )}
                </View>
              </View>
            );
          }}
        />
      ) : (
        <FlatList
          data={txns}
          keyExtractor={(t) => t.id}
          ListEmptyComponent={<Text style={s.empty}>No entries yet</Text>}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={async () => {
                setRefreshing(true);
                await load();
                setRefreshing(false);
              }}
            />
          }
          renderItem={({ item: t }) => (
            <View style={[s.item, t.status !== "confirmed" && { opacity: 0.65 }]}>
              <View style={{ flex: 1 }}>
                <Text style={s.name}>{t.customer_name || "Unknown Customer"}</Text>
                <Text style={s.sub}>
                  {when(t.created_at)}
                  {t.status !== "confirmed" ? ` · [${t.status.toUpperCase()}]` : ""}
                </Text>
              </View>
              <Text style={[s.amt, { color: t.type === "credit" ? C.red : C.brand }]}>
                {t.type === "credit" ? "+" : "−"}
                {inr(t.amount)}
              </Text>
            </View>
          )}
        />
      )}
    </View>
  );
}

const s = StyleSheet.create({
  hero: {
    margin: 12,
    padding: 20,
    borderRadius: 20,
    backgroundColor: "#090d16",
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 10,
    elevation: 4,
  },
  heroLbl: { color: "#94a3b8", fontSize: 11, fontWeight: "800", letterSpacing: 0.5 },
  heroVal: { color: "#ffffff", fontSize: 34, fontWeight: "900", marginTop: 4 },
  heroSubRow: { marginTop: 6 },
  heroSub: { color: "#cbd5e1", fontSize: 13, fontWeight: "600" },
  err: { textAlign: "center", color: C.red, marginBottom: 6, fontSize: 12 },
  seg: {
    flexDirection: "row",
    marginHorizontal: 12,
    marginBottom: 8,
    backgroundColor: "#e2e8f0",
    borderRadius: 12,
    padding: 3,
  },
  segBtn: { flex: 1, paddingVertical: 8, alignItems: "center", borderRadius: 10 },
  segOn: { backgroundColor: C.brand },
  segTxt: { fontWeight: "700", color: C.muted, fontSize: 13 },
  search: {
    marginHorizontal: 12,
    marginBottom: 8,
    padding: 12,
    borderRadius: 12,
    backgroundColor: "#ffffff",
    borderWidth: 1,
    borderColor: "#e2e8f0",
    fontSize: 14,
    color: C.text,
  },
  item: {
    flexDirection: "row",
    alignItems: "center",
    marginHorizontal: 12,
    marginTop: 8,
    padding: 14,
    borderRadius: 16,
    backgroundColor: "#ffffff",
    borderWidth: 1,
    borderColor: "#e2e8f0",
  },
  name: { fontSize: 16, fontWeight: "700", color: C.text },
  sub: { fontSize: 12, color: C.muted, marginTop: 2 },
  amt: { fontSize: 17, fontWeight: "800" },
  waBtn: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    backgroundColor: "#dcfce7",
    borderRadius: 6,
    borderWidth: 1,
    borderColor: "#bbf7d0",
  },
  waTxt: { fontSize: 11, fontWeight: "700", color: "#15803d" },
  addWaBtn: {
    alignSelf: "flex-start",
    marginTop: 4,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
    backgroundColor: "#ecfdf5",
    borderWidth: 1,
    borderColor: "#6ee7b7",
  },
  addWaTxt: { fontSize: 11, fontWeight: "700", color: "#047857" },
  waFormRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 4 },
  waInput: {
    flex: 1,
    maxWidth: 150,
    borderWidth: 1,
    borderColor: "#34d399",
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 4,
    fontSize: 12,
    backgroundColor: "#fff",
    color: C.text,
  },
  waSaveBtn: { backgroundColor: C.brand, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8 },
  waSaveTxt: { color: "#fff", fontSize: 11, fontWeight: "700" },
  waCancelBtn: { backgroundColor: "#f1f5f9", paddingHorizontal: 8, paddingVertical: 5, borderRadius: 8 },
  waCancelTxt: { color: C.muted, fontSize: 11, fontWeight: "700" },
  empty: { textAlign: "center", color: C.muted, marginTop: 40, fontSize: 14 },
});
