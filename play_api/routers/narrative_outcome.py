"""Narrative outcome distribution endpoints for Story and Session scopes."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from play_api.routers._locator import resolve_session_or_404
from rpg_core.rp_modules.narrative_outcome import NARRATIVE_OUTCOME_DEFINITIONS
from rpg_core.settings import settings
from rpg_data import models
from rpg_data.services import get_data_service_gateway


router = APIRouter(tags=["play-narrative-outcome"])
WeightValue = Annotated[int, Field(strict=True, ge=0, le=100)]


class PlayNarrativeOutcomeWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    critical_success: WeightValue
    success: WeightValue
    success_with_cost: WeightValue
    setback: WeightValue
    critical_failure: WeightValue

    @model_validator(mode="after")
    def _total_must_equal_one_hundred(self):
        if sum(self.model_dump().values()) != 100:
            raise ValueError("narrative outcome weights must sum to 100")
        return self

    def to_data(self) -> models.NarrativeOutcomeWeights:
        return models.NarrativeOutcomeWeights.from_mapping(self.model_dump())

    @classmethod
    def from_data(
        cls,
        weights: models.NarrativeOutcomeWeights,
    ) -> "PlayNarrativeOutcomeWeights":
        return cls.model_validate(weights.to_dict())


class PlayNarrativeOutcomeDefinition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    label: str
    narrative_guidance: str = Field(alias="narrativeGuidance")


class PlayNarrativeOutcomePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weights: PlayNarrativeOutcomeWeights | None


class PlayNarrativeOutcomeConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    definitions: list[PlayNarrativeOutcomeDefinition]
    system_default: PlayNarrativeOutcomeWeights = Field(alias="systemDefault")
    story_override: PlayNarrativeOutcomeWeights | None = Field(alias="storyOverride")
    session_override: PlayNarrativeOutcomeWeights | None = Field(alias="sessionOverride")
    effective_weights: PlayNarrativeOutcomeWeights = Field(alias="effectiveWeights")
    effective_source: Literal["config", "story", "session"] = Field(alias="effectiveSource")


def _default_weights() -> models.NarrativeOutcomeWeights:
    return settings.rp_module_settings.narrative_outcome.default_weights


def _response(selection: models.NarrativeOutcomeSelection) -> PlayNarrativeOutcomeConfig:
    return PlayNarrativeOutcomeConfig(
        definitions=[
            PlayNarrativeOutcomeDefinition.model_validate(definition.to_public_dict())
            for definition in NARRATIVE_OUTCOME_DEFINITIONS
        ],
        systemDefault=PlayNarrativeOutcomeWeights.from_data(selection.config_default),
        storyOverride=(
            PlayNarrativeOutcomeWeights.from_data(selection.story_weights)
            if selection.story_weights is not None
            else None
        ),
        sessionOverride=(
            PlayNarrativeOutcomeWeights.from_data(selection.session_weights)
            if selection.session_weights is not None
            else None
        ),
        effectiveWeights=PlayNarrativeOutcomeWeights.from_data(
            selection.effective_weights
        ),
        effectiveSource=selection.effective_source,
    )


@router.get(
    "/workspaces/{workspace_id}/stories/{story_id}/narrative-outcome",
    response_model=PlayNarrativeOutcomeConfig,
)
async def get_story_narrative_outcome(
    workspace_id: str,
    story_id: int,
) -> PlayNarrativeOutcomeConfig:
    selection = get_data_service_gateway().narrative_outcomes.get_story_selection(
        workspace_id,
        story_id,
        _default_weights(),
    )
    if selection is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return _response(selection)


@router.patch(
    "/workspaces/{workspace_id}/stories/{story_id}/narrative-outcome",
    response_model=PlayNarrativeOutcomeConfig,
)
async def patch_story_narrative_outcome(
    workspace_id: str,
    story_id: int,
    payload: PlayNarrativeOutcomePatch,
) -> PlayNarrativeOutcomeConfig:
    selection = get_data_service_gateway().narrative_outcomes.set_story_weights(
        workspace_id,
        story_id,
        payload.weights.to_data() if payload.weights is not None else None,
        _default_weights(),
    )
    if selection is None:
        raise HTTPException(status_code=404, detail="story not found in workspace")
    return _response(selection)


@router.get(
    "/sessions/{session_id}/narrative-outcome",
    response_model=PlayNarrativeOutcomeConfig,
)
async def get_session_narrative_outcome(
    session_id: str,
) -> PlayNarrativeOutcomeConfig:
    await resolve_session_or_404(session_id)
    selection = get_data_service_gateway().narrative_outcomes.get_session_selection(
        session_id,
        _default_weights(),
    )
    if selection is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _response(selection)


@router.patch(
    "/sessions/{session_id}/narrative-outcome",
    response_model=PlayNarrativeOutcomeConfig,
)
async def patch_session_narrative_outcome(
    session_id: str,
    payload: PlayNarrativeOutcomePatch,
) -> PlayNarrativeOutcomeConfig:
    await resolve_session_or_404(session_id)
    selection = get_data_service_gateway().narrative_outcomes.set_session_weights(
        session_id,
        payload.weights.to_data() if payload.weights is not None else None,
        _default_weights(),
    )
    if selection is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _response(selection)
