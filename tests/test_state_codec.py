from devforge.persistence import JsonStore
from devforge.state import decode_snapshot, encode_snapshot


def test_decode_snapshot_returns_typed_sections() -> None:
    store = JsonStore("src/devforge/fixtures")
    snapshot = store.load_snapshot("game_project")
    typed = decode_snapshot(snapshot)

    assert typed["initiative"].initiative_id == "game-001"
    assert typed["projects"][0].project_id == "game-client"
    assert typed["work_packages"][0].work_package_id == "wp-combat-core"
    assert typed["seams"][0].seam_id == "seam-client-server-combat"


def test_encode_snapshot_round_trips_typed_snapshot() -> None:
    store = JsonStore("src/devforge/fixtures")
    snapshot = store.load_snapshot("ecommerce_project")
    typed = decode_snapshot(snapshot)
    encoded = encode_snapshot(typed)

    assert encoded["initiative"]["initiative_id"] == "shop-001"
    assert encoded["projects"][0]["project_id"] == "shop-web"
    assert encoded["work_packages"][0]["work_package_id"] == "wp-cart-frontend"
