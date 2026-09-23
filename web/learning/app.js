const STORAGE_KEY = "marinetime:web:progress:v1";

const state = {
  data: null,
  flat: [],
  currentId: null,
  query: "",
  progress: loadProgress(),
};

function loadProgress() {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    return {
      completed: Array.isArray(value.completed) ? value.completed : [],
      lastSourceId: typeof value.lastSourceId === "string" ? value.lastSourceId : null,
    };
  } catch {
    return { completed: [], lastSourceId: null };
  }
}

function saveProgress() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.progress));
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function button(label, className, onClick) {
  const element = node("button", className, label);
  element.type = "button";
  element.addEventListener("click", onClick);
  return element;
}

function isDone(sourceId) {
  return state.progress.completed.includes(sourceId);
}

function toggleDone(sourceId) {
  const completed = new Set(state.progress.completed);
  if (completed.has(sourceId)) completed.delete(sourceId);
  else completed.add(sourceId);
  state.progress.completed = [...completed];
  state.progress.lastSourceId = sourceId;
  saveProgress();
  renderSidebar();
  renderProgress();
  renderLesson(sourceId);
}

function allSessionRefs() {
  const refs = [];
  for (const track of state.data.tracks || []) {
    for (const session of track.sessions || []) {
      refs.push({ ...session, track_id: track.track_id, track_title: track.title });
    }
  }
  return refs;
}

function sessionIndex(sourceId) {
  return state.flat.findIndex((item) => item.source_id === sourceId);
}

function goRelative(delta) {
  if (!state.currentId) return;
  const index = sessionIndex(state.currentId);
  if (index < 0) return;
  const next = state.flat[index + delta];
  if (next) selectSession(next.source_id);
}

function selectSession(sourceId) {
  if (!state.data.sessions[sourceId]) return;
  state.currentId = sourceId;
  state.progress.lastSourceId = sourceId;
  saveProgress();
  renderSidebar();
  renderProgress();
  renderLesson(sourceId);
  window.scrollTo({ top: 0, behavior: "smooth" });
  closeSidebar();
}

function renderProgress() {
  const total = state.flat.length;
  const completed = state.progress.completed.filter((id) => state.data.sessions[id]).length;
  document.getElementById("progressLabel").textContent = `${completed} / ${total}`;
  document.getElementById("progressBar").style.width =
    total ? `${Math.round((completed / total) * 100)}%` : "0%";

  const index = state.currentId ? sessionIndex(state.currentId) : -1;
  document.getElementById("prevButton").disabled = index <= 0;
  document.getElementById("nextButton").disabled = index < 0 || index >= total - 1;
}

