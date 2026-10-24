from fastapi import APIRouter
from app.api.v1.endpoints import router as v1_endpoints

api_router = APIRouter()
api_router.include_router(v1_endpoints)
