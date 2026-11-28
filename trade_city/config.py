"""Configuração da mesa: travas de risco e o elenco de traders."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .models import AssetClass
from .strategies import DonchianEnsemble, OpeningRangeDayTrade, Strategy, TrendFollower, TurtleBreakout


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
            strategy=DonchianEnsemble(),
            data_lookback_days=100,  # 561 candles de 4h para os canais de até 360 candles
            approved=True,  # escola 27/11/2026 (2ª rodada): Donchian em conjunto, prova com fator de lucro 2,09
            atr_stop_multiple=2.0,
            reward_ratio=50.0,  # sem alvo: sai quando a maioria dos canais sai
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
            persona="Disciplinado e paciente: compra o Nasdaq 100 quando rompe a máxima de 20 dias.",
            symbol="QQQ",
            asset_class=AssetClass.EQUITY,
            timeframe="1d",
            strategy=TurtleBreakout(20, 10),
            data_lookback_days=90,
            # escola em swing (28/11/2026, 10 anos de diário): Turtle sistema 1, prova com fator de lucro 1,42.
            # No day trade (2 anos, 228 combinações) nada passou na prova.
            approved=True,
            atr_stop_multiple=2.0,
            reward_ratio=50.0,  # sem alvo: sai na perda da mínima de 10 dias
        ),
        TraderProfile(
            key="lena",
            name="Dona Lena",
            persona="Paciente e experiente: compra o S&P 500 quando rompe a máxima de 20 dias.",
            symbol="SPY",
            asset_class=AssetClass.EQUITY,
            timeframe="1d",
            strategy=TurtleBreakout(20, 10),
            data_lookback_days=90,
            # escola em swing (28/11/2026, 10 anos de diário): Turtle sistema 1, prova com fator de lucro 1,59.
            # No day trade (2 anos, 228 combinações) nada passou na prova.
            approved=True,
            atr_stop_multiple=2.0,
            reward_ratio=50.0,  # sem alvo: sai na perda da mínima de 10 dias
        ),
        TraderProfile(
            key="davi",
            name="Davi Dow",
            persona="Veterano do pregão: compra o Dow Jones (DIA) quando rompe a máxima de 20 dias.",
            symbol="DIA",
            asset_class=AssetClass.EQUITY,
            timeframe="1d",
            strategy=TurtleBreakout(20, 10),
            data_lookback_days=90,
            # escola em swing (28/11/2026, 10 anos de diário): Turtle sistema 1, prova com fator de lucro 2,21.
            # No day trade (2 anos, 228 combinações) nada passou na prova.
            approved=True,
            atr_stop_multiple=2.0,
            reward_ratio=50.0,  # sem alvo: sai na perda da mínima de 10 dias
        ),
        TraderProfile(
            key="ivo",
            name="Ivo Miúdo",
            persona="Elétrico: faz day trade nas pequenas empresas americanas (Russell 2000, IWM).",
            symbol="IWM",
            asset_class=AssetClass.EQUITY,
            timeframe="1min",
            strategy=OpeningRangeDayTrade(5),
            data_lookback_days=5,
            reward_ratio=2.0,  # melhor no treino da escola de 2 anos; reprovado na prova
            day_trade=True,
        ),
    ]
