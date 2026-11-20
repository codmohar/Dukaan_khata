import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import HomeVoiceScreen from "./screens/HomeVoiceScreen";
import ScanScreen from "./screens/ScanScreen";
import QuickLedgerScreen from "./screens/QuickLedgerScreen";
import MemoryScreen from "./screens/MemoryScreen";
import AuthScreen from "./screens/AuthScreen";
import { api, setMobileShopId, Shop } from "./services/api";
import { C } from "./theme";

const TABS = [
  { key: "voice", label: "Voice", icon: "🎙️" },
  { key: "scan", label: "Scan", icon: "📷" },
  { key: "ledger", label: "Khata", icon: "📒" },
  { key: "memory", label: "Memory", icon: "🧠" },
] as const;

export default function App() {
  const [shop, setShop] = useState<Shop | null>(null);
  const [tab, setTab] = useState<"voice" | "scan" | "ledger" | "memory">("voice");

  useEffect(() => {
    // Attempt auto-login with default shop or first shop
    api
      .shop()
      .then((s) => {
        if (s && s.id) {
          setMobileShopId(s.id);
          setShop(s);
        }
      })
      .catch(() => {
        // If server not connected or needs explicit login
      });
  }, []);

  const handleAuthenticated = (authenticatedShop: Shop) => {
    setMobileShopId(authenticatedShop.id);
    setShop(authenticatedShop);
  };

  const handleSwitchShop = () => {
    setMobileShopId("");
    setShop(null);
  };

  return (
    <SafeAreaProvider>
      <SafeAreaView style={s.root} edges={["top", "bottom"]}>
        <StatusBar style="dark" />

        {!shop ? (
          <AuthScreen onAuthenticated={handleAuthenticated} />
        ) : (
          <>
            {/* Top Store Header */}
            <View style={s.topBar}>
              <View style={s.shopInfo}>
                <View style={s.shopAvatar}>
                  <Text style={s.avatarTxt}>{shop.name.charAt(0).toUpperCase()}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.topShopName} numberOfLines={1}>{shop.name}</Text>
                  <Text style={s.topProp} numberOfLines={1}>
                    {shop.owner_name ? `Prop: ${shop.owner_name}` : "Kirana Store"}
                  </Text>
                </View>
              </View>
              <Pressable style={s.switchBtn} onPress={handleSwitchShop}>
                <Text style={s.switchTxt}>🔄 Switch</Text>
              </Pressable>
            </View>

            {/* All screens stay mounted so state survives tab switches */}
            <View style={[s.body, tab !== "voice" && s.hidden]}><HomeVoiceScreen /></View>
            <View style={[s.body, tab !== "scan" && s.hidden]}><ScanScreen /></View>
            <View style={[s.body, tab !== "ledger" && s.hidden]}><QuickLedgerScreen /></View>
            <View style={[s.body, tab !== "memory" && s.hidden]}><MemoryScreen /></View>

            {/* Bottom Tabs */}
            <View style={s.tabs}>
              {TABS.map((t) => (
                <Pressable key={t.key} style={s.tab} onPress={() => setTab(t.key)}>
                  <Text style={s.icon}>{t.icon}</Text>
                  <Text style={[s.label, tab === t.key && s.active]}>{t.label}</Text>
                </Pressable>
              ))}
            </View>
          </>
        )}
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  body: { flex: 1 },
  hidden: { display: "none" },
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 14,
    paddingVertical: 10,
    backgroundColor: C.card,
    borderBottomWidth: 1,
    borderColor: C.border,
  },
  shopInfo: { flexDirection: "row", alignItems: "center", gap: 10, flex: 1 },
  shopAvatar: {
    width: 34,
    height: 34,
    borderRadius: 10,
    backgroundColor: C.brand,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarTxt: { color: "#fff", fontSize: 16, fontWeight: "900" },
  topShopName: { fontSize: 13, fontWeight: "800", color: C.text },
  topProp: { fontSize: 10, color: C.muted },
  switchBtn: {
    backgroundColor: "#f1f5f9",
    borderWidth: 1,
    borderColor: C.border,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 10,
  },
  switchTxt: { fontSize: 11, fontWeight: "700", color: C.text },
  tabs: { flexDirection: "row", borderTopWidth: 1, borderColor: C.border, backgroundColor: C.card },
  tab: { flex: 1, alignItems: "center", paddingVertical: 8 },
  icon: { fontSize: 22 },
  label: { fontSize: 12, color: C.muted, marginTop: 2 },
  active: { color: C.brand, fontWeight: "700" },
});
