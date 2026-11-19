// 320x240 layout (M5Stack CoreS3; same resolution as the Pimoroni Tufty 2350).
// Matches the mockups: route + clock + status chip, the pixel bus, a big countdown, two
// arrival rows. Pixel look comes from the built-in bitmap fonts (8x16 and 24x48).
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "ui.h"

namespace sparrow {

namespace {

constexpr int W = 320, H = 240;
const lgfx::IFont* const F16 = &fonts::AsciiFont8x16;   // 8x16 px per char at size 1
const lgfx::IFont* const F48 = &fonts::AsciiFont24x48;  // 24x48 px per char at size 1

int text(lgfx::LGFX_Sprite& c, const char* s, int x, int y, const lgfx::IFont* font, float size,
         uint16_t color, lgfx::textdatum_t datum = lgfx::top_left) {
  c.setFont(font);
  c.setTextSize(size);
  c.setTextColor(color);
  c.setTextDatum(datum);
  c.drawString(s, x, y);
  return c.textWidth(s);
}

// "7:41 PM" in Eastern time. setup() sets TZ, so localtime handles EST/EDT.
void etTime(int64_t epoch, char* out, size_t n, bool compact = false) {
  time_t t = static_cast<time_t>(epoch);
  struct tm tm;
  localtime_r(&t, &tm);
  int h = tm.tm_hour % 12;
  if (h == 0) h = 12;
  if (compact) snprintf(out, n, "%d:%02d%c", h, tm.tm_min, tm.tm_hour < 12 ? 'a' : 'p');
  else snprintf(out, n, "%d:%02d %s", h, tm.tm_min, tm.tm_hour < 12 ? "AM" : "PM");
}

void dashedRect(lgfx::LGFX_Sprite& c, int x, int y, int w, int h, uint16_t color) {
  for (int i = 0; i < w; i += 13) {
    c.fillRect(x + i, y, 8, 3, color);
    c.fillRect(x + i, y + h - 3, 8, 3, color);
  }
  for (int j = 0; j < h; j += 13) {
    c.fillRect(x, y + j, 3, 8, color);
    c.fillRect(x + w - 3, y + j, 3, 8, color);
  }
}

// The web app's 120x26 pixel bus scene, drawn at 2x. The bus's distance from the stop
// tracks the recommended bus (15+ min away = far left); a dimmed bus means "not live".
void drawScene(lgfx::LGFX_Sprite& c, const Rec& r, int64_t now) {
  const int s = 2, ox = 40, oy = 28;
  auto px = [&](int x, int y, int w, int h, uint16_t col) { c.fillRect(ox + x * s, oy + y * s, w * s, h * s, col); };
  px(0, 21, 120, 1, 0x39E7);
  for (int x = 2; x < 120; x += 8) px(x, 24, 4, 1, 0x2945);
  px(110, 7, 1, 14, kGrey);
  px(106, 3, 9, 6, 0x2C1D);
  px(108, 5, 5, 2, kWhite);
  if (!r.present) return;
  int64_t until = r.busAt - now;
  if (until < 0) until = 0;
  const float p = until >= 900 ? 0.0f : 1.0f - until / 900.0f;
  const int bx = static_cast<int>(-4 + p * 84), by = 10;
  const bool dim = r.approx;
  const uint16_t body = dim ? 0x6B4D : 0xE73C, glass = dim ? 0x2124 : 0x3209;
  const uint16_t stripe = dim ? 0x6000 : 0xD000, wind = dim ? 0x4228 : 0x7D9B;
  auto b = [&](int x, int y, int w, int h, uint16_t col) { px(bx + x, by + y, w, h, col); };
  b(1, 0, 22, 1, body); b(0, 1, 24, 9, body);
  for (int i = 0; i < 4; i++) b(2 + i * 4, 2, 3, 3, glass);
  b(18, 2, 2, 7, glass); b(21, 2, 3, 4, wind);
  b(0, 6, 18, 1, stripe); b(20, 6, 4, 1, stripe);
  b(23, 8, 1, 1, kYellow);
  for (int wx : {3, 16}) { b(wx, 9, 5, 3, 0x1082); b(wx + 1, 10, 1, 1, kGrey); }
}

void drawTop(lgfx::LGFX_Sprite& c, const ScreenState& s) {
  const Model& m = *s.model;
  char buf[24];
  if (m.rec.present) snprintf(buf, sizeof buf, "BUS %s", m.rec.route);
  else snprintf(buf, sizeof buf, "SPARROW");
  text(c, buf, 6, 0, F16, 2, kWhite);

  const char* label;
  uint16_t color;
  if (s.noConn) { label = "NO WIFI"; color = kRed; }
  else if (m.simulated) { label = "SIM"; color = kYellow; }
  else if (m.status == DataStatus::Live) { label = "LIVE"; color = kGreen; }
  else if (m.status == DataStatus::Stale) { label = "STALE"; color = kYellow; }
  else { label = "SCHED"; color = kYellow; }
  c.setFont(F16);
  c.setTextSize(1);
  const int cw = c.textWidth(label) + 12;
  c.drawRect(W - cw - 4, 6, cw, 22, color);
  c.drawRect(W - cw - 3, 7, cw - 2, 20, color);
  text(c, label, W - cw / 2 - 4, 9, F16, 1, color, lgfx::top_center);

  etTime(s.now, buf, sizeof buf);
  int x = W - cw - 12;
  x -= text(c, buf, x, 9, F16, 1, kGrey, lgfx::top_right) + 10;
  if (s.batteryPct >= 0) {
    snprintf(buf, sizeof buf, "%d%%", s.batteryPct);
    text(c, buf, x, 9, F16, 1, s.batteryPct <= 15 ? kRed : kGrey, lgfx::top_right);
  }
}

void drawHero(lgfx::LGFX_Sprite& c, const ScreenState& s) {
  const Model& m = *s.model;
  const Rec& r = m.rec;
  char buf[48];
  if (!r.present) {
    text(c, "NO BUS", W / 2, 96, F48, 1, kGrey, lgfx::top_center);
    text(c, m.msg, W / 2, 152, F16, 1, kWhite, lgfx::top_center);
    return;
  }
  const HeroView v = hero(m, s.now);
  switch (v.hero) {
    case Hero::Leave:
    case Hero::Ready: {
      const bool ready = v.hero == Hero::Ready;
      int numW;
      if (s.clockView) {
        text(c, ready ? "GET READY - LEAVE AT" : "LEAVE AT", 12, 88, F16, 1, ready ? kYellow : kGrey);
        etTime(r.leaveAt, buf, sizeof buf);
        numW = text(c, buf, 10, 104, F48, 1.0f, kWhite);
      } else {
        text(c, ready ? "GET READY" : "LEAVE IN", 12, 88, F16, 1, ready ? kYellow : kGrey);
        snprintf(buf, sizeof buf, "%d", v.minutes);
        numW = text(c, buf, 10, 104, F48, 1.25f, kWhite);
        text(c, "min", 18 + numW, 132, F16, 2, kWhite);
        etTime(r.leaveAt, buf, sizeof buf);
        char by[24];
        snprintf(by, sizeof by, "by %s", buf);
        text(c, by, W - 10, 148, F16, 1, kGrey, lgfx::top_right);
      }
      if (ready) {
        c.drawRect(4, 84, numW + 120, 82, kYellow);
        c.drawRect(5, 85, numW + 118, 80, kYellow);
      }
      break;
    }
    case Hero::Now:
      c.fillRect(6, 86, W - 12, 78, kWhite);
      text(c, "LEAVE NOW", W / 2, 101, F48, 1, kBlack, lgfx::top_center);
      break;
    case Hero::Tight:
      dashedRect(c, 6, 86, W - 12, 78, kRed);
      text(c, "TIGHT - GO", W / 2, 94, F48, 1, kWhite, lgfx::top_center);
      if (v.spareS < 60) snprintf(buf, sizeof buf, "<1 min to spare");
      else snprintf(buf, sizeof buf, "%d min to spare", floorMinutes(v.spareS));
      text(c, buf, W / 2, 144, F16, 1, kRed, lgfx::top_center);
      break;
    case Hero::Checking:
      text(c, "CHECKING...", W / 2, 112, F16, 2, kGrey, lgfx::top_center);
      break;
    case Hero::NoBus:
      break;
  }
  if ((r.approx || s.noConn) && v.hero != Hero::Checking && v.hero != Hero::Now &&
      v.hero != Hero::Tight) {
    text(c, "~ not live", W - 10, 88, F16, 1, kYellow, lgfx::top_right);
  }

  // Secondary line: offline warning > safer alternative > reason.
  if (s.noConn) {
    snprintf(buf, sizeof buf, "Offline: countdown may be off");
  } else if (r.hasAlt) {
    const int64_t al = r.altLeaveAt - s.now;
    if (al >= 0) snprintf(buf, sizeof buf, "Safer: %s - leave in %dm", r.altRoute, floorMinutes(al));
    else snprintf(buf, sizeof buf, "Safer: bus %s", r.altRoute);
  } else {
    snprintf(buf, sizeof buf, "%s", r.why);
  }
  text(c, buf, W / 2, 168, F16, 1, s.noConn ? kRed : kGrey, lgfx::top_center);
}

void drawRows(lgfx::LGFX_Sprite& c, const ScreenState& s) {
  const Model& m = *s.model;
  char buf[12];
  for (int i = 0; i < m.nRows; i++) {
    const Row& row = m.rows[i];
    const int y = 190 + i * 25;
    text(c, row.route, 8, y, F16, 1.5f, kWhite);
    for (int j = 0; j < kMaxArrivals; j++) {
      const int x = 136 + j * 72;
      if (j >= row.n) {
        text(c, "-", x, y, F16, 1.5f, kGrey, lgfx::top_right);
        continue;
      }
      const Arrival& a = row.t[j];
      const bool live = a.kind == Kind::Live;
      const int64_t to = a.at - s.now;
      if (s.clockView) {
        char t[10];
        etTime(a.at, t, sizeof t, true);
        snprintf(buf, sizeof buf, "%s%s", live ? "" : "~", t);
      } else if (to <= 30) {
        snprintf(buf, sizeof buf, "%snow", live ? "" : "~");
      } else {
        snprintf(buf, sizeof buf, "%s%d", live ? "" : "~", floorMinutes(to));
      }
      const Cell cs = cell(m, row, a, s.now);
      const uint16_t color = cs == Cell::Missed ? kGrey : live ? kWhite : kYellow;
      const float size = s.clockView ? 1.0f : 1.5f;
      const int w = text(c, buf, x, y + (s.clockView ? 4 : 0), F16, size, color, lgfx::top_right);
      if (cs == Cell::Missed) c.fillRect(x - w, y + 11, w, 2, kGrey);
      if (cs == Cell::Tight) text(c, "!", x + 2, y, F16, 1.5f, kRed);
    }
    if (!s.clockView) text(c, "min", W - 4, y + 6, F16, 1, kGrey, lgfx::top_right);
  }
}

}  // namespace

int screenWidth() { return W; }
int screenHeight() { return H; }

void drawScreen(lgfx::LGFX_Sprite& c, const ScreenState& s) {
  c.fillScreen(kBlack);
  if (!s.haveModel) {
    text(c, s.lastPollFailed ? "NO CONNECTION" : "CONNECTING...", W / 2, 96, F16, 2,
         s.lastPollFailed ? kRed : kWhite, lgfx::top_center);
    if (s.lastPollFailed) text(c, s.lastError, W / 2, 140, F16, 1, kGrey, lgfx::top_center);
    return;
  }
  drawTop(c, s);
  drawScene(c, s.model->rec, s.now);
  drawHero(c, s);
  drawRows(c, s);
}

}  // namespace sparrow
