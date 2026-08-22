from fastapi import APIRouter

from goldenson_api.api.agent import router as agent_router
from goldenson_api.api.blocks import router as blocks_router
from goldenson_api.api.files import router as files_router
from goldenson_api.api.health import router as health_router
from goldenson_api.api.local_ai import router as local_ai_router
from goldenson_api.api.pages import router as pages_router
from goldenson_api.api.workspaces import router as workspaces_router

router = APIRouter()
router.include_router(health_router)
router.include_router(local_ai_router)
router.include_router(agent_router)
router.include_router(workspaces_router)
router.include_router(pages_router)
router.include_router(blocks_router)
router.include_router(files_router)
