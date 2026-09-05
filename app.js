const $ = selector => document.querySelector(selector);
const grid = $("#movie-grid");
const modal = $(".modal");
const searchInput = $("#search-input");
const searchForm = $("#search-form");
const status = $("#api-status");
const loadMore = $("#load-more");
const state = { page: 1, pageSize: 24, total: 0, q: "", type: "Todos", genre: "Todos", year: "", order: "popular", loading: false };
let movies = [], activeMovie = null, searchTimer, requestSequence = 0, catalogController;
function readSaved(key) {
  try { const value = JSON.parse(localStorage.getItem(key) || "[]"); return Array.isArray(value) ? value : []; }
  catch { return []; }
}
const saved = new Set(readSaved("cineverse-saved"));
const savedItems = new Map(readSaved("cineverse-saved-items").filter(item => item && item.id).map(item => [item.id, item]));
savedItems.forEach((_, id) => saved.add(id));
const FALLBACK_POSTER = "poster-placeholder.svg";

const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const posterUrl = value => value && value !== "N/A" ? value : FALLBACK_POSTER;
const hasPoster = movie => posterUrl(movie.image) !== FALLBACK_POSTER;
const failedPosters = new Set();
const hero = { items: [], index: 0, layer: 0, sequence: 0, timer: null, paused: false };
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

function posterMarkup(movie, eager = false) {
  const hue = [...movie.title].reduce((hash, char) => hash + char.charCodeAt(0), 0) % 360;
  const missing = !hasPoster(movie) || failedPosters.has(movie.image);
  return `<div class="poster-art ${missing ? "no-cover" : ""}" style="--poster-hue:${hue}">
    <div class="poster-lettering"><span class="poster-monogram" aria-hidden="true">${escapeHtml(movie.title.slice(0, 1))}</span><small>CINEVERSE · ${escapeHtml(movie.type)}</small><strong>${escapeHtml(movie.title)}</strong><span>${escapeHtml(movie.year)}</span><small>Capa indisponível</small></div>
    ${missing ? "" : `<img src="${escapeHtml(movie.image)}" alt="Capa de ${escapeHtml(movie.title)}" loading="${eager ? "eager" : "lazy"}" decoding="async" width="300" height="450" referrerpolicy="no-referrer">`}
  </div>`;
}

document.addEventListener("error", event => {
  if (!event.target.matches?.(".poster-art img")) return;
  failedPosters.add(event.target.getAttribute("src"));
  event.target.parentElement.classList.add("no-cover");
  event.target.remove();
}, true);

function loadPoster(source) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.referrerPolicy = "no-referrer";
    image.onload = () => resolve(source);
    image.onerror = reject;
    image.src = source;
  });
}

async function heroPoster(source) {
  // Request a larger Amazon image only on its supported image hosts.
  const url = new URL(source, location.href);
  const larger = /(^|\.)(media-amazon\.com|ssl-images-amazon\.com)$/.test(url.hostname)
    ? source.replace(/\._V1_.*?(?=\.(?:jpg|png)(?:\?|$))/i, "._V1_SX1280") : source;
  try { return await loadPoster(larger); }
  catch { return larger !== source ? loadPoster(source) : Promise.reject(); }
}

function apiUrl() {
  const params = new URLSearchParams({ page: state.page, pageSize: state.pageSize });
  for (const key of ["q", "year", "order"]) if (state[key]) params.set(key, state[key]);
  if (state.type !== "Todos") params.set("type", state.type);
  if (state.genre !== "Todos") params.set("genre", state.genre);
  return `/api/catalog?${params}`;
}

function skeletons() {
  grid.innerHTML = Array.from({ length: 12 }, () => `<article class="movie-card skeleton-card"><div class="poster skeleton"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line short"></div></article>`).join("");
}

