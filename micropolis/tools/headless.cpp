/* headless.cpp -- the Micropolis engine with no interface, for tests
 *
 * Micropolis, Unix Version.  This game was released for the Unix platform
 * in or about 1990 and has been modified for inclusion in the One Laptop
 * Per Child program.  Copyright (C) 1989 - 2007 Electronic Arts Inc.
 * This file is part of the BOX's port (rosgd/ports/micropolis) and is
 * under the same licence: the GNU General Public License, version 3 or
 * later, with the ADDITIONAL TERMS per GNU GPL Section 7 in
 * MicropolisGPLLicenseNotice.md, which every copy must carry.
 *
 *   headless CITY.cty TICKS [SEED]
 *       loads the city, runs TICKS simulation ticks with the random
 *       generator seeded from SEED (default 7), and prints the census once
 *       a simulated year, then the map's and the generator's state
 *   headless --roundtrip CITY.cty OUT.cty
 *       loads the city, saves it, loads the copy, and checks that the
 *       file's 32-bit and flag fields come back the same
 */
#include "micropolis.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>

/* every callback ignored: there is no one to tell */
class NullCallback : public Callback {
public:
    void autoGoto(Micropolis *micropolis, emscripten::val callbackVal, int x, int y, std::string message) override {}
    void didGenerateMap(Micropolis *micropolis, emscripten::val callbackVal, int seed) override {}
    void didLoadCity(Micropolis *micropolis, emscripten::val callbackVal, std::string filename) override {}
    void didLoadScenario(Micropolis *micropolis, emscripten::val callbackVals, std::string name, std::string fname) override {}
    void didLoseGame(Micropolis *micropolis, emscripten::val callbackVal) override {}
    void didSaveCity(Micropolis *micropolis, emscripten::val callbackVal, std::string filename) override {}
    void didTool(Micropolis *micropolis, emscripten::val callbackVal, std::string name, int x, int y) override {}
    void didWinGame(Micropolis *micropolis, emscripten::val callbackVal) override {}
    void didntLoadCity(Micropolis *micropolis, emscripten::val callbackVal, std::string filename) override {}
    void didntSaveCity(Micropolis *micropolis, emscripten::val callbackVal, std::string filename) override {}
    void makeSound(Micropolis *micropolis, emscripten::val callbackVal, std::string channel, std::string sound, int x, int y) override {}
    void newGame(Micropolis *micropolis, emscripten::val callbackVal) override {}
    void saveCityAs(Micropolis *micropolis, emscripten::val callbackVal, std::string filename) override {}
    void sendMessage(Micropolis *micropolis, emscripten::val callbackVal, int messageIndex, int x, int y, bool picture, bool important) override {}
    void showBudgetAndWait(Micropolis *micropolis, emscripten::val callbackVal) override {}
    void showZoneStatus(Micropolis *micropolis, emscripten::val callbackVal, int tileCategoryIndex, int populationDensityIndex, int landValueIndex, int crimeRateIndex, int pollutionIndex, int growthRateIndex, int x, int y) override {}
    void simulateRobots(Micropolis *micropolis, emscripten::val callbackVal) override {}
    void simulateChurch(Micropolis *micropolis, emscripten::val callbackVal, int posX, int posY, int churchNumber) override {}
    void startEarthquake(Micropolis *micropolis, emscripten::val callbackVal, int strength) override {}
    void startGame(Micropolis *micropolis, emscripten::val callbackVal) override {}
    void startScenario(Micropolis *micropolis, emscripten::val callbackVal, int scenario) override {}
    void updateBudget(Micropolis *micropolis, emscripten::val callbackVal) override {}
    void updateCityName(Micropolis *micropolis, emscripten::val callbackVal, std::string cityName) override {}
    void updateDate(Micropolis *micropolis, emscripten::val callbackVal, int cityYear, int cityMonth) override {}
    void updateDemand(Micropolis *micropolis, emscripten::val callbackVal, float r, float c, float i) override {}
    void updateEvaluation(Micropolis *micropolis, emscripten::val callbackVal) override {}
    void updateFunds(Micropolis *micropolis, emscripten::val callbackVal, int totalFunds) override {}
    void updateGameLevel(Micropolis *micropolis, emscripten::val callbackVal, int gameLevel) override {}
    void updateHistory(Micropolis *micropolis, emscripten::val callbackVal) override {}
    void updateMap(Micropolis *micropolis, emscripten::val callbackVal) override {}
    void updateOptions(Micropolis *micropolis, emscripten::val callbackVal) override {}
    void updatePasses(Micropolis *micropolis, emscripten::val callbackVal, int passes) override {}
    void updatePaused(Micropolis *micropolis, emscripten::val callbackVal, bool simPaused) override {}
    void updateSpeed(Micropolis *micropolis, emscripten::val callbackVal, int speed) override {}
    void updateTaxRate(Micropolis *micropolis, emscripten::val callbackVal, int cityTax) override {}
};

