from django.contrib import admin

from .models import Publication, Author


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    list_display = ('pk', 'doi', 'title', 'publication_date', 'date_created', 'date_updated', "display_authors")
    search_fields = ('doi', 'title')
    list_filter = ('publication_date',)
    ordering = ("title",)


    def display_authors(self, obj):
        return ", ".join(str(a) for a in obj.authors.all())

    display_authors.short_description = "Authors"

@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ('pk', 'first_name', 'last_name', 'orcid', "display_publications")
    search_fields = ('first_name', 'last_name', 'orcid')
    ordering = ("last_name",)

    def display_publications(self, obj):
        pubs = obj.publications.all().order_by("authorpublication__order")
        return ", ".join(str(p) for p in pubs)

    display_publications.short_description = "Publications"