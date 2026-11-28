"""Configuração da mesa: travas de risco e o elenco de traders."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .models import AssetClass
from .strategies import DonchianEnsemble, MovingAverageTrend, OpeningRangeDayTrade, Strategy, TimeSeriesMomentum, TrendFollower, TurtleBreakout
from .strategies.orderflow import DeltaBreakout


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade: float = 0.005  # 0,5% do capital do trader por operação
    # micro futuros: se nem 1 contrato cabe no risco normal, aceita 1 contrato desde que o
    # risco dele não passe disto (senão a operação é recusada)
    max_contract_risk: float = 0.01
    atr_period: int = 14
    atr_stop_multiple: float = 2.0  # stop a 2 ATR da entrada
    reward_ratio: float = 2.0  # alvo = 2x o risco
    min_reward_ratio: float = 1.5  # o Auditor recusa alvo menor que 1,5x o risco
    max_daily_losses: int = 5
    max_daily_loss_pct: float = 0.03
    max_drawdown_pct: float = 0.10  # queda desde o pico que manda o trader de volta à escola
    # carteira (carteira.py): risco aberto somado de todos os traders e de cada grupo
    # correlacionado, em fração do capital total da mesa
    max_portfolio_risk: float = 0.03
    max_cluster_risk: float = 0.015
    # fim de semana (sábado e domingo em Nova York, bolsa fechada): multiplica o risco das
    # criptos, que são as únicas que operam. Calibrado em carteira.py (1 = desligado)
    weekend_crypto_boost: float = 1.5  # carteira 28/11/2026: 1,5x melhorou treino e prova
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
    # carteira (carteira.py): peso de risco por paridade de risco (multiplica o risco por
    # operação) e grupo de ativos correlacionados (limite de risco aberto por grupo)
    risk_weight: float = 1.0
    group: str = ""
    micro: bool = False  # True = opera o microcontrato futuro do índice (futures.MICROS), não o ETF


def weekend_multiplier(cfg: RiskConfig, asset_class: AssetClass, ts) -> float:
    """Multiplicador de risco das criptos no fim de semana (bolsa fechada)."""
    if cfg.weekend_crypto_boost == 1.0 or asset_class is not AssetClass.CRYPTO or ts is None:
        return 1.0
    from zoneinfo import ZoneInfo

    return cfg.weekend_crypto_boost if ts.astimezone(ZoneInfo("America/New_York")).weekday() >= 5 else 1.0


def risk_for(trader: TraderProfile, base: RiskConfig) -> RiskConfig:
    """Travas da mesa com o ajuste de stop/alvo que o trader aprovou na escola."""
    changes = {}
    if trader.risk_weight != 1.0:
        changes["risk_per_trade"] = base.risk_per_trade * trader.risk_weight
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
            persona="Não dorme: vigia o Bitcoin 24h e só compra o rompimento quando os compradores agridem.",
            symbol="BTC/USD",
            asset_class=AssetClass.CRYPTO,
            timeframe="4h",
            strategy=DeltaBreakout(55),
            data_lookback_days=100,
            # escola de fluxo 28/11/2026 (Binance desde 2017): rompimento de 55 com agressão de
            # compra, 4h; treino FL 4,71 (31 op.), prova FL 1,25 (26 op., +2,3%)
            approved=True,
            risk_weight=1.4,  # carteira 28/11/2026: paridade de risco (ver carteira.py)
            group="bia",
            atr_stop_multiple=2.0,
            reward_ratio=50.0,  # sem alvo: sai na perda da mínima de 27 candles
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
            persona="Rápida e ousada: compra a Solana quando o retorno de 28 dias vira positivo.",
            symbol="SOL/USD",
            asset_class=AssetClass.CRYPTO,
            timeframe="1d",
            strategy=TimeSeriesMomentum(28),
            data_lookback_days=90,
            # escola 28/11/2026 (~5 anos de histórico): momento de série temporal 28, prova com fator de lucro 1,62
            approved=True,
            risk_weight=1.4,  # carteira 28/11/2026: paridade de risco (ver carteira.py)
            group="sol",
            atr_stop_multiple=2.0,
            reward_ratio=50.0,  # sem alvo: sai quando o retorno de 28 dias fica negativo
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
            approved=True,
            risk_weight=1.4,  # carteira 28/11/2026: paridade de risco (ver carteira.py)
            group="rui",  # escola 27/11/2026 (2ª rodada): Donchian em conjunto, prova com fator de lucro 2,09
            atr_stop_multiple=2.0,
            reward_ratio=50.0,  # sem alvo: sai quando a maioria dos canais sai
        ),
        TraderProfile(
            key="dora",
            name="Dora Doge",
            persona="A mais animada do escritório: compra o Dogecoin quando ele rompe com agressão de compra.",
            symbol="DOGE/USD",
            asset_class=AssetClass.CRYPTO,
            timeframe="4h",
            strategy=DeltaBreakout(20),
            data_lookback_days=100,
            # escola de fluxo 28/11/2026 (Binance desde 2019): rompimento de 20 com agressão, 4h;
            # treino FL 5,19 (37 op.), prova FL 1,82 (18 op., +4,2%). Trocou o Donchian em
            # conjunto (prova FL 1,17), que ficou atrás no treino e na prova.
            approved=True,
            risk_weight=1.4,  # carteira 28/11/2026: paridade de risco (ver carteira.py)
            group="dora",
            atr_stop_multiple=2.0,
            reward_ratio=50.0,  # sem alvo: sai na perda da mínima de 10 candles
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
            risk_weight=0.47,  # carteira 28/11/2026: paridade de risco (ver carteira.py)
            group="indices",
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
            risk_weight=0.47,  # carteira 28/11/2026: paridade de risco (ver carteira.py)
            group="indices",
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
            risk_weight=0.47,  # carteira 28/11/2026: paridade de risco (ver carteira.py)
            group="indices",
            atr_stop_multiple=2.0,
            reward_ratio=50.0,  # sem alvo: sai na perda da mínima de 10 dias
        ),
        TraderProfile(
            key="mia",
            name="Mia Média",
            persona="Day trade no Dow com o microcontrato MYM: só opera a favor das médias e entra no candle de força.",
            symbol="DIA",
            asset_class=AssetClass.EQUITY,
            timeframe="1min",
            strategy=MovingAverageTrend("forca", (60, 15, 5)),
            data_lookback_days=50,  # a MMA200 do 60 min pede ~33 pregões de 1 min
            # escola com microcontratos (28/11/2026, 2 anos de 1 min, 60 combinações a favor das
            # médias): MME9 > MMA20 > MMA50 > MMA200 em 60/15/5 min, candle de força no 2 min.
            # Treino 63 operações, fator de lucro 1,42; prova 27 operações, fator 1,34.
            approved=True,
            atr_stop_multiple=2.0,
            reward_ratio=10.0,
            day_trade=True,
            micro=True,
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
