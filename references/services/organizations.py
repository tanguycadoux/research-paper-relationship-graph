"""
Organizations from OpenAlex institutions, with their hierarchy (lineage): IRFU
belongs to the Direction de la Recherche Fondamentale, which belongs to the CEA.
A joint unit can belong to several top-level organizations.
"""

from django.db.models import Q

from ..models import AuthorPublication, Organization


def organizations_for(institutions):
    """
    {OpenAlex id: Organization} for the institutions, creating the missing ones and
    linking them to their known ancestors. An organization is recognized by its
    OpenAlex id or by its ROR (OpenAlex sometimes merges institutions).
    """
    by_id = {openalex_id(i): i for i in institutions if openalex_id(i)}
    rors = {ror_id(i) for i in by_id.values() if ror_id(i)}
    existing = Organization.objects.filter(Q(openalex_id__in=by_id) | Q(ror__in=rors))
    by_oid = {org.openalex_id: org for org in existing}
    by_ror = {org.ror: org for org in existing if org.ror}
    found = {
        oid: by_oid.get(oid) or by_ror.get(ror_id(i))
        for oid, i in by_id.items()
        if oid in by_oid or ror_id(i) in by_ror
    }
    missing = [new_organization(i) for oid, i in by_id.items() if oid not in found]
    Organization.objects.bulk_create(missing)
    organizations = found | {org.openalex_id: org for org in missing}
    link_ancestors(organizations, by_id)
    return organizations


def link_ancestors(organizations, institutions_by_id):
    """Set the ancestors of each organization from its OpenAlex lineage, when given."""
    lineages = {
        oid: [a for a in lineage_ids(i) if a != oid]
        for oid, i in institutions_by_id.items()
        if "lineage" in i and oid in organizations
    }
    ancestor_ids = {a for lineage in lineages.values() for a in lineage}
    known = {o.openalex_id: o for o in Organization.objects.filter(openalex_id__in=ancestor_ids)}
    links = Organization.ancestors.through
    links.objects.filter(from_organization__in=[organizations[oid] for oid in lineages]).delete()
    links.objects.bulk_create(
        links(from_organization=organizations[oid], to_organization=known[a])
        for oid, lineage in lineages.items()
        for a in lineage
        if a in known
    )


def missing_ancestor_ids(institutions, include_known=False):
    """Ancestors named in the lineages but neither given nor (by default) already known."""
    given = {openalex_id(i) for i in institutions}
    wanted = {a for i in institutions for a in lineage_ids(i)} - given
    if include_known:
        return sorted(wanted)
    known = set(
        Organization.objects.filter(openalex_id__in=wanted).values_list("openalex_id", flat=True)
    )
    return sorted(wanted - known)


def new_organization(institution):
    return Organization(
        name=institution.get("display_name") or "",
        ror=ror_id(institution),
        openalex_id=openalex_id(institution),
        country_code=institution.get("country_code") or "",
    )


def lineage_ids(institution):
    return [short_id(a) for a in institution.get("lineage") or []]


def ror_id(institution):
    """'https://ror.org/03f0apy98' -> '03f0apy98'."""
    return short_id(institution.get("ror") or "")


def openalex_id(institution):
    """'https://openalex.org/I4210141222' -> 'I4210141222'."""
    return short_id(institution.get("id") or "")


def short_id(url):
    return url.rsplit("/", 1)[-1]


def top_levels(organization):
    """Its top-level ancestors (several for a joint unit), or itself."""
    roots = [a for a in organization.ancestors.all() if not a.ancestors.all()]
    return roots or [organization]


def numbered_affiliations(slots):
    """
    The authors of a publication with the numbers of their affiliations, and the
    affiliations numbered once, in order of appearance, as in an article (#155).
    """
    numbers = {}  # organization: number, in order of appearance
    authors = []
    for slot in slots:
        organizations = most_precise(slot.organizations.all())
        authors.append(
            {
                "slot": slot,
                "numbers": [numbers.setdefault(o, len(numbers) + 1) for o in organizations],
            }
        )
    return {"authors": authors, "affiliations": list(numbers)}


def most_precise(organizations):
    """Without those that are an ancestor of another one: IRFU rather than IRFU and CEA."""
    ancestors = {a.pk for organization in organizations for a in organization.ancestors.all()}
    return [organization for organization in organizations if organization.pk not in ancestors]


def organization_groups(author):
    """
    Organizations of an author grouped by top-level organization (the CEA, with
    IRFU and CEA Paris-Saclay as details), with the period and number of their
    publications, computed from the publications.
    """
    slots = (
        AuthorPublication.objects.filter(author=author)
        .select_related("publication")
        .prefetch_related("organizations__ancestors__ancestors")
    )
    groups = {}
    for slot in slots:
        for organization in slot.organizations.all():
            for root in top_levels(organization):
                group = groups.setdefault(root.pk, new_group(root))
                group["publications"].add(slot.publication)
                if organization != root:
                    group["details"].add(organization)
    return sorted((summary(g) for g in groups.values()), key=lambda g: g["sort_key"], reverse=True)


def new_group(root):
    return {"organization": root, "details": set(), "publications": set()}


def summary(group):
    dates = sorted(p.publication_date for p in group["publications"] if p.publication_date)
    return {
        "organization": group["organization"],
        "details": sorted(group["details"], key=lambda o: o.name),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "publication_count": len(group["publications"]),
        "sort_key": (dates[-1].isoformat() if dates else "", len(group["publications"])),
    }
