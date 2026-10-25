"""
Tags of a user's corpus (#130), hierarchical: « Projet A/Groupe A ». A parent exists
implicitly as soon as one of its descendants does, and filtering on a tag includes
its descendants. A tag is recognized whatever its case: the levels already known
keep the case they were first written with.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from django.db import transaction
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


def known_paths(user, excluded=()):
    """Every path of the user's tags but the excluded ones, the implicit parents included."""
    names = Tag.objects.filter(user=user).exclude(pk__in=excluded).values_list("name", flat=True)
    return {path for name in names for path in ancestors_and_self(name)}


def canonical_path(user, raw, excluded=()):
    """
    The cleaned path of raw, each level known (but from the excluded tags) written as
    it was first: « projet a/X » → « Projet A/X ».
    """
    path = clean_path(raw)
    check_length(path)
    known = {known_path.casefold(): known_path for known_path in known_paths(user, excluded)}
    result = ""
    for level in path.split(SEPARATOR) if path else []:
        candidate = f"{result}{SEPARATOR}{level}" if result else level
        result = known.get(candidate.casefold(), candidate)
    return result


def check_length(path):
    if len(path) > MAX_LENGTH:
        raise InvalidTag(f"Un tag ne dépasse pas {MAX_LENGTH} caractères.")


def is_descendant(path, ancestor):
    return path.startswith(ancestor + SEPARATOR)


@dataclass
class Tagging:
    """What tagging an entry did: the tag added, or the more precise one that covers it."""

    tag: Tag | None = None
    covered_by: Tag | None = None
    replaced: list = field(default_factory=list)


def tag_entry(entry, raw):
    """
    Tag a corpus entry, the tag created if needed. A tag is redundant beside one of its
    descendants, which the filter includes: a more precise tag replaces its ancestors,
    a less precise one is not added. Nothing is done for an empty name.
    """
    path = canonical_path(entry.user, raw)
    if not path:
        return Tagging()
    current = list(entry.tags.all())
    covering = [tag for tag in current if is_descendant(tag.name, path)]
    if covering:
        return Tagging(covered_by=covering[0])
    tag, _ = Tag.objects.get_or_create(user=entry.user, name=path)
    replaced = [old for old in current if is_descendant(path, old.name)]
    entry.tags.remove(*replaced)
    entry.tags.add(tag)
    if replaced:
        forget_unused_tags(entry.user)
    return Tagging(tag=tag, replaced=replaced)


def drop_redundant_tags(entries):
    """Remove from each entry the tags one of its other tags is a descendant of."""
    for entry in entries:
        current = list(entry.tags.all())
        redundant = [
            tag for tag in current if any(is_descendant(other.name, tag.name) for other in current)
        ]
        entry.tags.remove(*redundant)


def untag_entry(entry, tag):
    """Remove a tag from an entry; a tag left on no entry is forgotten."""
    entry.tags.remove(tag)
    forget_unused_tags(entry.user)


def forget_unused_tags(user):
    Tag.objects.filter(user=user, entries__isnull=True).delete()


def subtree(user, path):
    """The user's tags named path or one of its descendants."""
    return [
        tag
        for tag in Tag.objects.filter(user=user)
        if tag.name == path or is_descendant(tag.name, path)
    ]


def tagged_entries(tags):
    return UserPublication.objects.filter(tags__in=tags).distinct()


@transaction.atomic
def rename_path(user, path, raw_name):
    """
    Rename a tag and its descendants: « Projet B » → « ASTERICS » renames « Projet B/Groupe »
    too. A name the user already has merges both tags. Return the number of
    publications tagged, or raise InvalidTag.
    """
    moved = subtree(user, path)
    if not moved:
        raise InvalidTag(f"Le tag « {label(path)} » n'existe plus.")
    new_path = canonical_path(user, raw_name, excluded=[tag.pk for tag in moved])
    if not new_path:
        raise InvalidTag("Écrivez le nouveau nom du tag.")
    entries = list(tagged_entries(moved))
    others = {
        tag.name.casefold(): tag
        for tag in Tag.objects.filter(user=user).exclude(pk__in=[tag.pk for tag in moved])
    }
    # The deepest first: « A » → « A/X » must not collide with « A/X » still to move.
    for tag in sorted(moved, key=lambda tag: -len(tag.name)):
        name = new_path + tag.name[len(path) :]
        check_length(name)
        target = others.get(name.casefold())
        if target:
            for entry in tag.entries.all():
                entry.tags.add(target)
            tag.delete()
        else:
            tag.name = name
            tag.save(update_fields=["name"])
    drop_redundant_tags(entries)
    forget_unused_tags(user)
    return len(entries)


@transaction.atomic
def delete_path(user, path):
    """
    Delete a tag and its descendants; the publications stay in the corpus. Return the
    number of publications that were tagged, or raise InvalidTag.
    """
    deleted = subtree(user, path)
    if not deleted:
        raise InvalidTag(f"Le tag « {label(path)} » n'existe plus.")
    count = tagged_entries(deleted).count()
    Tag.objects.filter(pk__in=[tag.pk for tag in deleted]).delete()
    return count


def tag_tree(user):
    """
    The user's tags as a tree, parents first: [{path, name, depth, count, has_children}],
    the count being the entries tagged with the path or one of its descendants.
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
            "has_children": any(is_descendant(other, path) for other in paths),
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
