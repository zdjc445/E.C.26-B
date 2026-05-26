const els = {
  apiBase: document.querySelector("#apiBase"),
  sourceType: document.querySelector("#sourceType"),
  platformFilter: document.querySelector("#platformFilter"),
  ecommerceStatus: document.querySelector("#ecommerceStatus"),
  ecommerceCheckBtn: document.querySelector("#ecommerceCheckBtn"),
  username: document.querySelector("#username"),
  password: document.querySelector("#password"),
  nickname: document.querySelector("#nickname"),
  authStatus: document.querySelector("#authStatus"),
  registerBtn: document.querySelector("#registerBtn"),
  loginBtn: document.querySelector("#loginBtn"),
  loadMeBtn: document.querySelector("#loadMeBtn"),
  imageInput: document.querySelector("#imageInput"),
  demoImageBtn: document.querySelector("#demoImageBtn"),
  startCameraBtn: document.querySelector("#startCameraBtn"),
  capturePhotoBtn: document.querySelector("#capturePhotoBtn"),
  stopCameraBtn: document.querySelector("#stopCameraBtn"),
  cameraVideo: document.querySelector("#cameraVideo"),
  analyzeBtn: document.querySelector("#analyzeBtn"),
  previewImage: document.querySelector("#previewImage"),
  recognitionBox: document.querySelector("#recognitionBox"),
  suggestionCards: document.querySelector("#suggestionCards"),
  refineText: document.querySelector("#refineText"),
  refineBtn: document.querySelector("#refineBtn"),
  productGrid: document.querySelector("#productGrid"),
  resultCount: document.querySelector("#resultCount"),
  platformStats: document.querySelector("#platformStats"),
  compareBtn: document.querySelector("#compareBtn"),
  recommendBtn: document.querySelector("#recommendBtn"),
  comparisonBox: document.querySelector("#comparisonBox"),
  recommendationBox: document.querySelector("#recommendationBox"),
  toast: document.querySelector("#toast"),
};

const state = {
  accessToken: localStorage.getItem("accessToken") || "",
  refreshToken: localStorage.getItem("refreshToken") || "",
  sourceType: localStorage.getItem("sourceType") || "mock",
  file: null,
  image: null,
  recognition: null,
  searchTask: null,
  lastFilterText: "",
  sortBy: "comprehensive",
  items: [],
  selectedIds: new Set(),
  cameraStream: null,
  ecommerceStatus: null,
};

function apiBase() {
  return els.apiBase.value.replace(/\/$/, "");
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.accessToken) {
    headers.set("Authorization", `Bearer ${state.accessToken}`);
  }
  let body = options.body;
  if (body && !(body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }
  const response = await fetch(`${apiBase()}${path}`, { ...options, headers, body });
  const payload = await response.json().catch(() => ({ code: response.status, message: response.statusText }));
  if (!response.ok || payload.code !== 0) {
    throw new Error(payload.message || "request failed");
  }
  return payload.data;
}

function setAuth(payload) {
  state.accessToken = payload.accessToken;
  state.refreshToken = payload.refreshToken;
  localStorage.setItem("accessToken", state.accessToken);
  localStorage.setItem("refreshToken", state.refreshToken);
  els.authStatus.textContent = payload.user?.nickname || payload.user?.username || "已登录";
  els.authStatus.classList.add("ok");
}

async function register() {
  const payload = await api("/auth/register", {
    method: "POST",
    body: {
      username: els.username.value,
      password: els.password.value,
      nickname: els.nickname.value,
    },
  });
  setAuth(payload);
  toast("注册成功");
}

async function login() {
  const payload = await api("/auth/login", {
    method: "POST",
    body: {
      username: els.username.value,
      password: els.password.value,
    },
  });
  setAuth(payload);
  toast("登录成功");
}

async function loadMe() {
  const user = await api("/auth/me");
  els.authStatus.textContent = user.nickname || user.username;
  els.authStatus.classList.add("ok");
  toast("当前登录：" + user.username);
}

async function loadEcommerceStatus() {
  try {
    state.ecommerceStatus = await api("/ecommerce/status");
    renderEcommerceStatus();
  } catch (error) {
    state.ecommerceStatus = null;
    renderEcommerceStatus("检测失败");
  }
}

