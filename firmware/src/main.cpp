// Sparrow V1 firmware for M5Stack boards (StickS3, CoreS3): work commute only.
//
// The device polls /api/v1/device every 20 s, counts down locally every second, and powers
// itself off after 10 minutes without input. Press the power button to wake it.
//   StickS3: button A or B = refresh now.
//   CoreS3:  tap the arrival rows = switch countdown / clock times; tap anywhere else = refresh.
//
// All transit decisions come from the backend; all screen decisions live in core/ (unit-tested
// natively); layouts live in ui/. This file is only hardware: Wi-Fi, HTTPS, input, power.
#include <HTTPClient.h>
#include <M5Unified.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <WiFiMulti.h>
#include <time.h>

#include "core/sparrow_core.h"
#include "root_ca.h"
#include "secrets.h"
#include "ui/ui.h"

using namespace sparrow;

namespace {

constexpr uint32_t kPollMs = 20000;           // backend caches SEPTA for 20 s
constexpr uint32_t kAwakeMs = 10 * 60 * 1000;  // power off after 10 min idle
constexpr uint32_t kHttpTimeoutMs = 6000;
constexpr bool kBeep = true;                   // beep once on LEAVE NOW / TIGHT

WiFiMulti wifi;
M5Canvas canvas(&M5.Display);

Model model;
bool haveModel = false;
uint32_t fetchedAtMs = 0, lastOkMs = 0, lastPollMs = 0, lastActivityMs = 0;
bool lastPollFailed = false;
char lastError[40] = "";
Hero lastHero = Hero::NoBus;
bool clockView = false;

void setError(const char* e) {
  strncpy(lastError, e, sizeof lastError - 1);
  lastPollFailed = true;
}

void poll() {
  lastPollMs = millis();
  if (wifi.run(5000) != WL_CONNECTED) return setError("Wi-Fi not connected");

  const bool https = strncmp(SPARROW_API_URL, "https://", 8) == 0;
  WiFiClientSecure secure;
  WiFiClient plain;
  if (https) secure.setCACert(kRootCAs);
  HTTPClient http;
  http.setTimeout(kHttpTimeoutMs);
  http.setConnectTimeout(kHttpTimeoutMs);
  if (!http.begin(https ? static_cast<WiFiClient&>(secure) : plain, SPARROW_API_URL)) {
    return setError("bad URL");
  }
  http.addHeader("X-Sparrow-Token", SPARROW_TOKEN);
  const int code = http.GET();
  if (code != 200) {
    char e[24];
    snprintf(e, sizeof e, code < 0 ? "network %d" : "HTTP %d", code);
    http.end();
    return setError(e);
  }
  String body = http.getString();
  http.end();
  Model m;
  if (!parse(body.c_str(), body.length(), m)) return setError("bad data");
  model = m;
  haveModel = true;
  fetchedAtMs = lastOkMs = millis();
  lastPollFailed = false;
  lastError[0] = '\0';
}

void render() {
  const uint32_t nowMs = millis();
  ScreenState s;
  s.model = &model;
  s.haveModel = haveModel;
  s.now = haveModel ? deviceNow(model, fetchedAtMs, nowMs) : 0;
  s.noConn = noConnection(lastPollFailed, lastOkMs, nowMs);
  s.lastPollFailed = lastPollFailed;
  s.lastError = lastError;
  s.batteryPct = M5.Power.getBatteryLevel();
  s.clockView = clockView;

  if (haveModel) {
    const Hero h = hero(model, s.now).hero;
    if (kBeep && h != lastHero && (h == Hero::Now || h == Hero::Tight)) M5.Speaker.tone(2600, 120);
    lastHero = h;
  }
  drawScreen(canvas, s);
  canvas.pushSprite(0, 0);
}

void handleInput(uint32_t nowMs) {
  bool refresh = M5.BtnA.wasPressed() || M5.BtnB.wasPressed();
  if (M5.Touch.getCount() > 0) {
    const auto& t = M5.Touch.getDetail();
    if (t.wasClicked()) {
      if (t.y >= screenHeight() - 56) clockView = !clockView;  // tapped the arrival rows
      else refresh = true;
      lastActivityMs = nowMs;
    }
  }
  if (refresh) {
    lastActivityMs = nowMs;
    poll();
  }
}

}  // namespace

void setup() {
  auto cfg = M5.config();
  M5.begin(cfg);
  M5.Display.setRotation(1);  // landscape on both boards
  M5.Display.setBrightness(160);
  M5.Speaker.setVolume(96);   // keep it modest on battery
  canvas.setColorDepth(16);
  canvas.createSprite(screenWidth(), screenHeight());

  // Eastern time for on-screen clock times (EST/EDT switch handled by the C library).
  setenv("TZ", "EST5EDT,M3.2.0,M11.1.0", 1);
  tzset();

  WiFi.mode(WIFI_STA);
  wifi.addAP(SPARROW_WIFI_1_SSID, SPARROW_WIFI_1_PASS);
  if (strlen(SPARROW_WIFI_2_SSID) > 0) wifi.addAP(SPARROW_WIFI_2_SSID, SPARROW_WIFI_2_PASS);

  lastActivityMs = millis();
  render();  // "CONNECTING..." immediately
  poll();
}

void loop() {
  M5.update();
  const uint32_t nowMs = millis();
  handleInput(nowMs);
  if (nowMs - lastPollMs >= kPollMs) poll();
  if (nowMs - lastActivityMs >= kAwakeMs) {
    M5.Display.fillScreen(kBlack);
    M5.Power.powerOff();  // press the power button to wake
  }
  static uint32_t lastDraw = 0;
  if (nowMs - lastDraw >= 250) {
    lastDraw = nowMs;
    render();
  }
  delay(10);
}
