from django.contrib.auth.models import User
from django.db import models


class Publication(models.Model):
    doi = models.CharField(max_length=100, blank=True)
    crossref_json = models.JSONField(blank=True, null=True)
    title = models.CharField(max_length=300, null=True, blank=True)
    publication_date = models.DateField(null=True, blank=True)
    authors = models.ManyToManyField(
        "Author",
        through="AuthorPublication",
        related_name="publications",
        blank=True
    )
    references = models.ManyToManyField(
        "self",
        through="PublicationReference",
        symmetrical=False,
        related_name="cited_by",
    )
    parse_references = models.BooleanField(default=True)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)


    def save(self, *args, **kwargs):
        if self.doi:
            self.doi = self.doi.lower().replace('https://doi.org/', '').strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title or self.doi or f'PK : {self.pk}'

class Author(models.Model):
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    orcid = models.CharField(max_length=50, blank=True, null=True)


    def __str__(self):
        return f"{self.first_name or ''} {self.last_name or ''}".strip()
    

    def merge_with(self, others: list["Author"]):
        from .models import AuthorPublication  # éviter les imports circulaires

        for other in others:
            AuthorPublication.objects.filter(author=other).update(author=self)

            # Ici éventuellement fusionner les ORCID, emails, affiliations etc.
            # Selon ce que tu décideras.

            # Puis supprimer l'ancien auteur
            other.delete()
        return None

class AuthorPublication(models.Model):
    publication = models.ForeignKey("Publication", on_delete=models.CASCADE)
    author = models.ForeignKey("Author", on_delete=models.CASCADE)
    order = models.PositiveIntegerField()


    class Meta:
        unique_together = ('publication', 'author')
        ordering = ['order']


    def __str__(self):
        return f"{self.order} – {self.author}"

class PublicationReference(models.Model):
    source = models.ForeignKey(
        "Publication",
        related_name="outgoing_references",
        on_delete=models.CASCADE
    )
    target = models.ForeignKey(
        "Publication",
        related_name="incoming_references",
        on_delete=models.CASCADE
    )
    ref_key = models.PositiveIntegerField()
    
    class Meta:
        unique_together = ("source", "target")
        ordering = ["ref_key"]

    def __str__(self):
        return f"{self.source} → {self.target} (ref {self.ref_key})"

class UserPublication(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'publication')
