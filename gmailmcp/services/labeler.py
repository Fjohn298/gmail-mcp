"""Etiqueta el inbox por remitente según config/label_rules.json."""
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from gmailmcp.gmail.ports import MessageLabeler, MessageReader
from gmailmcp.repositories.settings_repo import JsonSettingsRepository


class LabelerMailbox(MessageReader, MessageLabeler, Protocol):
    """Lo único que el labeler necesita de Gmail."""


@dataclass(frozen=True)
class LabelPolicy:
    """Reglas fijas del etiquetado. Se inyectan para poder cambiarlas sin tocar el servicio."""
    lookback_days: int = 7
    total_seconds: int = 300       # ventana total por ejecución
    phase1_seconds: int = 270      # primero: correos de los últimos `lookback_days`
    skip_if_has: frozenset[str] = frozenset({
        'Label_2', 'Label_3', 'Label_4', 'Label_6',
        'Label_13', 'Label_15', 'Label_17',
        'Label_1834638960901538876',
        'Label_8650347335116413717', 'Label_11',
        'Label_8229819340533470960', 'Label_1938252154982079077',
        'Label_1714922903715444819',
    })
    corrections: dict[str, list[str]] = field(default_factory=lambda: {
        'Label_1834638960901538876': ['iseade.edu.sv', 'utec.edu.sv'],
        'Label_13': ['datacamp', 'notify.thinkific', 'kaggle', 'platzi', 'netec', 'coursera'],
    })
    priority: dict[str, int] = field(default_factory=lambda: {
        'Label_1834638960901538876': 1,  # Banco Cuscatlán (más específico)
        'Label_17': 2,    # Fun Capital/Conciertos
        'Label_3': 3,     # Recibos
        'Label_4': 4,     # Trabajo
        'Label_2': 5,     # Cursos
        'Label_6': 6,     # Archivo
        'Label_15': 7,    # Newsletters
        'Label_13': 8,    # Promociones
    })


def load_rules(path: str) -> list[tuple[str, str]]:
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    rules = []
    for category, data in raw.items():
        if category.startswith('_'):
            continue
        for sender in data['senders']:
            rules.append((sender.lower(), data['_label_id']))
    return rules


def match_label(from_header: str, rules: list[tuple[str, str]]) -> str | None:
    from_lower = from_header.lower()
    return next((label_id for fragment, label_id in rules if fragment in from_lower), None)


def needs_correction(from_header: str, existing_labels: list[str],
                     corrections: dict[str, list[str]] | None = None) -> tuple[bool, str | None]:
    corrections = LabelPolicy().corrections if corrections is None else corrections
    from_lower = from_header.lower()
    for wrong_label, fragments in corrections.items():
        if wrong_label in existing_labels and any(f in from_lower for f in fragments):
            return True, wrong_label
    return False, None


@dataclass
class _Stats:
    labeled: int = 0
    corrected: int = 0
    skipped: int = 0
    cleaned: int = 0
    label_counts: dict[str, int] = field(default_factory=dict)


class LabelerService:
    def __init__(self, mailbox: LabelerMailbox, settings_repo: JsonSettingsRepository,
                 logger: logging.Logger, policy: LabelPolicy | None = None,
                 now: Callable[[], datetime] = datetime.now):
        self._mailbox = mailbox
        self._settings_repo = settings_repo
        self._logger = logger
        self._policy = policy or LabelPolicy()
        self._now = now

    def run(self) -> int:
        p = self._policy
        self._logger.info("=== Etiquetado iniciado (ventana 5 min) ===")
        start = self._now()
        settings = self._settings_repo.load()
        rules = load_rules(settings['paths']['label_rules_file'])
        if not rules:
            self._logger.warning("Sin reglas.")
            return 0
        page_size = settings['gmail']['page_size']
        stats = _Stats()

        self._logger.info(f"  Fase 1: últimos {p.lookback_days} días")
        self._process(f'in:inbox newer_than:{p.lookback_days}d', rules, start, p.phase1_seconds,
                      page_size, stats)

        remaining = p.total_seconds - (self._now() - start).total_seconds()
        if remaining > 10:
            self._logger.info(f"  Fase 2: correos sin etiqueta ({remaining:.0f}s disponibles)")
            self._process('in:inbox has:nouserlabels', rules, start, p.total_seconds, page_size, stats)
        else:
            self._logger.info("  Fase 2 omitida: sin tiempo disponible")

        duration = (self._now() - start).total_seconds()
        self._logger.info(
            f"=== Etiquetado finalizado: {stats.labeled} nuevos, {stats.corrected} corregidos, "
            f"{stats.cleaned} dedup, {stats.skipped} ya etiquetados — {duration:.1f}s ===")
        for lid, count in sorted(stats.label_counts.items(), key=lambda x: x[1], reverse=True):
            self._logger.info(f"  {count:3d}x  {lid}")
        return stats.labeled + stats.corrected

    def _process(self, query, rules, start, deadline, page_size, stats: _Stats) -> None:
        page_token = None
        while (self._now() - start).total_seconds() < deadline:
            result = self._mailbox.list_messages(query=query, max_results=page_size, page_token=page_token)
            messages = result.get('messages', [])
            if not messages:
                return
            for msg in messages:
                if (self._now() - start).total_seconds() >= deadline:
                    return
                self._label_one(msg['id'], rules, stats)
            page_token = result.get('nextPageToken')
            if not page_token:
                return

    def _label_one(self, message_id, rules, stats: _Stats) -> None:
        p = self._policy
        m = self._mailbox.get_message(message_id, format='metadata', metadata_headers=['From'])
        existing = m.get('labelIds', [])
        from_header = next((h['value'] for h in m['payload']['headers'] if h['name'] == 'From'), '')

        # Una sola etiqueta propia por correo: se queda la de mayor prioridad
        ours = [lbl for lbl in existing if lbl in p.skip_if_has]
        if len(ours) > 1:
            keep = min(ours, key=lambda lbl: p.priority.get(lbl, 99))
            remove = [lbl for lbl in ours if lbl != keep]
            self._mailbox.modify_message(message_id, remove=remove)
            stats.cleaned += 1
            stats.skipped += 1
            self._logger.info(f"  Dedup: {from_header[:40]} | kept={keep}, removed={remove}")
            return

        wrong, wrong_label = needs_correction(from_header, existing, p.corrections)
        if wrong:
            correct = match_label(from_header, rules)
            if correct and correct != wrong_label:
                self._mailbox.modify_message(message_id, add=[correct], remove=[wrong_label])
                stats.corrected += 1
                self._logger.info(f"  Corregido: {from_header[:50]} | {wrong_label}→{correct}")
            return

        if any(lbl in p.skip_if_has for lbl in existing):
            stats.skipped += 1
            return

        label_id = match_label(from_header, rules)
        if label_id:
            self._mailbox.modify_message(message_id, add=[label_id])
            stats.labeled += 1
            stats.label_counts[label_id] = stats.label_counts.get(label_id, 0) + 1
