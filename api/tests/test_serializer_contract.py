"""Every API relation agrees with its database column about being optional.

Found the hard way: `Prescription.visit` is NOT NULL in the database, but the
serializer declared it optional, so a prescription saved without a visit got
past validation and died on the INSERT — a 500 where the doctor should have
seen "required". Checking each serializer by eye is how that slipped through,
so this derives the answer from the models for all of them at once.
"""

import inspect

from django.test import SimpleTestCase
from rest_framework import serializers

from api.relations import TenantScopedRelatedField
from api.serializers import accounts, appointments, billing, clinical, core, patients


def api_serializers():
    for module in (accounts, appointments, billing, clinical, core, patients):
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(cls, serializers.ModelSerializer)
                and cls.__module__ == module.__name__
                and hasattr(cls, "Meta")
            ):
                yield cls


class RelationNullabilityTests(SimpleTestCase):
    def test_required_relations_match_the_database(self):
        mismatches = []
        for cls in api_serializers():
            model = cls.Meta.model
            # Fields the server fills in itself when they are left out (and
            # refuses with a message when it cannot) — declared per serializer,
            # so an exemption is a visible decision rather than a gap.
            server_filled = getattr(cls.Meta, "server_filled", ())
            for name, field in cls().get_fields().items():
                if not isinstance(field, TenantScopedRelatedField) or name in server_filled:
                    continue
                try:
                    column = model._meta.get_field(field.source or name)
                except Exception:
                    continue
                if not column.null and (field.allow_null or not field.required):
                    mismatches.append(
                        f"{cls.__name__}.{name}: NOT NULL in the database, optional in the API"
                    )
                if column.null and not field.allow_null:
                    mismatches.append(
                        f"{cls.__name__}.{name}: nullable in the database, but the API cannot clear it"
                    )
        self.assertEqual(mismatches, [], "\n" + "\n".join(mismatches))
