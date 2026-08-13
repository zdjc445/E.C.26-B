"""错误码与异常层级（方案 §18.1）。

错误对用户只返回可操作信息；完整异常栈只写服务端 trace。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import ValidationError


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    IMAGE_UNAVAILABLE = "IMAGE_UNAVAILABLE"
    VISION_UNAVAILABLE = "VISION_UNAVAILABLE"
    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"
    UNKNOWN_CATEGORY = "UNKNOWN_CATEGORY"
    CONSTRAINT_CONFLICT = "CONSTRAINT_CONFLICT"
    RETRIEVAL_UNAVAILABLE = "RETRIEVAL_UNAVAILABLE"
    PRODUCT_SCHEMA_INVALID = "PRODUCT_SCHEMA_INVALID"
    CHECKPOINT_UNAVAILABLE = "CHECKPOINT_UNAVAILABLE"
    SESSION_CONFLICT = "SESSION_CONFLICT"
    WORKFLOW_STEP_LIMIT = "WORKFLOW_STEP_LIMIT"
    TURN_TIMEOUT = "TURN_TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ShijiajingError(Exception):
    """Agent 领域异常基类。"""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    user_message: str = "内部错误"

    def __init__(self, message: str | None = None, *, user_message: str | None = None) -> None:
        super().__init__(message or self.user_message)
        self.user_message = user_message or self.user_message


class InvalidRequestError(ShijiajingError):
    code = ErrorCode.INVALID_REQUEST
    user_message = "请求参数非法"


class ImageUnavailableError(ShijiajingError):
    code = ErrorCode.IMAGE_UNAVAILABLE
    user_message = "图片不可用"


class VisionUnavailableError(ShijiajingError):
    code = ErrorCode.VISION_UNAVAILABLE
    user_message = "图片识别服务不可用"


class ModelOutputInvalidError(ShijiajingError):
    code = ErrorCode.MODEL_OUTPUT_INVALID
    user_message = "模型输出校验失败"


class UnknownCategoryError(ShijiajingError):
    code = ErrorCode.UNKNOWN_CATEGORY
    user_message = "品类不在当前 taxonomy 中"


class ConstraintConflictError(ShijiajingError):
    code = ErrorCode.CONSTRAINT_CONFLICT
    user_message = "约束冲突"


class RetrievalUnavailableError(ShijiajingError):
    code = ErrorCode.RETRIEVAL_UNAVAILABLE
    user_message = "检索服务不可用"


class ProductSchemaInvalidError(ShijiajingError):
    code = ErrorCode.PRODUCT_SCHEMA_INVALID
    user_message = "商品数据格式非法"


class CheckpointUnavailableError(ShijiajingError):
    code = ErrorCode.CHECKPOINT_UNAVAILABLE
    user_message = "状态存储不可用"


class SessionConflictError(ShijiajingError):
    code = ErrorCode.SESSION_CONFLICT
    user_message = "会话并发冲突，请重试"


class WorkflowStepLimitError(ShijiajingError):
    code = ErrorCode.WORKFLOW_STEP_LIMIT
    user_message = "工作流步数超限"


class TurnTimeoutError(ShijiajingError):
    code = ErrorCode.TURN_TIMEOUT
    user_message = "请求处理超时"


def validation_to_code(exc: ValidationError) -> ErrorCode:
    return ErrorCode.MODEL_OUTPUT_INVALID
