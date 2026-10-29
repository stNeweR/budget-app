from pydantic import BaseModel

from app.schemas.auth import FamilyMemberOut, FamilyOut


class FamilyDetailOut(BaseModel):
    family: FamilyOut
    members: list[FamilyMemberOut]
