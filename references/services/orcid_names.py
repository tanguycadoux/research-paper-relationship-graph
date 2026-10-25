"""
Names of the authors completed from ORCID (#220). ORCID gives the name the person
declares, often more complete than the published one: « T. Thuillier » becomes
« Thomas Thuillier ». Nothing is overwritten:
- a given name that only extends the known one completes it;
- a different name is reported as a conflict (an ORCID can be wrongly attributed);
- a name corrected by hand is never changed (Author.name_edited).
The family name of the base is kept: its case is more reliable than ORCID's, where
« SIMON » or « vallcorba » are common.
"""

import re

from django.utils import timezone

from ..models import Author, OrcidRecord
from .conflicts import Kind, close_obsolete, report_conflict
from .external_records import Source
from .names import name_parts
from .orcid_api import fetch_orcid_names

GLUED_INITIALS = re.compile(r"(?<=\.)(?=\w)")  # « C.M. » -> « C. M. »


def complete_names(authors, refresh=False):
    """
    Ask ORCID the names of the authors whose ORCID was never asked (all of them with
    refresh), in grouped requests, then complete them. Return the number of names
    completed.
    """
    orcids = {author.orcid for author in authors if author.orcid}
    if not refresh:
        asked = OrcidRecord.objects.filter(orcid__in=orcids, search_data__isnull=False)
        orcids -= set(asked.values_list("orcid", flat=True))
    if not orcids:
        return 0
    found = fetch_orcid_names(sorted(orcids))
    now = timezone.now()
    for orcid, entry in found.items():
        OrcidRecord.objects.update_or_create(
            orcid=orcid, defaults={"search_data": entry or {}, "search_fetched_at": now}
        )
    return sum(
        update_holders(orcid, entry.get("given-names") or "", entry.get("family-names") or "")
        for orcid, entry in found.items()
        if entry
    )


def update_holders(orcid, given, family):
    """Update the name of the authors with this ORCID. Return how many were completed."""
    return sum(update_name(author, given, family) for author in Author.objects.filter(orcid=orcid))


def update_name(author, given, family):
    """Complete the name of the author from ORCID, or report a conflict. True if completed."""
    given, family = readable_case(given.strip()), readable_case(family.strip())
    if author.name_edited or not given or not family:
        return False
    completed = None
    if name_parts(family) == name_parts(author.last_name):
        completed = completed_given_name(author.first_name, given)
    if completed is None:
        report_conflict(
            Kind.ORCID_NAME,
            author=author,
            field="name",
            current=f"{author.last_name}, {author.first_name}",
            proposed=f"{family}, {given}",
            source=Source.ORCID,
        )
        return False
    close_obsolete(Kind.ORCID_NAME, author=author)
    if completed == author.first_name:
        return False
    author.first_name = completed
    author.save(update_fields=["first_name"])
    return True


def completed_given_name(current, orcid):
    """
    The known given name completed word by word with ORCID's, or None if they
    differ: « T. » and « Thomas » give « Thomas »; « A. K. » or « A.K. » and
    « Angie » give « Angie K. »; « Thomas » and « T. » keep « Thomas ».
    """
    if name_parts(current) == name_parts(orcid):
        return current  # same name, up to accents and punctuation
    known, declared = GLUED_INITIALS.sub(" ", current).split(), orcid.split()
    words = []
    for index, word in enumerate(known):
        other = declared[index] if index < len(declared) else None
        if other is None or abbreviates(other, word):
            words.append(word)
        elif abbreviates(word, other):
            words.append(other)
        else:
            return None
    return " ".join(words + declared[len(known) :])


def abbreviates(short, long):
    """« J.-L. » abbreviates « Jean-Luc »: same parts, each one equal or its initial."""
    short_parts, long_parts = name_parts(short), name_parts(long)
    return len(short_parts) == len(long_parts) and all(
        part == whole or (len(part) == 1 and whole.startswith(part))
        for part, whole in zip(short_parts, long_parts, strict=True)
    )


def readable_case(name):
    """« ezio » or « CORREIA MACHADO » -> « Ezio », « Correia Machado »."""
    return name.title() if name.islower() or name.isupper() else name
