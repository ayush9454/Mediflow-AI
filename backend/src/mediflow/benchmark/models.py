"""Strict inputs for independently authored fixtures and offline run observations."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mediflow.contracts import LaboratoryRow

DATASET_VERSION = "synthetic-labs-v1"
Split = Literal["development", "held-out", "negative"]
Medium = Literal["digital", "scanned"]
Kind = Literal[
    "valid",
    "corrupt",
    "truncated",
    "unreadable",
    "unsupported_category",
    "unsupported_language",
    "password_protected",
    "over_size",
    "over_pages",
]
Nonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Text = Annotated[str, Field(min_length=1, max_length=500)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceRow(InputModel):
    analyte: Text
    result: Text
    unit: Text | None = None
    reference_range: Text | None = None
    abnormality_flag: Text | None = None
    collection_date: Text | None = None

    def quotation(self) -> str:
        return " ".join(value for value in self.model_dump().values() if value is not None)


class SourceDocument(InputModel):
    document_id: Annotated[str, Field(pattern=r"^(dev|hold|neg)-[0-9]{2}$")]
    split: Split
    medium: Medium
    seed: int
    layout: Literal["table", "compact", "ledger"]
    kind: Kind
    pages: tuple[tuple[SourceRow, ...], ...]
    text_lines: tuple[str, ...]

    @model_validator(mode="after")
    def consistent_fixture(self) -> Self:
        if self.kind == "valid" and (not self.pages or not all(self.pages)):
            raise ValueError("Valid fixtures require nonempty source pages.")
        if (self.kind == "valid") != (self.split != "negative"):
            raise ValueError("Only negative fixtures have a rejection kind.")
        return self


class Annotation(InputModel):
    document_id: str
    split: Split
    medium: Medium
    expected_outcome: Literal["succeeded", "rejected"]
    rejection_reason: Kind | None = None
    pages: tuple[str, ...]
    rows: tuple[LaboratoryRow, ...]


class Resource(InputModel):
    """Named measured usage, e.g. cpu_seconds, blob_bytes or provider_input_tokens."""

    name: Text
    unit: Text
    amount: Nonnegative


class Prediction(InputModel):
    document_id: str
    outcome: Literal["succeeded", "rejected", "failed"]
    rejection_reason: Kind | None = None
    rows: tuple[LaboratoryRow, ...] = ()
    latency_seconds: Nonnegative | None = None
    # Manual assessment; absent means unassessed, never zero unsupported claims.
    unsupported_summary_claims: Annotated[int, Field(ge=0)] | None = None
    flagged_rows: Annotated[int, Field(ge=0)] | None = None
    unresolved_rows: Annotated[int, Field(ge=0)] | None = None
    provider_cost_usd: Nonnegative | None = None
    student_credit_charge_usd: Nonnegative | None = None
    out_of_pocket_usd: Nonnegative | None = None
    resources: tuple[Resource, ...] = ()


class PredictionFile(InputModel):
    dataset_version: Literal["synthetic-labs-v1"]
    documents: tuple[Prediction, ...]
