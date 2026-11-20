#!/bin/bash
# DukaanAI 1-Click Container Launcher (Linux/macOS/Cloud VPS)
set -e

echo "================================================="
echo " 🏪 DukaanAI - Docker Deployment & Phone Access "
echo "================================================="

cd "$(dirname "$0")"

COMPOSE="docker compose"
if ! command -v docker &> /dev/null; then
    COMPOSE="docker-compose"
fi

echo "1. Building and launching DukaanAI containers..."
$COMPOSE up --build -d

echo ""
echo "2. Container status:"
$COMPOSE ps

LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "YOUR-SERVER-IP")

echo ""
echo "================================================="
echo " 🎉 DukaanAI is Running in Docker!"
echo "================================================="
echo "💻 Local Browser:     http://localhost (or http://localhost:4000)"
echo "📱 Phone Browser/PWA: http://${LAN_IP} (on same Wi-Fi / LAN)"
echo "⚙️ Backend API:       http://${LAN_IP}:8000"
echo "🐘 PostgreSQL DB:     localhost:5432"
echo ""
echo "To view real-time logs: $COMPOSE logs -f"
echo "To stop containers:     $COMPOSE down"
echo "================================================="
