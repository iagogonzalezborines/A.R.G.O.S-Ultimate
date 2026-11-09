#define _GNU_SOURCE
/* Minimal private-seat lifetime helper. The Broker never passes the host display.
 * Only the private socket accepts bounded input; it cannot open a host seat.
 * Protocol copyright/license is retained in the adjacent XML. */
#include <wayland-client.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <stdio.h>
#include <signal.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <stdlib.h>
#include "virtual-pointer.h"
static struct zwlr_virtual_pointer_manager_v1 *manager;
static void global(void *data, struct wl_registry *r, uint32_t id, const char *iface, uint32_t version) {
    (void)data;(void)version;
    if (!strcmp(iface, "zwlr_virtual_pointer_manager_v1"))
        manager=wl_registry_bind(r,id,&zwlr_virtual_pointer_manager_v1_interface,1);
}
static void removed(void *data,struct wl_registry *r,uint32_t id){(void)data;(void)r;(void)id;}
int main(void){
    prctl(PR_SET_PDEATHSIG,SIGTERM);
    struct wl_display *display=wl_display_connect(NULL);
    if(!display)return 2;
    struct wl_registry *registry=wl_display_get_registry(display);
    struct wl_registry_listener listener={global,removed};
    wl_registry_add_listener(registry,&listener,NULL);
    if(wl_display_roundtrip(display)<0||!manager)return 3;
    struct zwlr_virtual_pointer_v1 *pointer=zwlr_virtual_pointer_manager_v1_create_virtual_pointer(manager,NULL);
    if(wl_display_roundtrip(display)<0)return 4;
    int server=socket(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0);
    struct sockaddr_un address={.sun_family=AF_UNIX};
    strcpy(address.sun_path,"/run/av/pointer.sock");unlink(address.sun_path);
    if(server<0||bind(server,(struct sockaddr*)&address,sizeof(address))||listen(server,4))return 5;
    puts("ready");fflush(stdout);
    for(;;){
        int client=accept4(server,NULL,NULL,SOCK_CLOEXEC);if(client<0)break;
        struct timeval timeout={.tv_sec=1};setsockopt(client,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout));
        char line[128]={0};size_t used=0;
        while(used<sizeof(line)-1){ssize_t n=read(client,line+used,1);if(n!=1)break;if(line[used++]=='\n')break;}
        unsigned x,y,w,h,button,state;int axis,amount;char extra;int valid=0;
        struct timespec now;clock_gettime(CLOCK_MONOTONIC,&now);uint32_t stamp=(uint32_t)(now.tv_sec*1000+now.tv_nsec/1000000);
        if(sscanf(line,"M %u %u %u %u %c",&x,&y,&w,&h,&extra)==4&&w>0&&w<=2200&&h>0&&h<=1600&&x<w&&y<h){
            zwlr_virtual_pointer_v1_motion_absolute(pointer,stamp,x,y,w,h);valid=1;
        }else if(sscanf(line,"B %u %u %c",&button,&state,&extra)==2&&button>=272&&button<=274&&state<=1){
            zwlr_virtual_pointer_v1_button(pointer,stamp,button,state);valid=1;
        }else if(sscanf(line,"S %d %d %c",&axis,&amount,&extra)==2&&axis>=0&&axis<=1&&amount>=-10&&amount<=10&&amount!=0){
            zwlr_virtual_pointer_v1_axis_source(pointer,WL_POINTER_AXIS_SOURCE_WHEEL);
            zwlr_virtual_pointer_v1_axis_discrete(pointer,stamp,(uint32_t)axis,wl_fixed_from_int(amount*15),amount);valid=1;
        }
        if(valid){zwlr_virtual_pointer_v1_frame(pointer);if(wl_display_roundtrip(display)<0)valid=0;}
        const char *reply=valid?"ok\n":"error\n";ssize_t ignored=write(client,reply,strlen(reply));(void)ignored;close(client);
    }
    zwlr_virtual_pointer_v1_destroy(pointer);wl_display_flush(display);wl_display_disconnect(display);return 0;
}
