"""
database/neo4j.py
-----------------
Centralised Neo4j connection and query runner.
All other layers call run_query() — nothing else talks to the driver directly.
"""

import os
import logging
from typing import Any, Optional

from neo4j import GraphDatabase, Driver

log = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "Trungvip2404@")

_driver: Optional[Driver] = None


def get_driver():
    global _driver
    if _driver is None:
        log.info("Initialising Neo4j driver -> %s", NEO4J_URI)
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
        log.info("Neo4j driver closed.")


def run_query(query: str, params: Optional[dict] = None) -> list:
    """
    Execute a Cypher query and return all records as plain dicts.
    Raises RuntimeError with a clear message on failure so FastAPI
    returns a readable 500 instead of a bare crash.
    """
    driver = get_driver()
    params = params or {}
    try:
        with driver.session() as session:
            result = session.run(query, params)
            return result.data()
    except Exception as exc:
        log.error("Neo4j query failed: %s\nQuery: %s\nParams: %s", exc, query, params)
        raise RuntimeError(f"Neo4j query error: {exc}") from exc
