from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from references.models import Author, AuthorMerge, AuthorPublication, MetadataConflict, Publication
from references.services import conflicts
from references.services.author_distinctions import declare_distinct
from references.services.author_merge import merge_authors
from references.services.orcid_merge import merge_all_same_orcid, merge_same_orcid
from references.tests.test_orcid_completion import authorship, publication

ORCID = "0000-0002-1937-4040"


def author(first_name, last_name="Prestemon", orcid=ORCID):
    return Author.objects.create(first_name=first_name, last_name=last_name, orcid=orcid)


def sign(author, title="Article"):
    pub = Publication.objects.create(title=title)
    AuthorPublication.objects.create(
        publication=pub,
        author=author,
        order=0,
        published_given_name=author.first_name,
        published_family_name=author.last_name,
    )
    return pub


class MergeSameOrcidTests(TestCase):
    """#158: an ORCID designates one person."""

    def test_holders_are_merged_into_the_oldest_with_the_most_complete_name(self):
        first, second, third = author("S."), author("Soren"), author("S. O.")
        pubs = [sign(first, "A"), sign(second, "B"), sign(third, "C")]
        kept = merge_same_orcid(third)
        self.assertEqual(kept, first)
        self.assertEqual(list(Author.objects.all()), [first])
        first.refresh_from_db()
        self.assertEqual((first.first_name, first.orcid), ("Soren", ORCID))
        self.assertEqual(set(first.publications.all()), set(pubs))

    def test_merge_is_traced_as_automatic(self):
        first, second = author("S."), author("Soren")
        merge_same_orcid(second)
        merge = AuthorMerge.objects.get()
        self.assertEqual((merge.kept, merge.reason, merge.merged_by), (first, "orcid", None))
        self.assertEqual(
            merge.absorbed, [{"first_name": "Soren", "last_name": "Prestemon", "orcid": ORCID}]
        )
        self.assertEqual(merge.absorbed_names, "Soren Prestemon")

    def test_nothing_to_merge(self):
        lone = author("Soren")
        self.assertEqual(merge_same_orcid(lone), lone)
        self.assertEqual(merge_same_orcid(author("Ada", "Lovelace", orcid="")).orcid, "")
        self.assertFalse(AuthorMerge.objects.exists())

    def test_declared_distinct_authors_are_reported_not_merged(self):
        first, second = author("S."), author("Soren")
        declare_distinct([first, second], None)
        self.assertEqual(merge_same_orcid(second), second)
        self.assertEqual(Author.objects.count(), 2)
        conflict = MetadataConflict.objects.get()
        self.assertEqual(
            (conflict.kind, conflict.author, conflict.current_value, conflict.proposed_value),
            (conflicts.Kind.SHARED_ORCID, second, ORCID, "S. Prestemon"),
        )
        self.assertTrue(conflict.is_informative)

    def test_earlier_merges_follow_the_kept_author(self):
        first, second = author("S."), author("Soren", orcid="")
        values = {"first_name": "Soren", "last_name": "Prestemon", "orcid": ORCID}
        merge_authors(second, [author("Søren", orcid="")], values)
        merge_same_orcid(second)
        self.assertEqual(sorted(first.merges.values_list("reason", flat=True)), ["manual", "orcid"])


class CompletionMergeTests(TestCase):
    def test_orcid_completed_by_openalex_merges_the_holders(self):
        holder = author("Yann", "LeCun", orcid="0000-0002-1992-2684")
        publication(
            [{"given": "Y.", "family": "LeCun"}],
            [authorship("Y. LeCun", "0000-0002-1992-2684")],
        )
        self.assertEqual(list(Author.objects.all()), [holder])
        self.assertEqual(holder.publications.count(), 1)
        self.assertEqual(AuthorMerge.objects.get().reason, "orcid")


class MergeAllTests(TestCase):
    def test_command_merges_every_shared_orcid(self):
        author("S."), author("Soren")
        (
            author("E.", "Rochepault", "0000-0002-8483-9107"),
            author("Etienne", "Rochepault", "0000-0002-8483-9107"),
        )
        distinct = [
            author("H.", "Pan", "0000-0001-9620-0573"),
            author("Heng", "Pan", "0000-0001-9620-0573"),
        ]
        declare_distinct(distinct, None)
        out = StringIO()
        call_command("merge_same_orcid", stdout=out)
        self.assertIn("ORCID fusionnés : 2", out.getvalue())
        self.assertIn("déclarés distincts : 1", out.getvalue())
        self.assertEqual(Author.objects.count(), 4)
        self.assertEqual(merge_all_same_orcid(), {"merged": 0, "conflicts": 1})


class ViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        self.client.force_login(self.user)

    def test_orcid_typed_by_hand_merges_into_the_holder(self):
        holder, typed = author("Soren"), author("S.", orcid="")
        response = self.client.post(
            reverse("author_edit", args=[typed.pk]),
            {"first_name": "S.", "last_name": "Prestemon", "orcid": f"https://orcid.org/{ORCID}"},
        )
        self.assertRedirects(response, reverse("author_detail", args=[holder.pk]))
        self.assertEqual(AuthorMerge.objects.get().merged_by, self.user)
        detail = self.client.get(reverse("author_detail", args=[holder.pk]))
        self.assertContains(detail, "S. Prestemon")
        self.assertContains(detail, "même ORCID, par alice")

    def test_orcid_typed_by_hand_on_distinct_authors_warns(self):
        holder, typed = author("Soren"), author("S.", orcid="")
        declare_distinct([holder, typed], self.user)
        response = self.client.post(
            reverse("author_edit", args=[typed.pk]),
            {"first_name": "S.", "last_name": "Prestemon", "orcid": ORCID},
            follow=True,
        )
        self.assertContains(response, "déclarés distincts")
        self.assertEqual(Author.objects.count(), 2)
        conflicts_page = self.client.get(reverse("conflict_list"))
        self.assertContains(conflicts_page, "Porté aussi par")
        self.assertContains(conflicts_page, 'value="seen"')

    def test_manual_merge_is_traced_with_its_user(self):
        first, second = author("S.", orcid=""), author("Soren", orcid="")
        self.client.post(
            reverse("author_merge_confirm", args=[f"{first.pk},{second.pk}"]),
            {"first_name": "Soren", "last_name": "Prestemon", "orcid": ""},
        )
        merge = AuthorMerge.objects.get()
        self.assertEqual((merge.kept, merge.reason, merge.merged_by), (first, "manual", self.user))
        detail = self.client.get(reverse("author_detail", args=[first.pk]))
        self.assertContains(detail, "fusion manuelle, par alice")

    def test_accepted_orcid_conflict_merges_the_holders(self):
        holder, other = author("Soren"), author("S.", orcid="0000-0001-1111-1111")
        conflict = conflicts.report_conflict(
            conflicts.Kind.ORCID,
            author=other,
            field="orcid",
            current=other.orcid,
            proposed=ORCID,
            source="openalex",
        )
        self.client.post(reverse("conflict_resolve", args=[conflict.pk]), {"decision": "accepted"})
        self.assertEqual(list(Author.objects.all()), [holder])
