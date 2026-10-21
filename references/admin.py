from django.contrib import admin

from .models import (
    Author,
    AuthorDistinction,
    CitedReference,
    ExternalRecord,
    Publication,
    UserPublication,
)


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "doi",
        "title",
        "publication_date",
        "date_created",
        "date_updated",
        "display_authors",
    )
    search_fields = ("doi", "title")
    list_filter = ("publication_date",)
    ordering = ("title",)

    @admin.display(description="Authors")
    def display_authors(self, obj):
        return ", ".join(str(a) for a in obj.authors.all())


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("pk", "first_name", "last_name", "orcid", "display_publications")
    search_fields = ("first_name", "last_name", "orcid")
    ordering = ("last_name",)

    @admin.display(description="Publications")
    def display_publications(self, obj):
        pubs = obj.publications.all().order_by("authorpublication__order")
        return ", ".join(str(p) for p in pubs)


@admin.register(CitedReference)
class CitedReferenceAdmin(admin.ModelAdmin):
    list_display = ("pk", "source", "position", "doi", "target")
    list_select_related = ("source", "target")
    search_fields = ("doi", "unstructured", "source__title")


@admin.register(UserPublication)
class UserPublicationAdmin(admin.ModelAdmin):
    list_display = ("pk", "user", "publication", "added_at")
    list_select_related = ("user", "publication")


@admin.register(ExternalRecord)
class ExternalRecordAdmin(admin.ModelAdmin):
    list_display = ("pk", "publication", "source", "fetched_at")
    list_filter = ("source",)
    list_select_related = ("publication",)


@admin.register(AuthorDistinction)
class AuthorDistinctionAdmin(admin.ModelAdmin):
    list_display = ("pk", "first", "second", "declared_by", "declared_at")
    list_select_related = ("first", "second", "declared_by")
