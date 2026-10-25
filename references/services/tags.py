"""
Tags of a user's corpus (#130), hierarchical: « Projet A/Groupe A ». A parent exists
implicitly as soon as one of its descendants does, and filtering on a tag includes
its descendants. A tag is recognized whatever its case: the levels already known
keep the case they were first written with.
"""

from collections import defaultdict

from django.db.models import Exists, OuterRef, Q

from ..models import Tag, UserPublication

SEPARATOR = Tag.SEPARATOR
MAX_LENGTH = Tag._meta.get_field("name").max_length


class InvalidTag(ValueError):
    pass


def clean_path(raw):
    """« projet a / groupe  a/ » → « projet a/groupe a »: spaces trimmed, empty levels dropped."""
    levels = (" ".join(level.split()) for level in str(raw or "").split(SEPARATOR))
    return SEPARATOR.join(level for level in levels if level)


def label(path):
    """« Projet A › Groupe A »."""
    return " › ".join(path.split(SEPARATOR))


def ancestors_and_self(path):
    """« A/B/C » → « A », « A/B », « A/B/C »."""
    levels = path.split(SEPARATOR)
    return [SEPARATOR.join(levels[: depth + 1]) for depth in range(len(levels))]


def known_paths(user):
    """Every path of the user's tags, the implicit parents included."""
    names = Tag.objects.filter(user=user).values_list("name", flat=True)
    return {path for name in names for path in ancestors_and_self(name)}


def canonical_path(user, raw):
    """
    The cleaned path of raw, each known level written as it was first:
    « projet a/X » → « Projet A/X ».
    """
    path = clean_path(raw)
    if len(path) > MAX_LENGTH:
        raise InvalidTag(f"Un tag ne dépasse pas {MAX_LENGTH} caractères.")
    known = {known_path.casefold(): known_path for known_path in known_paths(user)}
    result = ""
    for level in path.split(SEPARATOR) if path else []:
        candidate = f"{result}{SEPARATOR}{level}" if result else level
        result = known.get(candidate.casefold(), candidate)
    return result


def tag_entry(entry, raw):
    """Tag a corpus entry, the tag created if needed. Return the tag, None for an empty name."""
    path = canonical_path(entry.user, raw)
    if not path:
        return None
    tag, _ = Tag.objects.get_or_create(user=entry.user, name=path)
    entry.tags.add(tag)
    return tag


def untag_entry(entry, tag):
    """Remove a tag from an entry; a tag left on no entry is forgotten."""
    entry.tags.remove(tag)
    forget_unused_tags(entry.user)


def forget_unused_tags(user):
    Tag.objects.filter(user=user, entries__isnull=True).delete()


def tag_tree(user):
    """
    The user's tags as a tree, parents first: [{path, name, depth, count}], the count
    being the entries tagged with the path or one of its descendants.
    """
    links = UserPublication.tags.through.objects.filter(userpublication__user=user)
    entries = defaultdict(set)
    for entry_id, name in links.values_list("userpublication_id", "tag__name"):
        for path in ancestors_and_self(name):
            entries[path].add(entry_id)
    paths = sorted(entries, key=lambda path: [level.casefold() for level in path.split(SEPARATOR)])
    return [
        {
            "path": path,
            "name": path.split(SEPARATOR)[-1],
            "depth": path.count(SEPARATOR),
            "count": len(entries[path]),
        }
        for path in paths
    ]


def tags_by_publication(user, publications):
    """{publication id: [tags of its entry in the user's corpus]}, in one query."""
    tags = defaultdict(list)
    links = UserPublication.tags.through.objects.filter(
        userpublication__user=user, userpublication__publication__in=publications
    ).select_related("tag", "userpublication")
    for link in links.order_by("tag__name"):
        tags[link.userpublication.publication_id].append(link.tag)
    return tags


def tagged(user, path):
    """
    The condition on publications whose entry in the user's corpus has the tag path
    or one of its descendants.
    """
    entries = UserPublication.objects.filter(user=user, publication=OuterRef("pk")).filter(
        Q(tags__name=path) | Q(tags__name__startswith=path + SEPARATOR)
    )
    return Q(Exists(entries))
