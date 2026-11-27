"""Configuração da mesa: travas de risco e o elenco de traders."""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import AssetClass
from .strategies import MeanReversion, OpeningRangeBreakout, Strategy, TrendFollower


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
            timeframe="1h",
            strategy=TrendFollower(fast=20, slow=50, breakout=20),
            data_lookback_days=10,
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
            persona="Chega antes do pregão e opera o Nasdaq 100 no rompimento da abertura.",
            symbol="QQQ",
            asset_class=AssetClass.EQUITY,
            timeframe="5min",
            strategy=OpeningRangeBreakout(range_minutes=30),
            data_lookback_days=5,
        ),
        TraderProfile(
            key="lena",
            name="Dona Lena",
            persona="Paciente: compra o S&P 500 quando todo mundo entra em pânico.",
            symbol="SPY",
            asset_class=AssetClass.EQUITY,
            timeframe="1d",
            strategy=MeanReversion(),
            data_lookback_days=420,
        ),
    ]
