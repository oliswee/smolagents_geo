"""FastAPI backend for GeoAnalysis Agent (optional).

Provides a REST API alternative to the Gradio UI. Useful for:
- Integration with external dashboards
- Batch analysis requests
- Health checks and monitoring
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import time

app = FastAPI(
    title="GeoAnalysis Agent API",
    description="悉尼城市规划空间资源分析 AI Agent",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent instance (initialized in startup)
_agent = None
_session_manager = None
_retriever = None


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户的自然语言问题")
    session_id: str = Field(default="default", description="会话 ID（多轮对话）")


class ChatResponse(BaseModel):
    response: str = Field(..., description="Agent 的自然语言回答")
    session_id: str
    round: int
    context_summary: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    knowledge_base_chunks: int
    model: str


@app.on_event("startup")
async def startup():
    global _agent, _session_manager, _retriever
    from src.config import load_config
    from src.agent import create_agent_with_kb
    from src.session.session_manager import SessionManager
    from data_warehouse.connection import DatabaseManager

    try:
        config = load_config()
        db_mgr = DatabaseManager(config)
        _, conn = db_mgr.connect()
        _agent, _retriever = create_agent_with_kb(config, conn)
        _session_manager = SessionManager(_agent)
        print("Agent initialized successfully.")
    except Exception as e:
        print(f"Agent initialization failed: {e}")
        print("API will start but agent endpoints will return 503.")


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    from src.config import get_config
    config = get_config()
    return HealthResponse(
        status="ok" if _agent else "agent_not_ready",
        version="1.0.0",
        knowledge_base_chunks=_retriever.vs.count() if _retriever else 0,
        model=config.get("llm", {}).get("model_id", "unknown"),
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Main chat endpoint — send a message and get an agent response."""
    if _session_manager is None:
        raise HTTPException(
            status_code=503,
            detail="Agent not initialized. Check server logs.",
        )

    start_time = time.time()
    try:
        response = _session_manager.chat(request.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    elapsed = time.time() - start_time
    if elapsed > 15:
        # Log slow responses
        print(f"WARNING: Slow response ({elapsed:.1f}s) for query: {request.message[:100]}")

    return ChatResponse(
        response=response,
        session_id=request.session_id,
        round=_session_manager.conversation_round,
        context_summary=_session_manager.get_context_summary(),
    )


@app.post("/chat/reset")
async def reset_chat(session_id: str = "default"):
    """Reset a conversation session."""
    if _session_manager:
        _session_manager.reset()
    return {"status": "ok", "session_id": session_id}


@app.post("/analyze/batch")
async def batch_analyze(queries: List[str]):
    """Analyze multiple queries in sequence (for evaluation)."""
    if _session_manager is None:
        raise HTTPException(status_code=503, detail="Agent not initialized.")

    results = []
    for i, query in enumerate(queries):
        try:
            response = _session_manager.chat(query)
            results.append({"query": query, "response": response, "index": i})
        except Exception as e:
            results.append({"query": query, "error": str(e), "index": i})
        _session_manager.reset()

    return {"results": results, "total": len(queries)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
