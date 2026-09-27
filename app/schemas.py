"""HTTP-boundary models for the owner API."""
import re
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

RESERVED = {"_hp", "_t", "widget_id"}


class FieldSpec(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    label: str = Field(min_length=1, max_length=80)
    type: Literal["text", "email", "textarea", "tel"] = "text"
    required: bool = False
    max_length: int = Field(default=200, ge=1, le=2000)

    @field_validator("name")
    @classmethod
    def not_reserved(cls, v):
        if v in RESERVED:
            raise ValueError(f"'{v}' is reserved")
        return v


class Display(BaseModel):
    position: Literal["inline", "bottom-right", "bottom-left"] = "inline"
    theme_color: str = Field(default="#2563eb", pattern=r"^#[0-9a-fA-F]{6}$")


class WidgetIn(BaseModel):
    type: Literal["signup", "contact", "cta"]
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    fields: list[FieldSpec] = Field(min_length=1, max_length=10)
    button_text: str = Field(default="Submit", min_length=1, max_length=40)
    display: Display = Display()
    allowed_origins: list[str] = Field(default_factory=list, max_length=20)
    notify_email: Optional[str] = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    @field_validator("allowed_origins")
    @classmethod
    def origins(cls, v):
        for o in v:
            if not re.fullmatch(r"(https?://[a-zA-Z0-9.-]+(:\d{1,5})?|null)", o):
                raise ValueError(f"invalid origin '{o}' (expected e.g. https://example.com or http://localhost:5500)")
        return v

    @model_validator(mode="after")
    def unique_names(self):
        names = [f.name for f in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("field names must be unique")
        return self


class WidgetPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    fields: Optional[list[FieldSpec]] = Field(default=None, min_length=1, max_length=10)
    button_text: Optional[str] = Field(default=None, min_length=1, max_length=40)
    display: Optional[Display] = None
    allowed_origins: Optional[list[str]] = None
    notify_email: Optional[str] = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    active: Optional[bool] = None


class TenantIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=120)
