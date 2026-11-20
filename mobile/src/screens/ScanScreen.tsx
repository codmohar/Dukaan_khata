import * as ImagePicker from "expo-image-picker";
import { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { inr, ScanData, ScanLine, scans } from "../services/api";
import { C } from "../theme";

export default function ScanScreen() {
  const [data, setData] = useState<ScanData | null>(null);
  const [uri, setUri] = useState("");
  const [busy, setBusy] = useState(false);

  async function pick(camera: boolean) {
    try {
      const perm = camera
        ? await ImagePicker.requestCameraPermissionsAsync()
        : await ImagePicker.requestMediaLibraryPermissionsAsync();

      if (!perm.granted) {
        Alert.alert(
          "Permission Required",
          camera
            ? "Camera permission is needed to photograph kirana khata pages."
            : "Photo library access is needed to pick an image."
        );
        return;
      }

      const opts: ImagePicker.ImagePickerOptions = {
        mediaTypes: ["images"],
        quality: 0.6, // Keep uploads fast and lightweight
      };
      const res = camera
        ? await ImagePicker.launchCameraAsync(opts)
        : await ImagePicker.launchImageLibraryAsync(opts);

      if (res.canceled || !res.assets || res.assets.length === 0) return;

      const selectedUri = res.assets[0].uri;
      setBusy(true);
      setUri(selectedUri);

      const scanResult = await scans.upload(selectedUri);
      setData(scanResult);
    } catch (e) {
      Alert.alert("Scan Error", (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const patch = async (id: string, p: Record<string, unknown>) => {
    try {
      const u = await scans.edit(id, p);
      setData((d) => d && { ...d, lines: d.lines.map((l) => (l.id === id ? u : l)) });
    } catch (e) {
      Alert.alert("Error", (e as Error).message);
    }
  };

  const approve = async () => {
    if (!data) return;
    try {
      const r = await scans.approve(data.scan.id);
      Alert.alert("Success", `✓ ${r.created} entries successfully added to your khata ledger!`);
      setData(null);
      setUri("");
    } catch (e) {
      Alert.alert("Cannot Approve", (e as Error).message);
    }
  };

  const discard = async () => {
    if (data) {
      await scans.reject(data.scan.id).catch(() => {});
      setData(null);
      setUri("");
    }
  };

  const included = data?.lines.filter((l) => l.include) ?? [];
  const unresolved = included.filter((l) => !l.customer_id).length;

  if (!data) {
    return (
      <View style={s.center}>
        {busy ? (
          <>
            <ActivityIndicator size="large" color={C.brand} />
            <Text style={s.title}>Reading Document Photo…</Text>
            <Text style={s.hint}>Gemini AI is extracting customer names, amounts and dates.</Text>
          </>
        ) : (
          <>
            <View style={s.iconCircle}>
              <Text style={{ fontSize: 40 }}>📷</Text>
            </View>
            <Text style={s.title}>Scan Khata, UPI or Bill</Text>
            <Text style={s.hint}>
              Take a photo of a handwritten udhar book, payment screenshot, or bill. AI reads it, you review, then it's saved.
            </Text>
            <Pressable style={s.big} onPress={() => pick(true)}>
              <Text style={s.bigTxt}>📷 Take Photo with Camera</Text>
            </Pressable>
            <Pressable style={[s.big, s.bigAlt]} onPress={() => pick(false)}>
              <Text style={[s.bigTxt, { color: C.brand }]}>🖼️ Choose from Gallery</Text>
            </Pressable>
            <Text style={s.privacyNotice}>
              🔒 Photos are processed securely for reading and are never stored on the server.
            </Text>
          </>
        )}
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={{ padding: 14, gap: 12 }}>
      {!!uri && <Image source={{ uri }} style={s.img} resizeMode="cover" />}
      {!!data.scan.summary && (
        <View style={s.summaryBox}>
          <Text style={s.summaryTxt}>{data.scan.summary}</Text>
        </View>
      )}

      {data.scan.warnings.map((w, i) => (
        <View key={i} style={s.warnBox}>
          <Text style={s.warn}>⚠️ {w}</Text>
        </View>
      ))}

      {data.lines.length === 0 && (
        <Text style={s.hint}>No ledger credit/payment entries found in this image.</Text>
      )}

      {data.lines.map((l) => (
        <Line key={l.id} l={l} patch={patch} />
      ))}

      <Pressable
        style={[s.big, (included.length === 0 || unresolved > 0) && { opacity: 0.4 }]}
        disabled={included.length === 0 || unresolved > 0}
        onPress={approve}
      >
        <Text style={s.bigTxt}>
          {unresolved > 0
            ? `Pick customer for ${unresolved} line(s)`
            : `✓ Approve & Commit ${included.length} Entries`}
        </Text>
      </Pressable>

      <Pressable onPress={discard} style={s.discardBtn}>
        <Text style={s.discard}>✕ Discard Scan</Text>
      </Pressable>
    </ScrollView>
  );
}

function Line({
  l,
  patch,
}: {
  l: ScanLine;
  patch: (id: string, p: Record<string, unknown>) => void;
}) {
  const [amt, setAmt] = useState(String(Number(l.amount)));
  const isMissing = l.include && !l.customer_id;

  return (
    <View
      style={[
        s.card,
        !l.include && { opacity: 0.45 },
        isMissing && { borderColor: C.red, borderWidth: 2 },
        l.confidence < 0.6 && { borderColor: C.amberBorder },
      ]}
    >
      <View style={s.rowBetween}>
        <Text style={s.raw} numberOfLines={1}>
          Line: “{l.raw_text}”
        </Text>
        <Switch
          value={l.include}
          onValueChange={(v) => patch(l.id, { include: v })}
          trackColor={{ true: C.brand }}
        />
      </View>

      {l.duplicate && (
        <Text style={s.warn}>⚠️ Looks already recorded (same customer, amount and date)</Text>
      )}
      {l.confidence < 0.6 && <Text style={s.warn}>⚠️ Low confidence handwriting, please check</Text>}
      {isMissing && (
        <Text style={{ fontSize: 12, color: C.red, fontWeight: "700" }}>
          * Select customer below or add as new customer
        </Text>
      )}

      {/* Customer Candidates Chips */}
      <View style={s.chips}>
        {l.candidates.map((c) => (
          <Pressable
            key={c.customer_id}
            onPress={() => patch(l.id, { customer_id: c.customer_id })}
            style={[s.chip, l.customer_id === c.customer_id && s.chipOn]}
          >
            <Text style={[s.chipTxt, l.customer_id === c.customer_id && { color: "#fff" }]}>
              {c.name}
              {c.landmark ? ` (${c.landmark})` : ""}
            </Text>
          </Pressable>
        ))}
        {!l.customer_id && !!l.raw_name && (
          <Pressable
            onPress={() => patch(l.id, { create_customer_name: l.raw_name })}
            style={[s.chip, { borderStyle: "dashed", borderColor: C.brand }]}
          >
            <Text style={[s.chipTxt, { color: C.brand }]}>＋ Add “{l.raw_name}” as New</Text>
          </Pressable>
        )}
      </View>

      <View style={s.rowBetween}>
        <Pressable
          onPress={() => patch(l.id, { type: l.type === "credit" ? "payment" : "credit" })}
          style={s.typeToggle}
        >
          <Text style={[s.type, { color: l.type === "credit" ? C.red : C.brand }]}>
            {l.type === "credit" ? "Udhar (Credit) ⇄" : "Paid (Jama) ⇄"}
          </Text>
        </Pressable>
        <TextInput
          style={s.amt}
          keyboardType="numeric"
          value={amt}
          onChangeText={setAmt}
          onEndEditing={() =>
            Number(amt) > 0 && Number(amt) !== Number(l.amount) && patch(l.id, { amount: Number(amt) })
          }
        />
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, gap: 14 },
  iconCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: "#ecfdf5",
    alignItems: "center",
    justifyContent: "center",
  },
  title: { fontSize: 22, fontWeight: "800", color: C.text, textAlign: "center" },
  hint: { color: C.muted, textAlign: "center", fontSize: 13, lineHeight: 18 },
  privacyNotice: { color: "#94a3b8", textAlign: "center", fontSize: 11, marginTop: 8 },
  big: { alignSelf: "stretch", backgroundColor: C.brand, padding: 16, borderRadius: 14, alignItems: "center" },
  bigAlt: { backgroundColor: "#fff", borderWidth: 1, borderColor: C.brand },
  bigTxt: { color: "#fff", fontWeight: "700", fontSize: 16 },
  img: { height: 180, borderRadius: 14, backgroundColor: "#e2e8f0" },
  summaryBox: { backgroundColor: "#f1f5f9", padding: 10, borderRadius: 10 },
  summaryTxt: { fontSize: 12, color: C.text, fontWeight: "600" },
  warnBox: { backgroundColor: "#fef3c7", padding: 10, borderRadius: 10, borderWidth: 1, borderColor: "#fde68a" },
  warn: { color: "#92400e", fontSize: 12, fontWeight: "600" },
  card: { backgroundColor: C.card, borderRadius: 14, padding: 12, borderWidth: 1, borderColor: C.border, gap: 8 },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  raw: { flex: 1, color: C.muted, fontSize: 12 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: "#fff" },
  chipOn: { backgroundColor: C.brand, borderColor: C.brand },
  chipTxt: { fontSize: 13, color: C.text, fontWeight: "600" },
  typeToggle: { paddingVertical: 4, paddingHorizontal: 8, backgroundColor: "#f8fafc", borderRadius: 8 },
  type: { fontWeight: "700", fontSize: 14 },
  amt: { minWidth: 90, textAlign: "right", fontSize: 20, fontWeight: "800", borderBottomWidth: 1, borderColor: C.border, color: C.text },
  discardBtn: { alignItems: "center", padding: 10 },
  discard: { textAlign: "center", color: C.red, fontWeight: "700", fontSize: 14 },
});

