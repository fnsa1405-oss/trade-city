"""Auditor: o portão. Só passa ordem com stops coerentes e todas as travas em dia."""
from __future__ import annotations

from dataclasses import dataclass

from .config import RiskConfig, weekend_multiplier
from .models import AssetClass, AuditResult, Side, TradePlan
from .mood import Mood


@dataclass(frozen=True)
class AuditContext:
    capital: float  # capital atual do trader (alocado + lucro realizado)
    peak_capital: float
    day_losses: int
    day_pnl: float
    has_open_position: bool
    buying_power: float
    kill_switch: bool = False
    market_open: bool = True
    unit_margin: float | None = None  # micro futuros: margem por contrato (no lugar do valor cheio)
    # carteira: capital total da mesa e risco já aberto (somado e no grupo do trader).
    # portfolio_capital = 0 desliga a checagem (backtest de um trader só)
    portfolio_capital: float = 0.0
    asset_class: AssetClass | None = None  # para o reforço das criptos no fim de semana
    portfolio_open_risk: float = 0.0
    group_open_risk: float = 0.0


class Auditor:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg

    def review(self, plan: TradePlan, ctx: AuditContext) -> AuditResult:
        cfg = self.cfg
        reasons: list[str] = []

        if ctx.kill_switch:
            reasons.append("botão de pânico acionado")
        if not ctx.market_open:
            reasons.append("mercado fechado")
        if ctx.has_open_position:
            reasons.append("já existe posição aberta neste ativo")

        if plan.side is Side.LONG:
            coherent = 0 < plan.stop_loss < plan.entry < plan.take_profit
        else:
            coherent = 0 < plan.take_profit < plan.entry < plan.stop_loss
        if not coherent:
            reasons.append("stop loss e stop gain incoerentes com a entrada")
        elif plan.reward_ratio < cfg.min_reward_ratio - 1e-9:
            reasons.append(f"alvo de {plan.reward_ratio:.2f}x o risco, mínimo {cfg.min_reward_ratio}x")

        max_risk = ctx.capital * cfg.risk_per_trade * Mood.CONFIANTE.size_multiplier
        max_risk *= weekend_multiplier(cfg, ctx.asset_class, plan.signal.ts)
        if ctx.unit_margin and plan.qty == 1:
            max_risk = max(max_risk, ctx.capital * cfg.max_contract_risk)  # 1 micro contrato
        if plan.risk_amount > max_risk * 1.01:  # folga para arredondamento de centavos
            reasons.append(f"risco de {plan.risk_amount:.2f} acima do máximo de {max_risk:.2f}")
        if plan.qty <= 0:
            reasons.append("quantidade inválida")
        exposure = plan.qty * ctx.unit_margin if ctx.unit_margin else plan.notional
        if exposure > ctx.buying_power + 1e-6:
            reasons.append("poder de compra insuficiente")
        if exposure > ctx.capital + 1e-6:
            reasons.append("posição maior que o capital do trader")

        if ctx.portfolio_capital > 0:
            total = ctx.portfolio_open_risk + plan.risk_amount
            if total > cfg.max_portfolio_risk * ctx.portfolio_capital * 1.01:
                reasons.append(
                    f"risco aberto da carteira iria a {total / ctx.portfolio_capital:.2%}, limite {cfg.max_portfolio_risk:.1%}"
                )
            group = ctx.group_open_risk + plan.risk_amount
            if group > cfg.max_cluster_risk * ctx.portfolio_capital * 1.01:
                reasons.append(
                    f"risco aberto do grupo correlacionado iria a {group / ctx.portfolio_capital:.2%}, limite {cfg.max_cluster_risk:.1%}"
                )

        if ctx.day_losses >= cfg.max_daily_losses:
            reasons.append(f"{ctx.day_losses} derrotas hoje: trader parado até amanhã")
        if ctx.day_pnl <= -cfg.max_daily_loss_pct * ctx.capital:
            reasons.append("perda máxima do dia atingida: trader parado até amanhã")
        if ctx.peak_capital > 0 and (ctx.peak_capital - ctx.capital) / ctx.peak_capital >= cfg.max_drawdown_pct:
            reasons.append("queda desde o pico passou do limite: trader volta para a escola")

        return AuditResult(approved=not reasons, reasons=reasons)
