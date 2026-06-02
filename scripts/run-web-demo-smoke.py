from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

try:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.support.ui import Select, WebDriverWait
except ImportError as exc:  # pragma: no cover - used as a local diagnostic script
    print("Missing dependency: selenium. Install it with `python -m pip install selenium`.", file=sys.stderr)
    raise SystemExit(2) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a real-browser smoke test for the Web/PWA one-click shopping demo."
    )
    parser.add_argument("--frontend-url", default="http://localhost:5173", help="Frontend origin.")
    parser.add_argument("--api-base", default="http://localhost:8080/api", help="Backend API base shown in the UI.")
    parser.add_argument(
        "--health-url",
        default="http://localhost:8080/api/health",
        help="Backend health URL checked before opening the browser.",
    )
    parser.add_argument(
        "--scenario",
        default="headphones",
        choices=("hair-dryer", "headphones", "phone", "keyboard", "cup", "running-shoes", "skincare"),
        help="Demo scenario selected before clicking the one-click flow.",
    )
    parser.add_argument("--timeout", type=int, default=60, help="Seconds to wait for the demo flow.")
    parser.add_argument("--width", type=int, default=1440, help="Browser viewport width.")
    parser.add_argument("--height", type=int, default=1100, help="Browser viewport height.")
    parser.add_argument(
        "--screenshot",
        default="backend/target/web-demo-smoke.png",
        help="Screenshot path written after the flow finishes. Use an empty string to disable.",
    )
    parser.add_argument(
        "--report",
        default="backend/target/web-demo-smoke-report.json",
        help="JSON report path. Use an empty string to disable.",
    )
    parser.add_argument("--headed", action="store_true", help="Run Edge with a visible window.")
    return parser.parse_args()


def get_json(url: str, timeout: int = 8) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def check_url(url: str, timeout: int = 8) -> None:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if response.status >= 400:
            raise RuntimeError(f"{url} returned HTTP {response.status}")


def ensure_servers(frontend_url: str, health_url: str) -> None:
    try:
        health = get_json(health_url)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Backend health check failed: {health_url}") from exc
    if health.get("code") != 0 or health.get("data", {}).get("status") != "ok":
        raise RuntimeError(f"Backend health check returned unexpected payload: {health}")
    try:
        check_url(frontend_url)
    except (OSError, urllib.error.URLError) as exc:
        raise RuntimeError(f"Frontend is not reachable: {frontend_url}") from exc


def create_driver(args: argparse.Namespace) -> webdriver.Edge:
    options = EdgeOptions()
    if not args.headed:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--force-device-scale-factor=1")
    options.add_argument(f"--window-size={args.width},{args.height}")
    try:
        driver = webdriver.Edge(options=options)
    except WebDriverException as exc:
        raise RuntimeError("Unable to start Microsoft Edge WebDriver. Check Edge/Selenium installation.") from exc
    driver.set_window_size(args.width, args.height)
    return driver


def set_input_value(driver: webdriver.Edge, selector: str, value: str) -> None:
    driver.execute_script(
        """
        const input = document.querySelector(arguments[0]);
        input.value = arguments[1];
        input.dispatchEvent(new Event("change", { bubbles: true }));
        """,
        selector,
        value,
    )


def collect_metrics(driver: webdriver.Edge) -> dict:
    return driver.execute_script(
        """
        const q = (selector) => document.querySelector(selector);
        const qa = (selector) => Array.from(document.querySelectorAll(selector));
        const text = (selector) => (q(selector)?.textContent || "").trim();
        const count = (selector) => qa(selector).length;
        const numberText = text("#resultCount").replace(/[^0-9]/g, "");
        return {
          demoStatus: text("#demoStatus"),
          doneSteps: count(".demo-step.done"),
          activeSteps: count(".demo-step.active"),
          errorSteps: count(".demo-step.error"),
          errorStepText: qa(".demo-step.error").map((el) => el.textContent.trim()).join(" | "),
          resultCount: Number.parseInt(numberText || "0", 10),
          productCards: count("#productGrid .product-card"),
          suggestionCards: count("#suggestionCards .suggestion-card"),
          platformStats: count("#platformStats .stat-card"),
          comparisonTables: count("#comparisonBox table"),
          insightReady: !q("#insightBox")?.classList.contains("empty"),
          recommendationReady: !q("#recommendationBox")?.classList.contains("empty"),
          decisionSignals: count("#recommendationBox .signal-row"),
          marketRationale: count("#recommendationBox .market-rationale"),
          decisionTraceSteps: count("#recommendationBox .trace-step"),
          candidateCells: count("#recommendationBox .candidate-cell"),
          evidenceChips: count("#recommendationBox .evidence-chip"),
          decisionBriefReady: q("#decisionBrief")?.classList.contains("complete") || false,
          recommendationId: q("#decisionBrief")?.dataset.recommendationId || "",
          briefText: text("#decisionBrief"),
          assetsText: text("#assetsBox"),
          toastText: text("#toast"),
          pageScrollWidth: document.documentElement.scrollWidth,
          viewportWidth: window.innerWidth
        };
        """
    )


