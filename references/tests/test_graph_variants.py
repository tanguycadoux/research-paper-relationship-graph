import datetime
import json

from django.http import QueryDict
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import CitedReference, Publication
from references.services.display.graph_variants import graph_layout, variant_links


def graph_of(*dates):
    return {"nodes": [{"data": {"id": str(i), "date": date}} for i, date in enumerate(dates)]}


class VariantTests(SimpleTestCase):
    """Variants of the layout of a graph, chosen in the URL (#288)."""

    def test_default_is_the_column_on_the_left(self):
        self.assertEqual(graph_layout(QueryDict("")), {"non_dates": "gauche"})

    def test_chosen_value(self):
        self.assertEqual(graph_layout(QueryDict("non_dates=bande")), {"non_dates": "bande"})

    def test_unknown_value_falls_back_to_the_default(self):
        self.assertEqual(graph_layout(QueryDict("non_dates=haut")), {"non_dates": "gauche"})

    def test_links_select_each_choice_and_keep_other_parameters(self):
        [variant] = variant_links(QueryDict("tag=Projet&non_dates=bande"), graph_of(None))
        self.assertEqual(variant["label"], "Non datés")
        options = {option["label"]: option for option in variant["options"]}
        self.assertEqual(
            QueryDict(options["À gauche"]["query"]).dict(), {"tag": "Projet", "non_dates": "gauche"}
        )
        self.assertFalse(options["À gauche"]["current"])
        self.assertTrue(options["En bas"]["current"])

    def test_no_choice_without_undated_publication(self):
        self.assertEqual(variant_links(QueryDict(""), graph_of("2020-01-01")), [])


class GraphPageVariantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = Publication.objects.create(
            title="Source", publication_date=datetime.date(2020, 1, 1)
        )
        cls.undated = Publication.objects.create(title="Sans date")
        cls.dated = Publication.objects.create(
            title="Datée", publication_date=datetime.date(2010, 1, 1)
        )
        CitedReference.objects.create(source=cls.source, target=cls.undated, position=0)
        CitedReference.objects.create(source=cls.source, target=cls.dated, position=1)

    def layout(self, response):
        start = response.content.decode().index('id="citation-graph-layout"')
        data = response.content.decode()[start:].split(">", 1)[1].split("</script>", 1)[0]
        return json.loads(data)

    def test_page_embeds_the_chosen_layout(self):
        url = reverse("publication_graph", args=[self.source.pk])
        self.assertEqual(self.layout(self.client.get(url)), {"non_dates": "gauche"})
        response = self.client.get(url, {"non_dates": "bande"})
        self.assertEqual(self.layout(response), {"non_dates": "bande"})
        self.assertContains(response, 'aria-current="true">En bas</a>', html=False)
        self.assertContains(response, 'id="citation-graph-band"')

    def test_no_selector_without_undated_publication(self):
        self.undated.publication_date = datetime.date(2015, 1, 1)
        self.undated.save()
        response = self.client.get(reverse("publication_graph", args=[self.source.pk]))
        self.assertNotContains(response, "Disposition du graphe")
        self.assertEqual(self.layout(response), {"non_dates": "gauche"})

    def test_base_graph_offers_the_choice(self):
        response = self.client.get(reverse("base_graph"))
        self.assertContains(response, "Disposition du graphe : non datés")
        self.assertContains(response, 'href="?non_dates=bande"')
