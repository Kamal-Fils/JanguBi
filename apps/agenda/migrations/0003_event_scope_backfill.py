"""Chantier 3b — conversion scope_id en FK. Étape 2/3 (data).

Résout legacy_scope_id (désambiguïsé par scope_type) vers les FK. DÉFENSIF :
parish/diocese introuvables flagués + NULL ; province → global + flagué ; jamais
de ligne perdue ni d'exception. Liste imprimée pour reprise manuelle.
"""

from django.db import migrations


def forward(apps, schema_editor):
    from apps.agenda.migration_ops import backfill_event_scope_fks

    Event = apps.get_model("agenda", "Event")
    Parish = apps.get_model("org", "Parish")
    Diocese = apps.get_model("org", "Diocese")

    resolved, flagged = backfill_event_scope_fks(
        Event=Event, Parish=Parish, Diocese=Diocese
    )

    print(f"\n[event_scope_backfill] {resolved} portée(s) résolue(s) en FK.")
    if flagged:
        print(
            f"[event_scope_backfill] ⚠ {len(flagged)} event(s) à reprendre manuellement :"
        )
        for entry in flagged:
            print(
                f"  - event={entry['event_id']} scope_type={entry['scope_type']} "
                f"value={entry['value']} {entry['action']}"
            )
    else:
        print("[event_scope_backfill] Aucun event à reprendre. ✔")


def reverse(apps, schema_editor):
    """Restaure legacy_scope_id depuis la FK posée (best-effort, no-crash).
    La conversion province→global n'est pas réversible (info province perdue)."""
    Event = apps.get_model("agenda", "Event")
    for event in Event.objects.iterator():
        event.legacy_scope_id = event.scope_parish_id or event.scope_diocese_id
        event.save(update_fields=["legacy_scope_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("agenda", "0002_event_scope_fk_pre"),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
