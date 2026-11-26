// Native mock HAL only. This executable never opens GPIO, USB or a motor port.
#include "j1_protocol.h"
#include <assert.h>
#include <chrono>
#include <stdio.h>
#include <string.h>
#include <string>
#include <sys/select.h>
#include <unistd.h>

struct FakeMotor: j1::MotorHal {
  bool bound=true,good=true,physical_stop=false,enabled=false,moving=false,jogging=false;
  bool fail=false,hold_busy=false;
  int jog_calls=0,rate_calls=0,pwm_calls=0,pair_calls=0,four_calls=0;
  int16_t four[4]={0,0,0,0};
  int32_t left=0,right=0;
  uint32_t now=0,finish=0;
  bool ready() const {return bound;}
  bool healthy() const {return good;}
  bool estopInput() const {return physical_stop;}
  bool enable(bool on) {enabled=on;return !on||!fail;}
  void stop() {moving=false;jogging=false;left=right=0;}
  bool rates(int32_t l,int32_t r) {++rate_calls;left=l;right=r;moving=l||r;return !fail;}
  bool jog(uint8_t,int32_t pulses,uint16_t rate) {
    ++jog_calls;jogging=moving=true;
    finish=now+static_cast<uint32_t>((pulses<0?-pulses:pulses)*1000/rate);
    return !fail;
  }
  bool busy() const {return moving&&(!jogging||hold_busy||static_cast<int32_t>(now-finish)<0);}
  bool pwm(uint8_t,int16_t,uint16_t duration) {
    ++pwm_calls;jogging=moving=true;finish=now+duration;return !fail;
  }
  bool pwmPair(int16_t l,int16_t r,uint16_t duration) {
    ++pair_calls;left=l;right=r;jogging=moving=true;finish=now+duration;return !fail;
  }
  bool pwmFour(int16_t a,int16_t b,int16_t c,int16_t d,uint16_t duration) {
    ++four_calls;four[0]=a;four[1]=b;four[2]=c;four[3]=d;
    jogging=moving=true;finish=now+duration;return !fail;
  }
};
struct Capture: j1::ReplySink {
  std::string last;int count=0;bool print=false,encoders=false;
  void send(const char* frame) {last=frame;++count;if(print){fputs(frame,stdout);fflush(stdout);}}
  bool reportEncoders() {
    if (!encoders) return false;
    const char body[]="J1ENC1,0,100,10,20,30,40,0,0,0,0";
    char sample[64];
    snprintf(sample,sizeof sample,"$%s*%04X\n",body,j1::crc16(body,strlen(body)));
    send(sample);
    return true;
  }
};
static std::string frame(uint32_t sid,uint32_t seq,const char* command) {
  char body[256],result[300];
  snprintf(body,sizeof(body),"J1,%u,%u,%s",sid,seq,command);
  snprintf(result,sizeof(result),"$%s*%04X\n",body,j1::crc16(body,strlen(body)));
  return result;
}
static void send(j1::Controller& c,FakeMotor& h,uint32_t sid,uint32_t seq,
                 const char* command,uint32_t now=0) {
  h.now=now;
  const std::string wire=frame(sid,seq,command);
  for(size_t i=0;i<wire.size();++i)c.feed(wire[i],now);
}
static bool has(const Capture& s,const char* text) {return s.last.find(text)!=std::string::npos;}
static void handshake(j1::Controller& c,FakeMotor& h,uint32_t sid,uint32_t now=0) {
  send(c,h,sid,1,"HELLO",now);send(c,h,sid,2,"ARM",now);
}
static void tests() {
  assert(j1::crc16("123456789",9)==0x29b1);
  {
    FakeMotor h;Capture sink;j1::Controller c(h,sink);
    assert(!h.enabled&&c.state()==j1::DISARMED);
    send(c,h,1,1,"WHEELS,20,20");assert(has(sink,"ERR,WHEELS,SESSION"));
    send(c,h,1,1,"HELLO");assert(has(sink,"ACK,HELLO,DISARMED"));
    send(c,h,1,2,"JOG,0,50,100");assert(has(sink,"ERR,JOG,STATE"));
    send(c,h,1,3,"ARM");assert(h.enabled);
    send(c,h,1,4,"JOG,0,50,100");assert(h.jog_calls==1&&c.state()==j1::JOGGING);
    send(c,h,1,4,"JOG,0,50,100",200);assert(h.jog_calls==1);
    send(c,h,1,4,"JOG,1,50,100",201);assert(has(sink,"ERR,JOG,SEQ")&&h.jog_calls==1);
    c.tick(299);assert(h.enabled);
    c.tick(300);assert(!h.enabled&&c.state()==j1::DISARMED);
    send(c,h,1,5,"ARM",301);assert(has(sink,"ERR,ARM,SESSION"));
    send(c,h,1,6,"HELLO",301);assert(has(sink,"ERR,HELLO,SESSION"));
  }
  {
    FakeMotor h;Capture sink;j1::Controller c(h,sink);handshake(c,h,2);
    send(c,h,2,3,"WHEELS,-25,25");assert(h.left==-25&&h.right==25);
    send(c,h,2,4,"KEEP",200);assert(has(sink,"ERR,KEEP,STATE"));
    send(c,h,2,5,"STATUS",250);c.tick(300);assert(!h.enabled&&!h.moving);
    handshake(c,h,3,400);send(c,h,3,3,"WHEELS,201,0",410);
    assert(has(sink,"ERR,WHEELS,RANGE")&&h.rate_calls==1);
    send(c,h,3,4,"JOG,0,200,1",415);assert(has(sink,"ERR,JOG,RANGE"));
    send(c,h,3,5,"JOG,0,4294967296,100",420);assert(has(sink,"ERR,JOG,RANGE"));
    send(c,h,3,6,"JOG,0,50,100",425);assert(h.jog_calls==1);
    send(c,h,99,1,"STOP",426);assert(!h.enabled&&!h.moving);
    send(c,h,3,7,"ARM",427);assert(has(sink,"ERR,ARM,SESSION"));
    send(c,h,3,8,"HELLO",428);assert(has(sink,"ERR,HELLO,SESSION"));
    send(c,h,77,1,"ESTOP",429);assert(c.state()==j1::ESTOP);
    handshake(c,h,4,430);assert(has(sink,"ERR,ARM,STATE")&&!h.enabled);
    send(c,h,4,3,"CLEAR",431);assert(c.state()==j1::DISARMED&&!h.enabled);
    handshake(c,h,5,432);assert(h.enabled);
    h.physical_stop=true;c.tick(433);assert(c.state()==j1::ESTOP&&!h.enabled);
    send(c,h,6,1,"HELLO",434);send(c,h,6,2,"CLEAR",435);assert(has(sink,"ERR,CLEAR,INTERLOCK"));
    h.physical_stop=false;send(c,h,6,3,"CLEAR",436);assert(c.state()==j1::DISARMED);
    h.good=false;handshake(c,h,7,437);assert(has(sink,"ERR,ARM,INTERLOCK"));
  }
  {
    FakeMotor h;Capture sink;j1::Controller c(h,sink);handshake(c,h,31);
    send(c,h,31,3,"ENC",50);assert(has(sink,"ERR,ENC,UNBOUND"));
    sink.encoders=true;
    const int before=sink.count;
    send(c,h,31,4,"ENC",250);
    assert(sink.count==before+2&&has(sink,"ACK,ENC,ARMED"));
    send(c,h,31,4,"ENC",275);assert(has(sink,"ERR,ENC,SEQ"));
    c.tick(300);assert(!h.enabled);
  }
  {
    FakeMotor h;h.bound=false;Capture sink;j1::Controller c(h,sink);
    handshake(c,h,8);assert(has(sink,"ERR,ARM,UNBOUND")&&!h.enabled);
    h.bound=true;send(c,h,8,3,"ARM",1);h.fail=true;
    send(c,h,8,4,"WHEELS,10,10",2);assert(c.state()==j1::FAULT&&!h.enabled&&!h.moving);
  }
  {
    FakeMotor h;Capture sink;j1::Controller c(h,sink);handshake(c,h,9);
    std::string bad=frame(9,3,"JOG,0,50,100");bad[bad.size()-3]='Z';
    int before=sink.count;for(size_t i=0;i<bad.size();++i)c.feed(bad[i],10);
    assert(sink.count==before&&h.jog_calls==0);
    for(int i=0;i<500;++i)c.feed('x',20);
    send(c,h,9,3,"JOG,0,50,100",30);assert(h.jog_calls==1);
    send(c,h,9,4,"KEEP",200);c.tick(400);assert(h.enabled);
    h.now=600;c.tick(600);assert(!h.enabled); // heartbeat timeout, not STATUS/read traffic
  }
  {
    FakeMotor h;Capture sink;j1::Controller c(h,sink);handshake(c,h,10);
    h.hold_busy=true;send(c,h,10,3,"JOG,1,-150,100");
    for(uint32_t t=100;t<2000;t+=100)send(c,h,10,3+t/100,"KEEP",t);
    assert(h.enabled);c.tick(2000);assert(!h.enabled&&!h.moving);
  }
  {
    FakeMotor h;Capture sink;j1::Controller c(h,sink);const uint32_t start=0xffffff00U;
    handshake(c,h,11,start);c.tick(start+299U);assert(h.enabled);
    c.tick(start+300U);assert(!h.enabled);
  }
  {
    FakeMotor h;Capture sink;j1::Controller c(h,sink);handshake(c,h,12);
    send(c,h,12,3,"PWM,0,201,250");assert(has(sink,"ERR,PWM,RANGE")&&h.pwm_calls==0);
    send(c,h,12,4,"PWM,0,200,401");assert(has(sink,"ERR,PWM,RANGE")&&h.pwm_calls==0);
    send(c,h,12,5,"PWM,0,200,250");assert(c.state()==j1::PWM_TEST&&h.pwm_calls==1);
    send(c,h,12,5,"PWM,0,200,250",50);assert(h.pwm_calls==1);
    send(c,h,12,6,"WHEELS,20,20",60);assert(has(sink,"ERR,WHEELS,STATE"));
    send(c,h,12,7,"KEEP",200);h.now=260;c.tick(260);assert(c.state()==j1::ARMED&&!h.busy());
    send(c,h,12,8,"STOP",261);assert(!h.enabled);
  }
  {
    FakeMotor h;Capture sink;j1::Controller c(h,sink);handshake(c,h,13);h.hold_busy=true;
    send(c,h,13,3,"PWM,1,-200,400");
    for(uint32_t t=100;t<500;t+=100)send(c,h,13,3+t/100,"KEEP",t);
    c.tick(500);assert(!h.enabled&&!h.moving);
  }
  {
    FakeMotor h;Capture sink;j1::Controller c(h,sink);
    send(c,h,14,1,"HELLO");send(c,h,14,2,"PWM_PAIR,200,200,250");
    assert(has(sink,"ERR,PWM_PAIR,STATE")&&h.pair_calls==0);
    send(c,h,14,3,"ARM");
    const char* invalid[]={"PWM_PAIR,201,0,250","PWM_PAIR,0,-201,250",
      "PWM_PAIR,0,0,250","PWM_PAIR,200,200,401","PWM_PAIR,200,200,0"};
    uint32_t seq=4;
    for(unsigned i=0;i<sizeof(invalid)/sizeof(invalid[0]);++i) {
      send(c,h,14,seq++,invalid[i]);assert(has(sink,"ERR,PWM_PAIR,RANGE")&&h.pair_calls==0);
    }
    send(c,h,14,seq,"PWM_PAIR,200,-200,250");
    assert(c.state()==j1::PWM_TEST&&h.pair_calls==1&&h.left==200&&h.right==-200);
    send(c,h,14,seq++,"PWM_PAIR,200,-200,250",50);assert(h.pair_calls==1);
    send(c,h,14,seq++,"PWM_PAIR,0,200,250",60);assert(has(sink,"ERR,PWM_PAIR,STATE"));
    send(c,h,14,seq++,"KEEP",200);h.now=260;c.tick(260);assert(c.state()==j1::ARMED&&!h.busy());
    send(c,h,14,seq++,"PWM_PAIR,0,200,250",270);assert(h.left==0&&h.right==200&&h.pair_calls==2);
    send(c,h,77,1,"STOP",280);assert(!h.enabled&&!h.moving&&h.left==0&&h.right==0);
  }
  {
    FakeMotor h;Capture sink;j1::Controller c(h,sink);handshake(c,h,15);
    send(c,h,15,3,"PWM_PAIR,200,200,400");
    h.now=300;c.tick(300);assert(!h.enabled&&!h.moving); // No heartbeat stops both sides.
    handshake(c,h,16,400);h.hold_busy=true;
    send(c,h,16,3,"PWM_PAIR,-200,200,400",400);
    for(uint32_t t=500;t<900;t+=100)send(c,h,16,3+(t-400)/100,"KEEP",t);
    c.tick(900);assert(!h.enabled&&!h.moving); // Hard cap still applies with KEEP.
  }
  {
    FakeMotor h;Capture sink;j1::Controller c(h,sink);
    send(c,h,17,1,"HELLO");send(c,h,17,2,"PWM_FOUR,0,0,200,200,250");
    assert(has(sink,"ERR,PWM_FOUR,STATE")&&h.four_calls==0);
    send(c,h,17,3,"ARM");
    char excessive[64],maximum[64];
    snprintf(excessive,sizeof excessive,"PWM_FOUR,0,0,%d,0,250",j1::PWM_FOUR_MAX+1);
    snprintf(maximum,sizeof maximum,"PWM_FOUR,%d,%d,-200,-200,250",j1::PWM_FOUR_MAX,j1::PWM_FOUR_MAX);
    send(c,h,17,4,excessive);assert(has(sink,"ERR,PWM_FOUR,RANGE"));
    send(c,h,17,5,"PWM_FOUR,0,0,0,0,250");assert(has(sink,"ERR,PWM_FOUR,RANGE"));
    snprintf(excessive,sizeof excessive,"PWM_FOUR,200,-200,200,-200,%u",unsigned(j1::PWM_FOUR_DURATION_MAX+1));
    send(c,h,17,6,excessive);assert(has(sink,"ERR,PWM_FOUR,RANGE"));
    send(c,h,17,7,maximum);
    assert(h.four_calls==1&&h.four[0]==j1::PWM_FOUR_MAX&&h.four[1]==j1::PWM_FOUR_MAX&&h.four[2]==-200&&h.four[3]==-200);
    send(c,h,17,7,maximum,50);assert(h.four_calls==1);
    send(c,h,17,8,"PWM_FOUR,0,0,200,200,250",60);assert(has(sink,"ERR,PWM_FOUR,STATE"));
    send(c,h,17,9,"KEEP",200);h.now=260;c.tick(260);assert(c.state()==j1::ARMED);
    send(c,h,17,10,"PWM,3,200,250",270);assert(h.pwm_calls==1);
    send(c,h,18,1,"STOP",280);assert(!h.enabled&&!h.moving);
    handshake(c,h,19,400);h.hold_busy=true;
    snprintf(maximum,sizeof maximum,"PWM_FOUR,200,200,200,200,%u",unsigned(j1::PWM_FOUR_DURATION_MAX));
    send(c,h,19,3,maximum,400);
    const uint32_t deadline=500+j1::PWM_FOUR_DURATION_MAX;
    for(uint32_t t=500;t<deadline;t+=100)send(c,h,19,3+(t-400)/100,"KEEP",t);
    c.tick(deadline-1);assert(h.enabled&&h.moving);
    c.tick(deadline);assert(!h.enabled&&!h.moving);
  }
#ifdef J1_PWM_FOUR_PAIRED
  {
    FakeMotor h;Capture sink;j1::Controller c(h,sink);handshake(c,h,20);
    send(c,h,20,3,"PWM_FOUR,200,150,0,0,250");assert(has(sink,"ERR,PWM_FOUR,PAIR"));
    send(c,h,20,4,"PWM_FOUR,0,0,200,-200,250");assert(has(sink,"ERR,PWM_FOUR,PAIR"));
    send(c,h,20,5,"PWM_FOUR,0,0,200,0,250");assert(has(sink,"ERR,PWM_FOUR,PAIR"));
    assert(h.four_calls==0&&!h.moving);
    send(c,h,20,6,"PWM_FOUR,300,300,0,0,5000");
    assert(h.four_calls==1&&h.four[0]==300&&h.four[1]==300&&h.four[2]==0&&h.four[3]==0);
    c.tick(300);assert(!h.enabled&&!h.moving);
  }
#endif
  puts("NATIVE_PROTOCOL_TESTS_PASSED");
}
static int emulator() {
  FakeMotor h;Capture sink;sink.print=true;sink.encoders=true;j1::Controller c(h,sink);
  const auto start=std::chrono::steady_clock::now();
  while(true) {
    h.now=static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now()-start).count());
    c.tick(h.now);
    fd_set input;FD_ZERO(&input);FD_SET(STDIN_FILENO,&input);timeval wait={0,5000};
    int ready=select(STDIN_FILENO+1,&input,0,0,&wait);
    if(ready>0) {
      char bytes[64];ssize_t n=read(STDIN_FILENO,bytes,sizeof(bytes));
      if(n<=0)break;
      for(ssize_t i=0;i<n;++i)c.feed(bytes[i],h.now);
    } else if(ready<0)break;
  }
  return 0;
}
int main(int argc,char** argv) {
  if(argc==2&&strcmp(argv[1],"--stdio")==0)return emulator();
  tests();return 0;
}
