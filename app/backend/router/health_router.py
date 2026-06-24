from fastapi import APIRouter

from backend.schemas.health import HealthResponse

# 健康检查接口
router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="deepresearch-backend")
