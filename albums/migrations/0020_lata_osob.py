from django.db import migrations


def fill_years(apps, schema_editor):
    """ETAP 62: przelicza lata urodzenia i śmierci z tekstu dat (część osób miała datę bez roku)."""
    from albums.models import person_year

    Person = apps.get_model("albums", "Person")
    for person in Person.objects.exclude(birth_date="", death_date=""):
        born, died = person_year(person.birth_date), person_year(person.death_date)
        if (born, died) != (person.birth_year, person.death_year):
            person.birth_year, person.death_year = born, died
            person.save(update_fields=["birth_year", "death_year"])


class Migration(migrations.Migration):
    dependencies = [("albums", "0019_moje_albumy_i_lata")]

    operations = [migrations.RunPython(fill_years, migrations.RunPython.noop)]