def collect_report_status(driver: webdriver.Edge) -> dict:
    driver.set_script_timeout(12)
    return driver.execute_async_script(
        """
        const done = arguments[0];
        const recommendationId = document.querySelector("#decisionBrief")?.dataset.recommendationId;
        const token = localStorage.getItem("accessToken");
        const apiBase = document.querySelector("#apiBase").value.replace(/\\/$/, "");
        if (!recommendationId || !token) {
          done({ ok: false, status: 0, markdown: "", reason: "missing recommendationId or token" });
          return;
        }
        fetch(`${apiBase}/agent/recommendations/${recommendationId}/report`, {
          headers: { Authorization: `Bearer ${token}` }
        })
          .then((response) => response.json().then((payload) => ({ response, payload })))
          .then(({ response, payload }) => {
            done({
              ok: response.ok && payload.code === 0,
              status: response.status,
              markdown: payload.data?.markdown || "",
              title: payload.data?.title || "",
              summary: payload.data?.summary || ""
            });
          })
          .catch((error) => done({ ok: false, status: 0, markdown: "", reason: String(error) }));
        """
    )


def collect_pwa_status(driver: webdriver.Edge) -> dict:
    driver.set_script_timeout(12)
    return driver.execute_async_script(
        """
        const done = arguments[0];
        if (!("serviceWorker" in navigator)) {
          done({ supported: false, active: false, controller: false, scriptURL: "", cacheKeys: [] });
          return;
        }
        Promise.all([
          navigator.serviceWorker.ready,
          "caches" in window ? caches.keys() : Promise.resolve([])
        ]).then(async ([registration, cacheKeys]) => {
          const appCacheKey = cacheKeys.find((key) => key.startsWith("ec26b-app-shell-"));
          const cacheUrls = appCacheKey
            ? (await caches.open(appCacheKey)).keys().then((requests) => requests.map((request) => request.url))
            : [];
          done({
            supported: true,
            active: Boolean(registration.active),
            controller: Boolean(navigator.serviceWorker.controller),
            scriptURL: registration.active?.scriptURL || "",
            cacheKeys,
            cacheUrls: await cacheUrls
          });
        }).catch((error) => {
          done({ supported: true, active: false, controller: false, scriptURL: "", cacheKeys: [], cacheUrls: [], error: String(error) });
        });
        """
    )


def assert_metric(condition: bool, message: str, metrics: dict) -> None:
    if not condition:
        raise AssertionError(f"{message}\nMetrics: {json.dumps(metrics, ensure_ascii=False, indent=2)}")


