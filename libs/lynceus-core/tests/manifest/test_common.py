# libs/lynceus-core/tests/manifest/__init__.py


import pytest
from lynceus_core import Manifest


def test_save_and_load(tmp_path):
    temp_path = tmp_path / "test_manifest.json"
    manifest = Manifest({"app": "web", "version": 1.0}, filepath=temp_path)

    assert not manifest.exists()
    manifest.save()
    assert manifest.exists()

    loaded_manifest = Manifest(filepath=temp_path).load()
    assert manifest.data == loaded_manifest.data


def test_load_file_not_found():
    with pytest.raises(FileNotFoundError):
        Manifest(filepath="/path/that/does/not/exist.json").load()


@pytest.mark.parametrize(
    "sub_data, full_data, expected",
    [
        # Basic dictionaries
        ({"a": 1, "c": 3}, {"a": 1, "b": 2, "c": 3}, True),
        ({"a": 1, "d": 4}, {"a": 1, "b": 2, "c": 3}, False),
        # Nested dictionaries
        (
            {"meta": {"author": "alice"}},
            {"meta": {"author": "alice", "date": "2026-10-22"}, "env": "prod"},
            True,
        ),
        (
            {"meta": {"author": "bob"}},
            {"meta": {"author": "alice", "date": "2026-10-22"}, "env": "prod"},
            False,
        ),
        # Arrays (Strict order & length required)
        ({"tags": ["api", "backend"]}, {"tags": ["api", "backend"]}, True),
        ({"tags": ["backend", "api"]}, {"tags": ["api", "backend"]}, False),
        ({"tags": ["api"]}, {"tags": ["api", "backend"]}, False),
        ({"tags": ["api", "backend", "v1"]}, {"tags": ["api", "backend"]}, False),
        # Arrays with nested dict subsets
        (
            {"services": [{"name": "auth"}, {"port": 5432}]},
            {
                "services": [
                    {"name": "auth", "port": 8080},
                    {"name": "db", "port": 5432},
                ]
            },
            True,
        ),
        (
            {"services": [{"port": 5432}, {"name": "auth"}]},
            {
                "services": [
                    {"name": "auth", "port": 8080},
                    {"name": "db", "port": 5432},
                ]
            },
            False,
        ),
        # Type mismatches
        ({"port": "8080"}, {"port": 8080, "config": {"timeout": 30}}, False),
        (
            {"config": [{"timeout": 30}]},
            {"port": 8080, "config": {"timeout": 30}},
            False,
        ),
    ],
)
def test_manifest_subset(sub_data, full_data, expected):
    assert (Manifest(sub_data) <= Manifest(full_data)) is expected


def test_strict_equality():
    manifest1 = Manifest({"a": 1, "b": 2})

    assert manifest1 == Manifest({"a": 1, "b": 2})
    assert manifest1 == Manifest({"b": 2, "a": 1})  # Dict key order doesn't matter
    assert manifest1 != Manifest({"a": 1})
    assert manifest1 == {"a": 1, "b": 2}
