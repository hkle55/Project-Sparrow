// Native unit tests for the board-independent firmware core: `pio test -e native`.
#include <string.h>
#include <unity.h>

#include "core/sparrow_core.h"

using namespace sparrow;

// Shape of a real /api/v1/device response captured 2026-11-18 (example times).
static const char* kLive =
    R"({"v":1,"now":1000,"st":"live","age":15,"rdy":180,)"
    R"("rec":{"r":"40","a":"leave_in","l":1300,"b":1660,"w":240,"k":"l","x":false,)"
    R"("why":"Route 40 preferred"},)"
    R"("rows":[{"r":"40","w":240,"t":[[1100,"l"],[1660,"l"],[2500,"s"]]},)"
    R"({"r":"42","w":420,"t":[[1540,"s"],[1900,"l"]]}]})";

static Model parsed(const char* json) {
  Model m;
  TEST_ASSERT_TRUE(parse(json, strlen(json), m));
  return m;
}

void setUp() {}
void tearDown() {}

void test_parse_live_payload() {
  Model m = parsed(kLive);
  TEST_ASSERT_EQUAL_INT64(1000, m.serverNow);
  TEST_ASSERT_TRUE(m.status == DataStatus::Live);
  TEST_ASSERT_EQUAL(15, m.ageS);
  TEST_ASSERT_TRUE(m.rec.present);
  TEST_ASSERT_EQUAL_STRING("40", m.rec.route);
  TEST_ASSERT_FALSE(m.rec.approx);
  TEST_ASSERT_EQUAL(2, m.nRows);
  TEST_ASSERT_EQUAL(3, m.rows[0].n);
  TEST_ASSERT_EQUAL(2, m.rows[1].n);
  TEST_ASSERT_TRUE(m.rows[0].t[2].kind == Kind::Scheduled);
}

void test_parse_rejects_garbage_and_keeps_old_model() {
  Model m = parsed(kLive);
  const char* bad[] = {"", "<html>502</html>", R"({"v":2,"now":1})", R"({"v":1})",
                       R"({"v":1,"now":5,"rec":{"r":"40"}})"};
  for (const char* b : bad) TEST_ASSERT_FALSE(parse(b, strlen(b), m));
  TEST_ASSERT_EQUAL_INT64(1000, m.serverNow);  // untouched
}

void test_parse_missing_approx_defaults_to_not_live() {
  const char* j = R"({"v":1,"now":1,"st":"live","rec":{"r":"40","a":"leave_in","l":500,"b":900,"w":240,"k":"l","why":""},"rows":[]})";
  TEST_ASSERT_TRUE(parsed(j).rec.approx);
}

void test_parse_no_rec_has_message() {
  const char* j = R"({"v":1,"now":1,"st":"live","rows":[],"msg":"No bus catchable"})";
  Model m = parsed(j);
  TEST_ASSERT_FALSE(m.rec.present);
  TEST_ASSERT_EQUAL_STRING("No bus catchable", m.msg);
  TEST_ASSERT_TRUE(hero(m, 1).hero == Hero::NoBus);
}

void test_parse_truncates_extra_rows_and_arrivals() {
  const char* j = R"({"v":1,"now":1,"st":"live","rows":[)"
                  R"({"r":"1","w":1,"t":[[1,"l"],[2,"l"],[3,"l"],[4,"l"]]},)"
                  R"({"r":"2","w":1,"t":[]},{"r":"3","w":1,"t":[]}]})";
  Model m = parsed(j);
  TEST_ASSERT_EQUAL(kMaxRows, m.nRows);
  TEST_ASSERT_EQUAL(kMaxArrivals, m.rows[0].n);
}

void test_hero_countdown_floors() {
  Model m = parsed(kLive);  // leave at 1300
  HeroView v = hero(m, 1000);
  TEST_ASSERT_TRUE(v.hero == Hero::Leave);
  TEST_ASSERT_EQUAL(5, v.minutes);
  TEST_ASSERT_EQUAL(4, hero(m, 1001).minutes);  // 4:59 left shows 4, never 5
}

