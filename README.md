# DukaanAI: Enterprise Voice Digital Khata for Indian Retailers

An always-listening, multilingual, voice-first digital ledger (*khata*) and shopkeeper intelligence system built specifically for Indian kirana shopkeepers.

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Frontend-Next.js%2014-black.svg)](https://nextjs.org)
[![React Native](https://img.shields.io/badge/Mobile-React%20Native%20Expo-61DAFB.svg)](https://reactnative.dev)
[![Supabase](https://img.shields.io/badge/Database-PostgreSQL%20%2B%20pg__trgm-3ECF8E.svg)](https://supabase.com)
[![Gemini](https://img.shields.io/badge/LLM-Gemini%20Flash--Lite%202.5-4285F4.svg)](https://ai.google.dev)
[![Sarvam AI](https://img.shields.io/badge/Speech-Sarvam%20%2F%20Gnani%20v3.0-blue.svg)](https://sarvam.ai)
[![Tests](https://img.shields.io/badge/Tests-32%20Passed%20(100%25)-brightgreen.svg)]()

---

## 1. System Architecture & High-Level Workflow

```mermaid
flowchart TD
    subgraph MobileDevice["📱 Mobile Devices & Counter Terminals"]
        PWA["Responsive PWA\n(Web Audio VAD + Safe Areas)"]
        EXPO["React Native Expo App\n(Background Audio Service)"]
        REV["Port 4000 Reverse Proxy\n(proxy.js + Cloudflare Tunnel)"]
    end

    subgraph Backend["🚀 FastAPI Voice & Rules Engine (Port 8000)"]
        WS["/ws/voice WebSocket"]
        REST["REST API Endpoints"]
        FAST["Deterministic Fast Engine\n(Regex + Number Normalizer)"]
        LLM["Gemini Flash-Lite Agent\n(Tools & System Guardrails)"]
        RULES["Dukaan Rules Engine\n(New Customer, Caps, Time Cutoff)"]
        RECON["Daily Reconciliation Engine\n(Cash & UPI Audit)"]
        VISION["Gemini Vision Engine\n(Khata Book OCR Digitizer)"]
        SPEECH["Sarvam AI / Gnani Prisma\n(Multilingual STT & TTS)"]
    end

    subgraph Database["🗄️ PostgreSQL / Supabase"]
        SHOPS["shops"]
        CUST["customers (atomic row locking)"]
        TX["transactions (drafts & confirmed)"]
        HOUSE["household_members"]
        PROM["promises & promises_effective view"]
        SHRULE["shop_rules"]
        DRECON["daily_reconciliations"]
        VBAL["customer_balances view"]
    end

    PWA -->|HTTP & WS| REV
    EXPO -->|HTTP & WS| REV
    REV -->|/api/* & /ws/*| WS
    REV -->|UI Routes| PWA
    WS --> FAST
    FAST -->|Fast Path Match| RULES
    FAST -.->|Complex Path| LLM
    LLM --> RULES
    RULES --> CUST
    RULES --> TX
    RULES --> PROM
    RULES --> HOUSE
    WS --> SPEECH
    SPEECH --> PWA
    SPEECH --> EXPO
```

### Core Operational Invariants:
1. **Never Commit in the Same Turn:** Spoken credit/payment orders are always drafted first. The assistant reads back the name, amount, items, and any shop policy warnings aloud and asks for explicit confirmation before committing.
2. **Explicit Policy Warnings Spoken Aloud:** When an active shop rule is triggered (e.g., *"Naye customer ko 1000 se zyada udhar matt do"*), the voice engine speaks the exact rule text to the shopkeeper and blocks auto-commit until the shopkeeper explicitly commands *"Continue anyway"*.
3. **Strict Row-Level Locking:** Every draft confirmation executes `SELECT ... FOR UPDATE` on the customer record, ensuring exact atomic balance updates under concurrent transactions.
4. **Automatic Promise Settlement:** Confirming a payment automatically fulfills corresponding pending payment promises for that customer.
5. **Real-Time Cross-Device Synchronization:** Supabase Realtime / WebSocket events instantly synchronize mobile devices and counter screens with zero manual refreshes.

---

## 2. Advanced Feature Architecture

### 1. Household Khata (`household_members`)
- Links family members (wife, son, brother, etc.) to a primary customer's balance.
- Spoken commands like *"Ramesh ke ladke ko 150 ka tel do"* resolve the member under the parent customer khata.
- Hard invariant: Member credit cannot cross customer boundaries; ambiguous members across families prompt disambiguation.

### 2. Dukaan Rules Policy Engine (`shop_rules`)
- Configurable shop policies: `NEW_CUSTOMER_CAP`, `BALANCE_CAP`, `TIME_CUTOFF`, `DISALLOW_MEMBER_CREDIT`.
- Evaluated deterministically before drafts are created.
- Warning banner and audible TTS alert spoken to the shopkeeper.
- Supports vocal and button overrides (*"Continue anyway"*).

### 3. Promise Memory (`promises`)
- Tracks spoken commitments: payment promises (*"Kal 500 de dunga"*), goods reservations (*"2 packet atta kal aayega"*), and supplier deliveries.
- `promises_effective` view flags past promises as `OVERDUE` automatically.
- Confirming payments auto-settles matching pending promises.

### 4. Shopkeeper Memory Recall
- Ambient conversational lookup tool (`recall_shopkeeper_memory`).
- Answers questions like: *"Ramesh ne kab bola tha paise dene ko?"* or *"Kal ka hisaab batao"*.
- Strict multi-tenant cross-shop isolation: queries never leak customer records across distinct `shop_id`s.

### 5. Smart Dispute Timeline
- Chronological transaction audit trail for customer balance verification.
- Calculates step-by-step running balance with transcript snippets and timestamps in Indian Standard Time (`Asia/Kolkata`).
- Flags any discrepancy between ledger sum and physical customer balance column.

### 6. Daily Reconciliation (`daily_reconciliations`)
- Evening cash & UPI reconciliation wizard.
- Compares recorded ledger payments against actual drawer cash and UPI app statements.
- Categorizes status: `MATCHED` or `NEEDS_INVESTIGATION`.
- Pinpoints unconfirmed drafts, duplicate transactions within 15 minutes, or walk-in non-khata cash differences without altering past confirmed records.

### 7. Book Scan (OCR Ledger Digitization)
- Takes photos of physical paper khata registers or supplier invoices.
- Gemini 2.5 Flash Vision extracts ledger lines with confidence scores and fuzzy customer candidate matching.
- Safe 2-step verification: shopkeeper inspects scanned rows before approving them into the digital ledger.

---

## 3. Monorepo Structure

```text
dukaan-ai/
├── docker-compose.yml              # Complete multi-service production stack
├── proxy.js                        # Unified reverse proxy (Port 4000)
├── tunnel_runner.ps1               # Persistent auto-reconnecting Cloudflare tunnel
├── pytest.ini                      # Python test configuration
├── supabase/
│   └── migrations/
│       ├── 001_init_schema.sql     # Base tables, views & pg_trgm indices
│       ├── 002_kirana_money_flows.sql # Payment modes & adjustment reasons
│       ├── 003_extended_languages_and_reminders.sql # 13 Indian languages
│       ├── 003_scans.sql           # Vision scan tables & duplicates tracking
│       └── 004_advanced_features.sql # Household, rules, promises, reconciliations
├── backend/                        # FastAPI High-Performance Backend
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                 # REST routes & WebSocket handler
│   │   ├── config.py               # Robust multi-path settings loader
│   │   ├── db.py                   # Async SQLAlchemy connection engine
│   │   ├── models.py               # Declarative database entities
│   │   ├── schemas.py              # Pydantic v2 validation models
│   │   ├── agent/
│   │   │   ├── fast_engine.py      # Sub-100ms deterministic regex & number parser
│   │   │   ├── indian_numbers.py   # Indian spoken numerical system (dedh, dhai, sava...)
│   │   │   ├── llm_provider.py     # Gemini Flash-Lite LLM client
│   │   │   ├── pipeline.py         # Voice session state machine
│   │   │   ├── prompts.py          # Multilingual system instructions
│   │   │   └── tools.py            # Complete database toolset
│   │   ├── routers/
│   │   │   ├── features.py         # Household, Rules, Promises, Reconciliation routes
│   │   │   └── scans.py            # Book Scan OCR routes
│   │   └── services/
│   │       ├── household.py        # Household member service
│   │       ├── memory.py           # Conversational memory recall
│   │       ├── promises.py         # Promise tracking & auto-fulfilment
│   │       ├── reconciliation.py   # Cash/UPI daily reconciliation
│   │       ├── rules.py            # Dukaan Rules policy validation
│   │       ├── speech.py           # PCM-to-WAV conversion & provider router
│   │       ├── stt_gnani.py        # Speech-to-text service
│   │       ├── timeline.py         # Running balance dispute resolver
│   │       ├── tts_gnani.py        # Text-to-speech service
│   │       └── vision.py           # Gemini Vision image analysis
│   └── tests/
│       ├── test_advanced_features.py # 24 advanced feature verification tests
│       └── test_scans.py           # 8 OCR scan tests
├── web/                            # Next.js 14 Mobile-First Web Application
│   ├── Dockerfile                  # Multi-stage production container
│   ├── package.json
│   ├── public/                     # PWA manifest, service worker, icons
│   └── src/
│       ├── app/
│       │   ├── layout.tsx          # Mobile viewport, notch cover, safe areas
│       │   ├── globals.css         # Touch manipulation, no-scrollbar utilities
│       │   ├── page.tsx            # Dashboard with Reconciliation trigger
│       │   ├── voice/page.tsx      # Voice Khata with colored cards & warning banners
│       │   ├── customers/page.tsx  # Customer directory
│       │   ├── customers/[id]/page.tsx # Customer detail, Household pills & Timeline tab
│       │   ├── memory/page.tsx     # Memory, Promises, Rules & Reconciliation UI
│       │   ├── scan/page.tsx       # Camera & OCR verification
│       │   ├── transactions/page.tsx # Ledger history & CSV export
│       │   └── settings/page.tsx   # Language selector & connectivity status
│       ├── components/
│       │   ├── Sidebar.tsx         # Responsive desktop sidebar & mobile bottom bar
│       │   ├── ui.tsx              # Touch-friendly buttons, badges, modals
│       │   └── PwaRegistrar.tsx    # Service worker lifecycle manager
│       └── lib/
│           ├── api.ts              # Unified REST client & WhatsApp link builder
│           ├── supabase.ts         # Realtime subscription hook
│           └── useVoice.ts         # Web Audio streaming & VAD hook
└── mobile/                         # React Native (Expo) Dedicated Mobile App
    ├── app.json                    # Permissions for background mic & audio
    ├── package.json
    └── src/
        ├── App.tsx                 # Screen preservation tab navigator
        ├── config.ts               # Mobile API and WebSocket endpoints
        ├── screens/
        │   ├── HomeVoiceScreen.tsx # Voice Khata screen with rule warnings
        │   ├── MemoryScreen.tsx    # Promise memory & rule browser
        │   ├── QuickLedgerScreen.tsx # Debtors summary & search
        │   └── ScanScreen.tsx      # Mobile camera document scanner
        └── services/
            ├── api.ts              # Mobile HTTP client
            └── voiceSocket.ts      # WebSocket 16kHz PCM streamer & player
```

---

## 4. Mobile-First Architecture & PWA Readiness

DukaanAI is engineered from the ground up to operate as a primary mobile application:
1. **Viewport Optimization:** `viewportFit: "cover"`, `maximum-scale=1`, and `user-scalable=no` ensure the layout locks cleanly to native device dimensions without zooming artifacts.
2. **Safe-Area Insets:** Dynamic CSS padding (`env(safe-area-inset-bottom)`) guarantees navigation buttons never overlap with Android navigation bars or iOS home indicator bars.
3. **Fast Touch Interaction:** `touch-action: manipulation;` and min-height 44px tap targets eliminate the 300ms mobile tap delay.
4. **Smooth Mobile Navigation:** The bottom navigation bar supports horizontal scrolling with smooth touch deceleration on narrow screens (e.g., 360px Android devices).
5. **Offline & PWA Installation:** Built-in `manifest.json`, high-resolution icons (192px, 512px, Apple Touch), and service worker (`sw.js`) allow full homescreen installation with standalone display mode.

---

## 5. Environment Variables Reference

### Backend (`backend/.env`)
| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `DATABASE_URL` | PostgreSQL connection string (asyncpg) | `postgresql+asyncpg://postgres:postgres@localhost:5432/dukaan` |
| `DEFAULT_SHOP_ID` | Default shop tenant UUID | `00000000-0000-0000-0000-000000000001` |
| `GEMINI_API_KEY` | Google Gemini API Key | `AIzaSy...` |
| `GEMINI_MODEL` | Gemini Model version | `gemini-3.1-flash-lite` or `gemini-2.5-flash` |
| `SPEECH_PROVIDER` | Speech provider (`sarvam`, `gnani`, or `mock`) | `sarvam` |
| `SARVAM_API_KEY` | Sarvam AI API Key | `...` |
| `GNANI_API_KEY` | Gnani AI API Key | `...` |
| `CORS_ORIGINS` | Allowed origins | `http://localhost:3000,http://127.0.0.1:3000,*` |
| `PORT` | Backend listening port | `8000` |

### Web Frontend (`web/.env.local`)
| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `NEXT_PUBLIC_API_URL` | Backend HTTP API base URL | `http://localhost:8000` (or `http://localhost:4000/api`) |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase Cloud URL (for live pub/sub) | `https://your-project.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase Anonymous Client Key | `eyJhbGci...` |

### Mobile App (`mobile/.env`)
| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `EXPO_PUBLIC_API_URL` | Backend URL accessible from phone | `http://192.168.1.X:8000` or Cloudflare Tunnel URL |
| `EXPO_PUBLIC_SUPABASE_URL` | Supabase Cloud URL | `https://your-project.supabase.co` |
| `EXPO_PUBLIC_SUPABASE_ANON_KEY` | Supabase Anonymous Key | `eyJhbGci...` |
| `EXPO_PUBLIC_PICOVOICE_KEY` | Porcupine wake-word access key | `...` |

---

## 6. Quickstart & Deployment Instructions

### 1. Run Everything with Docker Compose
```bash
cd dukaan-ai
docker compose up --build
```
This spins up:
- PostgreSQL with `pg_trgm` and automatic forward migrations (`001` through `004`) on port 5432.
- FastAPI Backend on port 8000.
- Next.js Web App on port 3000.

### 2. Run Manually for Local Development

#### Start Backend:
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows: venv\Scripts\activate, Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Start Web Frontend:
```bash
cd web
npm install
npm run dev
```

#### Start Mobile App (Expo):
```bash
cd mobile
npm install
npx expo start
```

### 3. Unified Proxy & Cloudflare Tunnel
To run both frontend and backend through a single HTTPS port accessible anywhere on mobile:
```bash
# Start unified reverse proxy (maps /api and /ws to 8000, and other traffic to 3000):
node proxy.js

# Start persistent auto-reconnecting tunnel:
powershell -ExecutionPolicy Bypass -File tunnel_runner.ps1
```

---

## 7. Verification & Testing

Run the automated test suites:
```bash
cd dukaan-ai

# Advanced Features Test Suite (24 tests):
python -m pytest backend/tests/test_advanced_features.py -v

# Book Scan Vision OCR Test Suite (8 tests):
python -m pytest backend/tests/test_scans.py -v

# Web TypeScript verification:
cd web && npx tsc --noEmit

# Mobile TypeScript verification:
cd mobile && npx tsc --noEmit
```

**Status:** All 32 automated tests pass with 100% success rate.

---

## 8. License
MIT License. Built for Indian Kirana Shopkeepers.
