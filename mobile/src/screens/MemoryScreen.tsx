import { useEffect, useState } from "react";
import {
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { inr, when, getBaseApiUrl } from "../services/api";
import { C } from "../theme";

export default function MemoryScreen() {
  const [seg, setSeg] = useState<"promises" | "rules" | "reconciliations">("promises");
  const [search, setSearch] = useState("");
  const [searchResults, setSearchResults] = useState<any[] | null>(null);

  const [promises, setPromises] = useState<any[]>([]);
  const [rules, setRules] = useState<any[]>([]);
  const [reconciliations, setReconciliations] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState("");

  const load = async () => {
    try {
      const [pRes, rRes, recRes] = await Promise.all([
        fetch(`${getBaseApiUrl()}/promises`).then((r) => r.json()).catch(() => []),
        fetch(`${getBaseApiUrl()}/rules`).then((r) => r.json()).catch(() => []),
        fetch(`${getBaseApiUrl()}/reconciliation`).then((r) => r.json()).catch(() => []),
      ]);
      setPromises(pRes);
      setRules(rRes);
      setReconciliations(recRes);
      setErr("");
    } catch {
      setErr("Failed to load memory data");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const handleSearch = async () => {
    const q = search.trim();
    if (!q) {
      setSearchResults(null);
      return;
    }
    try {
      const res = await fetch(`${getBaseApiUrl()}/memory/search?q=${encodeURIComponent(q)}`).then((r) => r.json());
      setSearchResults(res.results || []);
    } catch {
      setErr("Search failed");
    }
  };

  const toggleRule = async (ruleId: string, current: boolean) => {
    try {
      await fetch(`${getBaseApiUrl()}/rules/${ruleId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !current }),
      });
      setRules((prev) =>
        prev.map((r) => (r.id === ruleId ? { ...r, is_active: !current } : r))
      );
    } catch {}
  };

  return (
    <View style={s.wrap}>
      {/* Header & Search */}
      <View style={s.header}>
        <Text style={s.title}>Memory &amp; Rules</Text>
        <View style={s.searchRow}>
          <TextInput
            placeholder="Ask memory: 'Ramesh promise', 'credit rule'..."
            value={search}
            onChangeText={setSearch}
            onSubmitEditing={handleSearch}
            style={s.searchInp}
          />
          <Pressable onPress={handleSearch} style={s.searchBtn}>
            <Text style={{ color: "#fff", fontWeight: "700", fontSize: 12 }}>Recall</Text>
          </Pressable>
        </View>

        {/* Segmented Control */}
        <View style={s.seg}>
          {(["promises", "rules", "reconciliations"] as const).map((t) => (
            <Pressable
              key={t}
              onPress={() => {
                setSeg(t);
                setSearchResults(null);
              }}
              style={[s.segBtn, seg === t && s.segActive]}
            >
              <Text style={[s.segTxt, seg === t && s.segTxtActive]}>
                {t === "promises" ? "Promises" : t === "rules" ? "Rules" : "Reconciliation"}
              </Text>
            </Pressable>
          ))}
        </View>
      </View>

      {/* Search results banner */}
      {searchResults !== null && (
        <View style={s.searchCard}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 6 }}>
            <Text style={{ fontSize: 12, fontWeight: "700", color: C.text }}>
              Recall Results ({searchResults.length})
            </Text>
            <Pressable onPress={() => setSearchResults(null)}>
              <Text style={{ fontSize: 11, color: C.muted }}>Clear</Text>
            </Pressable>
          </View>
          {searchResults.map((r, i) => (
            <View key={i} style={s.resultItem}>
              <Text style={{ fontSize: 10, fontWeight: "800", color: "#2563eb", textTransform: "uppercase" }}>
                [{r.source}] {r.entity_name || r.rule_category}
              </Text>
              <Text style={{ fontSize: 12, color: C.text, marginTop: 1 }}>
                {r.description || r.rule_text}
              </Text>
            </View>
          ))}
        </View>
      )}

      {/* Main Lists */}
      {seg === "promises" && (
        <FlatList
          data={promises}
          keyExtractor={(item) => item.id}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
          contentContainerStyle={{ padding: 12 }}
          renderItem={({ item }) => (
            <View style={s.item}>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                  <Text style={{ fontSize: 14, fontWeight: "800", color: C.text }}>
                    {item.entity_name}
                  </Text>
                  <Text
                    style={{
                      fontSize: 10,
                      fontWeight: "800",
                      paddingHorizontal: 6,
                      paddingVertical: 1,
                      borderRadius: 6,
                      backgroundColor: item.status === "PENDING" ? "#dbeafe" : item.status === "OVERDUE" ? "#fee2e2" : "#dcfce7",
                      color: item.status === "PENDING" ? "#1e40af" : item.status === "OVERDUE" ? "#991b1b" : "#166534",
                    }}
                  >
                    {item.status}
                  </Text>
                </View>
                <Text style={{ fontSize: 12, color: C.muted, marginTop: 2 }}>{item.description}</Text>
                <Text style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>Expected: {item.expected_date}</Text>
              </View>
              {item.promised_amount ? (
                <Text style={{ fontSize: 16, fontWeight: "900", color: C.brand }}>
                  {inr(item.promised_amount)}
                </Text>
              ) : null}
            </View>
          )}
        />
      )}

      {seg === "rules" && (
        <FlatList
          data={rules}
          keyExtractor={(item) => item.id}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
          contentContainerStyle={{ padding: 12 }}
          renderItem={({ item }) => (
            <View style={s.item}>
              <View style={{ flex: 1, paddingRight: 8 }}>
                <Text style={{ fontSize: 13, fontWeight: "700", color: C.text }}>
                  &quot;{item.rule_text}&quot;
                </Text>
                <Text style={{ fontSize: 10, color: "#7e22ce", fontWeight: "700", marginTop: 2 }}>
                  {item.rule_category}
                </Text>
              </View>
              <Switch
                value={item.is_active}
                onValueChange={() => toggleRule(item.id, item.is_active)}
                trackColor={{ false: "#cbd5e1", true: "#86efac" }}
                thumbColor={item.is_active ? C.brand : "#f1f5f9"}
              />
            </View>
          )}
        />
      )}

      {seg === "reconciliations" && (
        <FlatList
          data={reconciliations}
          keyExtractor={(item) => item.id}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
          contentContainerStyle={{ padding: 12 }}
          renderItem={({ item }) => (
            <View style={s.item}>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                  <Text style={{ fontSize: 13, fontWeight: "800", color: C.text }}>
                    📅 {item.reconciliation_date}
                  </Text>
                  <Text
                    style={{
                      fontSize: 10,
                      fontWeight: "800",
                      paddingHorizontal: 6,
                      paddingVertical: 1,
                      borderRadius: 6,
                      backgroundColor: item.status === "MATCHED" ? "#dcfce7" : "#fef3c7",
                      color: item.status === "MATCHED" ? "#166534" : "#92400e",
                    }}
                  >
                    {item.status}
                  </Text>
                </View>
                <Text style={{ fontSize: 11, color: C.muted, marginTop: 2 }}>
                  Cash Diff: {inr(item.cash_difference)} · UPI Diff: {inr(item.upi_difference)}
                </Text>
                {item.findings?.length > 0 && (
                  <Text style={{ fontSize: 11, color: C.red, marginTop: 2 }}>
                    ⚠️ {item.findings.length} discrepancy finding(s)
                  </Text>
                )}
              </View>
            </View>
          )}
        />
      )}
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: "#f8fafc" },
  header: { backgroundColor: "#fff", padding: 12, borderBottomWidth: 1, borderColor: "#e2e8f0" },
  title: { fontSize: 18, fontWeight: "900", color: C.text, marginBottom: 8 },
  searchRow: { flexDirection: "row", gap: 6, marginBottom: 8 },
  searchInp: { flex: 1, backgroundColor: "#f1f5f9", borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, fontSize: 12 },
  searchBtn: { backgroundColor: C.text, borderRadius: 8, paddingHorizontal: 12, justifyContent: "center" },
  seg: { flexDirection: "row", backgroundColor: "#f1f5f9", borderRadius: 8, padding: 2 },
  segBtn: { flex: 1, alignItems: "center", paddingVertical: 6, borderRadius: 6 },
  segActive: { backgroundColor: "#fff", elevation: 1 },
  segTxt: { fontSize: 11, color: C.muted, fontWeight: "600" },
  segTxtActive: { color: C.brand, fontWeight: "800" },
  searchCard: { backgroundColor: "#eff6ff", margin: 12, padding: 10, borderRadius: 8, borderWidth: 1, borderColor: "#bfdbfe" },
  resultItem: { backgroundColor: "#fff", padding: 8, borderRadius: 6, marginBottom: 4 },
  item: { backgroundColor: "#fff", padding: 12, borderRadius: 10, marginBottom: 8, flexDirection: "row", alignItems: "center", borderWidth: 1, borderColor: "#e2e8f0" },
});

