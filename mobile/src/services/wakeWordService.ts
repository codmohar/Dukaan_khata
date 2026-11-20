import { Platform } from "react-native";
import { PICOVOICE_KEY, WAKE_KEYWORD_PATH } from "../config";

let manager: any = null;
let running = false;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function getPorcupine(): any {
  try {
    return require("@picovoice/porcupine-react-native")?.PorcupineManager ?? null;
  } catch {
    return null;
  }
}

function getBackgroundService(): any {
  try {
    return require("react-native-background-actions")?.default ?? null;
  } catch {
    return null;
  }
}

/** Starts offline "Hi Khata" detection (or zero-key continuous mode in Expo Go). */
export async function startAlwaysListening(onWake: () => void) {
  await stopAlwaysListening();

  const PorcupineManager = getPorcupine();
  if (PICOVOICE_KEY && PorcupineManager) {
    try {
      manager = await PorcupineManager.fromKeywordPaths(
        PICOVOICE_KEY,
        [WAKE_KEYWORD_PATH],
        () => {
          onWake();
        },
        (e: any) => {
          console.warn("Porcupine error:", e);
        }
      );
      await manager.start();
      running = true;
    } catch (err) {
      console.warn("Porcupine init notice:", err);
    }
  } else {
    console.info("Running in zero-key continuous voice mode (Expo Go compatible).");
  }

  const BackgroundService = getBackgroundService();
  if (Platform.OS === "android" && BackgroundService && !BackgroundService.isRunning()) {
    try {
      await BackgroundService.start(
        async () => {
          while (BackgroundService.isRunning()) {
            await sleep(5000);
          }
        },
        {
          taskName: "DukaanAI",
          taskTitle: "DukaanAI Voice Khata is Active",
          taskDesc: 'Listening for "Hi Khata" wake word',
          taskIcon: { name: "ic_launcher", type: "mipmap" },
          color: "#16a34a",
        }
      );
    } catch (bgErr) {
      console.warn("BackgroundService notice:", bgErr);
    }
  }
}

export async function pauseWakeWord() {
  if (manager && running) {
    try {
      await manager.stop();
    } catch {}
    running = false;
  }
}

export async function resumeWakeWord() {
  if (manager && !running) {
    try {
      await manager.start();
      running = true;
    } catch (e) {
      console.warn("Failed to resume Porcupine:", e);
    }
  }
}

export async function stopAlwaysListening() {
  if (manager) {
    try {
      await manager.stop();
      await manager.delete();
    } catch {}
    manager = null;
  }
  running = false;
  const BackgroundService = getBackgroundService();
  if (BackgroundService && BackgroundService.isRunning?.()) {
    try {
      await BackgroundService.stop();
    } catch {}
  }
}
