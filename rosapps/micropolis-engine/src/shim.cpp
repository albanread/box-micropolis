/* shim.cpp -- the Micropolis engine (ports/micropolis/engine) seen from
 * Rust: a flat C interface over the Micropolis class, and a callback that
 * queues what the simulation tells its front end, for the engine to take.
 *
 * Micropolis, Unix Version.  This game was released for the Unix platform
 * in or about 1990 and has been modified for inclusion in the One Laptop
 * Per Child program.  Copyright (C) 1989 - 2007 Electronic Arts Inc.
 * This file is part of the BOX's port and is under the same licence: the
 * GNU General Public License, version 3 or later, with the ADDITIONAL TERMS
 * per GNU GPL Section 7 in ports/micropolis/MicropolisGPLLicenseNotice.md.
 */
#include "micropolis.h"
#include <deque>
#include <string.h>

extern "C" {

/* one thing the simulation told us; text is copied, up to 120 bytes */
struct MpEvent {
    int kind;
    int a, b, c, d, e, f, g, h;
    char text[120];
};

enum {
    EV_MESSAGE = 1,     /* a: message number (stri.301), b c: where, d: picture, e: important */
    EV_ZONE,            /* a..f: category, density, land value, crime, pollution, growth; g h: where */
    EV_GOTO,            /* a b: where to look; text: why */
    EV_BUDGET,          /* the budget is due, and auto budget is off */
    EV_WIN,
    EV_LOSE,
    EV_QUAKE,           /* a: strength */
    EV_SOUND,           /* text: channel and sound, b c: where */
};

/* what the front end shows, read in one go */
struct MpStatus {
    int funds, pop, score, cityClass, tax, year, month, speed, paused;
    int level, scenario, disasters, autoBudget;
    float resDemand, comDemand, indDemand;
    float roadPercent, firePercent, policePercent;
    int roadFund, fireFund, policeFund, taxFund;
};

struct MpSprite {
    int type, frame, x, y, width, height, xOffset, yOffset;
};

}

namespace {

struct Queue : public Callback {
    std::deque<MpEvent> events;

    void push(int kind, int a = 0, int b = 0, int c = 0, int d = 0, int e = 0, int f = 0, int g = 0, int h = 0,
              const std::string &text = std::string())
    {
        if (events.size() > 256) {
            events.pop_front();         /* nobody is listening: keep the latest */
        }
        MpEvent ev;
        memset(&ev, 0, sizeof ev);
        ev.kind = kind;
        ev.a = a, ev.b = b, ev.c = c, ev.d = d, ev.e = e, ev.f = f, ev.g = g, ev.h = h;
        strncpy(ev.text, text.c_str(), sizeof ev.text - 1);
        events.push_back(ev);
    }

    void autoGoto(Micropolis *, emscripten::val, int x, int y, std::string message) override
    {
        push(EV_GOTO, x, y, 0, 0, 0, 0, 0, 0, message);
    }
    void didGenerateMap(Micropolis *, emscripten::val, int) override {}
    void didLoadCity(Micropolis *, emscripten::val, std::string) override {}
    void didLoadScenario(Micropolis *, emscripten::val, std::string, std::string) override {}
    void didLoseGame(Micropolis *, emscripten::val) override { push(EV_LOSE); }
    void didSaveCity(Micropolis *, emscripten::val, std::string) override {}
    void didTool(Micropolis *, emscripten::val, std::string, int, int) override {}
    void didWinGame(Micropolis *, emscripten::val) override { push(EV_WIN); }
    void didntLoadCity(Micropolis *, emscripten::val, std::string) override {}
    void didntSaveCity(Micropolis *, emscripten::val, std::string) override {}
    void makeSound(Micropolis *, emscripten::val, std::string channel, std::string sound, int x, int y) override
    {
        push(EV_SOUND, 0, x, y, 0, 0, 0, 0, 0, channel + " " + sound);
    }
    void newGame(Micropolis *, emscripten::val) override {}
    void saveCityAs(Micropolis *, emscripten::val, std::string) override {}
    void sendMessage(Micropolis *, emscripten::val, int index, int x, int y, bool picture, bool important) override
    {
        push(EV_MESSAGE, index, x, y, picture, important);
    }
    void showBudgetAndWait(Micropolis *, emscripten::val) override { push(EV_BUDGET); }
    void showZoneStatus(Micropolis *, emscripten::val, int category, int density, int landValue, int crime,
                        int pollution, int growth, int x, int y) override
    {
        push(EV_ZONE, category, density, landValue, crime, pollution, growth, x, y);
    }
    void simulateRobots(Micropolis *, emscripten::val) override {}
    void simulateChurch(Micropolis *, emscripten::val, int, int, int) override {}
    void startEarthquake(Micropolis *, emscripten::val, int strength) override { push(EV_QUAKE, strength); }
    void startGame(Micropolis *, emscripten::val) override {}
    void startScenario(Micropolis *, emscripten::val, int) override {}
    void updateBudget(Micropolis *, emscripten::val) override {}
    void updateCityName(Micropolis *, emscripten::val, std::string) override {}
    void updateDate(Micropolis *, emscripten::val, int, int) override {}
    void updateDemand(Micropolis *, emscripten::val, float, float, float) override {}
    void updateEvaluation(Micropolis *, emscripten::val) override {}
    void updateFunds(Micropolis *, emscripten::val, int) override {}
    void updateGameLevel(Micropolis *, emscripten::val, int) override {}
    void updateHistory(Micropolis *, emscripten::val) override {}
    void updateMap(Micropolis *, emscripten::val) override {}
    void updateOptions(Micropolis *, emscripten::val) override {}
    void updatePasses(Micropolis *, emscripten::val, int) override {}
    void updatePaused(Micropolis *, emscripten::val, bool) override {}
    void updateSpeed(Micropolis *, emscripten::val, int) override {}
    void updateTaxRate(Micropolis *, emscripten::val, int) override {}
};

struct City {
    Micropolis sim;
    Queue queue;
};

}

