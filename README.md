# DukaanAI: Production Multi-Platform Voice Khata

An always-listening, multilingual, voice-first digital ledger (*khata*) built for Indian kirana shopkeepers.

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Frontend-Next.js%2014-black.svg)](https://nextjs.org)
[![React Native](https://img.shields.io/badge/Mobile-React%20Native%20Expo-61DAFB.svg)](https://reactnative.dev)
[![Supabase](https://img.shields.io/badge/Database-Supabase%20PostgreSQL-3ECF8E.svg)](https://supabase.com)
[![Gemini](https://img.shields.io/badge/LLM-Gemini%202.5%20Flash-4285F4.svg)](https://ai.google.dev)
[![Gnani AI](https://img.shields.io/badge/Speech-Gnani%20Prisma%20v3.0%20%2F%20Sarvam-blue.svg)](https://gnani.ai)

---

## 1. System Architecture & Workflow

```mermaid
flowchart TD
    subgraph MobileApp["📱 Installable Mobile App (Expo)"]
        WW["Picovoice Porcupine ('Hey Dukaan')"]
        BGS["Android Foreground Service (Screen Locked)"]
        MIC1["16kHz PCM Audio Streamer"]
    end

    subgraph WebApp["💻 Counter Desktop / Tablet (Next.js 14)"]
        MIC2["Browser Web Audio API"]
        DASH["Real-Time Dashboard & Ledgers"]
    end

    subgraph Backend["🚀 FastAPI Voice AI Orchestrator"]
        WS["/ws/voice WebSocket"]
        VAD["Voice Activity Detector & Framer"]
        STT["Gnani Prisma v3.0 STT\n(Sarvam 'saarika' Fallback)"]
        AGENT["Gemini 2.5 Flash LLM Agent\n(Strict Function Calling)"]
        TTS["Gnani Timbre v3.0 TTS\n(Sarvam 'bulbul' Fallback)"]
    end

    subgraph Database["🗄️ Supabase PostgreSQL Cloud"]
        TRGM["pg_trgm Fuzzy Customer Matching"]
        TBL["shops, customers, transactions"]
        VIEW["customer_balances view"]
        RT["Supabase Realtime Engine (Pub/Sub)"]
    end

    WW -->|Wake Event| MIC1
    BGS -.->|Keeps Mic Alive| WW
    MIC1 -->|WebSocket 16kHz PCM| WS
    MIC2 -->|WebSocket 16kHz PCM| WS

    WS --> VAD --> STT --> AGENT
    AGENT <-->|search_customers / create_draft / confirm_draft| TBL
    AGENT --> TTS --> WS
    WS -->|Live Audio WAV + Draft Card| MobileApp
    WS -->|Live Audio WAV + Draft Card| WebApp

    TBL --> VIEW
    TBL -.->|Postgres Changes| RT
    RT ==>|Live Push Updates| DASH
```

### Core Workflow:
1. **Wake & Capture:** Shopkeeper says *"Hey Dukaan"* (or taps the mic), and speaks in Kannada, Hindi, English, or code-mixed speech (e.g. *"Ramesh ge 340 rupayi udhar bardu"*).
2. **Entity Extraction:** AI agent transliterates the name to Latin script, queries `pg_trgm` fuzzy similarity indexes on the customer table, extracts transaction amount and type (*credit* or *payment*).
3. **Disambiguation:** If multiple customers share the same name (e.g., *Ramesh Kumar (Bus Stand)* vs *Ramesh Gowda (Temple)*), DukaanAI asks for clarification with identifying landmarks.
4. **Guardrail Enforced Confirmation:** The agent creates an unconfirmed draft transaction, reads back the customer name, amount, and type aloud, and asks: *"Confirm?"*. The agent **never commits a draft in the same turn**; it waits for the shopkeeper's explicit affirmation in a subsequent turn before committing.
5. **Real-Time Sync:** Once committed, the transaction is saved to PostgreSQL, customer balance updates, and Supabase Realtime immediately updates both the mobile app and web counter without manual refresh.

---

## 2. Monorepo Structure

```text
dukaan-ai/
├── docker-compose.yml          # Multi-container stack (Postgres + pg_trgm + Backend)
├── supabase/
│   └── migrations/
│       └── 001_init_schema.sql # Complete DB schema, pg_trgm, RLS, & seed data
├── backend/                    # Python 3.11+ FastAPI + Voice AI Orchestrator
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   └── app/
│       ├── main.py             # REST API routes + /ws/voice WebSocket
│       ├── config.py           # Configuration & fallback environment loader
│       ├── db.py               # Async engine pool (PgBouncer statement_cache_size=0)
│       ├── models.py           # SQLAlchemy declarative models
│       ├── schemas.py          # Pydantic v2 schemas
│       ├── agent/
│       │   ├── pipeline.py     # Pipecat-compatible STT -> LLM -> Tools -> TTS pipeline
│       │   ├── llm_provider.py # Unified LLMProvider interface (Gemini 2.5 Flash + Mock)
│       │   ├── tools.py        # Database tools with pg_trgm fuzzy search
│       │   └── prompts.py      # Multilingual system prompts & guardrails
│       └── services/
│           ├── speech.py       # Speech router & PCM-to-WAV converter
│           ├── stt_gnani.py    # Gnani Prisma v3.0 STT wrapper with Sarvam fallback
│           └── tts_gnani.py    # Gnani Timbre v3.0 TTS wrapper with Sarvam fallback
├── web/                        # Next.js 14 (App Router) Counter Dashboard
│   ├── package.json
│   ├── .env.example
│   └── src/
│       ├── app/
│       │   ├── layout.tsx      # Dark high-contrast counter sidebar layout
│       │   ├── page.tsx        # Dashboard (5 key stat cards + 7-day chart + drafts)
│       │   ├── voice/page.tsx  # Voice Khata (interactive mic + transcript + draft card)
│       │   ├── customers/page.tsx # Customer CRUD + ledger history + WhatsApp reminders
│       │   ├── transactions/page.tsx # Filterable ledger table + manual entry modal + CSV
│       │   ├── reports/page.tsx # Analytics, debtor ranking chart & WhatsApp recovery
│       │   └── settings/page.tsx # Shop profile, language selector, connectivity status
│       ├── components/
│       │   ├── Sidebar.tsx     # Desktop sidebar + mobile browser bottom navigation
│       │   └── ui.tsx          # High-contrast UI components, badges, modals
│       └── lib/
│           ├── api.ts          # Typed REST API & WhatsApp link generator
│           ├── supabase.ts     # Supabase Realtime subscription hook
│           └── useVoice.ts     # Web Audio API 16kHz PCM streaming hook
└── mobile/                     # React Native (Expo) Installable Mobile App
    ├── app.json                # Permissions for background audio & mic
    ├── package.json
    ├── .env.example
    ├── plugins/
    │   └── withWakeWord.js     # Android config plugin for background actions
    └── src/
        ├── App.tsx             # Tab navigation between Voice & Khata
        ├── config.ts           # Mobile configuration
        ├── theme.ts            # High-contrast color tokens
        ├── services/
        │   ├── api.ts          # REST client + Supabase Realtime subscription
        │   ├── voiceSocket.ts  # 16kHz PCM audio streamer & WAV player
        │   └── wakeWordService.ts # Picovoice Porcupine + Android foreground service
        └── screens/
            ├── HomeVoiceScreen.tsx # Giant mic button, 'Hey Dukaan' switch, live draft card
            └── QuickLedgerScreen.tsx # Debtors summary, search, and recent entries
```

---

## 3. Quickstart & Setup Guide

### Option A: Run Full Stack with Docker Compose
Run the entire backend and PostgreSQL database with `pg_trgm` and seeds in one command:
```bash
cd dukaan-ai
docker compose up --build
```
- FastAPI Backend: `http://localhost:8000`
- Interactive API Docs (Swagger): `http://localhost:8000/docs`
- PostgreSQL Database: `localhost:5432`

---

### Option B: Step-by-Step Manual Setup

#### Step 1: Database Setup (Supabase or PostgreSQL)
1. In your [Supabase Dashboard](https://supabase.com) (or local PostgreSQL), open the **SQL Editor**.
2. Run the migration file:
   `supabase/migrations/001_init_schema.sql`
3. This creates:
   - Extensions: `pg_trgm` and `pgcrypto`
   - Tables: `shops`, `customers`, `transactions`
   - Realtime Publication: `transactions` and `customers` added to `supabase_realtime`
   - Seed data: Default shop (`00000000-0000-0000-0000-000000000001`), demo customers (including duplicate name for disambiguation test: *Ramesh Kumar* and *Ramesh Gowda*), and initial transactions.

#### Step 2: Backend Setup
1. Navigate to `backend`:
   ```bash
   cd backend
   cp .env.example .env
   ```
2. Configure `.env`:
   ```env
   DATABASE_URL=postgresql+asyncpg://postgres:postgrespassword@localhost:5432/dukaan
   DEFAULT_SHOP_ID=00000000-0000-0000-0000-000000000001
   GEMINI_API_KEY=your_gemini_api_key
   GEMINI_MODEL=gemini-2.5-flash
   SPEECH_PROVIDER=sarvam
   SARVAM_API_KEY=your_sarvam_key
   ```
3. Install dependencies and start:
   ```bash
   pip install -r requirements.txt
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

#### Step 3: Web Dashboard Setup
1. Navigate to `web`:
   ```bash
   cd ../web
   cp .env.example .env.local
   ```
2. Configure `.env.local`:
   ```env
   NEXT_PUBLIC_API_URL=http://localhost:8000
   # Optional: For instant real-time sync across devices:
   NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
   ```
3. Install packages and start development server:
   ```bash
   npm install
   npm run dev
   ```
4. Open [http://localhost:3000](http://localhost:3000) in your browser.

#### Step 4: Mobile App (React Native Expo)
1. Navigate to `mobile`:
   ```bash
   cd ../mobile
   cp .env.example .env
   ```
2. In `.env`, set `EXPO_PUBLIC_API_URL` to your computer's local Wi-Fi IP (e.g. `http://192.168.1.50:8000`):
   ```env
   EXPO_PUBLIC_API_URL=http://192.168.1.50:8000
   EXPO_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
   EXPO_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
   EXPO_PUBLIC_PICOVOICE_KEY=your_picovoice_access_key
   ```
3. (Optional for Wake-Word): Download your trained `hey_dukaan_android.ppn` file from [console.picovoice.ai](https://console.picovoice.ai) and place it in `mobile/assets/wake/hey_dukaan_android.ppn`.
4. Run on Android or iOS development build:
   ```bash
   npm install
   npx expo prebuild
   npx expo run:android
   ```

---

## 4. Regional Kirana Speech Vocabulary & Testing Prompts

| Intent | Kannada (ಕನ್ನಡ) | Hindi (हिन्दी) | English |
| :--- | :--- | :--- | :--- |
| **Record Credit (Udhar)** | *"Ramesh ge 340 rupayi udhar bardu"* | *"Ramesh ka 340 rupaye udhar likho"* | *"Add 340 rupees credit for Ramesh"* |
| **Record Payment (Jama)** | *"Suresh 200 rupayi kotta, jama maadi"* | *"Suresh ne 200 rupaye diye, jama karo"* | *"Suresh paid 200 rupees, record payment"* |
| **Disambiguation Query** | *"Ramesh ge 500 udhar"* *(AI: Which Ramesh? Bus stand or temple?)* | *"Ramesh ka 500 udhar"* *(AI: Kaunsa Ramesh?)* | *"500 credit for Ramesh"* |
| **Check Balance** | *"Anita balance eshtu?"* | *"Anita ka kitna baaki hai?"* | *"What is Anita's outstanding balance?"* |
| **Explicit Confirmation** | *"Houdu, confirm maadi"* | *"Haan, theek hai"* | *"Yes, confirm"* |
| **Cancel Draft** | *"Beda, cancel maadi"* | *"Nahi, cancel karo"* | *"No, cancel this"* |

---

## 5. REST & WebSocket Protocols

### WebSocket `/ws/voice?language=kn-IN`
- **Client to Server:**
  - Raw binary audio frames: 16 kHz mono PCM16
  - `{"type": "end_utterance"}`: triggers speech-to-text transcription and agent turn
  - `{"type": "text", "text": "..."}`: typed input without audio
  - `{"type": "reset"}`: resets conversation history
- **Server to Client:**
  - `{"type": "transcript", "text": "..."}`: echoes recognized speech
  - `{"type": "draft", "draft_id": "...", "customer": "...", "type": "credit", "amount": 340}`
  - `{"type": "confirmed", "draft_id": "...", "new_balance": 990}`
  - `{"type": "reply", "text": "..."}`: textual readback
  - `{"type": "audio", "format": "wav", "data": "<base64_wav>"}`: spoken audio response

---

## 6. License
MIT License. Built for Indian Kirana Shopkeepers.
