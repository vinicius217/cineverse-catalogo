const $ = selector => document.querySelector(selector);
const $$ = selector => document.querySelectorAll(selector);
const on = (selector, event, handler) => $$(selector).forEach(node => node.addEventListener(event, handler));
async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error);
  return data;
}
const titleDetails = id => request(`/api/title/${encodeURIComponent(id)}`);
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
const hero = { items: [], index: 0, layer: 0, sequence: 0, timer: null, paused: false };
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

document.addEventListener("error", event => {
  if (!event.target.matches?.(".poster-art img")) return;
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
    const data = await request(apiUrl(), { signal: catalogController.signal });
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
    suggestions.innerHTML = data.suggestionsHtml || "";
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
  grid.innerHTML = movies.map(movie => movie.html.card).join("");
  grid.querySelectorAll(".movie-card").forEach((card, index) => {
    card.style.animationDelay = `${(index % 24) * 20}ms`;
    if (index < 4) card.querySelector("img")?.setAttribute("loading", "eager");
  });
  grid.querySelectorAll("[data-save]").forEach(button => {
    const selected = saved.has(button.dataset.save);
    button.classList.toggle("saved", selected);
    button.setAttribute("aria-pressed", selected);
    button.textContent = selected ? "✓" : "+";
  });
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
  const layers = $$(".hero-backdrop");
  hero.layer = 1 - hero.layer;
  layers[hero.layer].style.backgroundImage = `url(${JSON.stringify(source)})`;
  layers.forEach((layer, i) => layer.classList.toggle("visible", i === hero.layer));
  $(".hero h1").textContent = movie.title;
  $(".hero-description").textContent = movie.synopsis || "Explore informações, avaliações e detalhes deste título.";
  $(".hero .meta-row").innerHTML = movie.html?.heroMeta || "";
  $$(".hero [data-open]").forEach(button => { button.dataset.open = movie.id; button.disabled = false; });
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

on("#hero-prev", "click", () => { updateHero((hero.index - 1 + hero.items.length) % hero.items.length); scheduleHero(); });
on("#hero-next", "click", () => { updateHero((hero.index + 1) % hero.items.length); scheduleHero(); });
on("#hero-pause", "click", event => {
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
  $(".modal-image").innerHTML = movie.html?.poster || "";
  $(".modal-description").textContent = "Carregando informações…";
  $(".modal-facts").replaceChildren();
  $(".modal-meta").innerHTML = movie.html?.meta || "";
  syncSaveButton(); modal.classList.add("open"); modal.setAttribute("aria-hidden", "false"); document.body.style.overflow = "hidden";
  try {
    const details = await titleDetails(id);
    if (activeMovie?.id !== id) return;
    Object.assign(movie, details);
    $(".modal-meta").innerHTML = details.html.detailMeta;
    $(".modal-description").textContent = details.synopsis;
    $(".modal-image").innerHTML = movie.html?.poster || "";
    $(".modal-facts").innerHTML = details.html.facts;
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
  render(); syncSaveButton();
}
function syncSaveButton() { if (!activeMovie) return; const button = $(".modal-save"); button.dataset.save = activeMovie.id; button.textContent = saved.has(activeMovie.id) ? "✓ Na minha lista" : "＋ Adicionar à minha lista"; }
function updateSaved() {
  const box = $("#saved-preview"), items = [...savedItems.values()];
  box.className = `saved-preview${items.length ? " has-items" : ""}`;
  box.innerHTML = items.length ? items.map(item => item.html?.saved || `<p>${escapeHtml(item.title)}</p>`).join("") : "<span>＋</span><p>Sua lista ainda está vazia</p>";
}

function resetFilters() {
  state.type = "Todos"; state.genre = "Todos"; state.year = ""; state.order = "popular";
  $$(".filter").forEach(item => item.classList.toggle("active", item.dataset.filter === "Todos"));
  $("#year-filter").value = ""; $("#order-filter").value = "popular";
}

function showView(view) {
  const listOpen = view === "list";
  document.body.classList.toggle("list-view", listOpen);
  $$(".desktop-nav a").forEach(link => link.classList.toggle("active", listOpen ? link.hasAttribute("data-list-view") : link.getAttribute("href") === "#inicio"));
  $(".desktop-nav").classList.remove("mobile-open");
  updateSaved();
}

document.addEventListener("click", event => { const save = event.target.closest("[data-save]"); if (save) { event.stopPropagation(); return toggleSaved(save.dataset.save); } const open = event.target.closest("[data-open]"); if (open) openModal(open.dataset.open); });
$$(".filter").forEach(button => button.addEventListener("click", () => { $$(".filter").forEach(item => item.classList.remove("active")); button.classList.add("active"); const value = button.dataset.filter; state.type = ["Filme", "Série"].includes(value) ? value : "Todos"; state.genre = ["Todos", "Filme", "Série"].includes(value) ? "Todos" : value; fetchCatalog(true); }));
$$("[data-quick-filter]").forEach(link => link.addEventListener("click", () => { showView("home"); document.querySelector(`.filter[data-filter="${link.dataset.quickFilter}"]`)?.click(); }));
on("#year-filter", "change", event => { state.year = event.target.value; fetchCatalog(true); });
on("#order-filter", "change", event => { state.order = event.target.value; fetchCatalog(true); });
on("#clear-filters", "click", () => {
  resetFilters();
  clearTimeout(searchTimer);
  searchInput.value = state.q = "";
  fetchCatalog(true);
});
on("#view-all", "click", () => { resetFilters(); state.pageSize = 48; fetchCatalog(true); $("#catalogo").scrollIntoView({ behavior: "smooth" }); });
$$("[data-home]").forEach(link => link.addEventListener("click", () => showView("home")));
on("[data-list-view]", "click", () => showView("list"));
window.addEventListener("hashchange", () => showView(location.hash === "#minha-lista" ? "list" : "home"));
function runSearch() {
  clearTimeout(searchTimer);
  state.q = searchInput.value.trim();
  fetchCatalog(true);
}
on("#search-suggestions", "click", event => {
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
on(".search-toggle", "click", () => {
  showView("home");
  searchForm.scrollIntoView({ behavior: "smooth", block: "center" });
  searchInput.focus({ preventScroll: true });
});
on(".modal-close", "click", () => close(modal));
modal.addEventListener("click", event => { if (event.target === modal) close(modal); });
document.addEventListener("keydown", event => { if (event.key === "Escape") { close(modal); } if (event.key === "Enter" && event.target.matches(".poster")) openModal(event.target.dataset.open); });
on(".menu-button", "click", event => { $(".desktop-nav").classList.toggle("mobile-open"); event.currentTarget.setAttribute("aria-expanded", $(".desktop-nav").classList.contains("mobile-open")); });
showView(location.hash === "#minha-lista" ? "list" : "home");
fetchCatalog(true);

async function restoreSaved() {
  await Promise.allSettled([...savedItems.values()].filter(item => !item.html).map(async ({ id }) => {
    const details = await titleDetails(id);
    if (saved.has(id)) savedItems.set(id, details);
  }));
  persistSaved();
  updateSaved();
}
restoreSaved();
