#!/usr/bin/env bash
# Download maniger bot - one-command installer for an Ubuntu server (Oracle Cloud free VM).
#   curl -fsSL https://raw.githubusercontent.com/kbs7s/download-maiger/main/bot/install.sh | bash
set -euo pipefail

DIR="$HOME/download-maiger"
say() { printf '\n\033[1;36m%s\033[0m\n' "$*"; }
ask() { local v; read -r -p "$1: " v </dev/tty; printf '%s' "$v"; }

say "1/4  Installing Docker (هذا ياخذ دقيقتين)…"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER" || true
command -v git >/dev/null 2>&1 || { sudo apt-get update -y && sudo apt-get install -y git; }

say "2/4  Getting the bot code…"
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull --ff-only; else git clone https://github.com/kbs7s/download-maiger.git "$DIR"; fi
cd "$DIR/bot"
mkdir -p data

if [ ! -f .env ]; then
  say "3/4  Settings (الإعدادات)"
  echo "Bot token from @BotFather (توكن البوت من BotFather):"
  TOKEN=$(ask "BOT_TOKEN")
  echo "From my.telegram.org -> API development tools:"
  API_ID=$(ask "api_id (أرقام)")
  API_HASH=$(ask "api_hash")
  cat > .env <<ENV
BOT_TOKEN=$TOKEN
TELEGRAM_API_ID=$API_ID
TELEGRAM_API_HASH=$API_HASH
ADMIN_IDS=
ENV
  chmod 600 .env
else
  say "3/4  Keeping existing settings (.env)"
fi

say "4/4  Starting the bot…"
sudo docker compose up -d --build

say "✅ Done! تم. افتح البوت بالتلكرام ودز /start — أول واحد يدز /start يصير مدير البوت."
echo "Logs (السجل):     cd $DIR/bot && sudo docker compose logs -f bot"
echo "Update (تحديث):   curl -fsSL https://raw.githubusercontent.com/kbs7s/download-maiger/main/bot/install.sh | bash"