function normalized(value) {
  return String(value || "").toLocaleLowerCase("vi").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function sessionMatches(session, trackTitle) {
  if (!state.query) return true;
  const haystack = normalized([
    session.display_title,
    session.module_title,
    trackTitle,
    session.source_id,
  ].join(" "));
  return haystack.includes(normalized(state.query));
}

function renderSidebar() {
  const root = document.getElementById("trackList");
  root.replaceChildren();

  for (const track of state.data.tracks || []) {
    const matching = (track.sessions || []).filter((session) =>
      sessionMatches(session, track.title)
    );
    if (!matching.length) continue;

    const details = node("details", "track");
    details.open = !state.query || matching.some((item) => item.source_id === state.currentId);

    const summary = document.createElement("summary");
    summary.appendChild(node("span", "", track.title));
    summary.appendChild(node("span", "track-count", String(matching.length)));
    details.appendChild(summary);

    const list = node("div", "session-list");
    matching.forEach((session) => {
      const item = button("", "session-button", () => selectSession(session.source_id));
      if (session.source_id === state.currentId) item.classList.add("active");
      if (isDone(session.source_id)) item.classList.add("done");

      const globalIndex = state.flat.findIndex((ref) => ref.source_id === session.source_id) + 1;
      item.appendChild(node("span", "session-number", isDone(session.source_id) ? "✓" : globalIndex));

      const copy = node("span", "session-copy");
      copy.appendChild(node("span", "session-title", session.display_title));
      copy.appendChild(node("span", "session-module", session.module_title || "Foundations"));
      item.appendChild(copy);
      list.appendChild(item);
    });

    details.appendChild(list);
    root.appendChild(details);
  }
}

function sectionHeading(title, subtitle) {
  const wrap = node("div", "section-head");
  wrap.appendChild(node("h2", "", title));
  if (subtitle) wrap.appendChild(node("p", "", subtitle));
  return wrap;
}

function renderObjectives(session) {
  const section = node("section", "section");
  section.appendChild(sectionHeading(
    "Bạn sẽ học được gì",
    "Không cần nhớ ALU ID. Hãy hiểu ý trước, rồi mới quay lại evidence nếu cần."
  ));
  const panel = node("div", "panel");
  const list = node("ul", "objective-list");
  for (const objective of session.learning_objectives || []) {
    const text = typeof objective === "string" ? objective : objective.text;
    if (text) list.appendChild(node("li", "", text));
  }
  if (!list.children.length) list.appendChild(node("li", "", "Bài này chưa có learning objective."));
  panel.appendChild(list);
  section.appendChild(panel);
  return section;
}

function renderMentalModel(session) {
  const section = node("section", "section");
  section.appendChild(sectionHeading(
    "Bản đồ bài học",
    "Đọc phần này trước để biết các ý đang liên kết với nhau như thế nào."
  ));
  const panel = node("div", "panel");
  const list = node("ul", "mental-list");
  for (const item of session.mental_model || []) {
    list.appendChild(node("li", "", item));
  }
  if (!list.children.length) list.appendChild(node("li", "", "Chưa có mental model cho session này."));
  panel.appendChild(list);
  section.appendChild(panel);
  return section;
}

function renderKeyItems(session) {
  const section = node("section", "section");
  section.appendChild(sectionHeading(
    "Học từng ý",
    "Giải thích tiếng Việt để hiểu; English technical point để giữ đúng thuật ngữ ngành."
  ));
  const grid = node("div", "learn-grid");

  (session.key_items || []).forEach((item, index) => {
    const card = node("article", "learn-card");
    const main = node("div", "learn-card-main");
    main.appendChild(node("span", "learn-card-index", String(index + 1)));
    main.appendChild(node("h3", "", item.heading_vi || item.heading || `Ý ${index + 1}`));
    main.appendChild(node("p", "explanation", item.explanation_vi || item.statement || ""));

    const english = node("div", "english-point");
    english.appendChild(node("span", "", "English technical point"));
    english.appendChild(node("p", "", item.statement || ""));
    main.appendChild(english);

    const badges = node("div", "badges");
    if (item.safety_critical) badges.appendChild(node("span", "badge danger", "Safety-critical"));
    if (item.numeric_claim) badges.appendChild(node("span", "badge warn", "Numeric claim"));
    if (item.support_level) badges.appendChild(node("span", "badge", item.support_level));
    if (badges.children.length) main.appendChild(badges);

    card.appendChild(main);

    const details = node("details", "evidence");
    const summary = document.createElement("summary");
    summary.textContent = `Evidence / vì sao Marinetime nói ý này (${(item.evidence || []).length})`;
    details.appendChild(summary);
    const evidenceBody = node("div", "evidence-body");
    const list = node("ul");
    const evidence = item.evidence || [];
    if (evidence.length) {
      evidence.forEach((value) => list.appendChild(node("li", "", value)));
    } else {
      list.appendChild(node("li", "", "Không có evidence anchor trong learning card."));
    }
    evidenceBody.appendChild(list);
    details.appendChild(evidenceBody);
    card.appendChild(details);
    grid.appendChild(card);
  });

  if (!grid.children.length) {
    const panel = node("div", "panel", "Session này không có education-approved key item.");
    grid.appendChild(panel);
  }

  section.appendChild(grid);
  return section;
}

function renderQuiz(session) {
  const section = node("section", "section");
  section.appendChild(sectionHeading(
    "Tự kiểm tra",
    "Trả lời trước khi mở đáp án. Đây là lúc biến nội dung đọc thành thứ bạn thực sự nhớ."
  ));
  const list = node("div", "quiz-list");

  (session.quick_check || []).forEach((question, index) => {
    const item = node("details", "quiz-item");
    const summary = document.createElement("summary");
    const prompt = typeof question === "string"
      ? question
      : question.prompt || `Câu ${index + 1}`;
    summary.textContent = `${index + 1}. ${prompt}`;
    item.appendChild(summary);

    const answer = typeof question === "string"
      ? "Đối chiếu lại phần Học từng ý."
      : question.answer_anchor || "Đối chiếu lại phần Học từng ý.";
    item.appendChild(node("div", "quiz-answer", answer));
    list.appendChild(item);
  });

  if (!list.children.length) {
    list.appendChild(node("div", "panel", "Session này chưa có câu tự kiểm tra."));
  }
  section.appendChild(list);
  return section;
}

function renderOral(session) {
  if (!session.oral_exam_prompt) return null;
  const section = node("section", "section");
  const panel = node("div", "oral");
  panel.appendChild(node("span", "eyebrow", "ORAL PRACTICE"));
  panel.appendChild(node("p", "", session.oral_exam_prompt));
  section.appendChild(panel);
  return section;
}

function renderTrust(session) {
  const section = node("section", "section");
  const details = node("details", "panel trust");
  const summary = document.createElement("summary");
  summary.textContent = "Nguồn, giới hạn và authority check";
  details.appendChild(summary);

  const list = node("ul");
  list.appendChild(node("li", "", `Source: ${session.source_id}`));
  list.appendChild(node("li", "", `Provenance: ${session.provenance_class || "unknown"}`));
  list.appendChild(node("li", "", `Authority targets: ${(session.authority_targets || []).length}`));
  list.appendChild(node("li", "", `Withheld ALU items: ${session.withheld_items || 0}`));
  (session.warnings || []).forEach((warning) => list.appendChild(node("li", "", warning)));
  details.appendChild(list);
  section.appendChild(details);
  return section;
}

function renderLesson(sourceId) {
  const session = state.data.sessions[sourceId];
  const lessonView = document.getElementById("lessonView");
  const emptyState = document.getElementById("emptyState");
  if (!session) {
    lessonView.classList.add("hidden");
    emptyState.classList.remove("hidden");
    return;
  }

  emptyState.classList.add("hidden");
  lessonView.classList.remove("hidden");
  lessonView.replaceChildren();

  document.getElementById("crumbTrack").textContent =
    `${session.track_title} · ${session.module_title || "Foundations"}`;
  document.getElementById("crumbLesson").textContent = session.display_title;

  const hero = node("header", "lesson-hero");
  hero.appendChild(node("span", "eyebrow", `SESSION ${sessionIndex(sourceId) + 1} / ${state.flat.length}`));
  hero.appendChild(node("h1", "", session.display_title));
  hero.appendChild(node(
    "p",
    "lesson-sub",
    "Học phần nội dung trước. Evidence và trust metadata chỉ mở khi bạn muốn kiểm tra nguồn."
  ));

  const badges = node("div", "badges");
  badges.appendChild(node("span", "badge", session.module_title || session.track_title));
  if (session.safety_critical_items > 0) {
    badges.appendChild(node("span", "badge danger", `${session.safety_critical_items} safety-critical`));
  }
  if (session.numeric_items > 0) {
    badges.appendChild(node("span", "badge warn", `${session.numeric_items} numeric`));
  }
  if (session.authoritative_verification_required) {
    badges.appendChild(node("span", "badge warn", "Cần authority check"));
  }
  hero.appendChild(badges);

  const actions = node("div", "hero-actions");
  const complete = button(
    isDone(sourceId) ? "✓ Đã học xong" : "Đánh dấu đã học",
    isDone(sourceId) ? "button done" : "button primary",
    () => toggleDone(sourceId)
  );
  actions.appendChild(complete);
  actions.appendChild(button("← Session trước", "button ghost", () => goRelative(-1)));
  actions.appendChild(button("Session tiếp →", "button ghost", () => goRelative(1)));
  hero.appendChild(actions);
  lessonView.appendChild(hero);

  lessonView.appendChild(renderObjectives(session));
  lessonView.appendChild(renderMentalModel(session));
  lessonView.appendChild(renderKeyItems(session));
  lessonView.appendChild(renderQuiz(session));
  const oral = renderOral(session);
  if (oral) lessonView.appendChild(oral);
  lessonView.appendChild(renderTrust(session));

  renderProgress();
}

function openSidebar() {
  document.getElementById("sidebar").classList.add("open");
  document.getElementById("overlay").classList.remove("hidden");
}

function closeSidebar() {
  document.getElementById("sidebar").classList.remove("open");
  document.getElementById("overlay").classList.add("hidden");
}

async function init() {
  try {
    const response = await fetch("./data/course.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    state.flat = allSessionRefs();

    document.getElementById("searchInput").addEventListener("input", (event) => {
      state.query = event.target.value.trim();
      renderSidebar();
    });
    document.getElementById("prevButton").addEventListener("click", () => goRelative(-1));
    document.getElementById("nextButton").addEventListener("click", () => goRelative(1));
    document.getElementById("menuButton").addEventListener("click", openSidebar);
    document.getElementById("overlay").addEventListener("click", closeSidebar);

    document.addEventListener("keydown", (event) => {
      if (event.target instanceof HTMLInputElement) return;
      if (event.key === "ArrowLeft" && event.altKey) goRelative(-1);
      if (event.key === "ArrowRight" && event.altKey) goRelative(1);
    });

    renderSidebar();
    renderProgress();

    const preferred = state.progress.lastSourceId && state.data.sessions[state.progress.lastSourceId]
      ? state.progress.lastSourceId
      : state.flat[0]?.source_id;
    if (preferred) selectSession(preferred);
  } catch (error) {
    const empty = document.querySelector(".empty-card");
    empty.replaceChildren();
    empty.appendChild(node("span", "eyebrow", "LOAD ERROR"));
    empty.appendChild(node("h1", "", "Không đọc được course data."));
    empty.appendChild(node(
      "p",
      "",
      `Hãy chạy lại python scripts/build_learning_web.py rồi mở web qua HTTP server. Chi tiết: ${error.message}`
    ));
  }
}

init();
