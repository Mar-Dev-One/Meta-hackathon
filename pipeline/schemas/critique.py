"""The critic's verdict on one shot: scores against the rubric, measured
numbers, and fixes written in Studio terms for the director to apply."""

from typing import Literal

from pydantic import Field

from .storyboard import Strict

Category = Literal["composition", "lighting", "product_visibility", "brand", "continuity", "titles"]


class Scores(Strict):
    composition: int = Field(ge=0, le=10, description="balance, negative space, product placement")
    lighting: int = Field(ge=0, le=10, description="shape revealed, separation from the background, mood")
    product_visibility: int = Field(ge=0, le=10, description="whole, readable, the clear subject")
    brand: int = Field(ge=0, le=10, description="colours, materials and type true to the brand profile")
    continuity: int = Field(ge=0, le=10, description="fits with the shots around it")
    titles: int = Field(ge=0, le=10, description="readable, well placed, not over the product; 10 when there are none")


class Issue(Strict):
    severity: Literal["minor", "major"]
    category: Category
    time: float | None = Field(None, description="seconds into the ad where it shows")
    problem: str = Field(description="what's wrong, concretely: 'the cap is cut by the top edge'")
    fix: str = Field(description="what to change, in Studio terms: 'fill 0.6 instead of 0.9', 'rim intensity x1.5'")


class Critique(Strict):
    shot: str = Field(description="the shot's id")
    iteration: int = Field(ge=0, description="0 for the first look, +1 per revision")
    frames: list[float] = Field(description="the times it looked at")
    scores: Scores
    passed: bool = Field(description="every score 7 or more and no major issue")
    issues: list[Issue] = Field(default_factory=list)
    measured: dict[str, float] = Field(default_factory=dict, description="the renderer's numbers it used: fill, centre, cut edges, contrast ...")
