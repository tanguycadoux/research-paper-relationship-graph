from django.conf import settings
from django.db import models, transaction

from .services.doi import normalize_doi
from .services.isbn import normalize_isbn


class Publication(models.Model):
    doi = models.CharField(max_length=255, blank=True)
    isbn = models.CharField("ISBN", max_length=13, blank=True)
    title = models.TextField(blank=True)
    publication_date = models.DateField(null=True, blank=True)
    authors = models.ManyToManyField(
        "Author", through="AuthorPublication", related_name="publications", blank=True
    )
    # True once the publication is in a corpus: its cited references are imported.
    parse_references = models.BooleanField(default=False)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["doi"], condition=~models.Q(doi=""), name="unique_non_empty_doi"
            ),
            models.UniqueConstraint(
                fields=["isbn"], condition=~models.Q(isbn=""), name="unique_non_empty_isbn"
            ),
        ]

    def __str__(self):
        return self.title or self.doi or self.isbn or f"PK : {self.pk}"

    def save(self, *args, **kwargs):
        self.doi = normalize_doi(self.doi)
        self.isbn = normalize_isbn(self.isbn)
        super().save(*args, **kwargs)


class ExternalRecord(models.Model):
    """
    Answer of an external source about a publication, stored as is. data is None
    when the source answered that it does not know the publication.
    """

    class Source(models.TextChoices):
        CROSSREF = "crossref", "Crossref"
        DATACITE = "datacite", "DataCite"
        OPENLIBRARY = "openlibrary", "Open Library"

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

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()

    @transaction.atomic
    def merge_with(self, others: list["Author"]):
        """
        Move the publications of the other authors to this one, then delete them.
        The published names stay on each publication, so the merge survives re-imports.
        """
        for other in others:
            AuthorPublication.objects.filter(author=other).update(author=self)
            other.delete()


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
        return (
            self.unstructured
            or self.raw.get("article-title")
            or self.raw.get("volume-title")
            or self.raw.get("journal-title")
            or self.key
        )


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
