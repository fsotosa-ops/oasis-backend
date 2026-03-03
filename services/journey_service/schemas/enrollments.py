from datetime import datetime
from typing import Literal, Optional

from pydantic import UUID4, BaseModel, Field


class EnrollmentCreate(BaseModel):
    journey_id: UUID4 = Field(..., description="ID del Journey a iniciar.")
    event_id: Optional[UUID4] = Field(None, description="ID del evento que originó esta inscripción (trazabilidad QR).")


class EnrollmentResponse(BaseModel):
    id: UUID4
    user_id: UUID4
    journey_id: UUID4
    organization_id: UUID4 | None = None
    event_id: UUID4 | None = None
    journey_title: str | None = None
    status: str
    current_step_index: int
    progress_percentage: float
    started_at: datetime
    completed_at: datetime | None = None

    class Config:
        from_attributes = True


class StepProgressRead(BaseModel):
    step_id: UUID4
    title: str
    type: str
    order_index: int
    status: Literal["locked", "available", "completed"]
    completed_at: datetime | None = None
    points_earned: int = 0


class JourneyBasicInfo(BaseModel):
    id: UUID4
    title: str
    slug: str
    description: str | None = None
    thumbnail_url: str | None = None
    total_steps: int = 0


class EnrollmentDetailResponse(BaseModel):
    id: UUID4
    user_id: UUID4
    journey_id: UUID4
    status: str
    current_step_index: int
    progress_percentage: float
    started_at: datetime
    completed_at: datetime | None = None
    journey: JourneyBasicInfo | None = None
    steps_progress: list[StepProgressRead] = Field(default_factory=list)
    completed_steps: int = 0
    total_steps: int = 0

    class Config:
        from_attributes = True


class UpdateEnrollmentEventRequest(BaseModel):
    event_id: UUID4 = Field(..., description="Nuevo event_id para el enrollment activo del usuario en este journey.")


class StepCompleteRequest(BaseModel):
    metadata: dict | None = None
    external_reference: str | None = None
    service_data: dict | None = None


class StepCompleteResponse(BaseModel):
    step_id: UUID4
    completed_at: datetime
    enrollment_progress: float
    points_earned: int = 0
