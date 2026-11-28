"""Relógio da Trade City: substitui o agendador (cron) do GitHub, que não dispara neste repo.

Roda por quase 6 horas, confere o horário a cada minuto e dispara os workflows da agenda
abaixo pelo `gh workflow run`. Antes de disparar, confere se já existe uma execução daquele
workflow desde o horário marcado (assim dois relógios nunca disparam em dobro). No fim, o
workflow do relógio chama o próximo turno.

Horários em UTC. Dias: 0 = segunda ... 6 = domingo.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

WEEKDAYS = (0, 1, 2, 3, 4)
AGENDA = [
    # (workflow, hora, minuto, dias, entradas)
    ("mesa-daytrade.yml", 13, 20, WEEKDAYS, {}),
    ("mesa-daytrade.yml", 14, 20, WEEKDAYS, {}),
    ("mesa-daytrade.yml", 16, 40, WEEKDAYS, {}),
    ("mesa-daytrade.yml", 17, 40, WEEKDAYS, {}),
    ("coleta.yml", 21, 20, WEEKDAYS, {}),
    ("cerebros.yml", 12, 0, (5,), {}),  # sábado
    ("escola.yml", 12, 0, (6,), {"trader": "todos", "dias": "2900"}),  # domingo: reconfere com os dados novos
] + [("noticias.yml", h, 5, tuple(range(7)), {}) for h in range(24)]  # manchetes do telão, de hora em hora
WINDOW = timedelta(minutes=15)  # atraso máximo aceito para um horário perdido
REPO = os.environ.get("GITHUB_REPOSITORY", "")


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def already_ran(workflow: str, since: datetime) -> bool:
    out = gh("api", f"repos/{REPO}/actions/workflows/{workflow}/runs?per_page=10&created=%3E%3D{since:%Y-%m-%dT%H:%M:%SZ}")
    return json.loads(out).get("total_count", 0) > 0


def due(now: datetime):
    for wf, hh, mm, days, inputs in AGENDA:
        at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if at.weekday() in days and at <= now < at + WINDOW:
            yield wf, at, inputs


def tick(now: datetime, fired: set) -> None:
    for wf, at, inputs in due(now):
        key = (wf, at)
        if key in fired:
            continue
        try:
            if already_ran(wf, at):
                fired.add(key)
                continue
            args = ["workflow", "run", wf, "--ref", "main", "-R", REPO]
            for k, v in inputs.items():
                args += ["-f", f"{k}={v}"]
            gh(*args)
            fired.add(key)
            print(f"{now:%Y-%m-%d %H:%M} UTC: disparei {wf} (horário {at:%H:%M})", flush=True)
        except subprocess.CalledProcessError as exc:  # tenta de novo no próximo minuto
            print(f"{now:%H:%M} falha ao disparar {wf}: {exc.stderr.strip()}", flush=True)


def main(minutes: int) -> None:
    end = time.time() + minutes * 60
    fired: set = set()
    print(f"relógio ligado por {minutes} min", flush=True)
    while time.time() < end:
        tick(datetime.now(timezone.utc), fired)
        time.sleep(60)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 340)
