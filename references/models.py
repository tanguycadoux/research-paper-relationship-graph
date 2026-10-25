from django.conf import settings
from django.db import models, transaction
from django.utils.formats import date_format

from .services.doi import normalize_doi
from .services.isbn import normalize_isbn


class PublicationQuerySet(models.QuerySet):
    def with_doi(self, doi):
        """By its DOI, or by the DOI of the preprint it replaced (#227)."""
        return self.filter(models.Q(doi=doi) | models.Q(preprint_doi=doi))

    def with_dois(self, dois):
        return self.filter(models.Q(doi__in=dois) | models.Q(preprint_doi__in=dois))

    def get_or_create_doi(self, doi):
        """The publication of a DOI, or of the preprint it replaced, else a new one."""
        return self.with_doi(doi).first() or self.create(doi=doi)


class Publication(models.Model):
    class DatePrecision(models.TextChoices):
        """What the source gives of the date: the missing month or day is stored as 1 (#147)."""

        YEAR = "year", "année"
        MONTH = "month", "mois"
        DAY = "day", "jour"

    DATE_FORMATS = {DatePrecision.YEAR: "Y", DatePrecision.MONTH: "F Y", DatePrecision.DAY: "j F Y"}

    doi = models.CharField(max_length=255, blank=True)
    # The arXiv DOI of a preprint replaced by its published version (#227): importing
    # or citing it finds this publication again.
    preprint_doi = models.CharField("DOI de la prépublication", max_length=255, blank=True)
    isbn = models.CharField("ISBN", max_length=13, blank=True)
    title = models.TextField(blank=True)
    publication_date = models.DateField(null=True, blank=True)
    publication_date_precision = models.CharField(
        max_length=5, choices=DatePrecision.choices, default=DatePrecision.DAY
    )
    # Corrected by hand (« Modifier »): the sources no longer overwrite them (#146).
    title_edited = models.BooleanField(default=False)
    date_edited = models.BooleanField(default=False)
    authors = models.ManyToManyField(
        "Author", through="AuthorPublication", related_name="publications", blank=True
    )
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    objects = PublicationQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["doi"], condition=~models.Q(doi=""), name="unique_non_empty_doi"
            ),
            models.UniqueConstraint(
                fields=["preprint_doi"],
                condition=~models.Q(preprint_doi=""),
                name="unique_non_empty_preprint_doi",
            ),
            models.UniqueConstraint(
                fields=["isbn"], condition=~models.Q(isbn=""), name="unique_non_empty_isbn"
            ),
        ]

    def __str__(self):
        return self.title or self.doi or self.isbn or f"PK : {self.pk}"

    def save(self, *args, **kwargs):
        self.doi = normalize_doi(self.doi)
        self.preprint_doi = normalize_doi(self.preprint_doi)
        self.isbn = normalize_isbn(self.isbn)
        super().save(*args, **kwargs)

    @property
    def formatted_publication_date(self):
        """'2023', 'août 2023' or '1 août 2023', as precise as the source."""
        if not self.publication_date:
            return ""
        return date_format(
            self.publication_date, self.DATE_FORMATS[self.publication_date_precision]
        )

    @property
    def parse_references(self):
        """
        Whether the cited references are imported: as long as the publication is in
        the corpus of at least one user. Those already imported stay when it leaves.
        """
        return self.userpublication_set.exists()


class ExternalRecord(models.Model):
    """
    Answer of an external source about a publication, stored as is. data is None
    when the source answered that it does not know the publication.
    """

    class Source(models.TextChoices):
        CROSSREF = "crossref", "Crossref"
        DATACITE = "datacite", "DataCite"
        OPENALEX = "openalex", "OpenAlex"
        OPENLIBRARY = "openlibrary", "Open Library"
        ORCID = "orcid", "ORCID"
        # The LaTeX bibliography of an arXiv preprint, not its metadata (#227).
        ARXIV = "arxiv", "arXiv"

    publication = models.ForeignKey(
        Publication, on_delete=models.CASCADE, related_name="external_records"
    )
    source = models.CharField(max_length=20, choices=Source.choices)
    data = models.JSONField(null=True, blank=True)
    fetched_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["publication", "source"], name="unique_record_per_source"
            )
        ]

    def __str__(self):
        return f"{self.publication} – {self.get_source_display()}"


