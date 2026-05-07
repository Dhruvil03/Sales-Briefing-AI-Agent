from fastapi import APIRouter
router = APIRouter()

@router.get("/health", tags=["Health"])
def health()    :
    return {"ok": True}