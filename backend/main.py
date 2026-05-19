"""
main.py
-------
FastAPI application entry point.

Start the server:
    uvicorn main:app --reload --port 8000

Swagger UI: http://localhost:8000/docs
ReDoc:      http://localhost:8000/redoc
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.neo4j import get_driver, close_driver
from database.create_indexes import create_indexes
from routes.course_routes import router as course_router
from routes.subject_routes import router as subject_router
from routes.graph_routes import router as graph_router
from routes.similarity_routes import router as similarity_router
from routes.viz_routes import router as viz_router
from services.cache_warmer import start_cache_warmer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting up — connecting to Neo4j ...")
    get_driver()
    create_indexes()
    start_cache_warmer()
    yield
    log.info("Shutting down — closing Neo4j driver ...")
    close_driver()


app = FastAPI(
    title="UTS Curriculum Digital Twin API",
    description=(
        "Explore UTS course structures, subject details, "
        "and requisite relationships stored in Neo4j."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(course_router)
app.include_router(subject_router)
app.include_router(graph_router)
app.include_router(similarity_router)
app.include_router(viz_router)


@app.get("/", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "UTS Curriculum Digital Twin API"}
