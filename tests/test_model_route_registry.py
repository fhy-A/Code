import json
from pathlib import Path
import tempfile
import threading
import unittest

from code_runtime.model_route_registry import ModelRouteError, ModelRouteRegistry


class ModelRouteRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "model-routes.json"
        self.registry = ModelRouteRegistry(self.path)

    def tearDown(self):
        self.tempdir.cleanup()

    def connection(self, **overrides):
        value = {
            "connectionId": "manual_11111111-1111-4111-8111-111111111111",
            "source": "manual",
            "group": "manual",
            "label": "Synthetic manual",
            "baseUrl": "https://synthetic.invalid",
            "key": "sk-synthetic-secret",
            "enabled": True,
        }
        value.update(overrides)
        return value

    def test_catalog_is_secret_free_and_route_ref_is_opaque(self):
        snapshot = self.registry.refresh(
            [self.connection()],
            lambda _connection: ["model-a", "model-b"],
        )
        self.assertTrue(snapshot["ok"])
        self.assertEqual(snapshot["catalogRevision"], 1)
        self.assertEqual([item["modelId"] for item in snapshot["routes"]], ["model-a", "model-b"])
        route_ref = snapshot["routes"][0]["routeRef"]
        self.assertTrue(route_ref.startswith("mr1_"))
        self.assertNotIn("model-a", route_ref)
        self.assertEqual(
            set(snapshot["routes"][0]),
            {
                "routeRef", "connectionId", "source", "modelId", "label",
                "enabled", "credentialsAvailable",
            },
        )

        durable = self.path.read_text(encoding="utf-8")
        public = json.dumps(snapshot, ensure_ascii=False)
        for forbidden in ("sk-synthetic-secret", "https://synthetic.invalid"):
            self.assertNotIn(forbidden, durable)
            self.assertNotIn(forbidden, public)

    def test_workbar_connection_and_route_identity_are_stable_across_restart(self):
        connection_id = self.registry.workbar_connection_id(
            "https://synthetic.invalid", "7", "42",
        )
        connection = self.connection(connectionId=connection_id, source="workbar", group="premium")
        first = self.registry.refresh([connection], lambda _connection: ["shared-model"])
        restarted = ModelRouteRegistry(self.path)
        second_connection_id = restarted.workbar_connection_id(
            "https://synthetic.invalid", "7", "42",
        )
        second = restarted.refresh(
            [self.connection(connectionId=second_connection_id, source="workbar", group="premium")],
            lambda _connection: ["shared-model"],
        )
        self.assertEqual(connection_id, second_connection_id)
        self.assertEqual(first["routes"][0]["routeRef"], second["routes"][0]["routeRef"])
        self.assertEqual(first["catalogRevision"], second["catalogRevision"])

    def test_connection_and_model_are_the_only_public_route_identity(self):
        first = self.registry.refresh(
            [self.connection(group="price-a", label="DeepSeek")],
            lambda _connection: ["shared-model"],
        )
        route_ref = first["routes"][0]["routeRef"]
        second = self.registry.refresh(
            [self.connection(group="price-b", label="Renamed connection")],
            lambda _connection: ["shared-model"],
        )
        self.assertEqual(second["routes"][0]["routeRef"], route_ref)

        third = self.registry.refresh(
            [
                self.connection(group="price-b", label="Renamed connection"),
                self.connection(
                    connectionId="manual_22222222-2222-4222-8222-222222222222",
                    key="sk-second-synthetic-secret",
                    label="workbar",
                ),
            ],
            lambda _connection: ["shared-model"],
        )
        refs = {route["connectionId"]: route["routeRef"] for route in third["routes"]}
        self.assertEqual(len(refs), 2)
        self.assertNotEqual(*refs.values())
        self.assertEqual(refs[self.connection()["connectionId"]], route_ref)

        custom = self.registry.refresh(
            [self.connection(source="custom-openai")],
            lambda _connection: ["shared-model"],
        )
        self.assertEqual(custom["routes"][0]["routeRef"], route_ref)
        self.assertEqual(custom["routes"][0]["source"], "custom-openai")

    def test_model_limits_intersect_real_catalog_and_revision_changes_on_disable(self):
        limited = self.connection(
            modelLimitsEnabled=True,
            modelLimits=["model-b", "model-c"],
        )
        first = self.registry.refresh([limited], lambda _connection: ["model-a", "model-b"])
        self.assertEqual([item["modelId"] for item in first["routes"]], ["model-b"])
        route_ref = first["routes"][0]["routeRef"]

        second = self.registry.refresh(
            [{**limited, "enabled": False}],
            lambda _connection: self.fail("disabled connections must not be fetched"),
        )
        self.assertGreater(second["catalogRevision"], first["catalogRevision"])
        self.assertTrue(second["ok"])
        self.assertEqual(second["routes"], [])
        with self.assertRaises(ModelRouteError) as captured:
            self.registry.resolve(route_ref, second["catalogRevision"], "model-b")
        self.assertEqual(captured.exception.code, "route_catalog_unavailable")

    def test_disabling_the_last_connection_removes_routes_and_credentials(self):
        first = self.registry.refresh(
            [self.connection()],
            lambda _connection: ["model-a"],
        )
        route_ref = first["routes"][0]["routeRef"]

        disabled = self.registry.refresh(
            [{**self.connection(), "enabled": False}],
            lambda _connection: self.fail("disabled connections must not be fetched"),
        )

        self.assertTrue(disabled["ok"])
        self.assertEqual(disabled["routes"], [])
        self.assertGreater(disabled["catalogRevision"], first["catalogRevision"])
        with self.assertRaises(ModelRouteError) as captured:
            self.registry.resolve(route_ref, disabled["catalogRevision"], "model-a")
        self.assertEqual(captured.exception.code, "route_catalog_unavailable")

    def test_removing_one_connection_preserves_only_the_other_overlapping_route(self):
        kept_connection = self.connection(
            connectionId="manual_22222222-2222-4222-8222-222222222222",
            key="sk-second-synthetic-secret",
            label="Kept",
        )
        first = self.registry.refresh(
            [self.connection(label="Removed"), kept_connection],
            lambda _connection: ["shared-model"],
        )
        refs = {route["label"]: route["routeRef"] for route in first["routes"]}

        remaining = self.registry.refresh(
            [kept_connection],
            lambda _connection: ["shared-model"],
        )

        self.assertTrue(remaining["ok"])
        self.assertEqual(
            [(route["label"], route["routeRef"]) for route in remaining["routes"]],
            [("Kept", refs["Kept"])],
        )
        with self.assertRaises(ModelRouteError) as captured:
            self.registry.resolve(
                refs["Removed"], remaining["catalogRevision"], "shared-model",
            )
        self.assertEqual(captured.exception.code, "route_not_found")
        resolved = self.registry.resolve(
            refs["Kept"], remaining["catalogRevision"], "shared-model",
        )
        self.assertEqual(resolved.key, "sk-second-synthetic-secret")

    def test_refresh_empty_is_authoritative_and_removes_every_connection(self):
        second = self.connection(
            connectionId="manual_22222222-2222-4222-8222-222222222222",
            key="sk-second-synthetic-secret",
        )
        first = self.registry.refresh(
            [self.connection(), second],
            lambda _connection: ["shared-model"],
        )
        old_refs = [route["routeRef"] for route in first["routes"]]

        cleared = self.registry.refresh(
            [],
            lambda _connection: self.fail("empty refresh must not fetch models"),
        )

        self.assertTrue(cleared["ok"])
        self.assertEqual(cleared["routes"], [])
        self.assertGreater(cleared["catalogRevision"], first["catalogRevision"])
        for route_ref in old_refs:
            with self.subTest(route_ref=route_ref), self.assertRaises(ModelRouteError) as captured:
                self.registry.resolve(route_ref, cleared["catalogRevision"], "shared-model")
            self.assertEqual(captured.exception.code, "route_catalog_unavailable")
        restarted = ModelRouteRegistry(self.path)
        self.assertEqual(restarted.snapshot()["routes"], [])
        with self.assertRaises(ModelRouteError) as captured:
            restarted.resolve(old_refs[0], cleared["catalogRevision"], "shared-model")
        self.assertEqual(captured.exception.code, "route_catalog_unavailable")

    def test_newer_empty_refresh_wins_over_an_older_inflight_catalog(self):
        initial = self.registry.refresh(
            [self.connection()],
            lambda _connection: ["model-a"],
        )
        route_ref = initial["routes"][0]["routeRef"]
        fetch_started = threading.Event()
        release_fetch = threading.Event()
        results = {}

        def slow_fetch(_connection):
            fetch_started.set()
            self.assertTrue(release_fetch.wait(2))
            return ["model-a", "model-b"]

        old_refresh = threading.Thread(target=lambda: results.update(
            old=self.registry.refresh([self.connection()], slow_fetch)
        ))
        old_refresh.start()
        self.assertTrue(fetch_started.wait(1))

        delete_refresh = threading.Thread(target=lambda: results.update(
            deleted=self.registry.refresh([], lambda _connection: self.fail(
                "empty refresh must not fetch models"
            ))
        ))
        delete_refresh.start()
        self.assertTrue(delete_refresh.is_alive())
        release_fetch.set()
        old_refresh.join(2)
        delete_refresh.join(2)

        self.assertFalse(old_refresh.is_alive())
        self.assertFalse(delete_refresh.is_alive())
        self.assertEqual(results["deleted"]["routes"], [])
        self.assertEqual(self.registry.snapshot()["routes"], [])
        with self.assertRaises(ModelRouteError) as captured:
            self.registry.resolve(
                route_ref,
                results["deleted"]["catalogRevision"],
                "model-a",
            )
        self.assertEqual(captured.exception.code, "route_catalog_unavailable")

    def test_resolve_enforces_revision_model_and_runtime_credentials(self):
        first = self.registry.refresh([self.connection()], lambda _connection: ["model-a"])
        route_ref = first["routes"][0]["routeRef"]
        resolved = self.registry.resolve(route_ref, first["catalogRevision"], "model-a")
        self.assertEqual(resolved.key, "sk-synthetic-secret")
        self.assertEqual(resolved.model_id, "model-a")

        cases = [
            (route_ref, first["catalogRevision"] + 1, "model-a", "route_stale"),
            ("mr1_" + "0" * 64, first["catalogRevision"], "model-a", "route_not_found"),
            (route_ref, first["catalogRevision"], "model-b", "route_model_mismatch"),
        ]
        for candidate_ref, revision, model, code in cases:
            with self.subTest(code=code), self.assertRaises(ModelRouteError) as captured:
                self.registry.resolve(candidate_ref, revision, model)
            self.assertEqual(captured.exception.code, code)

        restarted = ModelRouteRegistry(self.path)
        with self.assertRaises(ModelRouteError) as captured:
            restarted.resolve(route_ref, first["catalogRevision"], "model-a")
        self.assertEqual(captured.exception.code, "route_credentials_unavailable")

    def test_catalog_failure_retains_identity_but_drops_credentials(self):
        first = self.registry.refresh([self.connection()], lambda _connection: ["model-a"])
        route_ref = first["routes"][0]["routeRef"]
        failed = self.registry.refresh(
            [self.connection()],
            lambda _connection: (_ for _ in ()).throw(TimeoutError("secret upstream detail")),
        )
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["routes"][0]["routeRef"], route_ref)
        self.assertEqual(failed["failures"], [{
            "connectionId": "manual_11111111-1111-4111-8111-111111111111",
            "code": "route_catalog_unavailable",
        }])
        self.assertNotIn("secret upstream detail", json.dumps(failed))
        with self.assertRaises(ModelRouteError) as captured:
            self.registry.resolve(route_ref, failed["catalogRevision"], "model-a")
        self.assertEqual(captured.exception.code, "route_credentials_unavailable")

    def test_healthy_resolve_does_not_wait_for_refresh_and_identical_refreshes_coalesce(self):
        initial = self.registry.refresh([self.connection()], lambda _connection: ["model-a"])
        route_ref = initial["routes"][0]["routeRef"]
        fetch_started = threading.Event()
        release_fetch = threading.Event()
        duplicate_fetch_called = threading.Event()
        results = []

        def slow_fetch(_connection):
            fetch_started.set()
            self.assertTrue(release_fetch.wait(2))
            return ["model-a"]

        first = threading.Thread(target=lambda: results.append(
            self.registry.refresh([self.connection()], slow_fetch)
        ))
        first.start()
        self.assertTrue(fetch_started.wait(1))

        resolved = []
        resolve_done = threading.Event()
        resolver = threading.Thread(target=lambda: (
            resolved.append(self.registry.resolve(
                route_ref, initial["catalogRevision"], "model-a",
            )),
            resolve_done.set(),
        ))
        resolver.start()
        self.assertTrue(resolve_done.wait(0.5), "healthy resolve waited for catalog refresh")

        def forbidden_duplicate_fetch(_connection):
            duplicate_fetch_called.set()
            return ["model-a"]

        second = threading.Thread(target=lambda: results.append(
            self.registry.refresh([self.connection()], forbidden_duplicate_fetch)
        ))
        second.start()
        release_fetch.set()
        first.join(2)
        second.join(2)
        resolver.join(2)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertFalse(duplicate_fetch_called.is_set())
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1])
        self.assertEqual(resolved[0].route_ref, route_ref)


if __name__ == "__main__":
    unittest.main()
