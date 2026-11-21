"""
The report of the last import of a file (#330), kept in the session until the user
closes it: a toast faded out after 6 s and left nothing after a reload.
"""

from django.utils import timezone

from ..display.wording import count

SESSION_KEY = "import_report"
# The lists of a report stay short: the rest is counted.
LIMIT = 20


def remember(session, report):
    """Keep an ImportReport (services/corpus/corpus_transfer.py) for the corpus page."""
    session[SESSION_KEY] = {
        "at": timezone.now().isoformat(),
        "added": shortened([(pub.pk, str(pub)) for pub in report.added]),
        "already_there": len(report.already_there),
        "without_metadata": shortened([(pub.pk, str(pub)) for pub in report.without_metadata]),
        "ignored": shortened(report.ignored),
        "unregistered": shortened(report.unregistered),
        "queued": shortened([(pub.pk, str(pub)) for pub in report.queued]),
    }


def shortened(items):
    return {"items": list(items[:LIMIT]), "count": len(items)}


def last(session):
    """The report of the last import, with its lists as dicts, or None."""
    data = session.get(SESSION_KEY)
    if not data:
        return None
    report = {
        **data,
        "at": timezone.datetime.fromisoformat(data["at"]),
        "added": publications(data["added"]),
        "without_metadata": publications(data["without_metadata"]),
        "ignored": titles(data["ignored"]),
        "unregistered": titles(data["unregistered"]),
        # Absent from the reports kept before #378.
        "queued": publications(data.get("queued", {"items": [], "count": 0})),
    }
    report["added_count"] = added_count(report)
    report["headline"] = headline(
        report["added_count"], report["queued"]["count"], data["already_there"]
    )
    return report


def added_count(report):
    """
    The publications added to the corpus: fetched, left to the queue (#378) or without
    metadata, all of them are in it now. An ImportReport, or the dict of last().
    """
    parts = ("added", "queued", "without_metadata")
    if isinstance(report, dict):
        return sum(report[part]["count"] for part in parts)
    return sum(len(getattr(report, part)) for part in parts)


def headline(added, queued, already):
    """
    The first line of the report (#411), with no count at 0: « 2 publications ajoutées
    à votre corpus ; leurs données arrivent en arrière-plan. 1 autre était déjà dans
    votre corpus. »
    """
    if not added:
        text = "Aucune publication ajoutée."
        if already:
            there = count(already, "publication était", "publications étaient")
            text += f" {there} déjà dans votre corpus."
        return text
    text = f"{count(added, 'publication ajoutée')} à votre corpus{in_background(added, queued)}."
    if already:
        text += f" {count(already, 'autre était', 'autres étaient')} déjà dans votre corpus."
    return text


def in_background(added, queued):
    """« ; leurs données arrivent en arrière-plan », when the queue fetches them (#378)."""
    if not queued:
        return ""
    if queued < added:
        whose = "de l'une d'elles" if queued == 1 else f"de {queued} d'entre elles"
        return f" ; les données {whose} arrivent en arrière-plan"
    return f" ; {'ses' if added == 1 else 'leurs'} données arrivent en arrière-plan"


def publications(part):
    items = [{"pk": pk, "title": title} for pk, title in part["items"]]
    return {"items": items, "count": part["count"], "rest": part["count"] - len(items)}


def titles(part):
    items = [title or "Entrée sans titre" for title in part["items"]]
    return {"items": items, "count": part["count"], "rest": part["count"] - len(items)}


def forget(session):
    session.pop(SESSION_KEY, None)