async function checkEcommerceApi() {
  const query = (els.refineText.value || "吹风机").trim();
  const platforms = selectedPlatforms();
  const params = new URLSearchParams({ query, pageSize: "3" });
  if (platforms.length) {
    params.set("platforms", platforms.join(","));
  }
  params.set("sortBy", state.sortBy || "comprehensive");
  Object.entries(currentDiagnosticFilters()).forEach(([key, value]) => {
    appendFilterParam(params, key, value);
  });
  const diagnostics = await api(`/ecommerce/diagnostics?${params.toString()}`);
  renderEcommerceDiagnostics(diagnostics);
  const successCount = (diagnostics.providers || []).filter((provider) => provider.success).length;
  toast(successCount ? `官方 API 诊断通过 ${successCount} 个平台` : "官方 API 诊断未通过");
}

function currentDiagnosticFilters() {
  if (normalizedText(state.lastFilterText) !== normalizedText(els.refineText.value)) {
    return {};
  }
  const filters = state.searchTask?.filters || {};
  const supported = ["minPrice", "maxPrice", "withCoupon", "officialOnly", "selfOperatedOnly"];
  return supported.reduce((result, key) => {
    if (Object.prototype.hasOwnProperty.call(filters, key)) {
      result[key] = filters[key];
    }
    return result;
  }, {});
}

function appendFilterParam(params, key, value) {
  if (value === null || value === undefined || value === "") {
    return;
  }
  if (typeof value === "object" && value.amount !== undefined) {
    params.set(key, String(value.amount));
    return;
  }
  params.set(key, String(value));
}

function normalizedText(value) {
  return (value || "").trim();
}

async function createDemoImage() {
  const canvas = document.createElement("canvas");
  canvas.width = 900;
  canvas.height = 640;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#eef3f0";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#0f766e";
  ctx.fillRect(150, 220, 400, 150);
  ctx.beginPath();
  ctx.arc(570, 295, 105, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#17211f";
  ctx.fillRect(245, 360, 75, 170);
  ctx.fillStyle = "#ffffff";
  ctx.font = "bold 48px Microsoft YaHei, sans-serif";
  ctx.fillText("MockCare", 150, 150);
  ctx.font = "32px Microsoft YaHei, sans-serif";
  ctx.fillText("低噪音宿舍吹风机", 150, 192);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  state.file = new File([blob], "hair-dryer.jpg", { type: "image/png" });
  showPreview(state.file);
  toast("已载入示例图");
}

function showPreview(file) {
  const url = URL.createObjectURL(file);
  els.previewImage.src = url;
  els.previewImage.style.display = "block";
}

async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("当前浏览器不支持相机预览");
  }
  stopCamera();
  state.cameraStream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: "environment" } },
    audio: false,
  });
  els.cameraVideo.srcObject = state.cameraStream;
  els.cameraVideo.style.display = "block";
  await els.cameraVideo.play();
  toast("相机已打开");
}

