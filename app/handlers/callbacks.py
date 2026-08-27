"""Inline-button callbacks. Every branch re-validates that the pending entry still
exists and belongs to the calling user before touching the sheet."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.formatting import format_parsed_transaction
from app.keyboards import category_picker_kb, confirm_transaction_kb, undo_kb
from app.models import Direction, Transaction
from app.pending_store import flip_direction, get, pop, update_category
from app.services import budget
from app.services.sheets import SheetsError, append_transaction, delete_last_transaction, get_all_transactions
from app.services.stats import compute_period_stats, month_key, start_of_this_month

logger = logging.getLogger(__name__)
router = Router(name="callbacks")


@router.callback_query(F.data.startswith("tx:confirm:"))
async def confirm_transaction(cq: CallbackQuery) -> None:
    pending_id = cq.data.split(":", 2)[2]
    entry = pop(pending_id, cq.from_user.id)
    if entry is None:
        await cq.answer("This entry has expired. Please send it again.", show_alert=True)
        return

    tx = Transaction(
        amount=entry.parsed.amount,
        currency=entry.parsed.currency,
        direction=entry.parsed.direction,
        category=entry.parsed.category,
        description=entry.parsed.description,
        merchant=entry.parsed.merchant,
        source=entry.source,
        raw_text=entry.raw_text,
    )

    try:
        await append_transaction(tx)
    except SheetsError as exc:
        logger.exception("Failed to save transaction to Sheets")
        await cq.message.edit_text(
            f"⚠️ Couldn't save this to Google Sheets: {exc}\n\nNothing was recorded — please try again."
        )
        await cq.answer()
        return
    except Exception:
        logger.exception("Unexpected error saving transaction")
        await cq.message.edit_text("⚠️ Something went wrong saving this. Nothing was recorded — please try again.")
        await cq.answer()
        return

    await cq.message.edit_text(f"✅ Saved!\n\n{format_parsed_transaction(entry.parsed)}", reply_markup=undo_kb(tx.id))
    await cq.answer("Saved")

    if tx.direction == Direction.EXPENSE:
        await _maybe_send_budget_alert(cq)


async def _maybe_send_budget_alert(cq: CallbackQuery) -> None:
    """Fires right after a save, so overspending is caught the moment it happens
    rather than buried in next week's digest. Best-effort: any failure here is
    logged and swallowed — the transaction is already safely saved either way."""
    try:
        target = await budget.get_effective_budget()
        if not target:
            return
        transactions = await get_all_transactions()
        stats = await compute_period_stats(transactions, since=start_of_this_month())
        alert = budget.check_threshold_alert(month_key(), stats.total_spent / target)
        if alert:
            await cq.message.answer(alert)
    except Exception:
        logger.exception("Budget alert check failed (non-fatal)")


@router.callback_query(F.data.startswith("tx:editcat:"))
async def show_category_picker(cq: CallbackQuery) -> None:
    pending_id = cq.data.split(":", 2)[2]
    entry = get(pending_id, cq.from_user.id)
    if entry is None:
        await cq.answer("This entry has expired. Please send it again.", show_alert=True)
        return
    kb = category_picker_kb(pending_id, current_category=entry.parsed.category)
    await cq.message.edit_reply_markup(reply_markup=kb)
    await cq.answer()


@router.callback_query(F.data.startswith("tx:setcat:"))
async def set_category(cq: CallbackQuery) -> None:
    _, _, pending_id, category = cq.data.split(":", 3)
    entry = update_category(pending_id, cq.from_user.id, category)
    if entry is None:
        await cq.answer("This entry has expired. Please send it again.", show_alert=True)
        return
    await cq.message.edit_text(format_parsed_transaction(entry.parsed), reply_markup=confirm_transaction_kb(pending_id))
    await cq.answer(f"Category set to {category}")


@router.callback_query(F.data.startswith("tx:flipdir:"))
async def flip_transaction_direction(cq: CallbackQuery) -> None:
    pending_id = cq.data.split(":", 2)[2]
    entry = flip_direction(pending_id, cq.from_user.id)
    if entry is None:
        await cq.answer("This entry has expired. Please send it again.", show_alert=True)
        return
    await cq.message.edit_text(format_parsed_transaction(entry.parsed), reply_markup=confirm_transaction_kb(pending_id))
    await cq.answer(f"Set to {entry.parsed.direction.value}")


@router.callback_query(F.data.startswith("tx:back:"))
async def back_to_confirm(cq: CallbackQuery) -> None:
    pending_id = cq.data.split(":", 2)[2]
    entry = get(pending_id, cq.from_user.id)
    if entry is None:
        await cq.answer("This entry has expired. Please send it again.", show_alert=True)
        return
    await cq.message.edit_text(format_parsed_transaction(entry.parsed), reply_markup=confirm_transaction_kb(pending_id))
    await cq.answer()


@router.callback_query(F.data.startswith("tx:discard:"))
async def discard_transaction(cq: CallbackQuery) -> None:
    pending_id = cq.data.split(":", 2)[2]
    pop(pending_id, cq.from_user.id)
    await cq.message.edit_text("🗑️ Discarded — nothing was saved.")
    await cq.answer()


@router.callback_query(F.data.startswith("tx:undo:"))
async def undo_transaction(cq: CallbackQuery) -> None:
    tx_id = cq.data.split(":", 2)[2]
    try:
        deleted = await delete_last_transaction(tx_id)
    except Exception:
        logger.exception("Failed to undo transaction")
        await cq.answer("Couldn't undo — please remove it manually from the sheet.", show_alert=True)
        return

    if deleted:
        await cq.message.edit_text("↩️ Undone — that entry was removed.")
        await cq.answer("Removed")
    else:
        await cq.answer(
            "Couldn't undo automatically (it's no longer the most recent entry). "
            "You can delete it manually from the sheet.",
            show_alert=True,
        )