class Author(models.Model):
    """Canonical author: the person behind one or several published names."""

    first_name = models.CharField(max_length=255, blank=True)
    last_name = models.CharField(max_length=255, blank=True)
    orcid = models.CharField(max_length=50, blank=True)
    # Corrected by hand: ORCID never changes the name again (#220).
    name_edited = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()

    @transaction.atomic
    def merge_with(self, others: list[Author]):
        """
        Move the publications of the other authors to this one, then delete them.
        The published names stay on each publication, so the merge survives re-imports.
        """
        for other in others:
            AuthorPublication.objects.filter(author=other).update(author=self)
            other.delete()


class OrcidRecord(models.Model):
    """
    What ORCID answered about a person, stored as is. Keyed by the ORCID, not by
    the author: it survives the merges. data is the public record (names, works),
    asked on demand from the author page (#59); search_data the names given by
    the grouped search at import (#220), {} when ORCID does not know the person.
    """

    orcid = models.CharField(max_length=50, unique=True)
    data = models.JSONField(null=True, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)
    search_data = models.JSONField(null=True, blank=True)
    search_fetched_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.orcid


class Organization(models.Model):
    """A research organization (laboratory, university, company), from OpenAlex."""

    name = models.CharField(max_length=500)
    ror = models.CharField("ROR", max_length=20, blank=True)
    openalex_id = models.CharField(max_length=20, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    # All the organizations it belongs to, at every level (OpenAlex lineage): IRFU
    # belongs to the Direction de la Recherche Fondamentale and to the CEA. A joint
    # unit can have several top-level ancestors.
    ancestors = models.ManyToManyField(
        "self", symmetrical=False, related_name="descendants", blank=True
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["ror"], condition=~models.Q(ror=""), name="unique_ror"),
            models.UniqueConstraint(
                fields=["openalex_id"],
                condition=~models.Q(openalex_id=""),
                name="unique_openalex_organization",
            ),
        ]

    def __str__(self):
        return self.name


class AuthorDistinction(models.Model):
    """
    Two authors declared to be different people: never suggested as duplicates.
    The pair is stored once, the author with the smaller id first.
    """

    first = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="+")
    second = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="+")
    declared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    declared_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["first", "second"], name="unique_author_distinction"),
            models.CheckConstraint(
                condition=models.Q(first__lt=models.F("second")), name="ordered_author_distinction"
            ),
        ]

    def __str__(self):
        return f"{self.first} ≠ {self.second}"


class AuthorMerge(models.Model):
    """
    Trace of a merge: the authors absorbed into kept, as they were. merged_by is
    empty for an automatic merge (same ORCID, #158).
    """

    class Reason(models.TextChoices):
        MANUAL = "manual", "fusion manuelle"
        ORCID = "orcid", "même ORCID"

    kept = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="merges")
    # [{"first_name", "last_name", "orcid"}] of the absorbed authors.
    absorbed = models.JSONField(default=list)
    reason = models.CharField(max_length=10, choices=Reason.choices)
    merged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    merged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-merged_at"]

    def __str__(self):
        return f"{self.kept} ← {self.absorbed_names}"

    @property
    def absorbed_names(self):
        return ", ".join(
            f"{author['first_name']} {author['last_name']}".strip() for author in self.absorbed
        )


class AuthorPublication(models.Model):
    """
    An author slot of a publication: the name as published by Crossref (never
    modified) and the canonical author it is resolved to.
    """

    publication = models.ForeignKey(Publication, on_delete=models.CASCADE)
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    order = models.PositiveIntegerField()
    published_given_name = models.CharField(max_length=255, blank=True)
    published_family_name = models.CharField(max_length=255, blank=True)
    published_orcid = models.CharField(max_length=50, blank=True)
    # Affiliations declared on this publication: a property of the signature, not
    # of the person, since researchers change laboratories.
    organizations = models.ManyToManyField(Organization, related_name="author_slots", blank=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["publication", "order"], name="unique_author_slot")
        ]

    def __str__(self):
        return f"{self.order} – {self.author}"