async function capturePhoto() {
  if (!state.cameraStream || !els.cameraVideo.videoWidth) {
    throw new Error("请先打开相机");
  }
  const canvas = document.createElement("canvas");
  canvas.width = els.cameraVideo.videoWidth;
  canvas.height = els.cameraVideo.videoHeight;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(els.cameraVideo, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
  state.file = new File([blob], "camera-capture.jpg", { type: "image/jpeg" });
  showPreview(state.file);
  toast("已拍照，可上传识别");
}

function stopCamera() {
  if (state.cameraStream) {
    state.cameraStream.getTracks().forEach((track) => track.stop());
    state.cameraStream = null;
  }
  if (els.cameraVideo) {
    els.cameraVideo.pause();
    els.cameraVideo.srcObject = null;
    els.cameraVideo.style.display = "none";
  }
}

async function analyze() {
  if (!state.file) {
    await createDemoImage();
  }
  const form = new FormData();
  form.append("file", state.file);
  form.append("scene", "recognition");
  state.image = await api("/images", { method: "POST", body: form });
  state.recognition = await api("/recognitions", {
    method: "POST",
    body: { imageId: state.image.imageId },
  });
  renderRecognition(state.recognition);
  state.searchTask = await api("/search-tasks", {
    method: "POST",
    body: {
      recognitionId: state.recognition.recognitionId,
      query: els.refineText.value,
      sourceType: state.sourceType,
      platforms: selectedPlatforms(),
      sortBy: state.sortBy,
    },
  });
  state.lastFilterText = els.refineText.value;
  state.selectedIds.clear();
  renderComparison(null);
  applySearchPayload(state.searchTask);
  toast("识别与推荐列表已刷新");
}

async function refine(text = els.refineText.value, sortBy = state.sortBy) {
  if (!state.searchTask) {
    throw new Error("请先完成识别");
  }
  const payload = await api(`/search-tasks/${state.searchTask.searchTaskId}/refine`, {
    method: "POST",
    body: { text, sortBy },
  });
  state.searchTask = { ...state.searchTask, ...payload };
  state.lastFilterText = text;
  state.selectedIds.clear();
  renderComparison(null);
  applySearchPayload(payload);
  toast("推荐列表已刷新");
}

async function compare() {
  if (!state.searchTask || state.items.length === 0) {
    throw new Error("没有可比价的商品");
  }
  const selected = Array.from(state.selectedIds);
  const ids = selected.length >= 2 ? selected.slice(0, 4) : state.items.slice(0, 4).map((item) => item.platformProductId);
  const comparison = await api("/comparisons", {
    method: "POST",
    body: {
      searchTaskId: state.searchTask.searchTaskId,
      platformProductIds: ids,
    },
  });
  renderStats(comparison.platformStats || []);
  renderComparison(comparison);
  toast(`最低价：${comparison.lowestPrice?.amount || "-"} CNY`);
}

async function recommend() {
  if (!state.searchTask || state.items.length === 0) {
    throw new Error("没有可推荐的商品");
  }
  const recommendation = await api("/agent/recommendations", {
    method: "POST",
    body: {
      searchTaskId: state.searchTask.searchTaskId,
      userQuery: els.refineText.value,
      candidateIds: state.items.slice(0, 6).map((item) => item.platformProductId),
    },
  });
  renderRecommendation(recommendation);
  toast("推荐理由已生成");
}

async function favorite(item) {
  await api("/favorites", {
    method: "POST",
    body: {
      platformProductId: item.platformProductId,
      note: `来自搜索任务 ${state.searchTask?.searchTaskId || "-"}`,
    },
  });
  toast("已加入收藏，后续推荐可作为个性化参考");
}

async function showPriceHistory() {
  if (!state.items.length) {
    throw new Error("没有商品可查询历史价格");
  }
  const first = state.items[0];
  const history = await api(`/platform-products/${first.platformProductId}/price-history?days=90`);
  els.recommendationBox.classList.remove("empty");
  els.recommendationBox.innerHTML = `
    <strong>${escapeHtml(first.title)}</strong>
    <p class="muted">趋势：${history.trend} · 当前 ${history.currentPrice.amount} · 低点 ${history.lowestPrice.amount} · 高点 ${history.highestPrice.amount}</p>
    <ul>${history.points.map((point) => `<li>${point.recordedAt.slice(0, 10)}：${point.price.amount} CNY</li>`).join("")}</ul>
  `;
}

function applySearchPayload(payload) {
  state.items = payload.items || [];
  renderSuggestions(payload.suggestionCards || []);
  renderStats(payload.platformStats || []);
  renderProducts(state.items);
}

function renderRecognition(data) {
  const attrs = Object.entries(data.attributes || {})
    .map(([key, value]) => `<span class="tag">${escapeHtml(key)}：${escapeHtml(String(value))}</span>`)
    .join("");
  els.recognitionBox.classList.remove("empty");
  els.recognitionBox.innerHTML = `
    <div class="price-line">
      <strong>${escapeHtml(data.category)}</strong>
      <span class="tag">${Math.round(data.confidence * 100)}%</span>
    </div>
    <p class="muted">品牌：${escapeHtml(data.brand || "未知")} · 型号：${escapeHtml(data.model || "-")} · AI：${escapeHtml(data.aiProvider || "mock")}${data.fallbackUsed ? " fallback" : ""}</p>
    <div class="tag-row">${data.keywords.map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")}</div>
    <div class="tag-row">${attrs}</div>
    ${data.explanation ? `<p class="muted">${escapeHtml(data.explanation)}</p>` : ""}
  `;
}

function renderSuggestions(cards) {
  els.suggestionCards.innerHTML = "";
  cards.forEach((card) => {
    const button = document.createElement("button");
    button.className = "suggestion-card";
    button.innerHTML = `<strong>${escapeHtml(card.title)}</strong><span>${escapeHtml(card.type)}</span>`;
    button.addEventListener("click", () => runSuggestion(card));
    els.suggestionCards.appendChild(button);
  });
}

function runSuggestion(card) {
  const payload = card.payload || {};
  if (card.type === "price_history") {
    return guard(showPriceHistory);
  }
  if (payload.sortBy) {
    state.sortBy = payload.sortBy;
    setSortActive(state.sortBy);
  }
  const text = suggestionText(card, payload);
  els.refineText.value = text;
  return guard(() => refine(text, payload.sortBy || state.sortBy));
}

function suggestionText(card, payload) {
  if (payload.officialOnly) return "只看官方旗舰店";
  if (payload.selfOperatedOnly) return "只看平台自营";
  if (payload.minRating) return `评价 ${payload.minRating} 分以上`;
  if (payload.color) return `只看${payload.color}款`;
  if (payload.sortBy === "price_asc") return "低价优先";
  if (payload.category) return `相似${payload.category}推荐`;
  return card.title;
}

function renderStats(stats) {
  els.platformStats.innerHTML = "";
  if (!stats.length) {
    els.platformStats.innerHTML = `<div class="stat-card"><span>暂无平台统计</span></div>`;
    return;
  }
  stats.forEach((stat) => {
    const node = document.createElement("div");
    node.className = "stat-card";
    node.innerHTML = `
      <strong>${escapeHtml(stat.platform)}</strong>
      <span>最低 ${stat.lowestPrice.amount} · 均价 ${stat.averagePrice.amount}</span>
      <span>${stat.productCount} 个商品</span>
    `;
    els.platformStats.appendChild(node);
  });
}

function renderEcommerceStatus(fallbackText) {
  els.ecommerceStatus.classList.remove("ok");
  els.ecommerceStatus.title = "";
  if (fallbackText) {
    els.ecommerceStatus.textContent = fallbackText;
    return;
  }
  const missing = ecommerceMissingConfig();
  if (missing.length) {
    els.ecommerceStatus.title = `缺少配置：${missing.join("、")}`;
  }
  if (!state.ecommerceStatus?.enabled) {
    els.ecommerceStatus.textContent = "未启用";
    return;
  }
  if (state.ecommerceStatus.hasConfiguredClient) {
    const enabled = (state.ecommerceStatus.providers || [])
      .filter((provider) => provider.configured)
      .map((provider) => provider.platform)
      .join(" / ");
    els.ecommerceStatus.textContent = enabled || "已配置";
    els.ecommerceStatus.classList.add("ok");
    return;
  }
  els.ecommerceStatus.textContent = missing.length ? "缺少配置" : "未配置";
}

function ecommerceMissingConfig() {
  const missing = new Set();
  (state.ecommerceStatus?.providers || []).forEach((provider) => {
    (provider.missingConfig || []).forEach((item) => missing.add(item));
  });
  return Array.from(missing);
}

function selectedPlatforms() {
  return els.platformFilter.value ? [els.platformFilter.value] : [];
}

function renderProducts(items) {
  els.resultCount.textContent = String(items.length);
  els.productGrid.innerHTML = "";
  if (!items.length) {
    els.productGrid.innerHTML = `<div class="panel empty">暂无结果</div>`;
    return;
  }
  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "product-card";
    const checked = state.selectedIds.has(item.platformProductId) ? "checked" : "";
    card.innerHTML = `
      <img src="${escapeAttr(item.imageUrl || "")}" alt="${escapeAttr(item.title)}" />
      <div class="product-body">
        <div class="product-actions">
          <label class="select-row">
            <input type="checkbox" data-select="${item.platformProductId}" ${checked} />
            对比
          </label>
          <button type="button" data-favorite="${item.platformProductId}">收藏</button>
        </div>
        <div class="product-title">${escapeHtml(item.title)}</div>
        <div class="price-line">
          <span class="price">¥${escapeHtml(item.price.amount)}</span>
          <span class="tag">${escapeHtml(item.platform)}</span>
        </div>
        <div class="metric-row">
          <span>评分 ${item.rating}</span>
          <span>销量 ${formatNumber(item.salesVolume)}</span>
          <span>匹配 ${Math.round(item.matchScore * 100)}%</span>
        </div>
        <div class="tag-row">
          ${sourceTypeTag(item)}
          ${(item.tags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}
          ${item.isOfficial ? `<span class="tag">官方</span>` : ""}
          ${item.isSelfOperated ? `<span class="tag">自营</span>` : ""}
        </div>
        <div class="tag-row">
          ${(item.matchReasons || []).slice(0, 3).map((reason) => `<span class="tag">${escapeHtml(reason)}</span>`).join("")}
        </div>
      </div>
    `;
    card.querySelector("[data-select]").addEventListener("change", (event) => {
      const id = Number(event.target.dataset.select);
      if (event.target.checked) {
        if (state.selectedIds.size >= 4) {
          event.target.checked = false;
          toast("最多选择 4 个商品对比");
          return;
        }
        state.selectedIds.add(id);
      } else {
        state.selectedIds.delete(id);
      }
    });
    card.querySelector("[data-favorite]").addEventListener("click", () => guard(() => favorite(item)));
    els.productGrid.appendChild(card);
  });
}

