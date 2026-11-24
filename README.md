[![Pump.fun Paper Sprint](https://make.fun/badge/u-boothlord-pump-fun-paper-sprint-any-bot-can-f83c389b.svg)](https://make.fun)
[![Rank](https://make.fun/badge/u-boothlord-pump-fun-paper-sprint-any-bot-can-f83c389b/Revaaa28/makefun-pump-sprint-boothlord/rank.svg)](https://make.fun)
[![Reward](https://make.fun/badge/u-boothlord-pump-fun-paper-sprint-any-bot-can-f83c389b/Revaaa28/makefun-pump-sprint-boothlord/reward.svg)](https://make.fun)

# Pump Sprint Boothlord

A paper-trading bot for make.fun's **Pump.fun Paper Sprint: Any Bot Can Win**
competition. The bot trades pump.fun bonding curves on a 6-hour window,
ranked by net PnL. Paper trading only — no real funds ever move.

## Strategy

Early-entry sniping with a rug filter — the least-bad active shape found
in a full post-mortem of this competition's dev window:

- **Entry:** only at a coin's birth — within 12 slots of its create,
  once real reserves reach 0.3 SOL (so the 1% size cap allows a real
  position), at most 3 distinct buyers so far, and never after the
  creator has sold. One buy per coin, min(cap, 0.1 SOL).
- **Exits:** take-profit +25%, stop-loss −8%, a hard 50-slot / 40-trade
  max hold, and an immediate exit the moment the creator sells.
- **Slippage wide open on both sides:** at a coin's birth the price
  moves inside the 2-slot latency, and a tight slippage only converts
  fills into paid-for rejections; in a dump, a rejected sell costs more
  than a bad fill.

## How this design was chosen

Every systematic shape was measured on the kit's own official grader
(`grade-local`) over the frozen dev window: the earlier momentum design
(−0.71 SOL), four momentum variants (−0.61 … −1.31), all five house
baselines (−0.02 … −9.45), and a 912-combination sweep on the house
research simulator, in which every combination that traded lost and the
only non-losing rows traded nothing at all. This bot graded **−0.597 SOL**
on the same official grader, with the smallest drawdown (0.063) of any
active bot we built. The dev window is a structurally hard market at
these fee levels (125 bps per side plus transaction fees, 2-slot
latency); the number is reported as measured, not dressed up. The final
score comes from a fresh live 6-hour window collected after the entry
deadline.

## Layout

- `main.py` — the bot (Python 3.13, standard library only).
- `vendor/makefun_bot.py` — the kit's `agent-fun/replay/v2` Python shim,
  vendored as the SDK instructs.

## Run it

```sh
PYTHONHASHSEED=0 python3 -P -s main.py
```

The bot speaks `agent-fun/replay/v2` on stdin/stdout: it reads `hello`,
one `batch` per slot, and `done`, and writes exactly one reply per
batch. It is fully deterministic — no clock, no environment reads, no
unseeded randomness — so the grader's two executions agree byte for
byte.

## Grade it (dev window)

From the unpacked kit directory:

```sh
node cli/makefun.mjs grade-local --kit . --bot /path/to/this/repo --driver process
```

## License

MIT. See [LICENSE](LICENSE).
