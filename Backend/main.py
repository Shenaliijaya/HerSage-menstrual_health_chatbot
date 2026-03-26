from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

from ontology_manager import OntologyManager
from llm_manager import LLMManager
from chat_service import ChatService

app = FastAPI(title="Menstrual Health Ontology Chatbot API")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialise once at startup
ontology     = OntologyManager()
llm          = LLMManager()
chat_service = ChatService(ontology, llm)


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message:    str
    lang:       str = "en"
    culture:    str = "general"   # NEW: cultural context


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest):
    return chat_service.chat(req.session_id, req.message, req.lang, req.culture)