async function fetchCatalog(reset = false) {
  const requestId = ++requestSequence;
  catalogController?.abort();
  catalogController = new AbortController();
  state.loading = true;
  grid.setAttribute("aria-busy", "true");
  if (reset) { state.page = 1; state.total = 0; movies = []; $(".catalog-section > .empty-state").hidden = true; skeletons(); }
  status.textContent = "Carregando catálogo…";
  loadMore.disabled = true;
  try {
    const response = await fetch(apiUrl(), { signal: catalogController.signal });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    if (requestId !== requestSequence) return;
    movies = reset ? data.items : [...movies, ...data.items];
    state.total = data.total;
    render();
    if (!hero.items.length) {
      const candidates = (data.featured || movies).filter(hasPoster);
      const films = candidates.filter(movie => movie.type === "Filme");
      const series = candidates.filter(movie => movie.type === "Série");
      hero.items = Array.from({ length: 4 }, (_, index) => [films[index], series[index]]).flat().filter(Boolean);
      updateHero(0);
      scheduleHero();
    }
    const interpretation = Object.values(data.interpreted || {}).join(" · ");
    $("#search-summary").textContent = data.correction
      ? `Resultados próximos de “${searchInput.value}”. Você quis dizer “${data.correction}”?`
      : `${data.total.toLocaleString("pt-BR")} títulos nesta seleção${interpretation ? ` · ${interpretation}` : ""}`;
    const suggestions = $("#search-suggestions");
    suggestions.hidden = !data.suggestions?.length;
    suggestions.innerHTML = (data.suggestions || []).map(title => `<button type="button" data-suggestion="${escapeHtml(title)}">${escapeHtml(title)}</button>`).join("");
    status.textContent = `${data.source || "OMDb"} · ${data.total.toLocaleString("pt-BR")} títulos`;
    status.classList.add("connected");
  } catch (error) {
    if (requestId !== requestSequence) return;
    if (error.name === "AbortError") return;
    if (!reset) state.page = Math.max(1, state.page - 1);
    status.classList.remove("connected");
    grid.innerHTML = `<p class="empty-state">${escapeHtml(error.message || "Catálogo indisponível.")}</p>`;
    status.textContent = "Catálogo indisponível";
  } finally {
    if (requestId === requestSequence) { state.loading = false; grid.setAttribute("aria-busy", "false"); updateLoadMore(); }
  }
}

function render() {
  movies.filter(movie => saved.has(movie.id)).forEach(movie => savedItems.set(movie.id, movie));
  persistSaved();
  grid.innerHTML = movies.map((movie, index) => `<article class="movie-card" style="animation-delay:${(index % 24) * 20}ms">
    <div class="poster" data-open="${movie.id}" tabindex="0" role="button" aria-label="Detalhes de ${escapeHtml(movie.title)}">
      ${posterMarkup(movie, index < 4)}
      <span class="card-badge">${movie.type}</span><button class="save-button ${saved.has(movie.id) ? "saved" : ""}" data-save="${movie.id}" aria-label="Salvar ${escapeHtml(movie.title)}" aria-pressed="${saved.has(movie.id)}">${saved.has(movie.id) ? "✓" : "+"}</button><span class="play-hover" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"></circle><path d="M12 11v5M12 8h.01"></path></svg></span>
    </div><div class="card-info"><div class="card-title-row"><h3>${escapeHtml(movie.title)}</h3><span class="score"><span>★</span> ${movie.score}</span></div><p>${movie.year} · ${movie.genre}</p></div></article>`).join("");
  $(".catalog-section > .empty-state").hidden = movies.length > 0;
  updateSaved();
}

function updateLoadMore() {
  loadMore.hidden = movies.length >= state.total;
  loadMore.disabled = state.loading;
  loadMore.textContent = state.loading ? "Carregando…" : `Carregar mais (${movies.length} de ${state.total})`;
}

async function updateHero(index) {
  const movie = hero.items[index];
  if (!movie) return;
  const sequence = ++hero.sequence;
  let source;
  try { source = await heroPoster(movie.backdrop || movie.image); }
  catch {
    if (sequence !== hero.sequence) return;
    hero.items = hero.items.filter(item => item.id !== movie.id);
    $(".hero-controls").hidden = hero.items.length < 2;
    if (hero.items.length) updateHero(index % hero.items.length);
    scheduleHero();
    return;
  }
  if (sequence !== hero.sequence) return;
  hero.index = index;
  const layers = document.querySelectorAll(".hero-backdrop");
  hero.layer = 1 - hero.layer;
  layers[hero.layer].style.backgroundImage = `url(${JSON.stringify(source)})`;
  layers.forEach((layer, i) => layer.classList.toggle("visible", i === hero.layer));
  $(".hero h1").textContent = movie.title;
  $(".hero-description").textContent = movie.synopsis || "Explore informações, avaliações e detalhes deste título.";
  $(".hero .meta-row").innerHTML = `<span>${escapeHtml(movie.year)}</span><span>${escapeHtml(movie.type)}</span><span>${escapeHtml(movie.genre)}</span>${movie.score && movie.score !== "—" ? `<span class="rating">★ ${escapeHtml(movie.score)} · ${escapeHtml(movie.source || "IMDb")}</span>` : ""}`;
  document.querySelectorAll(".hero [data-open]").forEach(button => { button.dataset.open = movie.id; button.disabled = false; });
  $(".hero-controls").hidden = hero.items.length < 2;
  $("#hero-count").textContent = `${String(index + 1).padStart(2, "0")} / ${String(hero.items.length).padStart(2, "0")}`;
  if (!reducedMotion.matches) $(".hero-content").animate([{ opacity: .3, transform: "translateY(10px)" }, { opacity: 1, transform: "translateY(0)" }], { duration: 600 });
}

