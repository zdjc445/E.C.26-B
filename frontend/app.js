const els = {
  appShell: document.querySelector(".app-shell"),
  apiBase: document.querySelector("#apiBase"),
  sidePanel: document.querySelector(".side-panel"),
  sidePanelToggle: document.querySelector("#sidePanelToggle"),
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
  demoScenario: document.querySelector("#demoScenario"),
  startCameraBtn: document.querySelector("#startCameraBtn"),
  capturePhotoBtn: document.querySelector("#capturePhotoBtn"),
  stopCameraBtn: document.querySelector("#stopCameraBtn"),
  capturePanel: document.querySelector(".capture-panel"),
  cameraVideo: document.querySelector("#cameraVideo"),
  analyzeBtn: document.querySelector("#analyzeBtn"),
  demoFlowBtn: document.querySelector("#demoFlowBtn"),
  demoStatus: document.querySelector("#demoStatus"),
  demoTimeline: document.querySelector("#demoTimeline"),
  previewImage: document.querySelector("#previewImage"),
  recognitionBox: document.querySelector("#recognitionBox"),
  suggestionCards: document.querySelector("#suggestionCards"),
  refineText: document.querySelector("#refineText"),
  refineBtn: document.querySelector("#refineBtn"),
  loadFavoritesBtn: document.querySelector("#loadFavoritesBtn"),
  loadAlertsBtn: document.querySelector("#loadAlertsBtn"),
  assetsBox: document.querySelector("#assetsBox"),
  loadHistoryBtn: document.querySelector("#loadHistoryBtn"),
  loadImagesBtn: document.querySelector("#loadImagesBtn"),
  historyStatus: document.querySelector("#historyStatus"),
  historyBox: document.querySelector("#historyBox"),
  productGrid: document.querySelector("#productGrid"),
  resultCount: document.querySelector("#resultCount"),
  platformStats: document.querySelector("#platformStats"),
  compareBtn: document.querySelector("#compareBtn"),
  recommendBtn: document.querySelector("#recommendBtn"),
  comparisonBox: document.querySelector("#comparisonBox"),
  recommendationBox: document.querySelector("#recommendationBox"),
  insightBox: document.querySelector("#insightBox"),
  decisionBrief: document.querySelector("#decisionBrief"),
  resultBand: document.querySelector(".result-band"),
  statsBand: document.querySelector(".stats-band"),
  toolbar: document.querySelector(".toolbar"),
  comparisonSection: document.querySelector(".comparison-section"),
  insightSection: document.querySelector(".insight-section"),
  copyBriefBtn: document.querySelector("#copyBriefBtn"),
  copyReportBtn: document.querySelector("#copyReportBtn"),
  toast: document.querySelector("#toast"),
};

let sparklineIdSeed = 0;
const analyzeButtonLabel = els.analyzeBtn?.textContent || "上传并识别";

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
  latestRecommendation: null,
  latestComparison: null,
  latestInsight: null,
  latestBriefText: "",
  demoSteps: [],
  activeDemoStep: "",
};

const demoStepTemplate = [
  { key: "auth", label: "账号就绪", idleDetail: "等待登录态" },
  { key: "recognition", label: "识别召回", idleDetail: "等待商品图" },
  { key: "insight", label: "商品洞察", idleDetail: "等待候选商品" },
  { key: "comparison", label: "跨平台比价", idleDetail: "等待对比" },
  { key: "decision", label: "Agent 决策", idleDetail: "等待证据链" },
  { key: "assets", label: "资产沉淀", idleDetail: "等待收藏提醒" },
];

const demoScenarios = {
  "hair-dryer": {
    fileName: "hair-dryer.jpg",
    brand: "LumaCare",
    title: "低噪音宿舍吹风机",
    subtitle: "黑色款 · 官方 · 1000 元以内",
    query: "1000 元以内的黑色款，要评价 4.8 分以上，只看官方",
    color: "#0f766e",
    accent: "#17211f",
    shape: "dryer",
  },
  headphones: {
    fileName: "headphones.jpg",
    brand: "Auralis",
    title: "主动降噪蓝牙耳机",
    subtitle: "通勤学习 · 长续航 · 只看官方",
    query: "500 元以内的黑色降噪耳机，要长续航，只看官方",
    color: "#2563eb",
    accent: "#3730a3",
    shape: "headphones",
  },
  phone: {
    fileName: "phone.jpg",
    brand: "NovaLink",
    title: "轻薄 5G 智能手机",
    subtitle: "256GB · 黑色 · 好评优先",
    query: "2500 元以内的 5G 手机，要 256GB，评分高一点，只看官方",
    color: "#4f46e5",
    accent: "#0f172a",
    shape: "phone",
  },
  keyboard: {
    fileName: "keyboard.jpg",
    brand: "KeyNest",
    title: "87 键机械键盘",
    subtitle: "茶轴 · 黑色 · 性价比",
    query: "300 元以内的 87 键机械键盘，茶轴，评价 4.6 分以上",
    color: "#b45309",
    accent: "#1f2937",
    shape: "keyboard",
  },
  cup: {
    fileName: "cup.jpg",
    brand: "ThermoNest",
    title: "316 不锈钢保温杯",
    subtitle: "500ml · 便携 · 自营",
    query: "120 元以内的 500ml 保温杯，要 316 不锈钢，自营优先",
    color: "#047857",
    accent: "#334155",
    shape: "cup",
  },
  "running-shoes": {
    fileName: "running-shoes.jpg",
    brand: "StrideLab",
    title: "缓震日常跑步鞋",
    subtitle: "跑步 · 缓震 · 官方渠道",
    query: "500 元以内的缓震跑步鞋，日常跑步用，只看官方",
    color: "#dc2626",
    accent: "#3730a3",
    shape: "shoe",
  },
  skincare: {
    fileName: "skincare.jpg",
    brand: "DermaKind",
    title: "敏感肌保湿护肤乳",
    subtitle: "温和 · 保湿 · 高评分",
    query: "200 元以内的敏感肌保湿护肤乳，要温和高评分，只看官方",
    color: "#be185d",
    accent: "#4a044e",
    shape: "bottle",
  },
};

function apiBase() {
  return els.apiBase.value.replace(/\/$/, "");
}

function sourceTypeLabel(value) {
  if (value === "official_api") return "官方 API";
  if (value === "sample_dataset") return "授权样例数据";
  return "演示数据集";
}

