from fastapi.testclient import TestClient
import pytest

from roomloop.config.database import DatabaseConnection
from roomloop.modules.rooms.contract import RoomResponse
from roomloop.modules.rooms.repository import RoomRepository
from roomloop.seeding.seeder import DatabaseSeeder
from roomloop.server import Server
from roomloop.shared.models.base import Base


@pytest.fixture
def test_db_server(tmp_path):
    """creates an isolated test database with tables and seed data initialized"""
    db_path = str(tmp_path / "rooms_test.db")
    db = DatabaseConnection(db_path=db_path)
    db.connect()
    Base.metadata.create_all(bind=db.engine)
    seeder = DatabaseSeeder(db)
    seeder.seed_all()
    server = Server(database=db)
    yield server, db
    db.disconnect()


def test_contract_c2_get_rooms(test_db_server):
    """verifies get /rooms strictly complies with contract c2 returning id, name, and capacity"""
    server, _ = test_db_server

    with TestClient(server.fastapi.app) as client:
        # test direct root path /rooms (contract c2 dashboard endpoint)
        res = client.get("/rooms")
        assert res.status_code == 200
        rooms = res.json()
        assert isinstance(rooms, list)
        assert len(rooms) == 4

        # verify exact keys on every item (no internal fields like timezone or is_active leaked)
        for room in rooms:
            assert set(room.keys()) == {"id", "name", "capacity"}
            assert isinstance(room["id"], int)
            assert isinstance(room["name"], str)
            assert isinstance(room["capacity"], int)

        # verify prototype room ids match contract c2 specifications [3, 4, 9, 17]
        room_ids = [room["id"] for room in rooms]
        assert room_ids == [3, 4, 9, 17]

        # verify versioned endpoint /api/v1/rooms also returns identical payload
        res_v1 = client.get("/api/v1/rooms")
        assert res_v1.status_code == 200
        assert res_v1.json() == rooms


def test_r5_sequential_assumption_refuted(test_db_server):
    """verifies that room repository queries only exist for actual ids, refuting r5 sequential 1..n"""
    _, db = test_db_server
    repo = RoomRepository(db)

    # room 1 does not exist in prototype inventory
    assert repo.get_by_id(1) is None
    # room 2 does not exist in prototype inventory
    assert repo.get_by_id(2) is None

    # room 3 (neukölln) exists
    room_3 = repo.get_by_id(3)
    assert room_3 is not None
    assert room_3.name == "Neukölln"
    assert room_3.capacity == 8
    assert room_3.timezone == "Europe/Berlin"


def test_room_response_schema_forbids_extra_fields():
    """verifies that roomresponse contract forbids unexpected attributes"""
    valid = RoomResponse(id=3, name="Neukölln", capacity=8)
    assert valid.id == 3
    assert valid.name == "Neukölln"
    assert valid.capacity == 8

    # extra fields must be rejected
    with pytest.raises(Exception):
        RoomResponse(
            id=3,
            name="Neukölln",
            capacity=8,
            timezone="Europe/Berlin",  # type: ignore
        )