function renderComparison(comparison) {
  if (!comparison) {
    els.comparisonBox.className = "comparison-box empty";
    els.comparisonBox.textContent = "勾选 2-4 个商品后生成对比";
    return;
  }
  const items = comparison.items || [];
  els.comparisonBox.className = "comparison-box";
  els.comparisonBox.innerHTML = `
    <table class="comparison-table">
      <thead>
        <tr>
          <th>维度</th>
          ${items.map((item) => `<th>${escapeHtml(item.platform)} · ${escapeHtml(item.shopName || "")}</th>`).join("")}
        </tr>
      </thead>
      <tbody>
        <tr><th>商品</th>${items.map((item) => `<td>${escapeHtml(item.title)}</td>`).join("")}</tr>
        <tr><th>价格</th>${items.map((item) => `<td>¥${escapeHtml(item.price.amount)}</td>`).join("")}</tr>
        <tr><th>评分/销量</th>${items.map((item) => `<td>${item.rating} · ${formatNumber(item.salesVolume)}</td>`).join("")}</tr>
        <tr><th>渠道</th>${items.map((item) => `<td>${item.isOfficial ? "官方 " : ""}${item.isSelfOperated ? "自营" : ""}</td>`).join("")}</tr>
        <tr><th>匹配解释</th>${items.map((item) => `<td>${(item.matchReasons || []).map(escapeHtml).join("；")}</td>`).join("")}</tr>
      </tbody>
    </table>
  `;
}

