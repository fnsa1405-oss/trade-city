"""Placar do dia, em texto, para o terminal (o painel visual vem depois)."""
from __future__ import annotations

from .desk import Desk


def render(desk: Desk) -> str:
    cfg = desk.risk
    lines = [f"Trade City ({'paper' if desk.broker.paper else 'REAL'})" + ("  [PÂNICO: mesa travada]" if desk.ledger.kill_switch else "")]
    for trader in desk.traders:
        stats = desk.stats(trader)
        mood = desk.mood(stats)
        open_trade = desk.ledger.open_trade_for(trader.key)
        apprentices = int(max(stats.realized_pnl, 0) // cfg.profit_milestone)
        lines += [
            "",
            f"{trader.name}  ({trader.symbol}, {trader.strategy.name})",
            f"  humor: {mood.label}",
            f"  hoje: {stats.day_wins}/{cfg.daily_win_goal} vitórias, {stats.day_losses}/{cfg.max_daily_losses} derrotas, {stats.day_pnl:+.2f}",
            f"  capital: {stats.capital:.2f} (pico {stats.peak_capital:.2f}), lucro realizado {stats.realized_pnl:+.2f}",
            f"  aprendizes liberados: {apprentices} (1 a cada {cfg.profit_milestone:.0f} de lucro)",
            f"  posição: {open_trade.qty:g} a {open_trade.entry_price:.2f}, stop {open_trade.stop_loss:.2f}, alvo {open_trade.take_profit:.2f}"
            if open_trade
            else "  posição: nenhuma",
        ]
    return "\n".join(lines)
