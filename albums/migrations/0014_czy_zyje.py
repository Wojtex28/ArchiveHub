from django.db import migrations, models


def mark_known_deaths(apps, schema_editor):
    """Kto ma wpisaną datę albo miejsce śmierci, ten od razu ma zaznaczone „Nie żyje”."""
    Person = apps.get_model("albums", "Person")
    Person.objects.exclude(death_date="", death_place="").update(deceased=True)


class Migration(migrations.Migration):
    dependencies = [("albums", "0013_ulubione")]

    operations = [
        migrations.AddField(
            model_name="person",
            name="deceased",
            field=models.BooleanField(default=False, verbose_name="nie żyje"),
        ),
        migrations.RunPython(mark_known_deaths, migrations.RunPython.noop),
    ]
