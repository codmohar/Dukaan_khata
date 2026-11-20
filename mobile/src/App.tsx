import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import HomeVoiceScreen from "./screens/HomeVoiceScreen";
import ScanScreen from "./screens/ScanScreen";
import QuickLedgerScreen from "./screens/QuickLedgerScreen";
import MemoryScreen from "./screens/MemoryScreen";
import { C } from "./theme";

const TABS = [
  { key: "voice", label: "Voice", icon: "🎙️" },
  { key: "scan", label: "Scan", icon: "📷" },
  { key: "ledger", label: "Khata", icon: "📒" },
  { key: "memory", label: "Memory", icon: "🧠" },
] as const;

export default function App() {
  const [tab, setTab] = useState<"voice" | "scan" | "ledger" | "memory">("voice");
  return (
    <SafeAreaProvider>
      <SafeAreaView style={s.root} edges={["top", "bottom"]}>
        <StatusBar style="dark" />
        {/* All screens stay mounted so state survives tab switches */}
        <View style={[s.body, tab !== "voice" && s.hidden]}><HomeVoiceScreen /></View>
        <View style={[s.body, tab !== "scan" && s.hidden]}><ScanScreen /></View>
        <View style={[s.body, tab !== "ledger" && s.hidden]}><QuickLedgerScreen /></View>
        <View style={[s.body, tab !== "memory" && s.hidden]}><MemoryScreen /></View>
        <View style={s.tabs}>
          {TABS.map((t) => (
            <Pressable key={t.key} style={s.tab} onPress={() => setTab(t.key)}>
              <Text style={s.icon}>{t.icon}</Text>
              <Text style={[s.label, tab === t.key && s.active]}>{t.label}</Text>
            </Pressable>
          ))}
        </View>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  body: { flex: 1 },
  hidden: { display: "none" },
  tabs: { flexDirection: "row", borderTopWidth: 1, borderColor: C.border, backgroundColor: C.card },
  tab: { flex: 1, alignItems: "center", paddingVertical: 8 },
  icon: { fontSize: 22 },
  label: { fontSize: 12, color: C.muted, marginTop: 2 },
  active: { color: C.brand, fontWeight: "700" },
});
