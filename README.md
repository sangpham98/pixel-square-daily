# Pixel Square Daily - Crypto Content Bot

Bot tự chọn coin hot, tạo post cho Binance Square, đăng tự động mỗi 6 giờ hoặc qua nút Telegram.

## Trạng thái

- ✅ Deployed v2.0 với modular architecture
- ✅ Webhook: `https://pixel.phsanghome.io.vn` (Cloudflare Named Tunnel)
- ✅ Timer: mỗi 6 giờ (`00/6:00:00`)
- ✅ Auto-post Binance Square
- ✅ Similarity gate chặn bài trùng
- ✅ Batch generation (3 draft cùng lúc)
- ✅ Draft queue viewer + xóa draft từ Telegram
- ✅ SQLite database cho history

---

## Triển khai trên Ubuntu (Docker)

Hướng dẫn từng bước để deploy trên máy Ubuntu mới. Mục tiêu: copy-paste vài lệnh là chạy được.

### Yêu cầu

- Ubuntu 22.04+ (hoặc Linux bất kỳ có Docker)
- RAM tối thiểu 1GB
- Có domain hoặc tunnel để expose webhook (Telegram cần HTTPS)

### Bước 1: Cài Docker

```bash
# Cài Docker + Docker Compose plugin
sudo apt update
sudo apt install -y docker.io docker-compose-plugin

# Cho phép chạy docker không cần sudo
sudo usermod -aG docker $USER

# Đăng nhập lại shell để group có hiệu lực
newgrp docker

# Kiểm tra
docker --version
docker compose version
```

### Bước 2: Clone repo

```bash
git clone https://github.com/sangpham98/pixel-square-daily.git
cd pixel-square-daily
```

### Bước 3: Tạo file `.env`

```bash
cp .env.example .env
```

Chỉnh sửa file `.env` với các giá trị thực:

```bash
nano .env
```

**Các biến bắt buộc phải điền:**

```env
# === Telegram Bot ===
# Lấy từ @BotFather trên Telegram
TELEGRAM_BOT_TOKEN=123456:ABCdefGHIjklMNOpqrSTUvwxYZ
# Chat ID của bạn (gửi /start cho @userinfobot để lấy)
TELEGRAM_CHAT_ID=123456789

# === Telegram Webhook ===
# URL public để Telegram gửi updates (HTTPS bắt buộc)
WEBHOOK_PUBLIC_URL=https://your-domain.com
# Secret key tự đặt, dùng để verify request từ Telegram
TELEGRAM_WEBHOOK_SECRET=mat-khau-bat-ky

# === LLM Endpoint ===
# API OpenAI-compatible (Ollama, vLLM, LM Studio, OpenAI, etc.)
OPENAI_BASE_URL=http://localhost:20128/v1
OPENAI_API_KEY=not-needed
OPENAI_MODEL=qw/qwen3-coder-plus

# === Binance Square ===
# Lấy từ Binance Square OpenAPI
BINANCE_SQUARE_OPENAPI_KEY=your_key_here
BINANCE_AUTO_POST_SHORT=true
```

**Các biến tùy chọn (giá trị mặc định đã OK):**

```env
RUN_ONCE=false
LOG_LEVEL=INFO
SIMILARITY_MAX_REGENERATIONS=2
SIMILARITY_BLOCK_THRESHOLD=0.98
COIN_RECENT_EXCLUDE_HOURS=48
```

### Bước 4: Tạo Cloudflare Tunnel

Tunnel giúp expose webhook ra public URL (HTTPS) để Telegram gửi updates.

**Tạo tunnel trên Cloudflare Dashboard:**

1. Vào [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) > **Networks** > **Tunnels**
2. Nhấn **Create a tunnel** > chọn **Cloudflared** > đặt tên (ví dụ: `pixel-daily`)
3. Copy lệnh **Docker** hiện ra (dạng `docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token <TOKEN>`)
4. Trong phần **Public Hostname**, thêm hostname:
   - Hostname: domain bạn muốn (ví dụ: `pixel.yourdomain.com`)
   - Service: `http://localhost:8096`
5. Lưu lại

**Chạy tunnel container:**

```bash
# Thay <TOKEN> bằng token từ Cloudflare Dashboard
docker run -d --name cloudflared --network host --restart unless-stopped cloudflare/cloudflared:latest tunnel --no-autoupdate run --token <TOKEN>
```

> `--network host` để container truy cập được `localhost:8096` từ webhook container.

**Kiểm tra tunnel chạy:**

```bash
docker ps | grep cloudflared
# Phải hiện "Up" và STATUS không có "(unhealthy)"
```

Cập nhật `WEBHOOK_PUBLIC_URL` trong `.env` thành domain đã cấu hình:

```env
WEBHOOK_PUBLIC_URL=https://pixel.yourdomain.com
```

### Bước 5: Build và chạy app

