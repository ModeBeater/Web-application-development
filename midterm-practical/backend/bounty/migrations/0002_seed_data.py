"""Prefill the database: 8 wanted criminals and 14 journal entries (runs once, on the first migrate)."""

from datetime import timedelta

from django.db import migrations
from django.utils import timezone

CRIMINALS = [
    # name, nickname, reward, lat, lon, note, difficulty, armed, has_crew, escape_master
    ("Asimov Solensan", "Red Eye Runner", 2500000, 19.6, 85.2, "Tijuana orbital spaceport, last seen boarding a freighter", 7, True, False, False),
    (None, "Ghost of Ganymede", 9000000, -14.2, 44.9, "Ganymede sea-ports, moves between fishing platforms", 9, True, True, True),
    ("Teddy Bomber", "Teddy", 4500000, None, None, "No fixed location; strikes skyscrapers in domed cities", 6, True, False, True),
    ("Pierrot Le Fou", "Mad Pierrot", 12000000, 25.4, 98.7, "Abandoned theme park outside Mars City", 10, True, False, True),
    ("Udai Taxim", "The Syndicate Accountant", 1800000, 33.9, 123.1, "Europa prison transport, escorted", 4, False, True, False),
    (None, "Twinkle Maria", 3200000, None, None, "Last ping from a Jupiter-bound tanker, cargo deck", 5, False, True, True),
    ("Decker Vasquez", "Decker", 1500000, -2.8, 32.5, "Asteroid belt mining colony, hangar 7", 3, True, False, False),
    ("Rhint Celonias", "Rhint", 800000, 51.0, -7.4, "Blue Crow, Callisto; local card dens", 2, False, False, False),
]

HUNTS = [
    # criminal index (1-based), success, notes, days ago
    (1, False, "Target escaped through an asteroid field.", 20),
    (1, True, "Captured at the spaceport customs line; bounty paid in full.", 18),
    (2, False, "Lost the signal in a storm over the Ganymede sea.", 15),
    (2, False, "Decoy ship; the real one left two hours earlier.", 11),
    (3, False, "Bomb threat forced evacuation; suspect blended into the crowd.", 14),
    (3, True, "Cornered on the roof after the fourth bombing attempt.", 9),
    (4, False, "Ship damaged; retreat. Do not engage alone.", 8),
    (5, True, "Handed over at Europa prison without a fight.", 7),
    (6, False, "Boarded the wrong tanker.", 6),
    (6, False, "She was on the cargo deck but vanished behind a bulkhead.", 4),
    (7, True, "Hangar 7 ambush worked; minor ship damage.", 3),
    (8, True, "Found at a card table, surrendered immediately.", 2),
    (8, False, "False tip from an informant.", 1),
    (4, False, "Theme park search found only traps and toys.", 0),
]


def seed(apps, schema_editor):
    WantedCriminal = apps.get_model("bounty", "WantedCriminal")
    HuntLog = apps.get_model("bounty", "HuntLog")
    if WantedCriminal.objects.exists():
        return
    created = []
    for name, nickname, reward, lat, lon, note, difficulty, armed, crew, escape in CRIMINALS:
        created.append(WantedCriminal.objects.create(
            name=name, nickname=nickname, reward=reward, latitude=lat, longitude=lon, location_note=note,
            difficulty=difficulty, armed=armed, has_crew=crew, escape_master=escape,
        ))
    now = timezone.now()
    for index, success, notes, days_ago in HUNTS:
        hunt = HuntLog.objects.create(criminal=created[index - 1], success=success, notes=notes)
        HuntLog.objects.filter(pk=hunt.pk).update(created_at=now - timedelta(days=days_ago, hours=index))  # bypass auto_now_add


def unseed(apps, schema_editor):
    apps.get_model("bounty", "WantedCriminal").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("bounty", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