static uint64_t map_hash(Micropolis &m)
{
    uint64_t h = 1469598103934665603ULL;       /* FNV-1a over the map */
    for (int x = 0; x < WORLD_W; x++)
        for (int y = 0; y < WORLD_H; y++)
            h = (h ^ m.map[x][y]) * 1099511628211ULL;
    return h;
}

static void census(Micropolis &m, long year)
{
    printf("%ld: pop %d funds %ld score %d class %d tax %d time %ld\n", year, (int)m.cityPop,
           (long)m.totalFunds, (int)m.cityScore, (int)m.cityClass, (int)m.cityTax, (long)m.cityTime);
}

static Micropolis *start(int seed)
{
    static Micropolis m;
    m.setCallback(new NullCallback(), emscripten::val::null());
    m.init();
    m.setFixedRandomSeed(seed);
    return &m;
}

static int roundtrip(const char *city, const char *out)
{
    Micropolis &m = *start(7);
    if (!m.loadCity(city)) { fprintf(stderr, "headless: %s did not load\n", city); return 1; }
    long funds = m.totalFunds, time = m.cityTime;
    float police = m.policePercent, fire = m.firePercent, road = m.roadPercent;
    int tax = m.cityTax;
    bool autoBulldoze = m.autoBulldoze, autoBudget = m.autoBudget;
    uint64_t h = map_hash(m);
    if (!m.saveFile(out)) { fprintf(stderr, "headless: %s not saved\n", out); return 1; }
    if (!m.loadCity(out)) { fprintf(stderr, "headless: %s did not load back\n", out); return 1; }
    int bad = 0;
#define SAME(a, b, what) if ((a) != (b)) { printf("%s: %s %g, then %g\n", city, what, (double)(a), (double)(b)); bad = 1; }
    SAME(funds, (long)m.totalFunds, "funds");
    SAME(time, (long)m.cityTime, "time");
    SAME(police, m.policePercent, "police funding");
    SAME(fire, m.firePercent, "fire funding");
    SAME(road, m.roadPercent, "road funding");
    SAME(tax, m.cityTax, "tax");
    (void)h;    /* every load runs a first simulation pass (doSimInit), which
                 * redoes the map's power and animation bits and the demand
                 * valves: the file's own fields are what is checked here */
    SAME(autoBulldoze, m.autoBulldoze, "auto bulldoze");
    SAME(autoBudget, m.autoBudget, "auto budget");
    printf("%s: %s (funds %ld, time %ld, police %.2f fire %.2f road %.2f)\n", city, bad ? "DIFFERS" : "same",
           funds, time, police, fire, road);
    return bad;
}

int main(int argc, char **argv)
{
    if (argc == 4 && !strcmp(argv[1], "--roundtrip"))
        return roundtrip(argv[2], argv[3]);
    if (argc < 3) {
        fprintf(stderr, "usage: headless CITY.cty TICKS [SEED] | headless --roundtrip CITY.cty OUT.cty\n");
        return 2;
    }
    Micropolis &m = *start(argc > 3 ? atoi(argv[3]) : 7);
    if (!m.loadCity(argv[1])) { fprintf(stderr, "headless: %s did not load\n", argv[1]); return 1; }
    int ticks = atoi(argv[2]);
    m.setSpeed(3);
    m.resume();
    long year = -1;
    for (int i = 0; i < ticks; i++) {
        m.simTick();
        long y = m.cityTime / 48 + m.startingYear;
        if (y != year) {
            year = y;
            census(m, y);
        }
    }
    printf("end: map %016llx random %08lx\n", (unsigned long long)map_hash(m), (unsigned long)m.nextRandom);
    return 0;
}
