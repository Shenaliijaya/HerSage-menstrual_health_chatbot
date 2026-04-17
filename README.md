# HerSage – Menstrual Health Chatbot (Prototype)

HerSage is a prototype web-based chatbot for menstrual health education, built with a FastAPI backend and a simple HTML/JS frontend. It uses a custom OWL ontology and, optionally, a local LLM (Ollama) to polish responses.

---

## 1. Requirements

- Python 3.10 or above
- Google Chrome or another modern browser
- **Ontology file**:
  - Place `menstrual.owl` in a `data/` folder in the project root, or
  - Set the `OWL_PATH` environment variable to the full path of your ontology file.[file:304][file:310]
- Optional (for LLM‑polished answers):
  - [Ollama](https://ollama.com/) installed locally
  - Model pulled and available: `mistral:7b-instruct-q4_0` (default in `config.py`)[file:304]
  - Ollama running at `http://localhost:11434` or adjust `OLLAMA_URL` in `config.py`.[file:304]

---

## 2. Backend Setup

1. Create and activate a virtual environment (recommended):

   ```bash
   python -m venv venv
   source venv/bin/activate        # Linux / macOS
   # venv\Scripts\activate         # Windows
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```
   (FastAPI, Uvicorn, Pydantic, Requests, rdflib)[file:314]

3. Ensure the ontology file is available:

   - Create `data/` and copy `menstrual.owl` into it, **or**
   - Set `OWL_PATH` in the environment to your ontology path.[file:304][file:310]

4. (Optional) Enable LLM polishing:

   - Make sure Ollama is running and the `mistral:7b-instruct-q4_0` model is installed.[file:304][file:306]
   - In `config.py`, `ENABLE_LLM_POLISH = True` uses the LLM; set it to `False` for ontology‑only mode.[file:304]

5. Run the backend:

   ```bash
   uvicorn main:app --reload
   ```

   - Health check: `GET http://127.0.0.1:8000/health`.[file:307]
   - Chat endpoint: `POST http://127.0.0.1:8000/chat`.[file:307]

---

## 3. Frontend Setup

1. Make sure the backend is running on `http://127.0.0.1:8000`.

2. From the folder containing `index.html`, serve the files (for PWA and service worker):

   ```bash
   python -m http.server 8080
   ```

3. Open the chatbot:

   ```text
   http://localhost:8080/index.html
   ```

   The frontend uses the `API_URL` configured in `app.js` (local URL `http://127.0.0.1:8000/chat` is already present).[file:300][file:303]

---

## 4. Minimal Notes

- All session and feedback data are stored in memory only (prototype stage).[file:309]
- Security and deployment are prototype level; this is **not** intended for real clinical use.