function renderRecommendation(data) {
  els.recommendationBox.classList.remove("empty");
  els.recommendationBox.innerHTML = `
    <strong>${escapeHtml(data.suggestion)} · ${escapeHtml(data.recommendedPlatformProduct?.title || "")}</strong>
    <p class="muted">推荐商品：¥${data.recommendedPlatformProduct?.price?.amount || "-"} · 匹配 ${Math.round((data.recommendedPlatformProduct?.matchScore || 0) * 100)}%</p>
    <ul>${(data.reasons || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    ${(data.risks || []).length ? `<p class="muted">${data.risks.map(escapeHtml).join("；")}</p>` : ""}
    <div class="tag-row">${(data.evidence || []).map((item) => `<span class="tag">${escapeHtml(item.type)}</span>`).join("")}</div>
  `;
}

function renderEcommerceDiagnostics(data) {
  els.recommendationBox.classList.remove("empty");
  els.recommendationBox.innerHTML = `
    <strong>官方 API 诊断 · ${escapeHtml(data.query || "-")}</strong>
    <div class="diagnostic-grid">
      ${(data.providers || []).map((provider) => `
        <div class="diagnostic-row">
          <span>${escapeHtml(provider.platform)}</span>
          <span class="tag ${diagnosticTagClass(provider)}">${provider.success ? "通过" : statusLabel(provider.status)}</span>
          <span>${provider.itemCount || 0} 个商品</span>
          <span>${provider.durationMs || 0} ms</span>
          <p class="muted">${escapeHtml(diagnosticMessage(provider))}</p>
        </div>
      `).join("")}
    </div>
  `;
}

