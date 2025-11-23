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
    # references = models.ManyToManyField('self', blank=True)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    reference_level = models.PositiveIntegerField(default=0)


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

class AuthorPublication(models.Model):
    publication = models.ForeignKey("Publication", on_delete=models.CASCADE)
    author = models.ForeignKey("Author", on_delete=models.CASCADE)
    order = models.PositiveIntegerField()


    class Meta:
        unique_together = ('publication', 'author')
        ordering = ['order']


    def __str__(self):
        return f"{self.order} – {self.author}"
