from pydantic import BaseModel, ConfigDict

class DomainModel(BaseModel):
    """Immutable, validated base for all TrustLens domain objects."""
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )
