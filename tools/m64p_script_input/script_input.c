/* Dev tool: mupen64plus input plugin that plays a scripted controller (player 1 only).
 * Script file (env M64P_SCRIPT): one event per line "start count buttons x y" where start/count are
 * controller polls (MK64 polls about once per frame), buttons a '+'-joined list of
 * A B Z START L R CU CD CL CR DU DD DL DR, x/y stick -80..80. Build:
 *   zig cc -shared -target x86_64-windows-gnu -O2 -o mupen64plus-input-script.dll script_input.c
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define EXPORT __declspec(dllexport)
#define CALL __cdecl

typedef struct { int Present, RawData, Plugin, Type; } CONTROL;
typedef struct { CONTROL *Controls; } CONTROL_INFO;
typedef unsigned int u32;

typedef struct { long start, count; u32 buttons; int x, y; } Event;
static Event ev[4096];
static int nev;
static long polls;

static u32 parse_buttons(char *s) {
    static const char *names[] = {"DR", "DL", "DD", "DU", "START", "Z", "B", "A", "CR", "CL", "CD", "CU", "R", "L"};
    u32 v = 0;
    for (char *t = strtok(s, "+"); t; t = strtok(NULL, "+"))
        for (int i = 0; i < 14; i++)
            if (!strcmp(t, names[i])) v |= 1u << i;
    return v;
}

EXPORT int CALL PluginStartup(void *h, void *ctx, void *dbg) {
    const char *p = getenv("M64P_SCRIPT");
    FILE *f = p ? fopen(p, "r") : NULL;
    char line[256], b[128];
    nev = 0;
    while (f && fgets(line, sizeof line, f) && nev < 4096) {
        Event e = {0};
        b[0] = 0;
        if (sscanf(line, "%ld %ld %127s %d %d", &e.start, &e.count, b, &e.x, &e.y) >= 3) {
            e.buttons = strcmp(b, "-") ? parse_buttons(b) : 0;
            ev[nev++] = e;
        }
    }
    if (f) fclose(f);
    return 0;
}
EXPORT int CALL PluginShutdown(void) { return 0; }
EXPORT int CALL PluginGetVersion(int *type, int *ver, int *api, const char **name, int *caps) {
    if (type) *type = 4;              /* M64PLUGIN_INPUT */
    if (ver) *ver = 0x010000;
    if (api) *api = 0x020100;
    if (name) *name = "script input";
    if (caps) *caps = 0;
    return 0;
}
EXPORT void CALL InitiateControllers(CONTROL_INFO info) {
    info.Controls[0].Present = 1;
    info.Controls[0].Plugin = 1;      /* PLUGIN_NONE (no pak) */
    for (int i = 1; i < 4; i++) info.Controls[i].Present = 0;
}
EXPORT void CALL GetKeys(int control, u32 *keys) {
    if (control != 0) { *keys = 0; return; }
    u32 v = 0;
    for (int i = 0; i < nev; i++)
        if (polls >= ev[i].start && polls < ev[i].start + ev[i].count)
            v |= ev[i].buttons | ((u32)(unsigned char)(signed char)ev[i].x << 16) | ((u32)(unsigned char)(signed char)ev[i].y << 24);
    polls++;
    *keys = v;
}
EXPORT void CALL ControllerCommand(int c, unsigned char *cmd) {}
EXPORT void CALL ReadController(int c, unsigned char *cmd) {}
EXPORT int CALL RomOpen(void) { polls = 0; return 1; }
EXPORT void CALL RomClosed(void) {}
EXPORT void CALL SDL_KeyDown(int k, int s) {}
EXPORT void CALL SDL_KeyUp(int k, int s) {}
EXPORT void CALL RenderCallback(void) {}
