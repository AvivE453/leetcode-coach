import json

from coach import curriculum
from coach.config import CATALOG_PATH


def test_list_sizes():
    assert len(curriculum.load("blind75")) == 75
    assert len(curriculum.load("neetcode150")) == 150


def test_no_duplicates():
    for name in curriculum.FLAG_COLUMNS:
        slugs = curriculum.load(name)
        assert len(slugs) == len(set(slugs)), f"duplicates in {name}"


def test_blind75_is_subset_of_neetcode150():
    assert set(curriculum.load("blind75")) <= set(curriculum.load("neetcode150"))


def test_all_slugs_exist_in_catalog():
    catalog_slugs = {p["slug"] for p in json.loads(CATALOG_PATH.read_text())}
    for name in curriculum.FLAG_COLUMNS:
        missing = set(curriculum.load(name)) - catalog_slugs
        assert not missing, f"{name} slugs not in catalog: {sorted(missing)}"
