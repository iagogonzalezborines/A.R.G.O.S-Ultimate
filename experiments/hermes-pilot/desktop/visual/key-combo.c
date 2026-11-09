/* Fixed key combinations with a standard XKB map. Private Wayland socket only.
 * wtype's generated Unicode map is useful for text, but GTK accelerators need
 * ordinary keycodes. The controller destroys the private seat on interruption. */
#define _GNU_SOURCE
#include <wayland-client.h>
#include <xkbcommon/xkbcommon.h>
#include <string.h>
#include <stdlib.h>
#include <stdint.h>
#include <unistd.h>
#include <sys/mman.h>
#include <signal.h>
#include <sys/prctl.h>
#include "virtual-keyboard.h"
static struct zwp_virtual_keyboard_manager_v1 *manager;
static struct wl_seat *seat;
static void global(void *data,struct wl_registry *r,uint32_t id,const char *name,uint32_t version){
    (void)data;(void)version;
    if(!strcmp(name,"zwp_virtual_keyboard_manager_v1"))manager=wl_registry_bind(r,id,&zwp_virtual_keyboard_manager_v1_interface,1);
    if(!strcmp(name,"wl_seat"))seat=wl_registry_bind(r,id,&wl_seat_interface,1);
}
static void removed(void *data,struct wl_registry *r,uint32_t id){(void)data;(void)r;(void)id;}
int main(int argc,char **argv){
    if(argc!=3)return 2;
    char *end;unsigned long mods=strtoul(argv[1],&end,10);if(*end||mods>13||(mods&2))return 2;
    unsigned long key=strtoul(argv[2],&end,10);if(*end||key<1||key>111)return 2;
    prctl(PR_SET_PDEATHSIG,SIGTERM);
    struct wl_display *display=wl_display_connect(NULL);if(!display)return 3;
    struct wl_registry *registry=wl_display_get_registry(display);
    struct wl_registry_listener listener={global,removed};wl_registry_add_listener(registry,&listener,NULL);
    if(wl_display_roundtrip(display)<0||!manager||!seat)return 3;
    struct xkb_context *context=xkb_context_new(XKB_CONTEXT_NO_ENVIRONMENT_NAMES);
    struct xkb_rule_names names={.rules="evdev",.model="pc105",.layout="us"};
    struct xkb_keymap *map=xkb_keymap_new_from_names(context,&names,XKB_KEYMAP_COMPILE_NO_FLAGS);if(!map)return 4;
    char *text=xkb_keymap_get_as_string(map,XKB_KEYMAP_FORMAT_TEXT_V1);if(!text)return 4;
    size_t size=strlen(text)+1;int fd=memfd_create("argos-private-keymap",MFD_CLOEXEC);
    if(fd<0||write(fd,text,size)!=(ssize_t)size)return 4;
    struct zwp_virtual_keyboard_v1 *keyboard=zwp_virtual_keyboard_manager_v1_create_virtual_keyboard(manager,seat);
    zwp_virtual_keyboard_v1_keymap(keyboard,WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1,fd,size);close(fd);free(text);
    wl_display_roundtrip(display);usleep(80000);
    zwp_virtual_keyboard_v1_modifiers(keyboard,(uint32_t)mods,0,0,0);wl_display_roundtrip(display);usleep(20000);
    zwp_virtual_keyboard_v1_key(keyboard,0,(uint32_t)key,WL_KEYBOARD_KEY_STATE_PRESSED);wl_display_roundtrip(display);usleep(20000);
    zwp_virtual_keyboard_v1_key(keyboard,0,(uint32_t)key,WL_KEYBOARD_KEY_STATE_RELEASED);wl_display_roundtrip(display);
    zwp_virtual_keyboard_v1_modifiers(keyboard,0,0,0,0);wl_display_roundtrip(display);usleep(20000);
    zwp_virtual_keyboard_v1_destroy(keyboard);int status=wl_display_roundtrip(display);
    xkb_keymap_unref(map);xkb_context_unref(context);wl_display_disconnect(display);return status<0?5:0;
}