void test_hero_states_over_time() {
  Model m = parsed(kLive);  // leave 1300, bus 1660, walk 240, ready 180
  TEST_ASSERT_TRUE(hero(m, 1120).hero == Hero::Leave);  // 180 s left
  TEST_ASSERT_TRUE(hero(m, 1121).hero == Hero::Ready);
  TEST_ASSERT_EQUAL(2, hero(m, 1121).minutes);
  TEST_ASSERT_TRUE(hero(m, 1241).hero == Hero::Now);    // 59 s left
  TEST_ASSERT_TRUE(hero(m, 1300).hero == Hero::Now);    // 0 s left
  HeroView late = hero(m, 1350);                         // leave time passed: tight
  TEST_ASSERT_TRUE(late.hero == Hero::Tight);
  TEST_ASSERT_EQUAL(70, late.spareS);                   // 1660-1350-240
  TEST_ASSERT_TRUE(hero(m, 1421).hero == Hero::Checking);  // can't walk there anymore
}

void test_hero_server_tight() {
  const char* j = R"({"v":1,"now":1000,"st":"live","rec":{"r":"40","a":"tight","l":900,"b":1300,)"
                  R"("w":240,"k":"l","x":false,"why":"Tight","alt":{"r":"42","l":1500,"b":1900}},"rows":[]})";
  Model m = parsed(j);
  HeroView v = hero(m, 1000);
  TEST_ASSERT_TRUE(v.hero == Hero::Tight);
  TEST_ASSERT_EQUAL(60, v.spareS);
  TEST_ASSERT_TRUE(m.rec.hasAlt);
  TEST_ASSERT_EQUAL_STRING("42", m.rec.altRoute);
}

void test_cells() {
  Model m = parsed(kLive);  // buffer = 1660-1300-240 = 120
  const Row& r40 = m.rows[0];
  TEST_ASSERT_TRUE(cell(m, r40, r40.t[0], 1000) == Cell::Missed);  // 100 s away, 240 s walk
  TEST_ASSERT_TRUE(cell(m, r40, r40.t[1], 1000) == Cell::Ok);      // the recommended bus
}

void test_cells_exact() {
  Model m = parsed(kLive);
  const Row& r40 = m.rows[0];
  Arrival a{1000 + 239, Kind::Live};
  TEST_ASSERT_TRUE(cell(m, r40, a, 1000) == Cell::Missed);
  a.at = 1000 + 240;
  TEST_ASSERT_TRUE(cell(m, r40, a, 1000) == Cell::Tight);
  a.at = 1000 + 359;
  TEST_ASSERT_TRUE(cell(m, r40, a, 1000) == Cell::Tight);
  a.at = 1000 + 360;
  TEST_ASSERT_TRUE(cell(m, r40, a, 1000) == Cell::Ok);
}

void test_floor_minutes() {
  TEST_ASSERT_EQUAL(0, floorMinutes(-30));
  TEST_ASSERT_EQUAL(0, floorMinutes(59));
  TEST_ASSERT_EQUAL(1, floorMinutes(60));
  TEST_ASSERT_EQUAL(9, floorMinutes(599));
}

void test_device_clock_and_connection() {
  Model m = parsed(kLive);
  TEST_ASSERT_EQUAL_INT64(1000, deviceNow(m, 5000, 5999));
  TEST_ASSERT_EQUAL_INT64(1001, deviceNow(m, 5000, 6000));
  TEST_ASSERT_EQUAL_INT64(1001, deviceNow(m, 0xFFFFFF00u, 0x000002E8u));  // millis() wrap
  TEST_ASSERT_FALSE(noConnection(false, 1000, 999999));
  TEST_ASSERT_FALSE(noConnection(true, 1000, 1000 + 45000));
  TEST_ASSERT_TRUE(noConnection(true, 1000, 1000 + 46000));
  TEST_ASSERT_TRUE(noConnection(true, 0, 10));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_parse_live_payload);
  RUN_TEST(test_parse_rejects_garbage_and_keeps_old_model);
  RUN_TEST(test_parse_missing_approx_defaults_to_not_live);
  RUN_TEST(test_parse_no_rec_has_message);
  RUN_TEST(test_parse_truncates_extra_rows_and_arrivals);
  RUN_TEST(test_hero_countdown_floors);
  RUN_TEST(test_hero_states_over_time);
  RUN_TEST(test_hero_server_tight);
  RUN_TEST(test_cells);
  RUN_TEST(test_cells_exact);
  RUN_TEST(test_floor_minutes);
  RUN_TEST(test_device_clock_and_connection);
  return UNITY_END();
}
