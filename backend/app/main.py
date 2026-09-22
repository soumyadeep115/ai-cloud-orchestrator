from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  

from .routers.clusters import router as clusters_router
from .routers.predictions import router as predictions_router

from .routers.clusters import router as clusters_router

app = FastAPI(
    title="AI Cloud Orchestrator API",
    version="0.1.0",
    description="Phase 1 monitoring API for Kind clusters and Prometheus metrics.",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ↑↑↑ END OF ADDITION

app.include_router(clusters_router)

app.include_router(clusters_router)
app.include_router(predictions_router)

@app.get("/health")
def health():
    return {"status": "ok"}