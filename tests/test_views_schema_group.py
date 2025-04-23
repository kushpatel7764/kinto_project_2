from kinto.core.testing import unittest

from .support import BaseWebTest


BUCKET_URL = "/buckets/blog"
GROUPS_URL = "/buckets/blog/groups"
GROUP_URL = GROUPS_URL + "/tarnac-nine"


SCHEMA = {
    "title": "Group schema",
    "type": "object",
    "required": ["phone"],
    "properties": {
        "phone": {"type": "string"},
        "members": {"type": "array", "items": {"type": "string"}},
    },
}

VALID_GROUP = {"members": ["oidc:coupat"], "phone": "+33688776655"}


class DeactivatedSchemaTest(BaseWebTest, unittest.TestCase):
    def test_schema_should_be_json_schema(self):
        newschema = {**SCHEMA, "type": "Washmachine"}
        resp = self.app.put_json(
            BUCKET_URL, {"data": {"group:schema": newschema}}, headers=self.headers, status=400
        )
        error_msg = "'Washmachine' is not valid under any of the given schemas"
        self.assertIn(error_msg, resp.json["message"])

    def test_group_are_not_invalid_if_do_not_match_schema(self):
        self.app.put_json(BUCKET_URL, {"data": {"group:schema": SCHEMA}}, headers=self.headers)
        self.app.put_json(GROUP_URL, {"data": {"phone": 42}}, headers=self.headers, status=201)


class BaseWebTestWithSchema(BaseWebTest):
    @classmethod
    def get_app_settings(cls, extras=None):
        settings = super().get_app_settings(extras)
        settings["experimental_collection_schema_validation"] = "True"
        return settings


class GroupValidationTest(BaseWebTestWithSchema, unittest.TestCase):
    def setUp(self):
        super().setUp()
        resp = self.app.put_json(
            BUCKET_URL, {"data": {"group:schema": SCHEMA}}, headers=self.headers
        )
        self.collection = resp.json["data"]

    def tearDown(self):
        # Clean up the group if it was created
        try:
            self.app.delete(GROUP_URL, headers=self.headers)
        except Exception:
            print(
                "Group wasn't created or already deleted"
            )  # In case the group wasn't created or already deleted

        # Clean up the bucket
        try:
            self.app.delete(BUCKET_URL, headers=self.headers)
        except Exception:
            print("Bucket wasn't deleted")

    def test_empty_metadata_can_be_validated(self):
        self.app.post_json(BUCKET_URL + "/groups", headers=self.headers, status=400)
        self.app.post_json(BUCKET_URL + "/groups", {"data": {}}, headers=self.headers, status=400)

    def test_groups_are_valid_if_match_schema(self):
        self.app.put_json(GROUP_URL, {"data": VALID_GROUP}, headers=self.headers, status=201)

    def test_groups_are_invalid_if_do_not_match_schema(self):
        self.app.put_json(GROUP_URL, {"data": {"phone": 42}}, headers=self.headers, status=400)


class ValidateIDField(BaseWebTestWithSchema, unittest.TestCase):
    def setUp(self):
        super().setUp()
        schema = {"type": "object", "properties": {"id": {"type": "string", "pattern": "^[0-7]$"}}}
        self.app.put_json(BUCKET_URL, {"data": {"group:schema": schema}}, headers=self.headers)

    def tearDown(self):
        # Attempt to clean up any group with ID "1"
        try:
            resp = self.app.get(GROUPS_URL, headers=self.headers)
            for group in resp.json["data"]:
                group_id = group["id"]
                self.app.delete(f"{GROUPS_URL}/{group_id}", headers=self.headers)
        except Exception:
            print("Group not found")  # Ignore if not found

        # Remove the bucket
        try:
            self.app.delete(BUCKET_URL, headers=self.headers)
        except Exception:
            print("Bucket not found")

    def test_group_id_is_accepted_if_valid(self):
        self.app.post_json(GROUPS_URL, {"data": {"id": "1"}}, headers=self.headers)

    def test_group_id_is_rejected_if_does_not_match(self):
        self.app.post_json(GROUPS_URL, {"data": {"id": "a"}}, headers=self.headers, status=400)


SCHEMA_UNRESOLVABLE = {"properties": {"phone": {"$ref": "#/definitions/phone"}}}


class CollectionUnresolvableTest(BaseWebTestWithSchema, unittest.TestCase):
    def setUp(self):
        super().setUp()
        resp = self.app.put_json(
            BUCKET_URL, {"data": {"group:schema": SCHEMA_UNRESOLVABLE}}, headers=self.headers
        )
        self.collection = resp.json["data"]

    def tearDown(self):
        try:
            self.app.delete(BUCKET_URL, headers=self.headers)
        except Exception:
            print("Bucket not found")

    def test_unresolvable_errors_handled(self):
        self.app.put_json(GROUP_URL, {"data": {"phone": 42}}, headers=self.headers, status=400)
