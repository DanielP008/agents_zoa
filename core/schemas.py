"""Pydantic models for structured LLM output (agent decisions)."""

from pydantic import BaseModel, Field


class ReceptionistDecision(BaseModel):
    """Decision model for the receptionist agent."""
    domain: str | None = Field(
        default=None,
        description="El dominio detectado (siniestros, gestion, ventas) si está claro, o null si no."
    )
    message: str | None = Field(
        default=None,
        description="Respuesta natural al usuario si no se detecta dominio o se requiere más información."
    )
    nif: str | None = Field(
        default=None,
        description="NIF/DNI/NIE/CIF extraído del mensaje del usuario, si está presente."
    )
    confidence: float | None = Field(
        default=0.0,
        description="Nivel de confianza de la clasificación (0.0 a 1.0).",
        ge=0.0,
        le=1.0
    )


class ClassificationDecision(BaseModel):
    """Generic decision model for domain classifier agents."""
    route: str = Field(
        description="The target agent or specialist to route to. Use the specific names provided in the system prompt."
    )
    confidence: float = Field(
        default=0.0,
        description="Confidence score between 0.0 and 1.0.",
        ge=0.0,
        le=1.0
    )
    needs_more_info: bool = Field(
        default=True,
        description="Set to True if you need to ask the user a clarifying question before routing. Set to False if you are confident or want to end the chat."
    )
    action: str | None = Field(
        default="route",
        description="The action to take. 'route' to send to a specialist, or 'end_chat' if the user is just saying goodbye or doesn't need anything else."
    )
    question: str = Field(
        default="",
        description="The question to ask the user if needs_more_info is True. Otherwise, an empty string or polite closing."
    )
