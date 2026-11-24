"""Pump.fun Paper Sprint bot v9: early-entry sniper shape with a rug filter.

Design (from a full post-mortem of v1-v8 on the kit's official grader and
a 900-combination sweep on the house research simulator):

- Every momentum/reversion shape bled: across 378 round trips the v7
  momentum bot paid 0.50 SOL of its 0.71 SOL loss to fees alone, and its
  +10%/-5% exits need a 33% win rate against the 26% the signal earns.
  Wider, stronger and earlier momentum variants all graded the same or
  worse (-0.61 .. -1.31 SOL), as did all five house baselines
  (-0.02 .. -9.45 SOL). The least-bad active shape on the window is the
  early-entry one: buy at a coin's birth, leave fast.
- Entry: within AGE_MAX_SLOTS of the create, once real reserves reach
  MIN_REAL_SOL (the 1% size cap then allows a real position), at most
  MAX_BUYERS distinct buyers so far, and never after the creator has
  sold. One buy per coin, min(cap, 0.1 SOL).
- Exits: take-profit +25%, stop-loss -8%, a hard 50-slot / 40-trade max
  hold, and an immediate exit the moment the creator sells (the classic
  rug tell). Sells are wide-open on slippage: in a dump a rejected sell
  costs more than a bad fill. Buys are wide-open too: at a coin's birth
  the price moves inside the 2-slot latency, and a tight buy slippage
  only converts fills into paid-for rejections.

Determinism: no clock, no environment reads, no unseeded randomness.
All state is insertion-ordered dicts and capped sets, so the two graded
executions agree byte for byte.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bot  # noqa: E402

LAMPORTS_PER_SOL = makefun_bot.LAMPORTS_PER_SOL

STAKE_LAMPORTS = LAMPORTS_PER_SOL // 10          # 0.1 SOL per coin
MIN_BUY_LAMPORTS = LAMPORTS_PER_SOL // 100       # skip dust fills under 0.01 SOL
MIN_REAL_SOL = 3 * LAMPORTS_PER_SOL // 10        # 0.3 SOL of real reserves before entering
MAX_REAL_SOL = 30 * LAMPORTS_PER_SOL             # skip coins already far along the curve
AGE_MAX_SLOTS = 12                               # only at a coin's birth
MAX_BUYERS = 3                                   # distinct buyers seen before we enter
TAKE_PROFIT = 1.25                               # +25% from entry price
STOP_LOSS = 0.92                                 # -8% from entry price
MAX_HOLD_SLOTS = 50
MAX_HOLD_TRADES = 40
BUY_SLIPPAGE_BPS = 10_000
SELL_SLIPPAGE_BPS = 10_000

# mint -> {"create_slot", "creator", "dev_sold", "buyers" (capped list),
#          "entered", "peak", "entry_slot", "held_trades"}
coins = {}


def _price(curve):
    if curve is None or curve.virtual_token_reserves <= 0:
        return None
    return curve.virtual_quote_reserves / curve.virtual_token_reserves


def _pending_side(state, mint, side):
    for p in state.pending.values():
        if p.order["mint"] == mint and p.order["side"] == side:
            return True
    return False


def on_batch(state, batch):
    orders = []
    caps = state.hello["caps"]
    tx = state.tx_fee_lamports()
    free = state.free_cash_lamports()
    max_orders = caps["max_orders_per_batch"]

    for e in batch["events"]:
        mint = e["mint"]
        kind = e["event"]
        if kind == "CreateEvent":
            if mint not in coins:
                coins[mint] = {
                    "create_slot": state.slot,
                    "creator": e.get("creator") or e.get("user"),
                    "dev_sold": False,
                    "buyers": [],
                    "entered": False,
                    "peak": None,
                    "entry_slot": -1,
                    "held_trades": 0,
                }
        elif kind == "TradeEvent":
            c = coins.get(mint)
            if c is None:
                coins[mint] = {
                    "create_slot": None,
                    "creator": e.get("creator"),
                    "dev_sold": False,
                    "buyers": [],
                    "entered": False,
                    "peak": None,
                    "entry_slot": -1,
                    "held_trades": 0,
                }
                c = coins[mint]
            user = e.get("user")
            if e.get("is_buy"):
                if user is not None and user not in c["buyers"] and len(c["buyers"]) <= MAX_BUYERS:
                    c["buyers"].append(user)
            else:
                if user is not None and c["creator"] is not None and user == c["creator"]:
                    c["dev_sold"] = True
            if mint in state.positions:
                c["held_trades"] += 1
        elif kind == "CompleteEvent":
            coins.pop(mint, None)

    # Exits first: TP / SL / max hold / creator sold.
    for mint, holding in list(state.positions.items()):
        if len(orders) >= max_orders:
            break
        if _pending_side(state, mint, "sell"):
            continue
        curve = state.curves.get(mint)
        price = _price(curve)
        if price is None or holding.token_amount <= 0:
            continue
        c = coins.get(mint)
        entry_price = holding.cost_lamports / holding.token_amount
        exit_now = price >= entry_price * TAKE_PROFIT or price <= entry_price * STOP_LOSS
        if c is not None:
            if c["dev_sold"]:
                exit_now = True
            if c["held_trades"] >= MAX_HOLD_TRADES:
                exit_now = True
            if c["entry_slot"] >= 0 and state.slot - c["entry_slot"] >= MAX_HOLD_SLOTS:
                exit_now = True
        if exit_now:
            orders.append(
                {
                    "side": "sell",
                    "mint": mint,
                    "token_amount": holding.token_amount,
                    "max_slippage_bps": SELL_SLIPPAGE_BPS,
                }
            )

    # Entries: newborn coins only, before the crowd and before any dev sell.
    slots = caps["max_open_positions"] - state.committed_position_count()
    if slots > 0:
        for mint, c in list(coins.items()):
            if slots <= 0 or len(orders) >= max_orders:
                break
            if c["entered"] or c["create_slot"] is None:
                continue
            if state.slot - c["create_slot"] > AGE_MAX_SLOTS:
                continue
            if c["dev_sold"]:
                continue
            if len(c["buyers"]) > MAX_BUYERS:
                continue
            if mint in state.positions or _pending_side(state, mint, "buy"):
                continue
            curve = state.curves.get(mint)
            if curve is None or curve.complete:
                continue
            rq = curve.real_quote_reserves
            if rq < MIN_REAL_SOL or rq > MAX_REAL_SOL:
                continue
            amount = min(state.max_buy_lamports(mint), STAKE_LAMPORTS)
            if amount < MIN_BUY_LAMPORTS:
                continue
            if free < amount + tx:
                continue
            orders.append(
                {
                    "side": "buy",
                    "mint": mint,
                    "quote_lamports": amount,
                    "max_slippage_bps": BUY_SLIPPAGE_BPS,
                }
            )
            c["entered"] = True
            c["entry_slot"] = state.slot
            free -= amount + tx
            slots -= 1
    return orders


if __name__ == "__main__":
    makefun_bot.run(on_batch)
