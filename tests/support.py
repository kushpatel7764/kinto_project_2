from kinto import DEFAULT_SETTINGS
from kinto import main as kinto_main
from kinto.core import testing


MINIMALIST_BUCKET = {}
MINIMALIST_COLLECTION = {}
MINIMALIST_GROUP = {"data": dict(members=["fxa:user"])}
MINIMALIST_RECORD = {"data": dict(name="Hulled Barley", type="Whole Grain")}
USER_PRINCIPAL = "basicauth:8a931a10fc88ab2f6d1cc02a07d3a81b5d4768f6f13e85c5d8d4180419acb1b4"


class BaseWebTest(testing.BaseWebTest):
    api_prefix = "v1"
    entry_point = kinto_main
    principal = USER_PRINCIPAL

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.headers.update(testing.get_user_headers("mat"))

    @classmethod
    def get_app_settings(cls, extras=None):
        settings = {**DEFAULT_SETTINGS, "multiauth.policies": "basicauth"}
        if extras is not None:
            settings.update(extras)
        settings = super().get_app_settings(extras=settings)
        return settings

    def create_group(self, bucket_id, group_id, members=None):
        if members is None:
            group = MINIMALIST_GROUP
        else:
            group = {"data": {"members": members}}
        group_url = "/buckets/{}/groups/{}".format(bucket_id, group_id)
        self.app.put_json(group_url, group, headers=self.headers, status=201)

    def create_bucket(self, bucket_id):
        self.app.put_json(
            "/buckets/{}".format(bucket_id), MINIMALIST_BUCKET, headers=self.headers, status=201
        )

    @classmethod
    def tearDownClass(cls):
        # Deletes everything inside the buckets and then the buckets themselves
        # Use the headers to delete the buckets
        buckets = cls.app.get("/buckets", headers=cls.headers).json["data"]
        for bucket in buckets:
            bucket_id = bucket["id"]
            # Delete everything inside the buckets
            groups = cls.app.get(f"/buckets/{bucket_id}/groups", headers=cls.headers).json["data"]
            for group in groups:
                group_id = group["id"]
                cls.app.delete(f"/buckets/{bucket_id}/groups/{group_id}", headers=cls.headers)

            # Finally delete the bucket
            cls.app.delete(f"/buckets/{bucket_id}", headers=cls.headers)

        super().tearDownClass()
