from src.models import DraftQueueItem
from src.telegram_bot import draft_keyboard, draft_queue_keyboard
from src.telegram_handlers import build_draft_queue_message, handle_update


def _item(symbol: str = "BTC", name: str = "Bitcoin") -> DraftQueueItem:
    return DraftQueueItem(
        coin_symbol=symbol,
        coin_name=name,
        coin_reason="test",
        draft="draft",
        short_post=f"Short post for {name}",
        created_at="2026-05-17 12:00:00",
        angle="Market Watch",
    )


def test_draft_keyboard_contains_queue_button():
    keyboard = draft_keyboard()
    callbacks = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "pixel_draft_queue" in callbacks


def test_draft_queue_keyboard_contains_delete_buttons():
    keyboard = draft_queue_keyboard([_item("BTC"), _item("ETH", "Ethereum")])
    callbacks = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert callbacks == ["pixel_delete_draft:1", "pixel_delete_draft:2", "pixel_draft_queue"]


def test_build_draft_queue_message_formats_items():
    message = build_draft_queue_message([_item("BTC", "Bitcoin")])
    assert "Draft queue (1 bài)" in message
    assert "1. Bitcoin ($BTC) | Market Watch | 2026-05-17 12:00:00" in message
    assert "Short post for Bitcoin" in message


def test_build_draft_queue_message_empty():
    assert build_draft_queue_message([]) == "📋 Draft queue trống"


def test_start_command_sends_inline_menu(monkeypatch):
    sent: list[tuple[int, str, dict]] = []

    def fake_send(chat_id, text, **kwargs):
        sent.append((chat_id, text, kwargs))

    monkeypatch.setattr("src.telegram_handlers.telegram_send_best_effort", fake_send)

    handle_update({
        "message": {
            "chat": {"id": 123},
            "from": {"id": 456},
            "text": "/start",
        }
    })

    assert sent
    assert sent[0][0] == 123
    assert "reply_markup" in sent[0][2]
    callbacks = [button["callback_data"] for row in sent[0][2]["reply_markup"]["inline_keyboard"] for button in row]
    assert "pixel_generate_short" in callbacks