function aiProviderLabel(value, fallbackUsed = false) {
  const label = value === "ark"
    ? "Ark VLM"
    : value === "rule"
      ? "规则解析"
      : value === "mock"
        ? "本地识别样例"
        : value || "本地识别样例";
  return fallbackUsed ? `${label} · 已回退` : label;
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

async function ensureDemoAuth() {
  if (state.accessToken) {
    try {
      await loadMe();
      return;
    } catch {
      state.accessToken = "";
      state.refreshToken = "";
      localStorage.removeItem("accessToken");
      localStorage.removeItem("refreshToken");
    }
  }
  const username = els.username.value.trim() || "alice";
  const password = els.password.value || "password123";
  const nickname = els.nickname.value.trim() || username;
  try {
    const payload = await api("/auth/login", {
      method: "POST",
      body: {
        username,
        password,
      },
    });
    setAuth(payload);
    return;
  } catch {
    try {
      const payload = await api("/auth/register", {
        method: "POST",
        body: { username, password, nickname },
      });
      setAuth(payload);
      return;
    } catch {
      const fallbackUsername = `demo_${Date.now().toString(36)}`;
      els.username.value = fallbackUsername;
      els.password.value = password;
      els.nickname.value = "演示账号";
      const payload = await api("/auth/register", {
        method: "POST",
        body: {
          username: fallbackUsername,
          password,
          nickname: "演示账号",
        },
      });
      setAuth(payload);
    }
  }
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
  const scenario = currentDemoScenario();
  const canvas = document.createElement("canvas");
  canvas.width = 900;
  canvas.height = 640;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#eef3f0";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  drawDemoProduct(ctx, scenario);
  ctx.fillStyle = scenario.accent;
  ctx.font = "bold 48px Microsoft YaHei, sans-serif";
  ctx.fillText(scenario.brand, 150, 150);
  ctx.font = "32px Microsoft YaHei, sans-serif";
  ctx.fillText(scenario.title, 150, 192);
  ctx.font = "24px Microsoft YaHei, sans-serif";
  ctx.fillText(scenario.subtitle, 150, 525);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  state.file = new File([blob], scenario.fileName, { type: "image/png" });
  els.refineText.value = scenario.query;
  showPreview(state.file);
  toast(`已载入示例图：${scenario.title}`);
}

function currentDemoScenario() {
  return demoScenarios[els.demoScenario.value] || demoScenarios["hair-dryer"];
}

function drawDemoProduct(ctx, scenario) {
  ctx.fillStyle = scenario.color;
  if (scenario.shape === "dryer") {
    ctx.fillRect(150, 220, 400, 150);
    ctx.beginPath();
    ctx.arc(570, 295, 105, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = scenario.accent;
    ctx.fillRect(245, 360, 75, 170);
    return;
  }
  if (scenario.shape === "headphones") {
    ctx.lineWidth = 42;
    ctx.strokeStyle = scenario.color;
    ctx.beginPath();
    ctx.arc(430, 300, 160, Math.PI * 1.05, Math.PI * 1.95);
    ctx.stroke();
    ctx.fillRect(235, 285, 95, 165);
    ctx.fillRect(530, 285, 95, 165);
    return;
  }
  if (scenario.shape === "phone") {
    roundRect(ctx, 330, 210, 230, 320, 36, scenario.accent);
    roundRect(ctx, 350, 235, 190, 260, 22, scenario.color);
    return;
  }
  if (scenario.shape === "keyboard") {
    roundRect(ctx, 170, 235, 560, 230, 22, scenario.accent);
    ctx.fillStyle = scenario.color;
    for (let row = 0; row < 4; row++) {
      for (let col = 0; col < 10; col++) {
        roundRect(ctx, 205 + col * 50, 270 + row * 38, 36, 26, 6, scenario.color);
      }
    }
    return;
  }
  if (scenario.shape === "cup") {
    roundRect(ctx, 330, 230, 210, 280, 32, scenario.color);
    ctx.clearRect(360, 250, 150, 20);
    ctx.lineWidth = 22;
    ctx.strokeStyle = scenario.accent;
    ctx.beginPath();
    ctx.arc(550, 350, 70, -Math.PI / 2, Math.PI / 2);
    ctx.stroke();
    return;
  }
  if (scenario.shape === "shoe") {
    ctx.fillStyle = scenario.color;
    ctx.beginPath();
    ctx.moveTo(190, 380);
    ctx.bezierCurveTo(310, 260, 430, 280, 530, 350);
    ctx.bezierCurveTo(615, 355, 690, 390, 720, 430);
    ctx.lineTo(230, 460);
    ctx.closePath();
    ctx.fill();
    roundRect(ctx, 210, 440, 520, 34, 16, scenario.accent);
    return;
  }
  roundRect(ctx, 340, 210, 210, 330, 28, scenario.color);
  roundRect(ctx, 385, 160, 120, 70, 18, scenario.accent);
  roundRect(ctx, 370, 285, 150, 110, 14, "#ffffff");
}

function roundRect(ctx, x, y, width, height, radius, color) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + width - radius, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
  ctx.lineTo(x + width, y + height - radius);
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  ctx.lineTo(x + radius, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.fill();
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
  setVisualBusy(true);
  try {
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
    await refreshSearchFromRecognition();
    toast("识别与推荐列表已刷新");
  } finally {
    setVisualBusy(false);
  }
}

function setVisualBusy(isBusy) {
  els.capturePanel?.classList.toggle("is-scanning", isBusy);
  els.analyzeBtn.disabled = isBusy;
  els.analyzeBtn.setAttribute("aria-busy", String(isBusy));
  els.analyzeBtn.textContent = isBusy ? "识别中..." : analyzeButtonLabel;
}

async function runDemoFlow() {
  resetDemoTimeline();
  els.demoFlowBtn.disabled = true;
  toast("正在演示完整购物决策链路");
  try {
    updateDemoStep("auth", "active", "正在确认登录态");
    await ensureDemoAuth();
    updateDemoStep("auth", "done", `当前用户：${els.authStatus.textContent || "已登录"}`);

    updateDemoStep("recognition", "active", "正在载入示例图并召回商品");
    await createDemoImage();
    await analyze();
    if (!state.items.length) {
      throw new Error("演示数据未召回商品");
    }
    updateDemoStep("recognition", "done", `${state.recognition?.category || "商品"} · ${state.items.length} 个候选`);

    state.selectedIds = new Set(state.items.slice(0, 4).map((item) => item.platformProductId));
    renderProducts(state.items);

    updateDemoStep("insight", "active", "正在分析价格走势和评价风险");
    const insight = await showProductInsight(state.items[0]);
    updateDemoStep("insight", "done", insightSummary(insight));

    updateDemoStep("comparison", "active", "正在生成横向对比");
    const comparison = await compare();
    updateDemoStep("comparison", "done", `${comparison.items.length} 个商品 · ${comparison.platformStats.length} 个平台`);

    updateDemoStep("decision", "active", "正在计算决策信号和轨迹");
    const recommendation = await recommend();
    const action = decisionAction(recommendation.suggestion);
    updateDemoStep("decision", "done", `${recommendation.decisionScore} 分 · ${action.label}`);

    updateDemoStep("assets", "active", "正在沉淀收藏和价格提醒");
    await favorite(state.items[0]);
    await createPriceAlert(state.items[0]);
    updateDemoStep("assets", "done", "收藏与目标价提醒已同步");

    setDemoStatus("演示完成", "ok");
    els.decisionBrief.scrollIntoView({ behavior: "smooth", block: "start" });
    toast("演示链路已完成");
  } catch (error) {
    failActiveDemoStep(error.message || "演示失败");
    throw error;
  } finally {
    els.demoFlowBtn.disabled = false;
  }
}

function resetDemoTimeline() {
  state.activeDemoStep = "";
  state.demoSteps = demoStepTemplate.map((step) => ({
    ...step,
    status: "idle",
    detail: step.idleDetail,
  }));
  setDemoStatus("待启动");
  renderDemoTimeline();
}

function updateDemoStep(key, status, detail) {
  state.activeDemoStep = status === "active" ? key : "";
  state.demoSteps = state.demoSteps.map((step) => (
    step.key === key ? { ...step, status, detail: detail || step.detail } : step
  ));
  if (status === "active") {
    setDemoStatus("演示中", "live");
  }
  renderDemoTimeline();
}

function failActiveDemoStep(message) {
  if (state.activeDemoStep) {
    updateDemoStep(state.activeDemoStep, "error", message);
  }
  setDemoStatus("需检查", "failed");
}

function setDemoStatus(text, tone = "") {
  els.demoStatus.textContent = text;
  els.demoStatus.className = `status-pill ${tone}`.trim();
}

function renderDemoTimeline() {
  els.demoTimeline.innerHTML = state.demoSteps.map((step, index) => `
    <div class="demo-step ${escapeAttr(step.status)}">
      <span class="demo-index">${index + 1}</span>
      <div>
        <strong>${escapeHtml(step.label)}</strong>
        <p>${escapeHtml(step.detail || step.idleDetail)}</p>
      </div>
    </div>
  `).join("");
}

function insightSummary(insight) {
  const history = insight?.history || {};
  const review = insight?.review || {};
  const low = history.lowestPrice?.amount || "-";
  const risk = Math.round((review.riskScore || 0) * 100);
  return `低点 ¥${low} · 风险 ${risk}%`;
}

async function refreshSearchFromRecognition() {
  if (!state.recognition) {
    throw new Error("请先完成识别");
  }
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
  resetDecisionPanels();
  applySearchPayload(state.searchTask);
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
  resetDecisionPanels();
  applySearchPayload(payload);
  toast("推荐列表已刷新");
}

async function saveRecognitionCorrection() {
  if (!state.recognition) {
    throw new Error("请先完成识别");
  }
  const category = recognitionFieldValue("category");
  if (!category) {
    throw new Error("类目不能为空");
  }
  state.recognition = await api(`/recognitions/${state.recognition.recognitionId}/attributes`, {
    method: "PATCH",
    body: {
      category,
      brand: recognitionFieldValue("brand"),
      model: recognitionFieldValue("model"),
      attributes: parseAttributesText(recognitionFieldValue("attributes", false)),
    },
  });
  renderRecognition(state.recognition);
  await refreshSearchFromRecognition();
  toast("识别修正已生效");
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
  state.latestComparison = comparison;
  renderDecisionBrief();
  toast(`最低价：${comparison.lowestPrice?.amount || "-"} CNY`);
  return comparison;
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
  state.latestRecommendation = recommendation;
  renderRecommendation(recommendation);
  renderDecisionBrief(recommendation);
  toast("推荐理由已生成");
  return recommendation;
}

async function favorite(item) {
  try {
    const payload = await api("/favorites", {
      method: "POST",
      body: {
        platformProductId: item.platformProductId,
        note: `来自搜索任务 ${state.searchTask?.searchTaskId || "-"}`,
      },
    });
    toast("已加入收藏，后续推荐可作为个性化参考");
    await loadFavorites();
    return payload;
  } catch (error) {
    if (String(error.message || "").includes("already favorited")) {
      toast("该商品已在收藏中");
      await loadFavorites();
      return null;
    }
    throw error;
  }
}

async function createPriceAlert(item) {
  const current = Number(item.price?.amount || 0);
  const amount = Math.max(1, current * 0.92);
  try {
    const payload = await api("/price-alerts", {
      method: "POST",
      body: {
        platformProductId: item.platformProductId,
        targetPrice: { amount: formatMoney(amount), currency: "CNY" },
        enabled: true,
      },
    });
    toast(`已设置 ¥${formatMoney(amount)} 提醒`);
    await loadPriceAlerts();
    return payload;
  } catch (error) {
    if (String(error.message || "").includes("price alert already exists")) {
      toast("该商品已存在价格提醒");
      await loadPriceAlerts();
      return null;
    }
    throw error;
  }
}

async function loadFavorites() {
  const page = await api("/favorites?page=1&pageSize=5");
  renderAssets("收藏商品", page.items || []);
}

async function loadPriceAlerts() {
  const page = await api("/price-alerts?page=1&pageSize=5");
  renderAssets("价格提醒", page.items || []);
}

async function loadSearchHistory() {
  setHistoryStatus("加载中", "live");
  const page = await api("/search-tasks?page=1&pageSize=8");
  renderHistory("搜索历史", page.items || [], "search");
  setHistoryStatus(page.items?.length ? `${page.total} 条` : "暂无", page.items?.length ? "ok" : "");
}

async function loadImages() {
  setHistoryStatus("加载中", "live");
  const page = await api("/images?page=1&pageSize=8");
  renderHistory("上传图片", page.items || [], "image");
  setHistoryStatus(page.items?.length ? `${page.total} 张` : "暂无", page.items?.length ? "ok" : "");
}

async function restoreSearchTask(searchTaskId) {
  const task = await api(`/search-tasks/${searchTaskId}`);
  state.searchTask = task;
  state.recognition = task.recognition || null;
  state.items = task.items || [];
  state.selectedIds.clear();
  state.lastFilterText = task.query || "";
  if (task.query) {
    els.refineText.value = task.query;
  }
  if (task.sourceType && Array.from(els.sourceType.options).some((option) => option.value === task.sourceType)) {
    state.sourceType = task.sourceType;
    els.sourceType.value = task.sourceType;
    localStorage.setItem("sourceType", state.sourceType);
  }
  resetDecisionPanels();
  if (state.recognition) {
    renderRecognition(state.recognition);
  } else {
    setSectionVisible(els.resultBand, true);
    els.recognitionBox.className = "recognition-box empty";
    els.recognitionBox.textContent = "基于文字需求恢复";
  }
  applySearchPayload(task);
  setHistoryStatus("已恢复", "ok");
  els.decisionBrief?.scrollIntoView({ behavior: "smooth", block: "start" });
  toast(`已恢复搜索任务 #${searchTaskId}`);
}

async function deleteImage(imageId) {
  await api(`/images/${imageId}`, { method: "DELETE" });
  toast(`图片 #${imageId} 已删除`);
  await loadImages();
}

async function showPriceHistory() {
  return showProductInsight(state.items[0]);
}

async function showProductInsight(item) {
  if (!item) {
    throw new Error("没有商品可查询洞察");
  }
  const [history, review] = await Promise.all([
    api(`/platform-products/${item.platformProductId}/price-history?days=90`),
    api(`/platform-products/${item.platformProductId}/review-summary`),
  ]);
  state.latestInsight = { item, history, review };
  renderProductInsight(item, history, review);
  renderDecisionBrief();
  return { history, review };
}

function applySearchPayload(payload) {
  state.items = payload.items || [];
  renderSuggestions(payload.suggestionCards || []);
  renderStats(payload.platformStats || []);
  renderProducts(state.items);
  renderSearchSnapshot();
  renderDecisionBrief();
}

function renderRecognition(data) {
  const attrText = attributesToText(data.attributes || {});
  const attrs = Object.entries(data.attributes || {})
    .map(([key, value]) => `<span class="tag">${escapeHtml(key)}：${escapeHtml(String(value))}</span>`)
    .join("");
  els.recognitionBox.classList.remove("empty");
  setSectionVisible(els.resultBand, true);
  els.recognitionBox.innerHTML = `
    <div class="price-line">
      <strong>${escapeHtml(data.category)}</strong>
      <span class="tag">${Math.round(data.confidence * 100)}%</span>
    </div>
    <p class="muted">品牌：${escapeHtml(data.brand || "未知")} · 型号：${escapeHtml(data.model || "-")} · 识别源：${escapeHtml(aiProviderLabel(data.aiProvider, data.fallbackUsed))}</p>
    <div class="tag-row">${data.keywords.map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")}</div>
    <div class="tag-row">${attrs}</div>
    ${data.explanation ? `<p class="muted">${escapeHtml(data.explanation)}</p>` : ""}
    <div class="recognition-actions">
      <button type="button" data-edit-recognition>修正</button>
    </div>
    <form class="recognition-editor" data-recognition-editor hidden>
      <div class="editor-grid">
        <label>
          类目
          <input data-recognition-field="category" value="${escapeAttr(data.category || "")}" />
        </label>
        <label>
          品牌
          <input data-recognition-field="brand" value="${escapeAttr(data.brand || "")}" />
        </label>
        <label>
          型号
          <input data-recognition-field="model" value="${escapeAttr(data.model || "")}" />
        </label>
      </div>
      <label>
        属性
        <textarea data-recognition-field="attributes">${escapeHtml(attrText)}</textarea>
      </label>
      <div class="button-row">
        <button type="button" data-cancel-recognition>取消</button>
        <button type="button" class="primary" data-save-recognition>保存修正</button>
      </div>
    </form>
  `;
  els.recognitionBox.querySelector("[data-edit-recognition]").addEventListener("click", showRecognitionEditor);
  els.recognitionBox.querySelector("[data-cancel-recognition]").addEventListener("click", hideRecognitionEditor);
  els.recognitionBox.querySelector("[data-save-recognition]").addEventListener("click", () => guard(saveRecognitionCorrection));
}

function showRecognitionEditor() {
  const editor = els.recognitionBox.querySelector("[data-recognition-editor]");
  const editButton = els.recognitionBox.querySelector("[data-edit-recognition]");
  if (editor) {
    editor.hidden = false;
  }
  if (editButton) {
    editButton.hidden = true;
  }
}

function hideRecognitionEditor() {
  const editor = els.recognitionBox.querySelector("[data-recognition-editor]");
  const editButton = els.recognitionBox.querySelector("[data-edit-recognition]");
  if (editor) {
    editor.hidden = true;
  }
  if (editButton) {
    editButton.hidden = false;
  }
}

function recognitionFieldValue(name, trim = true) {
  const field = els.recognitionBox.querySelector(`[data-recognition-field="${name}"]`);
  const value = field?.value || "";
  return trim ? value.trim() : value;
}

function attributesToText(attributes) {
  return Object.entries(attributes)
    .map(([key, value]) => `${key}=${formatAttributeValue(value)}`)
    .join("\n");
}

function formatAttributeValue(value) {
  if (value && typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value ?? "");
}

function parseAttributesText(text) {
  return text.split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .reduce((attributes, line) => {
      const separator = attributeSeparatorIndex(line);
      if (separator <= 0) {
        return attributes;
      }
      const key = line.slice(0, separator).trim();
      const value = line.slice(separator + 1).trim();
      if (key) {
        attributes[key] = parseAttributeValue(value);
      }
      return attributes;
    }, {});
}

function attributeSeparatorIndex(line) {
  const candidates = ["=", "：", ":"]
    .map((separator) => line.indexOf(separator))
    .filter((index) => index >= 0);
  return candidates.length ? Math.min(...candidates) : -1;
}

function parseAttributeValue(value) {
  if (value === "true") return true;
  if (value === "false") return false;
  if (/^-?\d+(\.\d+)?$/.test(value)) return Number(value);
  if ((value.startsWith("{") && value.endsWith("}")) || (value.startsWith("[") && value.endsWith("]"))) {
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }
  return value;
}

function resetDecisionPanels() {
  renderComparison(null);
  state.latestRecommendation = null;
  state.latestComparison = null;
  state.latestInsight = null;
  els.recommendationBox.className = "recommendation-box empty";
  els.recommendationBox.textContent = "";
  els.insightBox.className = "insight-box empty";
  els.insightBox.textContent = "";
  setSectionVisible(els.insightSection, false);
  renderDecisionBrief();
}

function renderSuggestions(cards) {
  els.suggestionCards.innerHTML = "";
  setSectionVisible(els.resultBand, Boolean(state.recognition || cards.length));
  cards.forEach((card) => {
    const button = document.createElement("button");
    button.className = "suggestion-card";
    button.innerHTML = `<strong>${escapeHtml(card.title)}</strong><span>${escapeHtml(suggestionTypeLabel(card.type))}</span>`;
    button.addEventListener("click", () => runSuggestion(card));
    els.suggestionCards.appendChild(button);
  });
}

function suggestionTypeLabel(type) {
  if (type === "sort") return "排序建议";
  if (type === "official") return "官方渠道";
  if (type === "filter") return "筛选条件";
  if (type === "price_history") return "价格走势";
  if (type === "similar") return "相似推荐";
  return "智能建议";
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
    setSectionVisible(els.statsBand, Boolean(state.items.length || state.latestRecommendation));
    return;
  }
  setSectionVisible(els.statsBand, true);
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
    setSectionVisible(els.toolbar, false);
    setSectionVisible(els.productGrid, false);
    return;
  }
  setSectionVisible(els.toolbar, true);
  setSectionVisible(els.productGrid, true);
  const recommendedId = state.latestRecommendation?.recommendedPlatformProduct?.platformProductId;
  items.forEach((item, index) => {
    const card = document.createElement("article");
    const isPriority = item.platformProductId === recommendedId || Number(item.matchScore || 0) > 0.9;
    card.className = `product-card${isPriority ? " is-priority" : ""}`;
    card.style.animationDelay = `${index * 60}ms`;
    const checked = state.selectedIds.has(item.platformProductId) ? "checked" : "";
    card.innerHTML = `
      <img src="${escapeAttr(item.imageUrl || "")}" alt="${escapeAttr(item.title)}" loading="lazy" />
      <div class="product-body">
        <div class="product-actions">
          <label class="select-row">
            <input type="checkbox" data-select="${item.platformProductId}" ${checked} />
            对比
          </label>
          <div class="product-action-buttons">
            <button type="button" data-insight="${item.platformProductId}">洞察</button>
            <button type="button" data-alert="${item.platformProductId}">提醒</button>
            <button type="button" data-favorite="${item.platformProductId}">收藏</button>
          </div>
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
    card.querySelector("[data-alert]").addEventListener("click", () => guard(() => createPriceAlert(item)));
    card.querySelector("[data-insight]").addEventListener("click", () => guard(() => showProductInsight(item)));
    els.productGrid.appendChild(card);
  });
}

function renderComparison(comparison) {
  if (!comparison) {
    els.comparisonBox.className = "comparison-box empty";
    els.comparisonBox.textContent = "";
    setSectionVisible(els.comparisonSection, false);
    return;
  }
  const items = comparison.items || [];
  els.comparisonBox.className = "comparison-box";
  setSectionVisible(els.comparisonSection, true);
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
  const recommendedId = data.recommendedPlatformProduct?.platformProductId;
  const product = state.items.find((item) => item.platformProductId === recommendedId);
  const score = decisionScore(data, product);
  const action = decisionAction(data.suggestion);
  els.recommendationBox.className = "recommendation-box decision-box";
  setSectionVisible(els.statsBand, true);
  renderProducts(state.items);
  els.recommendationBox.innerHTML = `
    <div class="decision-hero">
      <div>
        <span class="decision-action ${action.className}">${escapeHtml(action.label)}</span>
        <strong>${escapeHtml(data.recommendedPlatformProduct?.title || "等待候选商品")}</strong>
        <p class="muted">¥${data.recommendedPlatformProduct?.price?.amount || "-"} · 匹配 ${Math.round((data.recommendedPlatformProduct?.matchScore || 0) * 100)}%</p>
      </div>
      <div class="score-ring score-ring-animate" style="--target-score:${score.total}">
        <span data-score-value>${score.total}</span>
        <small>决策分</small>
      </div>
    </div>
    <div class="signal-grid">
      ${score.signals.map((signal) => `
        <div class="signal-row">
          <span>${escapeHtml(signal.label)}</span>
          <div class="signal-bar"><i style="width:${signal.value}%"></i></div>
          <strong>${signal.value}</strong>
        </div>
      `).join("")}
    </div>
    ${renderMarketRationale(data, product)}
    ${renderDecisionTrace(data.decisionTrace || [])}
    ${renderCandidateMatrix(data.candidateAnalyses || [])}
    <div class="reason-grid">
      ${(data.reasons || []).slice(0, 4).map((item) => `<div class="reason-card">${escapeHtml(item)}</div>`).join("")}
    </div>
    ${(data.risks || []).length ? `<div class="risk-line">${data.risks.map(escapeHtml).join("；")}</div>` : ""}
    <div class="evidence-grid">
      ${(data.evidence || []).map((item) => `
        <div class="evidence-chip">
          <span>${escapeHtml(evidenceLabel(item.type))}</span>
          <p>${escapeHtml(item.content || "")}</p>
        </div>
      `).join("")}
    </div>
  `;
  animateScoreRing(els.recommendationBox.querySelector(".score-ring"), score.total);
  if (product) {
    guard(() => showProductInsight(product));
  }
}

function animateScoreRing(ring, targetScore) {
  if (!ring) {
    return;
  }
  const valueNode = ring.querySelector("[data-score-value]");
  const target = clampPercent(targetScore);
  const startedAt = performance.now();
  const duration = 650;
  ring.style.setProperty("--target-score", target);
  ring.classList.remove("score-ring-animate");
  ring.offsetWidth;
  ring.classList.add("score-ring-animate");

  function tick(now) {
    const progress = Math.min(1, (now - startedAt) / duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    if (valueNode) {
      valueNode.textContent = String(Math.round(target * eased));
    }
    if (progress < 1) {
      requestAnimationFrame(tick);
    }
  }
  requestAnimationFrame(tick);
}

function renderMarketRationale(data, product) {
  const items = Array.isArray(state.items) ? state.items.slice() : [];
  if (!items.length || !product) {
    return "";
  }
  const priced = items
    .filter((item) => Number.isFinite(Number(item.price?.amount)))
    .sort((left, right) => Number(left.price.amount) - Number(right.price.amount));
  if (!priced.length) {
    return "";
  }
  const lowest = priced[0];
  const highest = priced[priced.length - 1];
  const currentPrice = Number(product.price?.amount || data.recommendedPlatformProduct?.price?.amount || 0);
  const lowestPrice = Number(lowest.price?.amount || 0);
  const highestPrice = Number(highest.price?.amount || currentPrice);
  const gap = Math.max(0, currentPrice - lowestPrice);
  const saving = Math.max(0, highestPrice - currentPrice);
  const priceRank = priced.findIndex((item) => item.platformProductId === product.platformProductId) + 1 || "-";
  const channel = [
    product.isOfficial ? "官方" : "",
    product.isSelfOperated ? "自营" : "",
  ].filter(Boolean).join(" / ") || "普通渠道";
  const headline = gap > 0
    ? `比最低价高 ¥${formatMoney(gap)}，换取 ${channel} 确定性`
    : `当前推荐已处于最低价梯队，渠道为 ${channel}`;
  return `
    <div class="market-rationale">
      <div class="market-rationale-head">
        <span>价格-可信度取舍</span>
        <strong>${escapeHtml(headline)}</strong>
      </div>
      <div class="market-rationale-grid">
        <div><span>最低价</span><strong>¥${escapeHtml(formatMoney(lowestPrice))}</strong><small>${escapeHtml(lowest.platform)}</small></div>
        <div><span>信任溢价</span><strong>¥${escapeHtml(formatMoney(gap))}</strong><small>价格排名 #${escapeHtml(priceRank)}/${priced.length}</small></div>
        <div><span>高价差</span><strong>¥${escapeHtml(formatMoney(saving))}</strong><small>相对最高候选</small></div>
      </div>
    </div>
  `;
}

function renderDecisionTrace(steps) {
  if (!Array.isArray(steps) || !steps.length) {
    return "";
  }
  return `
    <div class="decision-trace">
      ${steps.map((step) => `
        <div class="trace-step trace-${escapeAttr(step.status || "done")}">
          <span class="trace-dot"></span>
          <div>
            <strong>${escapeHtml(step.label || evidenceLabel(step.key))}</strong>
            <p>${escapeHtml(step.observation || "")}</p>
          </div>
          <small>${clampPercent(step.confidence || 0)}</small>
        </div>
      `).join("")}
    </div>
  `;
}

function renderCandidateMatrix(candidates) {
  if (!Array.isArray(candidates) || !candidates.length) {
    return "";
  }
  return `
    <div class="candidate-matrix">
      ${candidates.slice(0, 4).map((candidate) => {
        const verdict = candidateVerdict(candidate.verdict);
        return `
          <div class="candidate-cell ${escapeAttr(candidate.verdict || "watch")}">
            <div class="candidate-head">
              <span>${escapeHtml(`#${candidate.rank || "-"}`)}</span>
              <strong>${escapeHtml(verdict)}</strong>
              <em>${clampPercent(candidate.decisionScore || 0)}</em>
            </div>
            <p>${escapeHtml(candidate.title || "-")}</p>
            <div class="candidate-tags">
              ${(candidate.strengths || []).slice(0, 3).map((item) => `<span class="tag status-ok">${escapeHtml(item)}</span>`).join("")}
              ${(candidate.weaknesses || []).slice(0, 2).map((item) => `<span class="tag status-failed">${escapeHtml(item)}</span>`).join("")}
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderProductInsight(item, history, review) {
  const points = history.points || [];
  const riskTags = review.riskTags || [];
  const positives = review.positiveTags || [];
  els.insightBox.className = "insight-box";
  setSectionVisible(els.insightSection, true);
  els.insightBox.innerHTML = `
    <div class="insight-head">
      <div>
        <strong>${escapeHtml(item.title)}</strong>
        <p class="muted">${escapeHtml(item.platform)} · ${escapeHtml(item.shopName || "-")} · ${review.reviewCount || 0} 条评价样本</p>
      </div>
      <span class="tag ${riskTags.length ? "status-failed" : "status-ok"}">风险 ${Math.round((review.riskScore || 0) * 100)}%</span>
    </div>
    <div class="price-summary">
      <div><span>当前</span><strong>¥${escapeHtml(history.currentPrice?.amount || item.price.amount)}</strong></div>
      <div><span>低点</span><strong>¥${escapeHtml(history.lowestPrice?.amount || "-")}</strong></div>
      <div><span>高点</span><strong>¥${escapeHtml(history.highestPrice?.amount || "-")}</strong></div>
      <div><span>趋势</span><strong>${trendLabel(history.trend)}</strong></div>
    </div>
    ${renderSparkline(points)}
    <div class="tag-row">
      ${positives.slice(0, 4).map((tag) => `<span class="tag status-ok">${escapeHtml(tag)}</span>`).join("")}
      ${riskTags.slice(0, 4).map((tag) => `<span class="tag status-failed">${escapeHtml(tag)}</span>`).join("")}
    </div>
    <p class="muted">${escapeHtml(review.summary || "暂无评价摘要。")}</p>
  `;
  attachSparklineTooltip(els.insightBox.querySelector(".sparkline-wrap"));
}

function renderSearchSnapshot() {
  if (!state.items.length || state.latestRecommendation) {
    return;
  }
  const best = state.items[0];
  const priceValues = state.items.map((item) => Number(item.price.amount)).filter(Number.isFinite);
  const min = Math.min(...priceValues);
  const max = Math.max(...priceValues);
  els.recommendationBox.className = "recommendation-box snapshot-box";
  setSectionVisible(els.statsBand, true);
  els.recommendationBox.innerHTML = `
    <div class="snapshot-grid">
      <div><span>候选</span><strong>${state.items.length}</strong></div>
      <div><span>最低价</span><strong>¥${formatMoney(min)}</strong></div>
      <div><span>价格带</span><strong>¥${formatMoney(min)}-${formatMoney(max)}</strong></div>
      <div><span>首位匹配</span><strong>${Math.round(best.matchScore * 100)}%</strong></div>
    </div>
    <p class="muted">当前首位：${escapeHtml(best.title)}</p>
  `;
}

function renderDecisionBrief(recommendation = state.latestRecommendation) {
  if (!state.items.length) {
    state.latestBriefText = "";
    if (els.copyBriefBtn) {
      els.copyBriefBtn.disabled = true;
    }
    els.decisionBrief.className = "brief-band empty";
    delete els.decisionBrief.dataset.recommendationId;
    setSectionVisible(els.decisionBrief, false);
    return;
  }
  setSectionVisible(els.decisionBrief, true);
  const prices = state.items.map((item) => Number(item.price?.amount)).filter(Number.isFinite);
  const minPrice = prices.length ? Math.min(...prices) : 0;
  const maxPrice = prices.length ? Math.max(...prices) : 0;
  const best = state.items[0];
  const recommendedId = recommendation?.recommendedPlatformProduct?.platformProductId;
  const recommendedItem = state.items.find((item) => item.platformProductId === recommendedId) || best;
  const action = decisionAction(recommendation?.suggestion || "compare");
  const score = recommendation?.decisionScore ?? "-";
  const riskCount = recommendation?.risks?.length ?? state.latestInsight?.review?.riskTags?.length ?? "-";
  const traceCount = recommendation?.decisionTrace?.length || 0;
  const platformCount = state.latestComparison?.platformStats?.length || uniquePlatforms(state.items).size;
  const summaryTitle = recommendation
    ? `${action.label}：${recommendation.recommendedPlatformProduct?.title || recommendedItem.title}`
    : `候选首位：${recommendedItem.title}`;
  const summaryLine = recommendation
    ? `¥${recommendation.recommendedPlatformProduct?.price?.amount || recommendedItem.price.amount} · ${platformCount} 个平台 · ${traceCount || 6} 步决策轨迹`
    : `${state.items.length} 个候选 · 价格带 ¥${formatMoney(minPrice)}-${formatMoney(maxPrice)} · 首位匹配 ${Math.round(best.matchScore * 100)}%`;
  state.latestBriefText = buildBriefText(recommendation, recommendedItem, minPrice, maxPrice, platformCount);
  els.decisionBrief.className = `brief-band ${recommendation ? "complete" : ""}`.trim();
  els.decisionBrief.dataset.recommendationId = recommendation?.recommendationId || "";
  els.decisionBrief.innerHTML = `
    <div class="brief-main">
      <span>决策摘要</span>
      <strong>${escapeHtml(summaryTitle)}</strong>
      <p>${escapeHtml(summaryLine)}</p>
    </div>
    <div class="brief-metrics">
      ${briefMetric("候选", state.items.length)}
      ${briefMetric("最低价", `¥${formatMoney(minPrice)}`)}
      ${briefMetric("决策分", score)}
      ${briefMetric("风险", riskCount)}
    </div>
    <div class="brief-actions">
      <button id="copyBriefBtn" type="button">复制摘要</button>
      <button id="copyReportBtn" type="button" ${recommendation ? "" : "disabled"}>复制报告</button>
    </div>
  `;
  bindBriefActions();
}

function briefMetric(label, value) {
  return `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function bindBriefActions() {
  els.copyBriefBtn = document.querySelector("#copyBriefBtn");
  els.copyReportBtn = document.querySelector("#copyReportBtn");
  els.copyBriefBtn.addEventListener("click", () => guard(copyBrief));
  els.copyReportBtn.addEventListener("click", () => guard(copyReport));
}

async function copyBrief() {
  const text = state.latestBriefText || buildBriefText(state.latestRecommendation);
  if (!text) {
    throw new Error("暂无摘要可复制");
  }
  await copyText(text);
  toast("答辩摘要已复制");
}

async function copyReport() {
  if (!state.latestRecommendation) {
    throw new Error("请先生成推荐");
  }
  const report = await api(`/agent/recommendations/${state.latestRecommendation.recommendationId}/report`);
  await copyText(report.markdown);
  toast("证据报告已复制");
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
  } else {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
}

function buildBriefText(recommendation = state.latestRecommendation, item, minPrice, maxPrice, platformCount) {
  if (!state.items.length) {
    return "";
  }
  const prices = state.items.map((entry) => Number(entry.price?.amount)).filter(Number.isFinite);
  const low = minPrice ?? (prices.length ? Math.min(...prices) : 0);
  const high = maxPrice ?? (prices.length ? Math.max(...prices) : 0);
  const selected = item || state.items.find((entry) => entry.platformProductId === recommendation?.recommendedPlatformProduct?.platformProductId) || state.items[0];
  const platforms = platformCount || uniquePlatforms(state.items).size;
  if (!recommendation) {
    return `当前召回 ${state.items.length} 个候选，覆盖 ${platforms} 个平台，价格带 ¥${formatMoney(low)}-${formatMoney(high)}，首位候选为 ${selected.title}。`;
  }
  const action = decisionAction(recommendation.suggestion);
  const signals = (recommendation.decisionSignals || [])
    .map((signal) => `${signal.label || signal.key}:${signal.score}`)
    .join("，");
  const candidateLine = (recommendation.candidateAnalyses || []).slice(0, 3)
    .map((candidate) => `#${candidate.rank}${candidateVerdict(candidate.verdict)}:${candidate.decisionScore}`)
    .join("，");
  const risks = (recommendation.risks || []).join("；") || "未发现明确高频风险";
  return `Agent ${action.label}：${recommendation.recommendedPlatformProduct?.title || selected.title}。决策分 ${recommendation.decisionScore}，候选 ${state.items.length} 个，覆盖 ${platforms} 个平台，最低价 ¥${formatMoney(low)}。候选矩阵：${candidateLine || "已完成"}。信号：${signals}。风险：${risks}。`;
}

function uniquePlatforms(items) {
  return new Set(items.map((item) => item.platform).filter(Boolean));
}

function renderAssets(title, items) {
  setSectionVisible(els.assetsBox, items.length > 0);
  els.assetsBox.className = items.length ? "assets-box" : "assets-box empty";
  if (!items.length) {
    els.assetsBox.textContent = "";
    return;
  }
  els.assetsBox.innerHTML = `
    <strong>${escapeHtml(title)}</strong>
    ${items.map((item) => `
      <div class="asset-row">
        <span>${escapeHtml(item.title || item.platform || "-")}</span>
        <small>${assetMeta(item)}</small>
      </div>
    `).join("")}
  `;
}

function renderHistory(title, items, kind) {
  setSectionVisible(els.historyBox, true);
  els.historyBox.className = items.length ? "history-box" : "history-box empty";
  if (!items.length) {
    els.historyBox.innerHTML = `<strong>${escapeHtml(title)}</strong><p class="muted">暂无记录</p>`;
    return;
  }
  els.historyBox.innerHTML = `
    <strong>${escapeHtml(title)}</strong>
    ${kind === "search"
      ? items.map((item) => `
        <button class="history-row" type="button" data-restore-search="${item.searchTaskId}">
          <span>${escapeHtml(item.query || `搜索任务 #${item.searchTaskId}`)}</span>
          <small>${escapeHtml(sourceTypeLabel(item.sourceType))} · ${item.resultCount || 0} 个候选 · ${formatDateTime(item.createdAt)}</small>
        </button>
      `).join("")
      : items.map((item) => `
        <div class="history-row image-history-row">
          <div>
            <span>图片 #${escapeHtml(item.imageId)}</span>
            <small>${escapeHtml(item.contentType || "-")} · ${formatBytes(item.size)} · ${formatDateTime(item.createdAt)}</small>
          </div>
          <button type="button" data-delete-image="${item.imageId}">删除</button>
        </div>
      `).join("")}
  `;
  els.historyBox.querySelectorAll("[data-restore-search]").forEach((button) => {
    button.addEventListener("click", () => guard(() => restoreSearchTask(Number(button.dataset.restoreSearch))));
  });
  els.historyBox.querySelectorAll("[data-delete-image]").forEach((button) => {
    button.addEventListener("click", () => guard(() => deleteImage(Number(button.dataset.deleteImage))));
  });
}

function setHistoryStatus(text, tone = "") {
  if (!els.historyStatus) {
    return;
  }
  els.historyStatus.textContent = text;
  els.historyStatus.className = `status-pill ${tone}`.trim();
}

function decisionScore(data, product) {
  if (Array.isArray(data.decisionSignals) && data.decisionSignals.length) {
    const signals = data.decisionSignals.map((signal) => ({
      label: signal.label || evidenceLabel(signal.key),
      value: clampPercent(signal.score),
    }));
    const total = data.decisionScore !== undefined
      ? clampPercent(data.decisionScore)
      : weightedDecisionScore(signals);
    return { total, signals };
  }
  const match = Math.round((data.recommendedPlatformProduct?.matchScore || product?.matchScore || 0) * 100);
  const rating = Math.round(((product?.rating || 4.5) / 5) * 100);
  const channel = product ? Math.min(100, 70 + (product.isOfficial ? 15 : 0) + (product.isSelfOperated ? 15 : 0)) : 70;
  const risk = Math.max(45, 100 - (data.risks || []).length * 18);
  const signals = [
    { label: "匹配", value: match },
    { label: "口碑", value: rating },
    { label: "渠道", value: channel },
    { label: "风险", value: risk },
  ];
  return { total: weightedDecisionScore(signals), signals };
}

function decisionAction(value) {
  if (value === "buy") return { label: "建议购买", className: "buy" };
  if (value === "wait") return { label: "建议观望", className: "wait" };
  if (value === "avoid") return { label: "建议避开", className: "avoid" };
  if (value === "compare") return { label: "建议比较", className: "wait" };
  return { label: value || "待判断", className: "wait" };
}

function weightedDecisionScore(signals) {
  if (!signals.length) return 0;
  const total = signals.reduce((sum, signal) => sum + clampPercent(signal.value), 0) / signals.length;
  return clampPercent(total);
}

function clampPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return Math.max(0, Math.min(100, Math.round(number)));
}

function evidenceLabel(type) {
  if (type === "price") return "价格";
  if (type === "match") return "匹配";
  if (type === "review") return "评价";
  if (type === "history") return "历史";
  return type || "证据";
}

function candidateVerdict(value) {
  if (value === "winner") return "胜出";
  if (value === "runner_up") return "强备选";
  if (value === "watch") return "观望";
  if (value === "rejected") return "淘汰";
  return value || "候选";
}

function trendLabel(trend) {
  if (trend === "down") return "下降";
  if (trend === "up") return "上升";
  if (trend === "stable") return "稳定";
  return trend || "未知";
}

function renderSparkline(points) {
  if (!points.length) {
    return `<div class="sparkline empty">暂无价格曲线</div>`;
  }
  const values = points.map((point) => Number(point.price?.amount || 0));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(1, max - min);
  const chart = {
    top: 14,
    bottom: 58,
    left: 8,
    right: 94,
  };
  const coords = values.map((value, index) => {
    const x = points.length === 1
      ? 50
      : chart.left + (index / (points.length - 1)) * (chart.right - chart.left);
    const y = chart.bottom - ((value - min) / span) * (chart.bottom - chart.top);
    return { x, y, value, point: points[index], index };
  });
  const line = coords.map((item) => `${item.x.toFixed(1)},${item.y.toFixed(1)}`).join(" ");
  const area = `${chart.left},${chart.bottom} ${line} ${chart.right},${chart.bottom}`;
  const minPoint = coords.reduce((winner, item) => item.value < winner.value ? item : winner, coords[0]);
  const maxPoint = coords.reduce((winner, item) => item.value > winner.value ? item : winner, coords[0]);
  const currentPoint = coords[coords.length - 1];
  const gradientId = `sparkArea${++sparklineIdSeed}`;
  const labelX = (point) => Math.max(14, Math.min(82, point.x));
  const dateLabel = (point) => String(point.point?.recordedAt || "").slice(5, 10) || `#${point.index + 1}`;
  return `
    <div class="sparkline-wrap">
      <svg class="sparkline" viewBox="0 0 100 72" preserveAspectRatio="none" role="img" aria-label="价格走势图">
        <defs>
          <linearGradient id="${gradientId}" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stop-color="currentColor" stop-opacity="0.22" />
            <stop offset="100%" stop-color="currentColor" stop-opacity="0" />
          </linearGradient>
        </defs>
        <polygon points="${area}" fill="url(#${gradientId})" />
        <polyline points="${line}" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
        <circle cx="${minPoint.x.toFixed(1)}" cy="${minPoint.y.toFixed(1)}" r="3.3" class="spark-dot min" />
        <circle cx="${currentPoint.x.toFixed(1)}" cy="${currentPoint.y.toFixed(1)}" r="3.3" class="spark-dot current" />
        <text x="${labelX(maxPoint).toFixed(1)}" y="10" class="spark-label">高 ¥${formatMoney(maxPoint.value)}</text>
        <text x="${labelX(minPoint).toFixed(1)}" y="68" class="spark-label">低 ¥${formatMoney(minPoint.value)}</text>
        ${coords.map((item) => `
          <circle
            cx="${item.x.toFixed(1)}"
            cy="${item.y.toFixed(1)}"
            r="8"
            class="spark-hit"
            data-price="¥${formatMoney(item.value)}"
            data-date="${escapeAttr(dateLabel(item))}"
          ></circle>
        `).join("")}
      </svg>
      <div class="sparkline-tooltip" hidden></div>
    </div>
  `;
}

function attachSparklineTooltip(wrapper) {
  if (!wrapper) {
    return;
  }
  const tooltip = wrapper.querySelector(".sparkline-tooltip");
  wrapper.addEventListener("mousemove", (event) => {
    const hit = event.target.closest?.(".spark-hit");
    if (!hit || !tooltip) {
      return;
    }
    tooltip.hidden = false;
    tooltip.textContent = `${hit.dataset.date} · ${hit.dataset.price}`;
    const rect = wrapper.getBoundingClientRect();
    tooltip.style.left = `${event.clientX - rect.left}px`;
    tooltip.style.top = `${event.clientY - rect.top}px`;
  });
  wrapper.addEventListener("mouseleave", () => {
    if (tooltip) {
      tooltip.hidden = true;
    }
  });
}

function renderEcommerceDiagnostics(data) {
  setSectionVisible(els.statsBand, true);
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
  return `<span class="tag source-demo">${escapeHtml(sourceTypeLabel(item.sourceType))}</span>`;
}

function setSectionVisible(element, visible) {
  if (!element) {
    return;
  }
  element.hidden = !visible;
}

function assetMeta(item) {
  if (item.targetPrice) {
    return `${item.enabled ? "启用" : "停用"} · 目标 ¥${escapeHtml(item.targetPrice.amount)} · 当前 ¥${escapeHtml(item.currentPrice?.amount || "-")}`;
  }
  if (item.price) {
    return `${escapeHtml(item.platform || "-")} · ¥${escapeHtml(item.price.amount)}`;
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

function formatBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function formatMoney(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "0.00";
  return number.toFixed(2);
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16);
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

els.registerBtn.addEventListener("click", () => guard(register));
els.loginBtn.addEventListener("click", () => guard(login));
els.loadMeBtn.addEventListener("click", () => guard(loadMe));
els.loadFavoritesBtn.addEventListener("click", () => guard(loadFavorites));
els.loadAlertsBtn.addEventListener("click", () => guard(loadPriceAlerts));
els.loadHistoryBtn.addEventListener("click", () => guard(loadSearchHistory));
els.loadImagesBtn.addEventListener("click", () => guard(loadImages));
els.demoImageBtn.addEventListener("click", () => guard(createDemoImage));
els.demoScenario.addEventListener("change", () => {
  els.refineText.value = currentDemoScenario().query;
});
els.startCameraBtn.addEventListener("click", () => guard(startCamera));
els.capturePhotoBtn.addEventListener("click", () => guard(capturePhoto));
els.stopCameraBtn.addEventListener("click", stopCamera);
els.analyzeBtn.addEventListener("click", () => guard(analyze));
els.demoFlowBtn.addEventListener("click", () => guard(runDemoFlow));
els.refineBtn.addEventListener("click", () => guard(() => refine()));
els.compareBtn.addEventListener("click", () => guard(compare));
els.recommendBtn.addEventListener("click", () => guard(recommend));
els.ecommerceCheckBtn.addEventListener("click", () => guard(checkEcommerceApi));
els.sidePanelToggle?.addEventListener("click", () => {
  const open = !els.sidePanel?.classList.contains("open");
  els.sidePanel?.classList.toggle("open", open);
  els.appShell?.classList.toggle("drawer-open", open);
  els.sidePanelToggle.setAttribute("aria-expanded", String(open));
  els.sidePanelToggle.textContent = open ? "关闭" : "操作";
});
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

function registerServiceWorker() {
  if (!("serviceWorker" in navigator) || !window.isSecureContext) {
    return;
  }
  const register = () => {
    navigator.serviceWorker.register("./service-worker.js").catch(() => {});
  };
  if (document.readyState === "complete") {
    register();
  } else {
    window.addEventListener("load", register, { once: true });
  }
}

resetDemoTimeline();
guard(loadEcommerceStatus);
registerServiceWorker();
