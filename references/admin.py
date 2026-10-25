from django.contrib import admin

from .models import (
    Author,
    AuthorDistinction,
    AuthorMerge,
    CitedReference,
    ExternalRecord,
    IncomingCitations,
    MetadataConflict,
    OrcidRecord,
    Organization,
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
    search_fields = ("doi", "preprint_doi", "title")
    list_filter = ("publication_date",)
    ordering = ("title",)

    @admin.display(description="Authors")
    def display_authors(self, obj):
        return ", ".join(str(a) for a in obj.authors.all())


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("pk", "first_name", "last_name", "orcid", "name_edited", "display_publications")
    list_filter = ("name_edited",)
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
    list_display = ("pk", "user", "publication", "added_at", "reading_status")
    list_filter = ("reading_status",)
    list_select_related = ("user", "publication")


@admin.register(ExternalRecord)
class ExternalRecordAdmin(admin.ModelAdmin):
    list_display = ("pk", "publication", "source", "fetched_at")
    list_filter = ("source",)
    list_select_related = ("publication",)


@admin.register(AuthorMerge)
class AuthorMergeAdmin(admin.ModelAdmin):
    list_display = ("kept", "absorbed_names", "reason", "merged_by", "merged_at")
    list_filter = ("reason",)
    raw_id_fields = ("kept",)


@admin.register(AuthorDistinction)
class AuthorDistinctionAdmin(admin.ModelAdmin):
    list_display = ("pk", "first", "second", "declared_by", "declared_at")
    list_select_related = ("first", "second", "declared_by")


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("pk", "name", "ror", "country_code")
    search_fields = ("name", "ror")


@admin.register(MetadataConflict)
class MetadataConflictAdmin(admin.ModelAdmin):
    list_display = ("pk", "kind", "publication", "author", "status", "detected_at")
    list_filter = ("kind", "status")
    list_select_related = ("publication", "author")


@admin.register(OrcidRecord)
class OrcidRecordAdmin(admin.ModelAdmin):
    list_display = ("orcid", "fetched_at", "search_fetched_at")
    search_fields = ("orcid",)


@admin.register(IncomingCitations)
class IncomingCitationsAdmin(admin.ModelAdmin):
    list_display = ("publication", "total", "fetched_at")
    list_select_related = ("publication",)
