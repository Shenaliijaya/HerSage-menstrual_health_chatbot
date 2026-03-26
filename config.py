import os

# ── Ontology ──────────────────────────────────────────────────────────────────
# Place your menstrual_enhanced.owl inside a /data folder as menstrual.owl
# OR set the OWL_PATH environment variable to point elsewhere
OWL_PATH = os.getenv("OWL_PATH", "data/menstrual.owl")

# ── Ollama (local LLM) ────────────────────────────────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct-q4_0")
OLLAMA_URL    = os.getenv("OLLAMA_URL",   "http://localhost:11434")

# ── Feature flags ─────────────────────────────────────────────────────────────
# LLM polish is NOW ENABLED - Mistral polishes ontology facts into natural language
ENABLE_LLM_POLISH = False

# ── Response limits ───────────────────────────────────────────────────────────
EXAMPLE_LIMIT = 3           # matches your original value
TOP_K_FACTS   = 12          # max ontology facts retrieved per query
