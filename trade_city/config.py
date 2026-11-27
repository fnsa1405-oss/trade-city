"""Configuração da mesa: travas de risco e o elenco de traders."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .models import AssetClass
from .strategies import OpeningRangeDayTrade, Strategy, TrendFollower, TurtleBreakout


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade: float = 0.005  # 0,5% do capital do trader por operação
    atr_period: int = 14
    atr_stop_multiple: float = 2.0  # stop a 2 ATR da entrada
    reward_ratio: float = 2.0  # alvo = 2x o risco
    min_reward_ratio: float = 1.5  # o Auditor recusa alvo menor que 1,5x o risco
    max_daily_losses: int = 5
    max_daily_loss_pct: float = 0.03
    max_drawdown_pct: float = 0.10  # queda desde o pico que manda o trader de volta à escola
    daily_win_goal: int = 10
    profit_milestone: float = 100.0  # a cada marco de lucro (USD), um novo aprendiz é liberado
    timezone: str = "America/Sao_Paulo"  # define o "dia" do placar


@dataclass(frozen=True)
class TraderProfile:
    key: str
    name: str
    persona: str
    symbol: str
    asset_class: AssetClass
    timeframe: str  # "1h", "5min", "1d"
    strategy: Strategy = field(compare=False)
    capital: float = 10_000.0  # capital (USD) alocado ao trader na conta
    data_lookback_days: int = 30
    approved: bool = False  # só traders aprovados na escola operam na mesa
    atr_stop_multiple: float | None = None  # ajuste de stop aprovado na escola (None = padrão)
    reward_ratio: float | None = None  # ajuste de alvo aprovado na escola (None = padrão)
    day_trade: bool = False  # True = a escola testa só day trade (gatilho de 5 ou 1 min)


def risk_for(trader: TraderProfile, base: RiskConfig) -> RiskConfig:
    """Travas da mesa com o ajuste de stop/alvo que o trader aprovou na escola."""
    changes = {}
    if trader.atr_stop_multiple is not None:
        changes["atr_stop_multiple"] = trader.atr_stop_multiple
    if trader.reward_ratio is not None:
        changes["reward_ratio"] = trader.reward_ratio
    return replace(base, **changes) if changes else base


def default_traders() -> list[TraderProfile]:
    return [
        TraderProfile(
            key="bia",
            name="Bia Satoshi",
            persona="Não dorme: vigia o Bitcoin 24h e só entra a favor da tendência.",
            symbol="BTC/USD",
            asset_class=AssetClass.CRYPTO,
            timeframe="1h",
            strategy=TrendFollower(fast=20, slow=50, breakout=20),
            data_lookback_days=10,
        ),
        TraderProfile(
            key="edu",
            name="Edu Éter",
            persona="Engenheiro da turma: opera Ethereum e confere tudo duas vezes.",
            symbol="ETH/USD",
            asset_class=AssetClass.CRYPTO,
            timeframe="1h",
            strategy=TrendFollower(fast=20, slow=50, breakout=20),
            data_lookback_days=10,
        ),
        TraderProfile(
            key="sol",
            name="Sol Ventura",
            persona="Rápida e ousada: vive no ritmo da Solana.",
            symbol="SOL/USD",
            asset_class=AssetClass.CRYPTO,
            timeframe="1h",
            strategy=TrendFollower(fast=20, slow=50, breakout=20),
            data_lookback_days=10,
        ),
        TraderProfile(
            key="rui",
            name="Rui Xis",
            persona="Calmo e paciente: espera o XRP sair do lugar.",
            symbol="XRP/USD",
            asset_class=AssetClass.CRYPTO,
            timeframe="4h",
            strategy=TrendFollower(fast=10, slow=30, breakout=10),
            data_lookback_days=15,
            approved=True,  # escola 27/11/2026: prova com fator de lucro 1,51
            atr_stop_multiple=1.5,
            reward_ratio=3.0,
        ),
        TraderProfile(
            key="dora",
            name="Dora Doge",
            persona="A mais animada do escritório: opera Dogecoin com stop sempre apertado.",
            symbol="DOGE/USD",
            asset_class=AssetClass.CRYPTO,
            timeframe="1h",
            strategy=TrendFollower(fast=20, slow=50, breakout=20),
            data_lookback_days=10,
        ),
        TraderProfile(
            key="teo",
            name="Teo Chip",
            persona="Disciplinado como os Turtles: opera o Nasdaq 100 no rompimento de 20 dias.",
            symbol="QQQ",
            asset_class=AssetClass.EQUITY,
            timeframe="1d",
            strategy=TurtleBreakout(entry=20, exit=10),
            data_lookback_days=60,
            approved=True,  # escola 27/11/2026: prova com fator de lucro 1,42
            atr_stop_multiple=2.0,
            reward_ratio=50.0,  # sem alvo: a saída é a mínima de 10 dias
            day_trade=True,  # 27/11/2026: passa para day trade quando uma estratégia for aprovada
        ),
        TraderProfile(
            key="lena",
            name="Dona Lena",
            persona="Paciente e experiente: segue o S&P 500 com o sistema 1 dos Turtles.",
            symbol="SPY",
            asset_class=AssetClass.EQUITY,
            timeframe="1d",
            strategy=TurtleBreakout(entry=20, exit=10),
            data_lookback_days=60,
            approved=True,  # escola 27/11/2026: prova com fator de lucro 1,59
            atr_stop_multiple=2.0,
            reward_ratio=50.0,  # sem alvo: a saída é a mínima de 10 dias
            day_trade=True,
        ),
        TraderProfile(
            key="davi",
            name="Davi Dow",
            persona="Veterano do pregão: faz day trade no Dow Jones (DIA) lendo topos e fundos.",
            symbol="DIA",
            asset_class=AssetClass.EQUITY,
            timeframe="5min",
            strategy=OpeningRangeDayTrade(5),
            data_lookback_days=25,
            day_trade=True,
        ),
        TraderProfile(
            key="ivo",
            name="Ivo Miúdo",
            persona="Elétrico: faz day trade nas pequenas empresas americanas (Russell 2000, IWM).",
            symbol="IWM",
            asset_class=AssetClass.EQUITY,
            timeframe="5min",
            strategy=OpeningRangeDayTrade(5),
            data_lookback_days=25,
            day_trade=True,
        ),
    ]
