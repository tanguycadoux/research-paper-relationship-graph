from django.test import SimpleTestCase

from references.services.sources.http import in_batches


class InBatchesTests(SimpleTestCase):
    """The batch loop shared by the clients of the sources (#294)."""

    def test_slices_in_order_and_merges(self):
        seen = []

        def fetch(batch):
            seen.append(batch)
            return {item: item * 10 for item in batch}

        merged = in_batches(list(range(7)), 3, fetch)
        self.assertEqual(seen, [[0, 1, 2], [3, 4, 5], [6]])
        self.assertEqual(merged, {item: item * 10 for item in range(7)})

    def test_failed_batch_is_absent(self):
        merged = in_batches([1, 2, 3], 2, lambda batch: {} if 1 in batch else {3: "ok"})
        self.assertEqual(merged, {3: "ok"})

    def test_no_items_no_call(self):
        self.assertEqual(in_batches([], 50, lambda batch: self.fail("called")), {})
