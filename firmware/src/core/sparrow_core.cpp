#include "sparrow_core.h"

#include <ArduinoJson.h>
#include <string.h>

namespace sparrow {

namespace {

void copyStr(char* dst, size_t cap, const char* src) {
  if (!src) src = "";
  strncpy(dst, src, cap - 1);
  dst[cap - 1] = '\0';
}

Kind toKind(const char* k) {
  if (!k || !*k) return Kind::Scheduled;
  switch (k[0]) {
    case 'l': return Kind::Live;
    case 'e': return Kind::Estimated;
    case 'o': return Kind::Stale;
    default: return Kind::Scheduled;
  }
}

}  // namespace

bool parse(const char* json, size_t len, Model& out) {
  JsonDocument doc;
  if (deserializeJson(doc, json, len)) return false;
  if (doc["v"].as<int>() != 1 || !doc["now"].is<int64_t>()) return false;

  Model m;
  m.serverNow = doc["now"].as<int64_t>();
  const char* st = doc["st"] | "offline";
  m.status = strcmp(st, "live") == 0    ? DataStatus::Live
             : strcmp(st, "stale") == 0 ? DataStatus::Stale
                                        : DataStatus::Offline;
  m.ageS = doc["age"] | -1;
  m.readyS = doc["rdy"] | 180;
  m.simulated = doc["sim"] | false;
  copyStr(m.msg, sizeof m.msg, doc["msg"] | "");

  JsonObjectConst rec = doc["rec"];
  if (!rec.isNull()) {
    m.rec.present = true;
    copyStr(m.rec.route, sizeof m.rec.route, rec["r"] | "");
    copyStr(m.rec.action, sizeof m.rec.action, rec["a"] | "");
    m.rec.leaveAt = rec["l"] | int64_t(0);
    m.rec.busAt = rec["b"] | int64_t(0);
    m.rec.walkS = rec["w"] | 0;
    m.rec.kind = toKind(rec["k"] | "s");
    m.rec.approx = rec["x"] | true;  // assume not-live unless told otherwise
    copyStr(m.rec.why, sizeof m.rec.why, rec["why"] | "");
    JsonObjectConst alt = rec["alt"];
    if (!alt.isNull()) {
      m.rec.hasAlt = true;
      copyStr(m.rec.altRoute, sizeof m.rec.altRoute, alt["r"] | "");
      m.rec.altLeaveAt = alt["l"] | int64_t(0);
      m.rec.altBusAt = alt["b"] | int64_t(0);
    }
    if (m.rec.busAt == 0 || m.rec.leaveAt == 0) return false;
  }

  for (JsonObjectConst row : doc["rows"].as<JsonArrayConst>()) {
    if (m.nRows >= kMaxRows) break;
    Row& r = m.rows[m.nRows++];
    copyStr(r.route, sizeof r.route, row["r"] | "");
    r.walkS = row["w"] | 0;
    for (JsonArrayConst a : row["t"].as<JsonArrayConst>()) {
      if (r.n >= kMaxArrivals) break;
      r.t[r.n].at = a[0] | int64_t(0);
      r.t[r.n].kind = toKind(a[1] | "s");
      r.n++;
    }
  }
  out = m;
  return true;
}

int floorMinutes(int64_t seconds) {
  if (seconds <= 0) return 0;
  return static_cast<int>(seconds / 60);
}

HeroView hero(const Model& m, int64_t now) {
  HeroView v;
  if (!m.rec.present) return v;  // NoBus
  const int64_t left = m.rec.leaveAt - now;
  const int64_t untilBus = m.rec.busAt - now;
  const bool tight = strcmp(m.rec.action, "tight") == 0;
  if (tight || left < 0) {
    // The server said TIGHT, or the leave time passed since the last poll.
    if (untilBus >= m.rec.walkS) {
      v.hero = Hero::Tight;
      v.spareS = static_cast<int>(untilBus - m.rec.walkS);
    } else {
      v.hero = Hero::Checking;
    }
    return v;
  }
  if (left < kLeaveNowS) {
    v.hero = Hero::Now;
  } else if (left < m.readyS) {
    v.hero = Hero::Ready;
    v.minutes = floorMinutes(left);
  } else {
    v.hero = Hero::Leave;
    v.minutes = floorMinutes(left);
  }
  return v;
}

Cell cell(const Model& m, const Row& row, const Arrival& a, int64_t now) {
  const int64_t buffer =
      m.rec.present ? (m.rec.busAt - m.rec.leaveAt - m.rec.walkS) : int64_t(120);
  const int64_t toBus = a.at - now;
  if (toBus < row.walkS) return Cell::Missed;
  if (toBus < row.walkS + buffer) return Cell::Tight;
  return Cell::Ok;
}

}  // namespace sparrow
