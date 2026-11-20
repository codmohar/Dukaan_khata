import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { api, setMobileShopId, Shop } from "../services/api";
import { C } from "../theme";

const LANGS = [
  { code: "kn-IN", label: "ಕನ್ನಡ (Kannada)" },
  { code: "hi-IN", label: "हिन्दी (Hindi)" },
  { code: "en-IN", label: "English" },
  { code: "ta-IN", label: "தமிழ் (Tamil)" },
  { code: "te-IN", label: "తెలుగు (Telugu)" },
  { code: "mr-IN", label: "मराठी (Marathi)" },
];

export default function AuthScreen({
  onAuthenticated,
}: {
  onAuthenticated: (shop: Shop) => void;
}) {
  const [tab, setTab] = useState<"quick" | "phone" | "new">("quick");
  const [shops, setShops] = useState<Shop[]>([]);
  const [selectedShopId, setSelectedShopId] = useState("");
  const [pin, setPin] = useState("1234");
  const [phone, setPhone] = useState("");

  // New shop fields
  const [newName, setNewName] = useState("");
  const [newOwner, setNewOwner] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newLang, setNewLang] = useState("kn-IN");
  const [newPin, setNewPin] = useState("1234");

  const [busy, setBusy] = useState(false);
  const [loadingShops, setLoadingShops] = useState(true);

  useEffect(() => {
    loadShops();
  }, []);

  const loadShops = async () => {
    setLoadingShops(true);
    try {
      const list = await api.getShops();
      setShops(list);
      if (list.length > 0 && !selectedShopId) {
        setSelectedShopId(list[0].id);
      }
    } catch {
      // Backend may be starting
    } finally {
      setLoadingShops(false);
    }
  };

  const handleQuickLogin = async () => {
    if (!selectedShopId) {
      Alert.alert("Select Dukaan", "Please choose a virtual dukaan to open.");
      return;
    }
    setBusy(true);
    try {
      const res = await api.login({ shop_id: selectedShopId, pin });
      setMobileShopId(res.token);
      onAuthenticated(res.shop);
    } catch (e) {
      Alert.alert("Login Failed", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handlePhoneLogin = async () => {
    if (phone.length < 10) {
      Alert.alert("Invalid Phone", "Please enter a valid 10-digit mobile number.");
      return;
    }
    setBusy(true);
    try {
      const res = await api.login({ phone, pin });
      setMobileShopId(res.token);
      onAuthenticated(res.shop);
    } catch (e) {
      Alert.alert("Login Failed", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleRegister = async () => {
    if (!newName.trim() || !newOwner.trim() || newPhone.length < 10) {
      Alert.alert("Required Fields", "Please enter shop name, owner name, and 10-digit phone number.");
      return;
    }
    setBusy(true);
    try {
      const res = await api.registerShop({
        name: newName.trim(),
        owner_name: newOwner.trim(),
        phone: newPhone.trim(),
        language: newLang,
        pin: newPin || "1234",
      });
      setMobileShopId(res.token);
      Alert.alert("Welcome!", res.message);
      onAuthenticated(res.shop);
    } catch (e) {
      Alert.alert("Registration Failed", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={s.container}>
      <View style={s.header}>
        <View style={s.iconCircle}>
          <Text style={{ fontSize: 32 }}>🏪</Text>
        </View>
        <Text style={s.title}>DukaanAI Khata</Text>
        <Text style={s.subtitle}>Voice Digital Ledger for Kirana Shopkeepers</Text>
      </View>

      <View style={s.card}>
        {/* Tab switch */}
        <View style={s.tabs}>
          <Pressable
            style={[s.tabBtn, tab === "quick" && s.tabActive]}
            onPress={() => setTab("quick")}
          >
            <Text style={[s.tabTxt, tab === "quick" && s.tabTxtActive]}>🏪 My Shop</Text>
          </Pressable>
          <Pressable
            style={[s.tabBtn, tab === "phone" && s.tabActive]}
            onPress={() => setTab("phone")}
          >
            <Text style={[s.tabTxt, tab === "phone" && s.tabTxtActive]}>📱 Mobile</Text>
          </Pressable>
          <Pressable
            style={[s.tabBtn, tab === "new" && s.tabActive]}
            onPress={() => setTab("new")}
          >
            <Text style={[s.tabTxt, tab === "new" && s.tabTxtActive]}>✨ New</Text>
          </Pressable>
        </View>

        {/* TAB 1: QUICK SHOP PICK */}
        {tab === "quick" && (
          <View style={s.form}>
            <Text style={s.label}>Select Virtual Dukaan:</Text>
            {loadingShops ? (
              <ActivityIndicator color={C.brand} style={{ marginVertical: 20 }} />
            ) : (
              <View style={s.shopList}>
                {shops.map((sh) => {
                  const isSel = selectedShopId === sh.id;
                  return (
                    <Pressable
                      key={sh.id}
                      style={[s.shopItem, isSel && s.shopItemActive]}
                      onPress={() => setSelectedShopId(sh.id)}
                    >
                      <View style={{ flex: 1 }}>
                        <Text style={[s.shopName, isSel && { color: C.brand }]}>{sh.name}</Text>
                        <Text style={s.shopSub}>
                          {sh.owner_name ? `Prop: ${sh.owner_name}` : "Kirana Store"} • {sh.phone || "No phone"}
                        </Text>
                      </View>
                      <View style={[s.radio, isSel && s.radioActive]}>
                        {isSel && <View style={s.radioDot} />}
                      </View>
                    </Pressable>
                  );
                })}
              </View>
            )}

            <Text style={[s.label, { marginTop: 12 }]}>Security PIN (Default 1234):</Text>
            <TextInput
              secureTextEntry
              maxLength={6}
              value={pin}
              onChangeText={setPin}
              placeholder="1234"
              placeholderTextColor={C.muted}
              style={s.input}
              keyboardType="numeric"
            />

            <Pressable
              disabled={busy || !selectedShopId}
              style={[s.mainBtn, (busy || !selectedShopId) && { opacity: 0.5 }]}
              onPress={handleQuickLogin}
            >
              <Text style={s.mainBtnTxt}>
                {busy ? "Opening Dukaan…" : "🔓 Open My Virtual Dukaan"}
              </Text>
            </Pressable>
          </View>
        )}

        {/* TAB 2: PHONE & PIN LOGIN */}
        {tab === "phone" && (
          <View style={s.form}>
            <Text style={s.label}>10-Digit Mobile Number:</Text>
            <View style={s.phoneRow}>
              <Text style={s.prefix}>+91</Text>
              <TextInput
                maxLength={10}
                keyboardType="numeric"
                value={phone}
                onChangeText={(t) => setPhone(t.replace(/[^0-9]/g, ""))}
                placeholder="9845000000"
                placeholderTextColor={C.muted}
                style={[s.input, { flex: 1, borderTopLeftRadius: 0, borderBottomLeftRadius: 0 }]}
              />
            </View>

            <Text style={[s.label, { marginTop: 12 }]}>4-Digit PIN:</Text>
            <TextInput
              secureTextEntry
              maxLength={6}
              value={pin}
              onChangeText={setPin}
              placeholder="1234"
              placeholderTextColor={C.muted}
              style={s.input}
              keyboardType="numeric"
            />

            <Pressable
              disabled={busy || phone.length < 10}
              style={[s.mainBtn, (busy || phone.length < 10) && { opacity: 0.5 }]}
              onPress={handlePhoneLogin}
            >
              <Text style={s.mainBtnTxt}>{busy ? "Logging in…" : "🚀 Login with Mobile"}</Text>
            </Pressable>
          </View>
        )}

        {/* TAB 3: REGISTER NEW SHOP */}
        {tab === "new" && (
          <View style={s.form}>
            <Text style={s.label}>Dukaan / Shop Name:</Text>
            <TextInput
              value={newName}
              onChangeText={setNewName}
              placeholder="e.g. Ramesh Kirana Store"
              placeholderTextColor={C.muted}
              style={s.input}
            />

            <Text style={[s.label, { marginTop: 10 }]}>Proprietor / Owner Name:</Text>
            <TextInput
              value={newOwner}
              onChangeText={setNewOwner}
              placeholder="e.g. Ramesh Kumar"
              placeholderTextColor={C.muted}
              style={s.input}
            />

            <Text style={[s.label, { marginTop: 10 }]}>10-Digit Mobile Number:</Text>
            <TextInput
              keyboardType="numeric"
              maxLength={10}
              value={newPhone}
              onChangeText={(t) => setNewPhone(t.replace(/[^0-9]/g, ""))}
              placeholder="9876543210"
              placeholderTextColor={C.muted}
              style={s.input}
            />

            <Text style={[s.label, { marginTop: 10 }]}>Language:</Text>
            <View style={s.langRow}>
              {LANGS.slice(0, 3).map((l) => (
                <Pressable
                  key={l.code}
                  style={[s.langChip, newLang === l.code && s.langChipActive]}
                  onPress={() => setNewLang(l.code)}
                >
                  <Text style={[s.langTxt, newLang === l.code && s.langTxtActive]}>{l.label}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={[s.label, { marginTop: 10 }]}>4-Digit PIN:</Text>
            <TextInput
              secureTextEntry
              keyboardType="numeric"
              maxLength={6}
              value={newPin}
              onChangeText={setNewPin}
              placeholder="1234"
              placeholderTextColor={C.muted}
              style={s.input}
            />

            <Pressable
              disabled={busy || !newName.trim() || !newOwner.trim() || newPhone.length < 10}
              style={[
                s.mainBtn,
                (busy || !newName.trim() || !newOwner.trim() || newPhone.length < 10) && {
                  opacity: 0.5,
                },
              ]}
              onPress={handleRegister}
            >
              <Text style={s.mainBtnTxt}>
                {busy ? "Creating…" : "✨ Create My Virtual Dukaan"}
              </Text>
            </Pressable>
          </View>
        )}
      </View>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  container: {
    padding: 20,
    paddingTop: 40,
    backgroundColor: C.bg,
    flexGrow: 1,
    justifyContent: "center",
  },
  header: { alignItems: "center", marginBottom: 20 },
  iconCircle: {
    width: 60,
    height: 60,
    borderRadius: 20,
    backgroundColor: "#dcfce7",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 8,
  },
  title: { fontSize: 24, fontWeight: "900", color: C.text },
  subtitle: { fontSize: 12, color: C.muted, marginTop: 4, textAlign: "center" },
  card: {
    backgroundColor: C.card,
    borderRadius: 24,
    borderWidth: 1,
    borderColor: C.border,
    padding: 16,
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 10,
    elevation: 2,
  },
  tabs: {
    flexDirection: "row",
    backgroundColor: "#f1f5f9",
    borderRadius: 14,
    padding: 3,
    marginBottom: 16,
  },
  tabBtn: { flex: 1, paddingVertical: 8, alignItems: "center", borderRadius: 12 },
  tabActive: { backgroundColor: C.brand },
  tabTxt: { fontSize: 12, fontWeight: "700", color: C.muted },
  tabTxtActive: { color: "#fff" },
  form: { gap: 4 },
  label: { fontSize: 11, fontWeight: "700", color: C.text, marginBottom: 4 },
  input: {
    borderWidth: 1,
    borderColor: C.border,
    backgroundColor: "#fff",
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    color: C.text,
  },
  phoneRow: { flexDirection: "row", alignItems: "center" },
  prefix: {
    backgroundColor: "#f1f5f9",
    borderWidth: 1,
    borderRightWidth: 0,
    borderColor: C.border,
    borderTopLeftRadius: 12,
    borderBottomLeftRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 11,
    fontSize: 13,
    fontWeight: "700",
    color: C.muted,
  },
  shopList: { maxHeight: 180, gap: 8 },
  shopItem: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderWidth: 1,
    borderColor: C.border,
    borderRadius: 14,
    padding: 12,
    backgroundColor: "#f8fafc",
  },
  shopItemActive: { borderColor: C.brand, backgroundColor: "#f0fdf4" },
  shopName: { fontSize: 13, fontWeight: "800", color: C.text },
  shopSub: { fontSize: 11, color: C.muted, marginTop: 2 },
  radio: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 2,
    borderColor: C.border,
    alignItems: "center",
    justifyContent: "center",
  },
  radioActive: { borderColor: C.brand },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: C.brand },
  langRow: { flexDirection: "row", gap: 6, marginVertical: 4 },
  langChip: {
    flex: 1,
    borderWidth: 1,
    borderColor: C.border,
    borderRadius: 10,
    paddingVertical: 6,
    alignItems: "center",
    backgroundColor: "#fff",
  },
  langChipActive: { borderColor: C.brand, backgroundColor: "#f0fdf4" },
  langTxt: { fontSize: 10, fontWeight: "700", color: C.muted },
  langTxtActive: { color: C.brand },
  mainBtn: {
    backgroundColor: C.brand,
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 16,
    shadowColor: C.brand,
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 3,
  },
  mainBtnTxt: { color: "#fff", fontSize: 14, fontWeight: "800" },
});

