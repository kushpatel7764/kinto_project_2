import os
import re
import threading
import unittest
from collections import defaultdict
from unittest import mock

import webtest
from pyramid.url import parse_url_overrides

from kinto.core import DEFAULT_SETTINGS
from kinto.core.cornice import errors as cornice_errors
from kinto.core.resource.model import Model
from kinto.core.storage import generators
from kinto.core.utils import encode64, follow_subrequest, memcache, sqlalchemy
from kinto.plugins import prometheus, statsd


skip_if_ci = unittest.skipIf("CI" in os.environ, "ci")
skip_if_no_postgresql = unittest.skipIf(sqlalchemy is None, "postgresql is not installed.")
skip_if_no_memcached = unittest.skipIf(memcache is None, "memcached is not installed.")
skip_if_no_statsd = unittest.skipIf(not statsd.statsd_module, "statsd is not installed.")
skip_if_no_prometheus = unittest.skipIf(
    not prometheus.prometheus_module, "prometheus is not installed."
)


class DummyRequest(mock.MagicMock):
    """Fully mocked request."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.upath_info = "/v0/"
        self.registry = mock.MagicMock(settings={**DEFAULT_SETTINGS})
        self.registry.id_generators = defaultdict(generators.UUID4)
        self.GET = {}
        self.headers = {}
        self.errors = cornice_errors.Errors()
        self.authenticated_userid = "bob"
        self.authn_type = "basicauth"
        self.prefixed_userid = "basicauth:bob"
        self.effective_principals = ["system.Everyone", "system.Authenticated", "bob"]
        self.prefixed_principals = self.effective_principals + [self.prefixed_userid]
        self.json = {}
        self.validated = {}
        self.log_context = lambda **kw: kw
        self.matchdict = {}
        self.response = mock.MagicMock(headers={})
        self.application_url = ""  # used by parse_url_overrides

        def route_url(*a, **kw):
            # XXX: refactor DummyRequest to take advantage of `pyramid.testing`
            parts = parse_url_overrides(self, kw)
            return "".join([p for p in parts if p])

        self.route_url = route_url

    follow_subrequest = follow_subrequest


def get_request_class(prefix):
    class PrefixedRequestClass(webtest.app.TestRequest):
        @classmethod
        def blank(cls, path, *args, **kwargs):
            if prefix:
                path = f"/{prefix}{path}"
            return webtest.app.TestRequest.blank(path, *args, **kwargs)

    return PrefixedRequestClass


class FormattedErrorMixin:
    """Test mixin in order to perform advanced error responses assertions."""

    def assertFormattedError(self, response, code, errno, error, message=None, info=None):
        self.assertIn("application/json", response.headers["Content-Type"])
        self.assertEqual(response.json["code"], code)
        self.assertEqual(response.json["errno"], errno.value)
        self.assertEqual(response.json["error"], error)
        if message is not None:
            self.assertIn(message, response.json["message"])
        else:  # pragma: no cover
            self.assertNotIn("message", response.json)

        if info is not None:
            self.assertIn(info, response.json["info"])
        else:  # pragma: no cover
            self.assertNotIn("info", response.json)


def get_user_headers(user, password="secret"):
    """Helper to obtain a Basic Auth authorization headers from the specified
    `user` (e.g. ``"user:pass"``)

    :rtype: dict
    """
    credentials = f"{user}:{password}"
    authorization = f"Basic {encode64(credentials)}"
    return {"Authorization": authorization}


class BaseWebTest:
    """Base Web Test to test your kinto.core service.

    It setups the database before each test and delete it after.
    """

    api_prefix = "v0"
    """URL version prefix"""

    entry_point = None
    """Main application entry"""

    headers = {"Content-Type": "application/json"}

    @classmethod
    def setUpClass(cls):
        cls.app = cls.make_app()
        cls.storage = cls.app.app.registry.storage
        cls.cache = cls.app.app.registry.cache
        cls.permission = cls.app.app.registry.permission

        cls.storage.initialize_schema()
        cls.permission.initialize_schema()
        cls.cache.initialize_schema()

    @classmethod
    def make_app(cls, settings=None, config=None):
        """Instantiate the application and setup requests to use the api
        prefix.

        :param dict settings: extra settings values
        :param pyramid.config.Configurator config: already initialized config
        :returns: webtest application instance
        """
        settings = cls.get_app_settings(extras=settings)

        main = cls.entry_point

        wsgi_app = main({}, config=config, **settings)
        app = webtest.TestApp(wsgi_app)
        app.RequestClass = get_request_class(cls.api_prefix)
        return app

    @classmethod
    def get_app_settings(cls, extras=None):
        """Application settings to be used. Override to tweak default settings
        for the tests.

        :param dict extras: extra settings values
        :rtype: dict
        """
        settings = {**DEFAULT_SETTINGS}

        settings["storage_backend"] = "kinto.core.storage.memory"
        settings["cache_backend"] = "kinto.core.cache.memory"
        settings["permission_backend"] = "kinto.core.permission.memory"

        settings.update(extras or None)

        return settings

    def tearDown(self):
        super().tearDown()
        self.storage.flush()
        self.cache.flush()
        self.permission.flush()


class ThreadMixin:
    def setUp(self):
        super().setUp()
        self._threads = []

    def tearDown(self):
        super().tearDown()

        for thread in self._threads:
            thread.join()

    def _create_thread(self, *args, **kwargs):
        thread = threading.Thread(*args, **kwargs)
        self._threads.append(thread)
        return thread


# Test underscore replacement
class DummyStorage:
    def create(self, **kwargs):
        # Simulate storage behavior by returning the object with an ID
        obj = kwargs["obj"]
        obj["id"] = "test-id"
        return obj


class DummyPermissions:
    def replace_object_permissions(self, obj_id, permissions):
        pass

    def add_principal_to_ace(self, obj_id, permission, principal):
        pass


class DummyResource(Model):
    def __init__(self):
        self.storage = DummyStorage()
        self.permission = DummyPermissions()
        self.resource_name = "test"
        self.parent_id = "parent"
        self.permissions_field = "permissions"
        self.id_generator = lambda: "test-id"
        self.id_field = "id"
        self.modified_field = "last_modified"

    def _annotate(self, obj, obj_id):
        return obj  # Skip annotation for test

    def _allow_write(self, obj_id):
        pass  # Skip permission logic for test

    def replace_bad_characters_in_keys(self, d):
        """Recursively replace dots with underscores in keys."""
        if not isinstance(d, dict):
            return d  # Return non-dict objects unchanged

        new_dict = {}
        for k, v in d.items():
            # Replace dots in the key
            new_key = re.sub(r"[.=+]", "_", k)
            new_dict[new_key] = (
                self.replace_bad_characters_in_keys(v) if isinstance(v, dict) else v
            )
        return new_dict


class TestCreateObject(unittest.TestCase):
    def test_dot_replacement_in_keys(self):
        resource = DummyResource()
        input_obj = {"foo.bar": "value", "baz": "qux", "permissions": {}}
        result = resource.create_object(input_obj.copy())
        self.assertIn("foo_bar", result)
        self.assertNotIn("foo.bar", result)
        self.assertEqual(result["foo_bar"], "value")
        self.assertEqual(result["baz"], "qux")

        input_obj = {"foo+bar": "value", "baz": "qux", "permissions": {}}
        result = resource.create_object(input_obj.copy())
        self.assertIn("foo_bar", result)
        self.assertNotIn("foo+bar", result)
        self.assertEqual(result["foo_bar"], "value")
        self.assertEqual(result["baz"], "qux")

        input_obj = {"foo=bar": "value", "baz": "qux", "permissions": {}}
        result = resource.create_object(input_obj.copy())
        self.assertIn("foo_bar", result)
        self.assertNotIn("foo=bar", result)
        self.assertEqual(result["foo_bar"], "value")
        self.assertEqual(result["baz"], "qux")


class TestSpecialCharacterKeys(unittest.TestCase):
    def setUp(self):
        self.resource = Model()
        self.resource.storage = MockStorage()
        self.resource.permission = MockPermission()
        self.resource.resource_name = "test"
        self.resource.parent_id = "parent"
        self.resource.id_field = "id"
        self.resource.modified_field = "last_modified"
        self.resource.id_generator = lambda: "generated-id"
        self.resource._annotate = lambda obj, perm_id: obj
        self.resource._allow_write = lambda perm_id: None

    def test_create_object_with_allowed_special_char_keys(self):
        special_keys_obj = {
            "key-with-dash": "dash",
            "key#hash": "hash",
            "key!exclaim": "exclaim",
            "key*star": "star",
            "key~tilde": "tilde",
            "key@at": "at",
        }

        created = self.resource.create_object(special_keys_obj)

        self.assertIn("key-with-dash", created)
        self.assertEqual(created["key-with-dash"], "dash")

        self.assertIn("key#hash", created)
        self.assertEqual(created["key#hash"], "hash")

        self.assertIn("key!exclaim", created)
        self.assertEqual(created["key!exclaim"], "exclaim")

        self.assertIn("key*star", created)
        self.assertEqual(created["key*star"], "star")

        self.assertIn("key~tilde", created)
        self.assertEqual(created["key~tilde"], "tilde")

        self.assertIn("key@at", created)
        self.assertEqual(created["key@at"], "at")


class MockStorage:
    def create(self, resource_name, parent_id, obj, id_generator, id_field, modified_field):
        obj["id"] = id_generator()
        obj["last_modified"] = 1234567890
        return obj


class MockPermission:
    def replace_object_permissions(self, perm_object_id, permissions):
        pass