function scheduleHero() {
  clearInterval(hero.timer);
  if (hero.paused || reducedMotion.matches || document.hidden || hero.items.length < 2) return;
  hero.timer = setInterval(() => {
    if (activeMovie || document.body.classList.contains("list-view") || $(".hero").matches(":hover, :focus-within")) return;
    updateHero((hero.index + 1) % hero.items.length);
  }, 7000);
}

$("#hero-prev").addEventListener("click", () => { updateHero((hero.index - 1 + hero.items.length) % hero.items.length); scheduleHero(); });
$("#hero-next").addEventListener("click", () => { updateHero((hero.index + 1) % hero.items.length); scheduleHero(); });
$("#hero-pause").addEventListener("click", event => {
  hero.paused = !hero.paused;
  event.currentTarget.textContent = hero.paused ? "Retomar" : "Pausar";
  event.currentTarget.setAttribute("aria-label", hero.paused ? "Retomar destaques" : "Pausar destaques");
  event.currentTarget.setAttribute("aria-pressed", hero.paused);
  scheduleHero();
});
document.addEventListener("visibilitychange", scheduleHero);
reducedMotion.addEventListener("change", scheduleHero);

async function openModal(id) {
  const movie = movies.find(item => item.id === id) || savedItems.get(id) || hero.items.find(item => item.id === id);
  if (!movie) return;
  activeMovie = movie;
  $("#modal-title").textContent = movie.title;
  $(".modal-image").innerHTML = posterMarkup(movie, true);
  $(".modal-description").textContent = "Carregando informações…";
  $(".modal-facts").replaceChildren();
  $(".modal-meta").innerHTML = `<span>${movie.year}</span><span>${movie.type}</span>`;
  syncSaveButton(); modal.classList.add("open"); modal.setAttribute("aria-hidden", "false"); document.body.style.overflow = "hidden";
  try {
    const response = await fetch(`/api/title/${encodeURIComponent(id)}`), details = await response.json();
    if (!response.ok) throw new Error(details.error);
    if (activeMovie?.id !== id) return;
    Object.assign(movie, details);
    $(".modal-meta").innerHTML = `<span class="rating"><strong>★</strong> ${escapeHtml(details.score)} · ${escapeHtml(details.ratingSource || "IMDb")}</span><span>${escapeHtml(details.year)}</span><span>${escapeHtml(details.type)}</span><span>${escapeHtml(details.genre)}</span>`;
    $(".modal-description").textContent = details.synopsis;
    $(".modal-image").innerHTML = posterMarkup(movie, true);
    const facts = [["Duração", details.runtime || "Não informada"], ["Elenco", details.cast?.join(", ") || "Não informado"]];
    if (details.seasons) facts.push(["Temporadas", details.seasons]);
    if (details.originalTitle && details.originalTitle !== details.title) facts.push(["Título original", details.originalTitle]);
    $(".modal-facts").innerHTML = facts.map(([label, value]) => `<div><dt>${label}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");
  } catch { if (activeMovie?.id === id) $(".modal-description").textContent = "Detalhes indisponíveis."; }
}

function close(element) { element.classList.remove("open"); element.setAttribute("aria-hidden", "true"); document.body.style.overflow = ""; if (element === modal) activeMovie = null; }
function persistSaved() {
  try {
  localStorage.setItem("cineverse-saved", JSON.stringify([...saved]));
  localStorage.setItem("cineverse-saved-items", JSON.stringify([...savedItems.values()]));
  } catch { /* A lista continua disponível nesta sessão. */ }
}
function toggleSaved(id) {
  if (saved.has(id)) { saved.delete(id); savedItems.delete(id); }
  else {
    saved.add(id);
    const movie = movies.find(item => item.id === id) || hero.items.find(item => item.id === id) || activeMovie;
    if (movie) savedItems.set(id, { ...movie });
  }
  persistSaved(); render(); syncSaveButton();
}
function syncSaveButton() { if (!activeMovie) return; const button = $(".modal-save"); button.dataset.save = activeMovie.id; button.textContent = saved.has(activeMovie.id) ? "✓ Na minha lista" : "＋ Adicionar à minha lista"; }
function updateSaved() {
  const box = $("#saved-preview"), items = [...savedItems.values()];
  box.className = `saved-preview${items.length ? " has-items" : ""}`;
  box.innerHTML = items.length ? items.map(item => `<article class="saved-card"><div class="saved-poster" data-open="${item.id}" tabindex="0" role="button">${posterMarkup(item)}<button data-save="${item.id}" aria-label="Remover ${escapeHtml(item.title)} da lista">×</button></div><h3>${escapeHtml(item.title)}</h3><p>${item.year} · ${item.type}</p></article>`).join("") : "<span>＋</span><p>Sua lista ainda está vazia</p>";
}

function resetFilters() {
  state.type = "Todos"; state.genre = "Todos"; state.year = ""; state.order = "popular";
  document.querySelectorAll(".filter").forEach(item => item.classList.toggle("active", item.dataset.filter === "Todos"));
  $("#year-filter").value = ""; $("#order-filter").value = "popular";
}

function showView(view) {
  const listOpen = view === "list";
  document.body.classList.toggle("list-view", listOpen);
  document.querySelectorAll(".desktop-nav a").forEach(link => link.classList.toggle("active", listOpen ? link.hasAttribute("data-list-view") : link.getAttribute("href") === "#inicio"));
  $(".desktop-nav").classList.remove("mobile-open");
  updateSaved();
}

document.addEventListener("click", event => { const save = event.target.closest("[data-save]"); if (save) { event.stopPropagation(); return toggleSaved(save.dataset.save); } const open = event.target.closest("[data-open]"); if (open) openModal(open.dataset.open); });
document.querySelectorAll(".filter").forEach(button => button.addEventListener("click", () => { document.querySelectorAll(".filter").forEach(item => item.classList.remove("active")); button.classList.add("active"); const value = button.dataset.filter; state.type = ["Filme", "Série"].includes(value) ? value : "Todos"; state.genre = ["Todos", "Filme", "Série"].includes(value) ? "Todos" : value; fetchCatalog(true); }));
document.querySelectorAll("[data-quick-filter]").forEach(link => link.addEventListener("click", () => { showView("home"); document.querySelector(`.filter[data-filter="${link.dataset.quickFilter}"]`)?.click(); }));
$("#year-filter").addEventListener("change", event => { state.year = event.target.value; fetchCatalog(true); });
$("#order-filter").addEventListener("change", event => { state.order = event.target.value; fetchCatalog(true); });
$("#clear-filters").addEventListener("click", () => {
  resetFilters();
  clearTimeout(searchTimer);
  searchInput.value = state.q = "";
  fetchCatalog(true);
});
$("#view-all").addEventListener("click", () => { resetFilters(); state.pageSize = 48; fetchCatalog(true); $("#catalogo").scrollIntoView({ behavior: "smooth" }); });
document.querySelectorAll("[data-home]").forEach(link => link.addEventListener("click", () => showView("home")));
document.querySelector("[data-list-view]").addEventListener("click", () => showView("list"));
window.addEventListener("hashchange", () => showView(location.hash === "#minha-lista" ? "list" : "home"));
function runSearch() {
  clearTimeout(searchTimer);
  state.q = searchInput.value.trim();
  fetchCatalog(true);
}
$("#search-suggestions").addEventListener("click", event => {
  const button = event.target.closest("[data-suggestion]");
  if (!button) return;
  searchInput.value = button.dataset.suggestion;
  runSearch();
});
searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  catalogController?.abort();
  searchTimer = setTimeout(runSearch, 300);
});
searchForm.addEventListener("submit", event => { event.preventDefault(); runSearch(); });
loadMore.addEventListener("click", () => { state.page += 1; fetchCatalog(); });
$(".search-toggle").addEventListener("click", () => {
  showView("home");
  searchForm.scrollIntoView({ behavior: "smooth", block: "center" });
  searchInput.focus({ preventScroll: true });
});
$(".modal-close").addEventListener("click", () => close(modal));
modal.addEventListener("click", event => { if (event.target === modal) close(modal); });
document.addEventListener("keydown", event => { if (event.key === "Escape") { close(modal); } if (event.key === "Enter" && event.target.matches(".poster")) openModal(event.target.dataset.open); });
$(".menu-button").addEventListener("click", event => { $(".desktop-nav").classList.toggle("mobile-open"); event.currentTarget.setAttribute("aria-expanded", $(".desktop-nav").classList.contains("mobile-open")); });
const yearFilter = $("#year-filter");
for (let year = 2026; year >= 2000; year--) yearFilter.add(new Option(year, year));
showView(location.hash === "#minha-lista" ? "list" : "home");
fetchCatalog(true);
