"""Dwoje rodziców jednego dziecka to para: dopisuje brakujące pary w istniejącym drzewie."""

from django.db import migrations


def pair_parents(apps, schema_editor):
    ParentChild = apps.get_model("family", "ParentChild")
    Partnership = apps.get_model("family", "Partnership")
    parents_of = {}
    for parent_id, child_id in ParentChild.objects.values_list("parent_id", "child_id"):
        parents_of.setdefault(child_id, []).append(parent_id)
    for ids in parents_of.values():
        if len(ids) == 2:
            first, second = sorted(ids)
            Partnership.objects.get_or_create(person1_id=first, person2_id=second)


class Migration(migrations.Migration):
    dependencies = [("family", "0002_cofanie_zmian")]

    operations = [migrations.RunPython(pair_parents, migrations.RunPython.noop)]