function statusLabel(status) {
  if (status === "not_configured") return "未配置";
  if (status === "not_supported") return "未接入";
  if (status === "failed") return "失败";
  return status || "未知";
}

function diagnosticTagClass(provider) {
  if (provider.success) return "status-ok";
  if (provider.status === "not_supported") return "status-muted";
  return "status-failed";
}

function diagnosticMessage(provider) {
  if (provider.success) {
    return (provider.sampleTitles || []).join("；") || "调用成功";
  }
  if ((provider.missingConfig || []).length) {
    return `缺少配置：${provider.missingConfig.join("、")}`;
  }
  const message = provider.errorMessage || "调用失败";
  return provider.errorCode ? `${provider.errorCode}：${message}` : message;
}

function sourceTypeTag(item) {
  if (item.sourceType === "official_api") {
    return `<span class="tag source-official">官方API</span>`;
  }
  return "";
}

function setSortActive(sortBy) {
  document.querySelectorAll(".sort-tabs button").forEach((button) => {
    button.classList.toggle("active", button.dataset.sort === sortBy);
  });
}

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.setTimeout(() => els.toast.classList.remove("show"), 2200);
}

async function guard(fn) {
  try {
    await fn();
  } catch (error) {
    toast(error.message || "操作失败");
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

function formatNumber(value) {
  if (value >= 10000) return `${(value / 10000).toFixed(1)}万`;
  return String(value);
}

els.registerBtn.addEventListener("click", () => guard(register));
els.loginBtn.addEventListener("click", () => guard(login));
els.loadMeBtn.addEventListener("click", () => guard(loadMe));
els.demoImageBtn.addEventListener("click", () => guard(createDemoImage));
els.startCameraBtn.addEventListener("click", () => guard(startCamera));
els.capturePhotoBtn.addEventListener("click", () => guard(capturePhoto));
els.stopCameraBtn.addEventListener("click", stopCamera);
els.analyzeBtn.addEventListener("click", () => guard(analyze));
els.refineBtn.addEventListener("click", () => guard(() => refine()));
els.compareBtn.addEventListener("click", () => guard(compare));
els.recommendBtn.addEventListener("click", () => guard(recommend));
els.ecommerceCheckBtn.addEventListener("click", () => guard(checkEcommerceApi));
els.imageInput.addEventListener("change", (event) => {
  const [file] = event.target.files || [];
  if (file) {
    state.file = file;
    showPreview(file);
  }
});

els.sourceType.value = state.sourceType;
els.sourceType.addEventListener("change", () => {
  state.sourceType = els.sourceType.value;
  localStorage.setItem("sourceType", state.sourceType);
  if (state.sourceType === "official_api" && !state.ecommerceStatus?.hasConfiguredClient) {
    const missing = ecommerceMissingConfig();
    toast(missing.length ? `官方 API 尚未配置：${missing.slice(0, 4).join("、")}` : "官方 API 尚未配置");
  }
  state.searchTask = null;
  state.items = [];
  state.selectedIds.clear();
  renderProducts([]);
  renderStats([]);
});
els.platformFilter.addEventListener("change", () => {
  state.searchTask = null;
  state.items = [];
  state.selectedIds.clear();
  renderProducts([]);
  renderStats([]);
});

els.apiBase.addEventListener("change", () => guard(loadEcommerceStatus));

document.querySelectorAll(".sort-tabs button").forEach((button) => {
  button.addEventListener("click", () => {
    state.sortBy = button.dataset.sort;
    setSortActive(state.sortBy);
    if (state.searchTask) {
      guard(() => refine(els.refineText.value, state.sortBy));
    }
  });
});

if (state.accessToken) {
  els.authStatus.textContent = "已保存登录态";
  els.authStatus.classList.add("ok");
}

guard(loadEcommerceStatus);
