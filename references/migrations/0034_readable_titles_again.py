from django.db import migrations


def refill_readable_titles(apps, schema_editor):
    """
    The readable titles computed again (#345): formula by formula, commands without
    their backslash, old IEEE markup. Only the titles that hold LaTeX or IEEE markup.
    The current conversion is used: a later change only makes it better.
    """
    from django.db.models import Q

    from references.services.imports.titles import readable_title

    Publication = apps.get_model("references", "Publication")
    markers = Q(title__contains="$") | Q(title__contains="\\")
    for marker in ("/spl ", "/sub ", "/sup "):
        markers |= Q(title__contains=marker)
    publications = list(Publication.objects.filter(markers).only("pk", "title"))
    for pub in publications:
        pub.readable_title = readable_title(pub.title)
    Publication.objects.bulk_update(publications, ["readable_title"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [("references", "0033_fetch_queue")]

    operations = [migrations.RunPython(refill_readable_titles, migrations.RunPython.noop)]