def run_flow(driver: webdriver.Edge, args: argparse.Namespace) -> dict:
    url = f"{args.frontend_url.rstrip('/')}?smoke={int(time.time())}"
    driver.get(url)
    wait = WebDriverWait(driver, args.timeout)
    wait.until(lambda browser: browser.find_element(By.ID, "demoFlowBtn").is_enabled())

    set_input_value(driver, "#apiBase", args.api_base)
    Select(driver.find_element(By.ID, "demoScenario")).select_by_value(args.scenario)
    driver.find_element(By.ID, "demoFlowBtn").click()

    wait.until(
        lambda browser: browser.find_element(By.ID, "demoStatus").text.strip()
        in ("演示完成", "需检查")
    )
    metrics = collect_metrics(driver)
    metrics["report"] = collect_report_status(driver)
    metrics["pwa"] = collect_pwa_status(driver)

    assert_metric(metrics["demoStatus"] == "演示完成", "Demo flow did not finish successfully.", metrics)
    assert_metric(metrics["errorSteps"] == 0, "Demo timeline contains an error step.", metrics)
    assert_metric(metrics["doneSteps"] >= 6, "Demo timeline did not complete all six steps.", metrics)
    assert_metric(metrics["resultCount"] >= 2, "Search did not return enough candidate products.", metrics)
    assert_metric(metrics["productCards"] >= metrics["resultCount"], "Product cards are missing.", metrics)
    assert_metric(metrics["suggestionCards"] >= 1, "Suggestion cards were not rendered.", metrics)
    assert_metric(metrics["platformStats"] >= 1, "Platform statistics were not rendered.", metrics)
    assert_metric(metrics["comparisonTables"] >= 1, "Comparison table was not rendered.", metrics)
    assert_metric(metrics["insightReady"], "Product insight panel is still empty.", metrics)
    assert_metric(metrics["recommendationReady"], "Agent recommendation panel is still empty.", metrics)
    assert_metric(metrics["decisionSignals"] >= 5, "Decision signals are incomplete.", metrics)
    assert_metric(metrics["marketRationale"] >= 1, "Price-trust rationale was not rendered.", metrics)
    assert_metric(metrics["decisionTraceSteps"] >= 6, "Decision trace is incomplete.", metrics)
    assert_metric(metrics["candidateCells"] >= 2, "Candidate win/loss matrix is incomplete.", metrics)
    assert_metric(metrics["evidenceChips"] >= 3, "Evidence chips are incomplete.", metrics)
    assert_metric(metrics["decisionBriefReady"], "Decision brief was not finalized.", metrics)
    assert_metric(metrics["recommendationId"], "Decision brief is missing recommendation id.", metrics)
    assert_metric("决策分" in metrics["briefText"], "Decision brief does not include decision score.", metrics)
    report = metrics["report"]
    assert_metric(report["ok"], "Recommendation evidence report endpoint failed.", metrics)
    for section in ("购物决策证据报告", "五类决策信号", "六步决策轨迹", "候选胜因/败因矩阵", "Evidence"):
        assert_metric(section in report["markdown"], f"Recommendation report is missing {section}.", metrics)
    assert_metric("数据源：演示数据集" in report["markdown"], "Recommendation report exposes a raw data-source label.", metrics)
    assert_metric("为空" not in metrics["assetsText"] and "等待" not in metrics["assetsText"], "Assets were not persisted.", metrics)
    assert_metric(
        metrics["pageScrollWidth"] <= metrics["viewportWidth"] + 2,
        "Page has unexpected horizontal overflow.",
        metrics,
    )
    pwa = metrics["pwa"]
    assert_metric(pwa["supported"], "Browser does not support service workers.", metrics)
    assert_metric(pwa["active"], "Service worker did not become active.", metrics)
    assert_metric("service-worker.js" in pwa["scriptURL"], "Unexpected service worker script.", metrics)
    assert_metric(
        any(key.startswith("ec26b-app-shell-") for key in pwa["cacheKeys"]),
        "PWA app shell cache was not created.",
        metrics,
    )
    cached_urls = " ".join(pwa.get("cacheUrls", []))
    for asset in ("index.html", "app.js", "styles.css", "icon-192.png", "icon-512.png"):
        assert_metric(asset in cached_urls, f"PWA app shell cache is missing {asset}.", metrics)
    return metrics


def write_artifacts(driver: webdriver.Edge, args: argparse.Namespace, metrics: dict) -> None:
    if args.screenshot:
        screenshot = Path(args.screenshot)
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(screenshot))
        metrics["screenshot"] = str(screenshot)
    if args.report:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    ensure_servers(args.frontend_url, args.health_url)
    driver = create_driver(args)
    try:
        metrics = run_flow(driver, args)
        write_artifacts(driver, args, metrics)
    finally:
        driver.quit()
    print(json.dumps({"status": "passed", "scenario": args.scenario, "metrics": metrics}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"web-demo-smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
