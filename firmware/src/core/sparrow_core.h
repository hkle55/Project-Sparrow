// Sparrow firmware core: board-independent. Parses /api/v1/device and decides what the
// screen should say. No Arduino, display, or Wi-Fi code here, so it unit-tests natively
// (`pio test -e native`). The rules mirror frontend/device.html and the backend engine.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace sparrow {

constexpr int kMaxRows = 2;
constexpr int kMaxArrivals = 3;
constexpr int kLeaveNowS = 60;      // under a minute of slack: LEAVE NOW
constexpr int kNoConnAfterS = 45;   // no successful poll for this long: NO WIFI

enum class Kind : char { Live = 'l', Estimated = 'e', Scheduled = 's', Stale = 'o' };

struct Arrival {
  int64_t at = 0;  // epoch seconds
  Kind kind = Kind::Scheduled;
};

struct Row {
  char route[6] = {0};
  int walkS = 0;
  Arrival t[kMaxArrivals];
  int n = 0;
};

struct Rec {
  bool present = false;
  char route[6] = {0};
  char action[12] = {0};  // leave_in | get_ready | leave_now | tight
  int64_t leaveAt = 0;
  int64_t busAt = 0;
  int walkS = 0;
  Kind kind = Kind::Live;
  bool approx = false;
  char why[49] = {0};
  bool hasAlt = false;
  char altRoute[6] = {0};
  int64_t altLeaveAt = 0;
  int64_t altBusAt = 0;
};

enum class DataStatus { Live, Stale, Offline };

struct Model {
  int64_t serverNow = 0;
  DataStatus status = DataStatus::Offline;
  int ageS = -1;  // -1 = unknown
  int readyS = 180;
  bool simulated = false;
  Rec rec;
  Row rows[kMaxRows];
  int nRows = 0;
  char msg[64] = {0};
};

// Parse the JSON payload. Returns false (and leaves `out` untouched) on bad input.
bool parse(const char* json, size_t len, Model& out);

// --- decisions -----------------------------------------------------------------------

enum class Hero {
  Leave,     // "LEAVE IN 5 min"
  Ready,     // "GET READY 2 min"
  Now,       // "LEAVE NOW"
  Tight,     // "TIGHT · GO": reachable only by cutting into the buffer
  Checking,  // the recommended bus can no longer be reached; wait for the next poll
  NoBus,     // nothing catchable / no data
};

struct HeroView {
  Hero hero = Hero::NoBus;
  int minutes = 0;   // floored minutes for Leave/Ready
  int spareS = 0;    // Tight: seconds you'd wait at the stop if you left now
};

HeroView hero(const Model& m, int64_t now);

enum class Cell { Ok, Tight, Missed };

// Catch state of one listed arrival right now. The buffer is implied by the
// recommendation (busAt - leaveAt - walk); default 120 s if there's no recommendation.
Cell cell(const Model& m, const Row& row, const Arrival& a, int64_t now);

// Whole minutes, rounded DOWN, never negative: a countdown must not overstate time left.
int floorMinutes(int64_t seconds);

// The device has no RTC sync: "now" = server time + seconds since that response arrived.
inline int64_t deviceNow(const Model& m, uint32_t fetchedAtMs, uint32_t nowMs) {
  return m.serverNow + static_cast<int64_t>((nowMs - fetchedAtMs) / 1000u);
}

inline bool noConnection(bool lastPollFailed, uint32_t lastOkMs, uint32_t nowMs) {
  return lastPollFailed && (lastOkMs == 0 || (nowMs - lastOkMs) / 1000u > kNoConnAfterS);
}

}  // namespace sparrow
