// --- Config ---
const API_URL = "https://hersage-menstrual-health-chatbot-api.onrender.com/chat"; 

let sessionId = localStorage.getItem("session_id") || null;

// FR09: feedback store
const feedbackStore = {};
let messageIndex = 0;

// --- Elements ---
const chatDiv      = document.getElementById("chat");
const msgInput     = document.getElementById("msg");
const sendBtn      = document.getElementById("send");
const showFacts    = document.getElementById("showFacts");
const sessionBadge = document.getElementById("sessionBadge");
const statusBadge  = document.getElementById("statusBadge");

// --- HTML escape ---
function escapeHtml(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// --- Safe markdown renderer ---
function renderSafeMarkdown(text) {
  const raw     = String(text ?? "");
  const escaped = escapeHtml(raw);
  const lines   = escaped.split(/\r?\n/);
  let html = "";
  let inUl = false;
  const closeUl = () => { if (inUl) { html += "</ul>"; inUl = false; } };
  for (let line of lines) {
    const bulletMatch = line.match(/^\s*-\s+(.*)$/);
    if (bulletMatch) {
      if (!inUl) { html += "<ul>"; inUl = true; }
      let li = bulletMatch[1].replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
      html += "<li>" + li + "</li>";
      continue;
    }
    closeUl();
    line = line.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    line = line.replace(/\*(.+?)\*/g, "<em>$1</em>");
    html += line.trim() === "" ? "<br>" : line + "<br>";
  }
  closeUl();
  return html.replace(/(<br>\s*)+$/g, "");
}

// --- FR10: Myth detection (uses backend flag) ---
function detectMyth(answerText, facts, backendFlag) {
  if (backendFlag === true) return true;
  const factsText = (facts || []).join(" ").toLowerCase();
  return factsText.includes("mythab") || factsText.includes("menstrualmyth") ||
         factsText.includes("myth about") || factsText.includes("false belief");
}

// --- FR10: Render myth/fact card ---
function renderMythCard(text) {
  const card = document.createElement("div");
  card.className = "myth-card";
  const upper = text.toUpperCase();
  const hasMythMarker = upper.includes("MYTH:") || upper.includes("MYTH -");
  const hasFactMarker  = upper.includes("FACT:") || upper.includes("FACT -");
  if (hasMythMarker || hasFactMarker) {
    const mythMatch = text.match(/MYTH[:\s-]+(.+?)(?=FACT[:\s-]|$)/si);
    const factMatch = text.match(/FACT[:\s-]+(.+)/si);
    const mythPart  = mythMatch ? mythMatch[1].trim() : "";
    const factPart  = factMatch ? factMatch[1].trim() : "";
    if (mythPart) {
      const md = document.createElement("div");
      md.className = "myth-section";
      md.innerHTML = "<span class='myth-badge'>MYTH</span><p>" + escapeHtml(mythPart) + "</p>";
      card.appendChild(md);
    }
    if (factPart) {
      const fd = document.createElement("div");
      fd.className = "fact-section";
      fd.innerHTML = "<span class='fact-badge'>FACT</span><p>" + escapeHtml(factPart) + "</p>";
      card.appendChild(fd);
    }
    if (!mythPart && !factPart) {
      card.innerHTML = "<span class='myth-badge'>MYTH / FACT</span><div class='myth-body'>" + renderSafeMarkdown(text) + "</div>";
    }
  } else {
    card.innerHTML = "<span class='myth-badge'>MYTH / FACT</span><div class='myth-body'>" + renderSafeMarkdown(text) + "</div>";
  }
  return card;
}

// --- FR09: Feedback bar ---
function createFeedbackBar(idx) {
  const bar = document.createElement("div");
  bar.className = "feedback-bar";
  const label = document.createElement("span");
  label.className = "feedback-label";
  label.textContent = "Was this helpful?";
  const thumbUp   = document.createElement("button");
  thumbUp.className = "thumb-btn";
  thumbUp.innerHTML = "&#128077;";
  thumbUp.title = "Helpful";
  const thumbDown = document.createElement("button");
  thumbDown.className = "thumb-btn";
  thumbDown.innerHTML = "&#128078;";
  thumbDown.title = "Not helpful";
  const thanks = document.createElement("span");
  thanks.className = "feedback-thanks";
  thanks.style.display = "none";
  thanks.textContent = "Thanks for your feedback!";
  function hideBtns() {
    label.style.display     = "none";
    thumbUp.style.display   = "none";
    thumbDown.style.display = "none";
    thanks.style.display    = "inline";
  }
  thumbUp.addEventListener("click",   function() { feedbackStore[idx] = "up";   thumbUp.classList.add("active-up");   hideBtns(); });
  thumbDown.addEventListener("click", function() { feedbackStore[idx] = "down"; thumbDown.classList.add("active-down"); hideBtns(); });
  bar.appendChild(label);
  bar.appendChild(thumbUp);
  bar.appendChild(thumbDown);
  bar.appendChild(thanks);
  return bar;
}

// --- Bot avatar ---
function makeBotAvatar() {
  const a = document.createElement("div");
  a.className = "bot-avatar";
  const img = document.createElement("img");
  img.src = "HerSage.png";
  img.alt = "HerSage";
  a.appendChild(img);
  return a;
}

// --- Status helpers ---
function setStatus(text) { statusBadge.textContent = text; }
function updateSessionBadge() {
  sessionBadge.textContent = "Session: " + (sessionId ? sessionId.slice(0, 8) : "-");
}
updateSessionBadge();

// --- Plain message (user, sys, error) ---
function addMessage(role, text, extraClass) {
  extraClass = extraClass || "";
  const row    = document.createElement("div");
  row.className = ("row " + role + " " + extraClass).trim();
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (role === "sys" || role === "bot") {
    bubble.innerHTML = renderSafeMarkdown(text);
  } else {
    bubble.textContent = String(text ?? "");
  }
  row.appendChild(bubble);
  chatDiv.appendChild(row);
  chatDiv.scrollTop = chatDiv.scrollHeight;
  return row;
}

// --- Bot message: avatar + FR10 myth card + FR09 feedback ---
function addBotMessage(answerText, facts, isMythFlag) {
  const idx     = messageIndex++;
  const isMythQ = detectMyth(answerText, facts, isMythFlag);
  const row  = document.createElement("div");
  row.className = "row bot";
  const wrap = document.createElement("div");
  wrap.className = "bot-wrap";
  wrap.appendChild(makeBotAvatar());
  if (isMythQ) {
    wrap.appendChild(renderMythCard(answerText));
  } else {
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = renderSafeMarkdown(answerText);
    wrap.appendChild(bubble);
  }
  row.appendChild(wrap);
  row.appendChild(createFeedbackBar(idx));
  chatDiv.appendChild(row);
  chatDiv.scrollTop = chatDiv.scrollHeight;
  return row;
}

// --- Facts panel ---
function addFacts(facts) {
  if (!showFacts.checked) return;
  if (!Array.isArray(facts) || facts.length === 0) return;
  const card  = document.createElement("div");
  card.className = "facts-card";
  const title = document.createElement("div");
  title.className = "facts-title";
  title.textContent = "Ontology facts used";
  const ul = document.createElement("ul");
  ul.className = "facts-list";
  facts.forEach(function(f) {
    const li = document.createElement("li");
    li.textContent = String(f ?? "");
    ul.appendChild(li);
  });
  card.appendChild(title);
  card.appendChild(ul);
  chatDiv.appendChild(card);
  chatDiv.scrollTop = chatDiv.scrollHeight;
}

// --- Typing indicator ---
let typingRow = null;
function showTyping() {
  if (typingRow) return;
  typingRow = document.createElement("div");
  typingRow.className = "row bot";
  const wrap = document.createElement("div");
  wrap.className = "bot-wrap";
  wrap.appendChild(makeBotAvatar());
  const t = document.createElement("div");
  t.className = "typing";
  t.innerHTML = "Thinking <span class='dots'><span class='dot'></span><span class='dot'></span><span class='dot'></span></span>";
  wrap.appendChild(t);
  typingRow.appendChild(wrap);
  chatDiv.appendChild(typingRow);
  chatDiv.scrollTop = chatDiv.scrollHeight;
}
function hideTyping() {
  if (typingRow) typingRow.remove();
  typingRow = null;
}

// --- Send button ---
function setSendEnabled() {
  sendBtn.disabled = msgInput.value.trim().length === 0;
}
msgInput.addEventListener("input", setSendEnabled);
setSendEnabled();

// --- Main send action ---
async function sendMessage() {
  const text = msgInput.value.trim();
  if (!text) return;
  addMessage("you", text);
  msgInput.value = "";
  setSendEnabled();
  setStatus("Thinking...");
  sendBtn.disabled = true;
  showTyping();
  const culture = document.getElementById("cultureSelect")
                  ? document.getElementById("cultureSelect").value
                  : "general";
  const payload = { session_id: sessionId, message: text, lang: "en", culture: culture };
  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    sessionId = data.session_id || sessionId;
    localStorage.setItem("session_id", sessionId);
    updateSessionBadge();
    hideTyping();
    setStatus("Ready");
    sendBtn.disabled = false;
    setSendEnabled();
    addBotMessage(data.answer || "No answer returned.", data.ontology_facts || [], data.is_myth || false);

    // Update XAI explainability panel
    if (window.updateXAIPanel) {
      const concept = (data.ontology_facts || [])
        .find(f => f.toLowerCase().startsWith("concept:"));
      const conceptLabel = concept ? concept.split(":")[1].trim() : "";
      window.updateXAIPanel(conceptLabel, data.ontology_facts || [], culture);
    }
    if (data.doctor_advice) addMessage("sys", data.doctor_advice);
    if (data.warnings && data.warnings.length > 0) addMessage("sys", data.warnings.join(" | "));
    if (data.ontology_facts) addFacts(data.ontology_facts);
  } catch (e) {
    hideTyping();
    setStatus("Offline");
    addMessage("sys", "Backend not reachable. Make sure FastAPI is running.", "error");
    sendBtn.disabled = false;
    setSendEnabled();
  }
}

// --- Events ---
sendBtn.addEventListener("click", sendMessage);
msgInput.addEventListener("keydown", function(e) {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

// --- Welcome message with suggestion chips ---
(function() {
  const row = document.createElement("div");
  row.className = "row bot";
  const wrap = document.createElement("div");
  wrap.className = "bot-wrap";
  wrap.appendChild(makeBotAvatar());
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = renderSafeMarkdown(
    "Hi! I am a menstrual health education assistant.\n\n" +
    "I use a verified knowledge base sourced from WHO, NHS, and MedlinePlus " +
    "to answer your questions accurately.\n\nTry one of the questions below or type your own:"
  );
  const chips = document.createElement("div");
  chips.className = "chips";
  ["What is PCOS?", "How do I relieve cramps?", "What is the luteal phase?", "Is severe pain normal?"].forEach(function(s) {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.textContent = s;
    chip.addEventListener("click", function() { msgInput.value = s; setSendEnabled(); sendMessage(); });
    chips.appendChild(chip);
  });
  bubble.appendChild(chips);
  wrap.appendChild(bubble);
  row.appendChild(wrap);
  chatDiv.appendChild(row);
})();