```bash
# Build image (lần đầu mất 1-2 phút)
docker compose build

# Chạy cả webhook + bot
docker compose up -d

# Kiểm tra container đang chạy
docker compose ps
```

### Bước 6: Đăng ký webhook với Telegram

Sau khi có public URL, đăng ký webhook:

```bash
# Thay YOUR_BOT_TOKEN và YOUR_URL cho đúng
curl -X POST "https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://YOUR_URL/telegram/webhook",
    "secret_token": "mat-khau-bat-ky",
    "allowed_updates": ["message", "callback_query"]
  }'
```

Kết quả mong đợi: `{"ok":true,"result":true,"description":"Webhook was set"}`

**Kiểm tra webhook đã đăng ký:**

```bash
curl "https://api.telegram.org/botYOUR_BOT_TOKEN/getWebhookInfo"
```

### Bước 7: Kiểm tra mọi thứ hoạt động

```bash
# 1. Kiểm tra container
docker compose ps
# Cả webhook và bot phải hiện "Up"

# 2. Test health endpoint
curl http://localhost:8096/health
# Phải trả về {"ok": true, ...}

# 3. Gửi lệnh /menu trên Telegram bot
# Bot phải trả về menu với các nút

# 4. Nhấn "📝 Tạo post thường" để test tạo bài
```

---

## Quản lý container

```bash
# Xem logs realtime
docker compose logs -f webhook

# Restart webhook
docker compose restart webhook

# Dừng tất cả (webhook + bot)
docker compose down

# Rebuild sau khi update code
git pull
docker compose build
docker compose up -d

# Chạy one-shot bot (tạo 1 bài rồi thoát)
docker compose run --rm bot

# Xem logs tunnel
docker logs cloudflared

# Restart tunnel
docker restart cloudflared
```

---

## Sử dụng

### Telegram Bot

Gõ `/menu` để mở menu với các nút:

| Nút | Chức năng |
|-----|-----------|
| 📝 Tạo post thường | Tạo 1 draft |
| 📦 Tạo batch 3 bài | Tạo 3 draft, lưu queue |
| 📋 Xem draft queue | Xem các draft đã tạo và xóa draft theo số thứ tự |
| 📤 Đăng bài tiếp theo | Đăng bài từ queue |
| 🔑 Set API key Binance | Cập nhật API key |
| 📊 Status | Kiểm tra trạng thái bot |
| 📈 Phân bố góc | Thống kê angle distribution |

### Test one-shot (không dùng Docker)

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
RUN_ONCE=true python pixel_square_daily.py
```

---

## Architecture

```
pixel_square_daily.py     # Main orchestration (one-shot job)
webhook_app.py            # FastAPI webhook server
src/
  coin_selector.py        # Coin selection + scoring
  content_generator.py    # Prompt building + LLM calls
  draft_generator.py      # Draft generation + similarity check
  draft_queue.py          # Batch generation + queue persistence
  similarity_checker.py   # Content similarity detection
  binance_api.py          # Binance Square posting
  telegram_bot.py         # Telegram API + keyboard
  telegram_handlers.py    # Update dispatch + async workers
  history.py              # SQLite history management
  cache.py                # TTL-based API cache
  logger.py               # Centralized logging
  models.py               # Dataclasses
  utils.py                # Helpers
```

## Services (systemd, không dùng Docker)

```bash
# Webhook (nhận Telegram updates)
systemctl --user status pixel-spare-webhook.service

# Daily timer (mỗi 6 giờ)
systemctl --user status pixel-square-daily.timer

# Cloudflare tunnel
sudo systemctl status cloudflared.service
```

## Content Rules

- Post thường: 450-900 ký tự, mobile-friendly
- Hook: tối đa 120 ký tự, có góc trader cụ thể
- Tags bắt buộc: `#SYMBOL $SYMBOL #Crypto #BinanceSquare #DYOR`
- 6 angle xoay vòng deterministic: Market Watch, Narrative/Catalyst, Risk-first, Price Action, On-chain/TVL, Catalyst Watch
- Không bịa số liệu, không hứa lợi nhuận, không kêu gọi mua/bán

## Similarity Check

```env
SIMILARITY_MAX_REGENERATIONS=2
SIMILARITY_BLOCK_THRESHOLD=0.98
COIN_RECENT_EXCLUDE_HOURS=48
```

- So sánh với 5 bài gần nhất trong SQLite DB
- Nếu vượt ngưỡng: regenerate (tối đa 2 lần)
- Nếu vẫn vượt: không đăng, gửi thông báo

## Git / Secret Policy

Không commit các file sau (đã có trong `.gitignore`):

- `.env`, `user_square_keys.json`, `history.db`, `draft_queue.json`
- `source_cache.json`, `coingecko_cache.json`, `telegram_offset.txt`
- `pixel_generation.lock`, logs, tunnel output
