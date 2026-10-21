from roomloop.config.database import DatabaseConnection
from roomloop.modules.rooms.repository import RoomRepository
from roomloop.seeding.seeder import DatabaseSeeder
from roomloop.shared.models.base import Base


def test_database_seeder_populates_prototype_rooms(tmp_path):
    """verifies that databaseseeder inserts all 4 prototype rooms"""
    db_path = str(tmp_path / "seeder_test.db")
    db = DatabaseConnection(db_path=db_path)
    db.connect()
    Base.metadata.create_all(bind=db.engine)

    seeder = DatabaseSeeder(db)
    seeder.seed_all()

    repo = RoomRepository(db)
    rooms = repo.list_active()
    assert len(rooms) == 4
    room_ids = [r.id for r in rooms]
    assert room_ids == [3, 4, 9, 17]

    db.disconnect()


def test_database_seeder_is_idempotent(tmp_path):
    """verifies that running databaseseeder multiple times does not duplicate records"""
    db_path = str(tmp_path / "seeder_idempotent_test.db")
    db = DatabaseConnection(db_path=db_path)
    db.connect()
    Base.metadata.create_all(bind=db.engine)

    seeder = DatabaseSeeder(db)
    # run seeder 3 times consecutively
    seeder.seed_all()
    seeder.seed_all()
    seeder.seed_all()

    repo = RoomRepository(db)
    rooms = repo.list_active()
    assert len(rooms) == 4
    names = [r.name for r in rooms]
    assert sorted(names) == ["Kreuzberg", "LoDo", "Neukölln", "RiNo"]

    db.disconnect()
