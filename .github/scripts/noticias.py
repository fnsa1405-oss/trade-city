"""Notícias do dia para o telão do escritório 3D.

Lê manchetes de mercado de fontes gratuitas (RSS em português; a API de notícias da Massive como
reserva) e grava noticias.json: só título, fonte, link e horário, sem copiar o texto das matérias.
Uso: python noticias.py saida.json
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

FEEDS = [
    ("InfoMoney", "https://www.infomoney.com.br/mercados/feed/"),
    ("Money Times", "https://www.moneytimes.com.br/feed/"),
    (None, "https://news.google.com/rss/search?q=ibovespa+OR+d%C3%B3lar+OR+bolsa+OR+bitcoin+when:1d&hl=pt-BR&gl=BR&ceid=BR:pt-419"),
]
MAX_IDADE = timedelta(hours=36)
UA = {"User-Agent": "Mozilla/5.0 (compatible; trade-city-telao/1.0)"}


def baixar(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return r.read()


def limpar(t: str) -> str:
    t = re.sub(r"<[^>]+>", "", t or "")
    return re.sub(r"\s+", " ", t).strip()


def ler_rss(fonte: str | None, url: str) -> list[dict]:
    raiz = ET.fromstring(baixar(url))
    itens = []
    for it in raiz.iter("item"):
        titulo = limpar(it.findtext("title", ""))
        quando = it.findtext("pubDate")
        try:
            dt = parsedate_to_datetime(quando).astimezone(timezone.utc) if quando else None
        except (TypeError, ValueError):
            dt = None
        nome = fonte or limpar(it.findtext("source", "")) or "Google Notícias"
        if fonte is None and titulo.endswith(" - " + nome):  # o Google põe a fonte no fim do título
            titulo = titulo[: -len(nome) - 3]
        if titulo and dt:
            itens.append({"titulo": titulo, "fonte": nome, "link": it.findtext("link", ""), "quando": dt.isoformat()})
    return itens


def ler_massive() -> list[dict]:
    chave = os.environ.get("MASSIVE_API_KEY")
    if not chave:
        return []
    url = f"https://api.massive.com/v2/reference/news?limit=15&order=desc&sort=published_utc&apiKey={chave}"
    dados = json.loads(baixar(url))
    return [
        {"titulo": limpar(r.get("title", "")), "fonte": (r.get("publisher") or {}).get("name", "Massive"), "link": r.get("article_url", ""), "quando": r.get("published_utc", "")}
        for r in dados.get("results", [])
        if r.get("title") and r.get("published_utc")
    ]


def main(saida: str) -> None:
    agora = datetime.now(timezone.utc)
    itens: list[dict] = []
    for fonte, url in FEEDS:
        try:
            itens += ler_rss(fonte, url)
            print(f"ok: {fonte or 'Google Notícias'}")
        except Exception as e:  # uma fonte fora do ar não derruba as outras
            print(f"falhou: {url}: {e}")
    if len(itens) < 5:
        try:
            itens += ler_massive()
            print("ok: Massive")
        except Exception as e:
            print(f"falhou: Massive: {e}")
    vistos, lista = set(), []
    for it in sorted(itens, key=lambda x: x["quando"], reverse=True):
        chave = re.sub(r"\W+", "", it["titulo"].lower())[:45]
        try:
            velho = agora - datetime.fromisoformat(it["quando"].replace("Z", "+00:00")) > MAX_IDADE
        except ValueError:
            velho = True
        if chave in vistos or velho:
            continue
        vistos.add(chave)
        lista.append(it)
    if not lista:
        print("nenhuma notícia nova; mantenho o arquivo anterior")
        return
    with open(saida, "w", encoding="utf-8") as f:
        json.dump({"atualizado": agora.isoformat(), "itens": lista[:20]}, f, ensure_ascii=False, indent=1)
    print(f"{len(lista[:20])} manchetes gravadas")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "noticias.json")
