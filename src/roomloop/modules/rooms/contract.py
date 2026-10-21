from pydantic import BaseModel, ConfigDict, Field


class RoomResponse(BaseModel):
    """contract c2 response schema strictly exposing only id, name, and capacity"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int = Field(ge=1, description="Unique room identifier")
    name: str = Field(
        min_length=1, max_length=50, description="Display name of meeting room"
    )
    capacity: int = Field(gt=0, description="Maximum seated room capacity")
