from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


ReactionType = Literal["like", "support", "insightful", "concern"]


class ReactionCreate(BaseModel):
    reaction_type: ReactionType = "like"


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    parent_id: Optional[int] = None

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Nội dung bình luận không được để trống")
        return normalized


class RoiCommentCreate(BaseModel):
    reply_to_id: Optional[int] = None
    visual_label: str = Field(min_length=1, max_length=120)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content", "visual_label")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Gia tri khong duoc de trong")
        return normalized

    @field_validator("width")
    @classmethod
    def validate_x_extent(cls, value: float, info):
        x = info.data.get("x", 0)
        if x + value > 1:
            raise ValueError("ROI vuot qua chieu ngang anh")
        return value

    @field_validator("height")
    @classmethod
    def validate_y_extent(cls, value: float, info):
        y = info.data.get("y", 0)
        if y + value > 1:
            raise ValueError("ROI vuot qua chieu doc anh")
        return value