extern "C" {

void *mp_new(void)
{
    City *c = new City();
    c->sim.setCallback(&c->queue, emscripten::val::null());
    c->sim.init();
    c->sim.setEnableSound(true);
    c->sim.setAutoBudget(true);
    c->sim.setAutoBulldoze(true);       /* roads and buildings clear trees as they go */
    c->sim.setAutoGoto(true);           /* the view goes to disasters (the engine's "Go to events") */
    return c;
}

static Micropolis &M(void *c) { return static_cast<City *>(c)->sim; }

/* a new city on a random map, at a game level (0 easy, 1 medium, 2 hard) */
void mp_generate(void *c, int level)
{
    Micropolis &m = M(c);
    m.generateSomeRandomCity();
    m.setGameLevelFunds((GameLevel)level);
    m.setCityName("New city");
    m.setCityTax(7);
    m.setSpeed(2);
    m.resume();
}

int mp_load(void *c, const char *path)
{
    Micropolis &m = M(c);
    bool ok = m.loadCity(path);
    m.resume();
    return ok;
}

/* scenario 1..8; its file is cities/scenario_*.cty in the working directory */
void mp_scenario(void *c, int s)
{
    Micropolis &m = M(c);
    m.loadScenario((Scenario)s);
    m.resume();
}

int mp_save(void *c, const char *path) { return M(c).saveFile(path); }

void mp_tick(void *c) { M(c).simTick(); }
void mp_animate(void *c) { M(c).animateTiles(); }

const unsigned short *mp_map(void *c) { return (const unsigned short *)M(c).getMapBuffer(); }

int mp_tool(void *c, int tool, int x, int y) { return (int)M(c).doTool((EditingTool)tool, (short)x, (short)y); }

void mp_set_speed(void *c, int speed)
{
    Micropolis &m = M(c);
    if (speed <= 0) {
        m.pause();
    } else {
        m.setSpeed((short)speed);
        m.resume();
    }
}

void mp_set_tax(void *c, int tax) { M(c).setCityTax((short)tax); }

void mp_set_funding(void *c, float road, float fire, float police)
{
    Micropolis &m = M(c);
    m.roadPercent = road;
    m.firePercent = fire;
    m.policePercent = police;
    m.updateFundEffects();
}

void mp_set_auto_budget(void *c, int on) { M(c).setAutoBudget(on != 0); }
void mp_set_disasters(void *c, int on) { M(c).setEnableDisasters(on != 0); }
void mp_set_auto_goto(void *c, int on) { M(c).setAutoGoto(on != 0); }
void mp_set_level(void *c, int level) { M(c).setGameLevel((GameLevel)level); }
void mp_set_name(void *c, const char *name) { M(c).setCityName(name); }
/* the name as given, spaces and all (setCityName makes them '_') */
void mp_set_clean_name(void *c, const char *name) { M(c).setCleanCityName(name); }

/* the disasters, as the Disasters menu orders them */
void mp_disaster(void *c, int which)
{
    Micropolis &m = M(c);
    switch (which) {
    case 0: m.makeFire(); break;
    case 1: m.makeFlood(); break;
    case 2: m.makeTornado(); break;
    case 3: m.makeEarthquake(); break;
    case 4: m.makeMonster(); break;
    case 5: m.makeMeltdown(); break;
    default: break;
    }
}

void mp_status(void *c, MpStatus *s)
{
    Micropolis &m = M(c);
    memset(s, 0, sizeof *s);
    s->funds = m.totalFunds;
    s->pop = m.cityPop;
    s->score = m.cityScore;
    s->cityClass = m.cityClass;
    s->tax = m.cityTax;
    s->year = m.cityTime / 48 + m.startingYear;
    s->month = (m.cityTime % 48) / 4;
    s->speed = m.simSpeed;
    s->paused = m.simPaused;
    s->level = m.gameLevel;
    s->scenario = m.scenario;
    s->disasters = m.enableDisasters;
    s->autoBudget = m.autoBudget;
    m.getDemands(&s->resDemand, &s->comDemand, &s->indDemand);
    s->roadPercent = m.roadPercent;
    s->firePercent = m.firePercent;
    s->policePercent = m.policePercent;
    s->roadFund = m.roadFund;
    s->fireFund = m.fireFund;
    s->policeFund = m.policeFund;
    s->taxFund = m.taxFund;
}

/* the city's name, into BUF */
void mp_name(void *c, char *buf, int len)
{
    strncpy(buf, M(c).cityName.c_str(), len - 1);
    buf[len - 1] = 0;
}

int mp_next_event(void *c, MpEvent *ev)
{
    Queue &q = static_cast<City *>(c)->queue;
    if (q.events.empty()) {
        return 0;
    }
    *ev = q.events.front();
    q.events.pop_front();
    return 1;
}

/* the active sprites (trains, aircraft, ships, the monster, tornadoes,
 * explosions), up to MAX, into OUT; their number */
int mp_sprites(void *c, MpSprite *out, int max)
{
    int n = 0;
    for (SimSprite *s = M(c).spriteList; s && n < max; s = s->next) {
        if (s->frame == 0) {
            continue;
        }
        out[n].type = s->type;
        out[n].frame = s->frame;
        out[n].x = s->x;
        out[n].y = s->y;
        out[n].width = s->width;
        out[n].height = s->height;
        out[n].xOffset = s->xOffset;
        out[n].yOffset = s->yOffset;
        n++;
    }
    return n;
}

}
