const $ = selector => document.querySelector(selector);
const grid = $("#movie-grid");
const modal = $(".modal");
const searchPanel = $(".search-panel");
const searchInput = $("#search-input");
const searchForm = $("#search-form");
const status = $("#api-status");
const loadMore = $("#load-more");
const state = { page: 1, pageSize: 24, total: 0, q: "", type: "Todos", genre: "Todos", year: "", rating: "", loading: false };
let movies = [], activeMovie = null, searchTimer, requestSequence = 0;
const saved = new Set(JSON.parse(localStorage.getItem("cineverse-saved") || "[]"));

const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);

function apiUrl() {
  const params = new URLSearchParams({ page: state.page, pageSize: state.pageSize });
  for (const key of ["q", "year"]) if (state[key]) params.set(key, state[key]);
  if (state.type !== "Todos") params.set("type", state.type);
  if (state.genre !== "Todos") params.set("genre", state.genre);
  if (state.rating) params.set("minRating", state.rating);
  return `/api/catalog?${params}`;
}

function skeletons() {
  grid.innerHTML = Array.from({ length: 12 }, () => `<article class="movie-card skeleton-card"><div class="poster skeleton"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line short"></div></article>`).join("");
}

async function fetchCatalog(reset = false) {
  const requestId = ++requestSequence;
  state.loading = true;
  if (reset) { state.page = 1; movies = []; skeletons(); }
  status.textContent = "Carregando catálogo…";
  loadMore.disabled = true;
  try {
    const response = await fetch(apiUrl());
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    if (requestId !== requestSequence) return;
    movies = reset ? data.items : [...movies, ...data.items];
    state.total = data.total;
    render();
    updateHero(movies[0]);
    status.textContent = `OMDb · ${data.total.toLocaleString("pt-BR")} títulos`;
    status.classList.add("connected");
  } catch (error) {
    if (requestId !== requestSequence) return;
    grid.innerHTML = `<p class="empty-state">${escapeHtml(error.message || "Catálogo indisponível.")}</p>`;
    status.textContent = "Catálogo indisponível";
  } finally {
    if (requestId === requestSequence) { state.loading = false; updateLoadMore(); }
  }
}

function render() {
  grid.innerHTML = movies.map((movie, index) => `<article class="movie-card" style="animation-delay:${(index % 24) * 20}ms">
    <div class="poster" data-open="${movie.id}" tabindex="0" role="button" aria-label="Detalhes de ${escapeHtml(movie.title)}">
      <img src="${escapeHtml(movie.image)}" alt="Capa de ${escapeHtml(movie.title)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.onerror=null;this.src='poster-placeholder.svg'">
      <span class="card-badge">${movie.type}</span><button class="save-button ${saved.has(movie.id) ? "saved" : ""}" data-save="${movie.id}">${saved.has(movie.id) ? "✓" : "+"}</button><span class="play-hover" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"></circle><path d="M12 11v5M12 8h.01"></path></svg></span>
    </div><div class="card-info"><div class="card-title-row"><h3>${escapeHtml(movie.title)}</h3><span class="score"><span>★</span> ${movie.score}</span></div><p>${movie.year} · ${movie.genre}</p></div></article>`).join("");
  updateSaved();
}

function updateLoadMore() {
  loadMore.hidden = movies.length >= state.total;
  loadMore.disabled = state.loading;
  loadMore.textContent = state.loading ? "Carregando…" : `Carregar mais (${movies.length} de ${state.total})`;
}

function updateHero(movie) {
  if (!movie) return;
  $(".hero-backdrop").style.backgroundImage = `url('${movie.image}')`;
  $(".hero h1").textContent = movie.title;
  $(".hero-description").textContent = "Explore informações, avaliações e detalhes deste título.";
  $(".hero .meta-row").innerHTML = `<span>${movie.year}</span><span>${movie.type}</span><span>${movie.genre}</span>`;
  document.querySelectorAll(".hero [data-open]").forEach(button => button.dataset.open = movie.id);
}

