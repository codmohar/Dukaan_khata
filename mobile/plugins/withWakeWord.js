// Expo config plugin: (1) registers the background-actions foreground service with the microphone type,
// (2) copies assets/wake/hey_dukaan_android.ppn into the Android assets folder at prebuild time.
const { withAndroidManifest, withDangerousMod } = require("@expo/config-plugins");
const fs = require("fs");
const path = require("path");

const SERVICE = "com.asterinet.react.bgactions.RNBackgroundActionsTask";

module.exports = (config) => {
  config = withAndroidManifest(config, (c) => {
    const app = c.modResults.manifest.application[0];
    app.service = app.service || [];
    if (!app.service.some((s) => s.$["android:name"] === SERVICE)) {
      app.service.push({ $: { "android:name": SERVICE, "android:foregroundServiceType": "microphone" } });
    }
    return c;
  });
  return withDangerousMod(config, ["android", async (c) => {
    const src = path.join(c.modRequest.projectRoot, "assets", "wake", "hey_dukaan_android.ppn");
    const destDir = path.join(c.modRequest.platformProjectRoot, "app", "src", "main", "assets");
    if (fs.existsSync(src)) {
      fs.mkdirSync(destDir, { recursive: true });
      fs.copyFileSync(src, path.join(destDir, "hey_dukaan_android.ppn"));
    }
    return c;
  }]);
};
