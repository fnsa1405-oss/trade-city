"""Estado da mesa em JSON, para o app do celular (pasta app/).

O app lê este arquivo direto do branch de dados da mesa (mesa-dados ou mesa-daytrade),
então ele precisa ser pequeno, estável e sem nada secreto.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .config import default_traders
from .desk import Desk

VERSAO = 1


def _num(x: float | None, casas: int = 2) -> float | None:
    return None if x is None else round(float(x), casas)


def _preco(x: float | None) -> float | None:
    # XRP e DOGE valem centavos: guarda mais casas para preços pequenos
    if x is None:
        return None
    return round(float(x), 6 if abs(x) < 10 else 2)


def build_state(desk: Desk, mesa: str, now: datetime | None = None, n_ops: int = 30, n_eventos: int = 40, n_dias: int = 30) -> dict:
    now = now or datetime.now(timezone.utc)
    cfg = desk.risk
    ativos = {t.key for t in desk.traders}
    traders = []
    for t in desk.traders:
        stats = desk.stats(t)
        mood = desk.mood(stats)
        pos = desk.ledger.open_trade_for(t.key)
        traders.append(
            {
                "key": t.key,
                "nome": t.name,
                "ativo": t.symbol,
                "classe": t.asset_class.value,
                "tempo": t.timeframe,
                "estrategia": t.strategy.name,
                "persona": t.persona,
                "humor": mood.label,
                "capital_inicial": _num(t.capital),
                "capital": _num(stats.capital),
                "pico": _num(stats.peak_capital),
                "lucro": _num(stats.realized_pnl),
                "hoje": {
                    "vitorias": stats.day_wins,
                    "derrotas": stats.day_losses,
                    "resultado": _num(stats.day_pnl),
                    "meta_vitorias": cfg.daily_win_goal,
                    "max_derrotas": cfg.max_daily_losses,
                },
                "ultimo_candle": desk.ledger.flag(f"last_bar:{t.key}") or None,
                "ultimos": ["v" if w else "d" for w in stats.recent_outcomes],
                "posicao": None
                if pos is None
                else {
                    "lado": pos.side.value,
                    "qtd": pos.qty,
                    "entrada": _preco(pos.entry_price),
                    "stop": _preco(pos.stop_loss),
                    "alvo": _preco(pos.take_profit),
                    "desde": pos.opened_at.astimezone(timezone.utc).isoformat(),
                },
            }
        )

    conn = desk.ledger.conn
    keys = sorted(ativos)
    marks = ",".join("?" * len(keys)) or "''"
    ops = [
        {
            "trader": r[0],
            "ativo": r[1],
            "lado": r[2],
            "qtd": r[3],
            "entrada": _preco(r[4]),
            "saida": _preco(r[5]),
            "resultado": _num(r[6]),
            "motivo": r[7],
            "aberta_em": r[8],
            "fechada_em": r[9],
        }
        for r in conn.execute(
            "SELECT trader, symbol, side, qty, entry_price, exit_price, pnl, exit_reason, opened_at, closed_at"
            f" FROM trades WHERE trader IN ({marks}) ORDER BY id DESC LIMIT ?",
            (*keys, n_ops),
        )
    ]
    eventos = [
        {"ts": r[0], "trader": r[1], "ativo": r[2], "etapa": r[3], "ok": bool(r[4]), "detalhe": r[5]}
        for r in conn.execute(
            f"SELECT ts, trader, symbol, stage, approved, detail FROM decisions WHERE trader IN ({marks})"
            " ORDER BY id DESC LIMIT ?",
            (*keys, n_eventos),
        )
    ]
    total = conn.execute(
        f"SELECT COUNT(*), COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0), COALESCE(SUM(pnl), 0)"
        f" FROM trades WHERE closed_at IS NOT NULL AND trader IN ({marks})",
        keys,
    ).fetchone()

    # resultado de cada dia (fuso do placar), para o gráfico "dia a dia" do app
    from zoneinfo import ZoneInfo

    fuso = ZoneInfo(cfg.timezone)
    por_dia: dict[str, dict] = {}
    for trader, pnl, closed in conn.execute(
        f"SELECT trader, pnl, closed_at FROM trades WHERE closed_at IS NOT NULL AND trader IN ({marks})", keys
    ):
        dia = datetime.fromisoformat(closed).astimezone(fuso).date().isoformat()
        d = por_dia.setdefault(dia, {"data": dia, "resultado": 0.0, "operacoes": 0, "vitorias": 0})
        d["resultado"] += pnl or 0.0
        d["operacoes"] += 1
        d["vitorias"] += 1 if (pnl or 0) > 0 else 0
    dias = [dict(d, resultado=_num(d["resultado"])) for _, d in sorted(por_dia.items())][-n_dias:]

    elenco = [
        {
            "key": t.key,
            "nome": t.name,
            "ativo": t.symbol,
            "persona": t.persona,
            "situacao": "na mesa" if t.key in ativos else "na escola",
        }
        for t in default_traders()
    ]
    return {
        "versao": VERSAO,
        "mesa": mesa,
        "gerado_em": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "modo": "simulado" if desk.broker.paper else "real",
        "travada": desk.ledger.kill_switch,
        "travas": {
            "risco_por_operacao": cfg.risk_per_trade,
            "max_derrotas_dia": cfg.max_daily_losses,
            "meta_vitorias_dia": cfg.daily_win_goal,
        },
        "resumo": {
            "operacoes": total[0],
            "vitorias": total[1],
            "resultado": _num(total[2]),
        },
        "traders": traders,
        "dias": dias,
        "operacoes": ops,
        "eventos": eventos,
        "elenco": elenco,
    }


def write_state(desk: Desk, mesa: str, path: str) -> dict:
    state = build_state(desk, mesa)
    with open(path, "w") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1)
    return state
