"""Doble en memoria del servicio de Google Gmail (misma forma: users().messages().list().execute())."""
import base64
import copy
import re


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode().rstrip("=")


def make_message(mid, sender, subject, body, labels=("INBOX",), date="Wed, 22 Oct 2026 13:24:00 +0000"):
    return {
        "id": mid, "threadId": "t" + mid, "labelIds": list(labels), "snippet": body[:180],
        "payload": {"mimeType": "multipart/mixed",
                    "headers": [{"name": "From", "value": sender}, {"name": "Subject", "value": subject},
                                {"name": "Date", "value": date}],
                    "parts": [{"mimeType": "text/plain", "body": {"data": b64(body)}}]},
    }


class _Exec:
    def __init__(self, fn):
        self._fn = fn

    def execute(self):
        return self._fn()


class FakeGmailService:
    """Cada mensaje es su propio hilo (id de hilo = 't' + id de mensaje)."""

    def __init__(self, messages=(), labels=()):
        self.msgs = {m["id"]: copy.deepcopy(m) for m in messages}
        self.order = [m["id"] for m in messages]
        self.labels_list = list(labels)
        self.trashed: set[str] = set()
        self.sent: list[str] = []
        self.calls: list[tuple] = []

    def add(self, *messages):
        for m in messages:
            self.msgs[m["id"]] = copy.deepcopy(m)
            self.order.append(m["id"])
        return self

    def users(self):
        return self

    def messages(self):
        return _Messages(self)

    def threads(self):
        return _Threads(self)

    def labels(self):
        return _Labels(self)

    def _matches(self, mid, q, label_ids):
        m = self.msgs[mid]
        if mid in self.trashed or (label_ids and not all(lbl in m["labelIds"] for lbl in label_ids)):
            return False
        q = q or ""
        if "in:inbox" in q and "INBOX" not in m["labelIds"]:
            return False
        if "has:nouserlabels" in q and any(lbl.startswith("Label_") for lbl in m["labelIds"]):
            return False
        sender = next(h["value"] for h in m["payload"]["headers"] if h["name"] == "From").lower()
        froms = re.findall(r"from:([^\s()]+)", q)
        return not froms or any(f.lower() in sender for f in froms)

    def _page(self, q, max_results, page_token, label_ids):
        ids = [i for i in self.order if self._matches(i, q, label_ids)]
        start, size = int(page_token or 0), max_results or 100
        return ids[start:start + size], (str(start + size) if start + size < len(ids) else None)

    def _get(self, mid, fmt, headers):
        m = copy.deepcopy(self.msgs[mid])
        if fmt == "metadata":
            m["payload"] = {"headers": [h for h in m["payload"]["headers"] if not headers or h["name"] in headers]}
        return m

    def _modify(self, mid, body):
        m = self.msgs[mid]
        m["labelIds"] = [lbl for lbl in m["labelIds"] if lbl not in body.get("removeLabelIds", [])]
        m["labelIds"] += [lbl for lbl in body.get("addLabelIds", []) if lbl not in m["labelIds"]]
        self.calls.append(("modify", mid, body))
        return {}


class _Messages:
    def __init__(self, g):
        self.g = g

    def list(self, userId, q="", maxResults=None, pageToken=None, labelIds=None):
        def run():
            ids, nxt = self.g._page(q, maxResults, pageToken, labelIds)
            out = {"messages": [{"id": i, "threadId": "t" + i} for i in ids]} if ids else {}
            if nxt:
                out["nextPageToken"] = nxt
            return out
        return _Exec(run)

    def get(self, userId, id, format="full", metadataHeaders=None):
        return _Exec(lambda: self.g._get(id, format, metadataHeaders))

    def modify(self, userId, id, body):
        return _Exec(lambda: self.g._modify(id, body))

    def trash(self, userId, id):
        return _Exec(lambda: self.g.trashed.add(id) or {})

    def send(self, userId, body):
        return _Exec(lambda: self.g.sent.append(body["raw"]) or {"id": "sent"})

    def attachments(self):
        class _Attachments:
            def get(self, userId, messageId, id):
                return _Exec(lambda: {"data": b64("no es un pdf")})
        return _Attachments()


class _Threads:
    def __init__(self, g):
        self.g = g

    def list(self, userId, q="", maxResults=None, pageToken=None):
        def run():
            ids, nxt = self.g._page(q, maxResults, pageToken, None)
            out = {"threads": [{"id": "t" + i} for i in ids]} if ids else {}
            if nxt:
                out["nextPageToken"] = nxt
            return out
        return _Exec(run)

    def get(self, userId, id, format="metadata", metadataHeaders=None):
        return _Exec(lambda: {"id": id, "messages": [self.g._get(id[1:], format, metadataHeaders)]})

    def trash(self, userId, id):
        self.g.calls.append(("trash-thread", id))
        return _Exec(lambda: self.g.trashed.add(id[1:]) or {})


class _Labels:
    def __init__(self, g):
        self.g = g

    def list(self, userId):
        return _Exec(lambda: {"labels": copy.deepcopy(self.g.labels_list)})
