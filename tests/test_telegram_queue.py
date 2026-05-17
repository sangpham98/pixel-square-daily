from src.models import DraftQueueItem
from src.telegram_bot import draft_keyboard, draft_queue_keyboard
from src.telegram_handlers import build_draft_queue_message


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