async function openModal(id) {
  const movie = movies.find(item => item.id === id);
  if (!movie) return;
  activeMovie = movie;
  $("#modal-title").textContent = movie.title;
  $(".modal-image").style.backgroundImage = `url('${movie.image}')`;
  $(".modal-description").textContent = "Carregando informações…";
  $(".modal-meta").innerHTML = `<span>${movie.year}</span><span>${movie.type}</span>`;
  syncSaveButton(); modal.classList.add("open"); modal.setAttribute("aria-hidden", "false"); document.body.style.overflow = "hidden";
  try {
    const response = await fetch(`/api/title/${encodeURIComponent(id)}`), details = await response.json();
    if (!response.ok) throw new Error(details.error);
    if (activeMovie?.id !== id) return;
    Object.assign(movie, details);
    $(".modal-meta").innerHTML = `<span class="rating"><strong>★</strong> ${details.score}</span><span>${details.year}</span><span>${details.type}</span><span>${details.genre}</span>`;
    $(".modal-description").textContent = details.synopsis;
  } catch { $(".modal-description").textContent = "Detalhes indisponíveis."; }
}

function close(element) { element.classList.remove("open"); element.setAttribute("aria-hidden", "true"); document.body.style.overflow = ""; if (element === modal) activeMovie = null; }
function toggleSaved(id) { saved.has(id) ? saved.delete(id) : saved.add(id); localStorage.setItem("cineverse-saved", JSON.stringify([...saved])); render(); syncSaveButton(); }
function syncSaveButton() { if (!activeMovie) return; const button = $(".modal-save"); button.dataset.save = activeMovie.id; button.textContent = saved.has(activeMovie.id) ? "✓ Na minha lista" : "＋ Adicionar à minha lista"; }
function updateSaved() { const box = $("#saved-preview"), items = movies.filter(movie => saved.has(movie.id)); box.className = `saved-preview${items.length ? " has-items" : ""}`; box.innerHTML = items.length ? items.slice(0, 4).map(item => `<img src="${item.image}" alt="${escapeHtml(item.title)}">`).join("") : "<span>＋</span><p>Sua lista ainda está vazia</p>"; }

document.addEventListener("click", event => { const save = event.target.closest("[data-save]"); if (save) { event.stopPropagation(); return toggleSaved(save.dataset.save); } const open = event.target.closest("[data-open]"); if (open) openModal(open.dataset.open); });
document.querySelectorAll(".filter").forEach(button => button.addEventListener("click", () => { document.querySelectorAll(".filter").forEach(item => item.classList.remove("active")); button.classList.add("active"); const value = button.dataset.filter; state.type = ["Filme", "Série"].includes(value) ? value : "Todos"; state.genre = ["Todos", "Filme", "Série"].includes(value) ? "Todos" : value; fetchCatalog(true); }));
document.querySelectorAll("[data-quick-filter]").forEach(link => link.addEventListener("click", () => document.querySelector(`.filter[data-filter="${link.dataset.quickFilter}"]`)?.click()));
$("#year-filter").addEventListener("change", event => { state.year = event.target.value; fetchCatalog(true); });
$("#rating-filter").addEventListener("change", event => { state.rating = event.target.value; fetchCatalog(true); });
searchInput.addEventListener("input", event => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { state.q = event.target.value.trim(); fetchCatalog(true); }, 450); });
searchForm.addEventListener("submit", event => {
  event.preventDefault();
  clearTimeout(searchTimer);
  state.q = searchInput.value.trim();
  fetchCatalog(true);
  close(searchPanel);
  $("#catalogo").scrollIntoView({ behavior: "smooth" });
});
loadMore.addEventListener("click", () => { state.page += 1; fetchCatalog(); });
$(".search-toggle").addEventListener("click", () => { searchPanel.classList.add("open"); searchPanel.setAttribute("aria-hidden", "false"); searchInput.focus(); });
$(".search-close").addEventListener("click", () => close(searchPanel)); $(".modal-close").addEventListener("click", () => close(modal));
modal.addEventListener("click", event => { if (event.target === modal) close(modal); });
document.addEventListener("keydown", event => { if (event.key === "Escape") { close(searchPanel); close(modal); } if (event.key === "Enter" && event.target.matches(".poster")) openModal(event.target.dataset.open); });
$(".menu-button").addEventListener("click", event => { $(".desktop-nav").classList.toggle("mobile-open"); event.currentTarget.setAttribute("aria-expanded", $(".desktop-nav").classList.contains("mobile-open")); });
fetchCatalog(true);