class CitedReference(models.Model):
    """
    An entry of the bibliography of a publication, as given by Crossref, and the
    publication it is resolved to when known.
    """

    source = models.ForeignKey(
        Publication, on_delete=models.CASCADE, related_name="cited_references"
    )
    target = models.ForeignKey(
        Publication,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="citations",
    )
    position = models.PositiveIntegerField()
    key = models.CharField(max_length=255, blank=True)
    doi = models.CharField(max_length=255, blank=True)
    unstructured = models.TextField(blank=True)
    raw = models.JSONField(default=dict, blank=True)
    # Manual identification: kept when the source publication is imported again.
    resolved_manually = models.BooleanField(default=False)
    # Declared by hand as matching no importable publication (internal report,
    # talk…): no longer to identify. A manual decision, so resolved_manually too.
    unidentifiable = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["source", "position"], name="unique_reference_position")
        ]

    def __str__(self):
        return f"{self.source} → {self.label}"

    @property
    def label(self):
        """Best human-readable description of the cited work."""
        if self.target:
            return str(self.target)
        return self.unstructured or self.structured_description() or "Référence sans description"

    def structured_description(self):
        """'Author (year). Title. Journal volume, p. page' from the Crossref fields."""
        raw = self.raw
        title = raw.get("article-title") or raw.get("volume-title") or raw.get("series-title")
        source = " ".join(filter(None, [raw.get("journal-title"), raw.get("volume")]))
        if raw.get("first-page"):
            source = ", ".join(filter(None, [source, f"p. {raw['first-page']}"]))
        year = f"({raw['year']})" if raw.get("year") else ""
        author = raw.get("author", "")
        if author:
            return ". ".join(filter(None, [f"{author} {year}".strip(), title, source]))
        return " ".join(filter(None, [". ".join(filter(None, [title, source])), year]))


class UserPublication(models.Model):
    """A publication in the corpus of a user."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "publication"], name="unique_corpus_entry")
        ]

    def __str__(self):
        return f"{self.user} – {self.publication}"


class MetadataConflict(models.Model):
    """
    A value from a source that contradicts a known value. The known value is kept
    until someone decides; decisions are shared by all users.
    """

    class Kind(models.TextChoices):
        AUTHORS_MISMATCH = "authors_mismatch", "Auteurs différents selon les sources"
        ORCID = "orcid", "ORCID différent"
        SHARED_ORCID = "shared_orcid", "ORCID porté par des auteurs déclarés distincts"
        ORCID_NAME = "orcid_name", "Nom différent selon ORCID"

    class Status(models.TextChoices):
        OPEN = "open", "Ouvert"
        KEPT = "kept", "Valeur existante conservée"
        ACCEPTED = "accepted", "Valeur proposée retenue"
        SEEN = "seen", "Vu"

    kind = models.CharField(max_length=30, choices=Kind.choices)
    publication = models.ForeignKey(
        Publication, on_delete=models.CASCADE, null=True, blank=True, related_name="conflicts"
    )
    author = models.ForeignKey(
        Author, on_delete=models.CASCADE, null=True, blank=True, related_name="conflicts"
    )
    field = models.CharField(max_length=50)
    current_value = models.TextField(blank=True)
    proposed_value = models.TextField(blank=True)
    # Empty when the value does not come from a source (shared ORCID typed by hand).
    source = models.CharField(max_length=20, choices=ExternalRecord.Source.choices, blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-detected_at"]

    def __str__(self):
        return f"{self.get_kind_display()} – {self.publication or self.author}"

    @property
    def is_informative(self):
        """Nothing to accept: the conflict can only be acknowledged."""
        return self.kind in (self.Kind.AUTHORS_MISMATCH, self.Kind.SHARED_ORCID)
