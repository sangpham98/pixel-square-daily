# Pixel Square Daily - Crypto Content Bot

Bot tự chọn coin hot, tạo post cho Binance Square, đăng tự động mỗi 6 giờ hoặc qua nút Telegram.

## Trạng thái

- ✅ Deployed v2.0 với modular architecture
- ✅ Webhook: `https://pixel.phsanghome.io.vn` (Cloudflare Named Tunnel)
- ✅ Timer: mỗi 6 giờ (`00/6:00:00`)
- ✅ Auto-post Binance Square
- ✅ Similarity gate chặn bài trùng
- ✅ Batch generation (3 draft cùng lúc)
- ✅ SQLite database cho history

## Cài đặt

```bash
cd pixel-square-daily
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

### .env bắt buộc

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
OPENAI_BASE_URL=http://localhost:20128/v1
OPENAI_API_KEY=not-needed
OPENAI_MODEL=...
BINANCE_AUTO_POST_SHORT=true
BINANCE_SQUARE_OPENAPI_KEY=...
WEBHOOK_PUBLIC_URL=https://pixel.phsanghome.io.vn
TELEGRAM_WEBHOOK_SECRET=...
```

## Cài đặt bằng Docker

### Build image

```bash
docker compose build
```

### Chạy webhook (nhận Telegram updates)

```bash
docker compose up -d webhook
```

Webhook chạy trên `http://localhost:8096`. Cần expose ra public URL (Cloudflare tunnel, nginx, etc.) để Telegram gửi webhook.

### Chạy one-shot bot (tạo 1 bài rồi thoát)

```bash
docker compose run --rm bot
```

### Chạy cả hai

```bash
docker compose up -d
```

- `webhook`: chạy nền, restart tự động
- `bot`: chạy one-shot rồi thoát

### Xem logs

```bash
docker compose logs -f webhook
docker compose logs -f bot
```

### Dừng

```bash
docker compose down
```

Lưu ý: `.env` không được copy vào image (`.dockerignore`). File `.env` phải tồn tại trong thư mục gốc khi chạy `docker compose`.

## Sử dụng

### Telegram Bot

Gõ `/menu` để mở menu với các nút:

| Nút | Chức năng |
|-----|-----------|
| 📝 Tạo post thường | Tạo 1 draft |
| 📦 Tạo batch 3 bài | Tạo 3 draft, lưu queue |
| 📤 Đăng bài tiếp theo | Đăng bài từ queue |
| 🔑 Set API key Binance | Cập nhật API key |
| 📊 Status | Kiểm tra trạng thái bot |
| 📈 Phân bố góc | Thống kê angle distribution |

### Test one-shot

```bash
RUN_ONCE=true ./.venv/bin/python pixel_square_daily.py
```

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

## Services

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
