#include "j1_protocol.h"
#include <stdio.h>
#include <string.h>

namespace j1 {
uint16_t crc16(const char* data, size_t length) {
  uint16_t crc = 0xffff;
  for (size_t i=0; i<length; ++i) {
    crc ^= static_cast<uint16_t>(static_cast<unsigned char>(data[i])) << 8;
    for (int bit=0; bit<8; ++bit)
      crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021)
                           : static_cast<uint16_t>(crc << 1);
  }
  return crc;
}
static bool number(const char* s, int64_t minimum, int64_t maximum, int64_t& out) {
  bool negative = *s=='-';
  if (negative) ++s;
  if (!*s) return false;
  int64_t n=0;
  for (; *s; ++s) {
    if (*s<'0' || *s>'9') return false;
    n=n*10+(*s-'0');
    if (n>4294967295LL) return false;
  }
  out=negative ? -n : n;
  return out>=minimum && out<=maximum;
}
Controller::Controller(MotorHal& hal, ReplySink& sink):hal_(hal),sink_(sink),
    state_(DISARMED),session_(0),retired_session_(0),last_seq_(0),lease_ms_(0),jog_start_ms_(0),
    pwm_timeout_ms_(500),enabled_(false),collecting_(false),length_(0) {
  last_request_[0]=cached_reply_[0]=0;
  hal_.stop();hal_.enable(false);
}
const char* Controller::stateName() const {
  const char* names[]={"DISARMED","ARMED","RUNNING","JOGGING","ESTOP","FAULT","PWM_TEST"};
  return names[state_];
}
void Controller::stop(State next) {
  hal_.stop();hal_.enable(false);enabled_=false;state_=next;
  if (session_) retired_session_=session_;
  session_=0;last_seq_=0;last_request_[0]=cached_reply_[0]=0;
}
void Controller::tick(uint32_t now) {
  if (hal_.estopInput()) { if (state_!=ESTOP || enabled_) stop(ESTOP);return; }
  if (enabled_ && (!hal_.healthy() || !hal_.ready())) { stop(FAULT);return; }
  if (enabled_ && static_cast<uint32_t>(now-lease_ms_)>=300) { stop(DISARMED);return; }
  if (state_==JOGGING && static_cast<uint32_t>(now-jog_start_ms_)>=2000) {
    stop(DISARMED);return;
  }
  if (state_==JOGGING && !hal_.busy()) state_=ARMED;
  if (state_==PWM_TEST && static_cast<uint32_t>(now-jog_start_ms_)>=pwm_timeout_ms_) { stop(DISARMED);return; }
  if (state_==PWM_TEST && !hal_.busy()) state_=ARMED;
}
void Controller::reply(uint32_t session,uint32_t seq,const char* kind,const char* cmd,
                       const char* reason,bool cache) {
  char body[128], frame[160];
  if (reason) {
    snprintf(body,sizeof(body),"J1,%lu,%lu,%s,%s,%s",static_cast<unsigned long>(session),
             static_cast<unsigned long>(seq),kind,cmd,reason);
  } else {
    snprintf(body,sizeof(body),"J1,%lu,%lu,%s,%s,%s,%d,%d,%d",static_cast<unsigned long>(session),
             static_cast<unsigned long>(seq),kind,cmd,stateName(),hal_.ready()?1:0,
             enabled_?1:0,hal_.busy()?1:0);
  }
  snprintf(frame,sizeof(frame),"$%s*%04X\n",body,crc16(body,strlen(body)));
  if (cache) { strncpy(cached_reply_,frame,sizeof(cached_reply_)-1);cached_reply_[159]=0; }
  sink_.send(frame);
}
void Controller::feed(char byte,uint32_t now) {
  tick(now);
  if (byte=='$') {collecting_=true;length_=0;line_[length_++]=byte;return;}
  if (!collecting_) return;
  if (byte=='\r') return;
  if (byte=='\n') {
    // 160 is the maximum complete wire frame length, including newline.
    if (length_<=159) {line_[length_]=0;process(now);}
    collecting_=false;length_=0;return;
  }
  if (static_cast<unsigned char>(byte)<32 || static_cast<unsigned char>(byte)>126 || length_>=159) {
    collecting_=false;length_=0;return;
  }
  line_[length_++]=byte;
}
void Controller::process(uint32_t now) {
  char* star=strchr(line_,'*');
  if (!star || strlen(star)!=5) return;
  unsigned received=0;
  for (int i=1;i<=4;++i) {
    char c=star[i];unsigned digit;
    if (c>='0'&&c<='9') digit=c-'0';
    else if (c>='A'&&c<='F') digit=c-'A'+10;
    else return;
    received=received*16+digit;
  }
  if (crc16(line_+1,static_cast<size_t>(star-line_-1))!=received) return;
  *star=0;
  char request[160];strcpy(request,line_+1);
  char* fields[10];size_t count=0;
  fields[count++]=line_+1;
  for (char* p=line_+1;*p;++p) {
    if (*p==',') {
      if (count>=10) return;
      *p=0;fields[count++]=p+1;
    }
  }
  if (count<4 || strcmp(fields[0],"J1")!=0) return;
  for (size_t i=0;i<count;++i) if (!fields[i][0]) return;
  int64_t sid64,seq64;
  if (!number(fields[1],1,4294967295LL,sid64)||!number(fields[2],1,4294967295LL,seq64)) return;
  uint32_t sid=static_cast<uint32_t>(sid64),seq=static_cast<uint32_t>(seq64);
  const char* cmd=fields[3];
  // Only uppercase letters and underscore can be echoed into a response.
  for (const char* p=cmd;*p;++p) if ((*p<'A'||*p>'Z')&&*p!='_') return;
  if (strlen(cmd)>16) return;
  bool safety=strcmp(cmd,"STOP")==0||strcmp(cmd,"DISARM")==0||strcmp(cmd,"ESTOP")==0;
  if (safety && count==4) {
    State next=(state_==ESTOP || strcmp(cmd,"ESTOP")==0) ? ESTOP : (state_==FAULT?FAULT:DISARMED);
    stop(next);reply(sid,seq,"ACK",cmd);return;
  }
  bool hello=strcmp(cmd,"HELLO")==0 && count==4;
  if (hello) {
    if (enabled_) {reply(sid,seq,"ERR",cmd,"BUSY");return;}
    if (sid==retired_session_) {reply(sid,seq,"ERR",cmd,"SESSION");return;}
    if (sid==session_ && seq==last_seq_ && strcmp(request,last_request_)==0) {
      sink_.send(cached_reply_);return;
    }
    // HELLO cannot reuse an existing session to rewind the sequence space.
    if (sid==session_ && seq<=last_seq_) {reply(sid,seq,"ERR",cmd,"SEQ");return;}
    session_=sid;last_seq_=0;
  }
  if (sid!=session_ || !session_) {reply(sid,seq,"ERR",cmd,"SESSION");return;}
  if (seq<=last_seq_) {
    if (seq==last_seq_ && strcmp(request,last_request_)==0 && cached_reply_[0]) sink_.send(cached_reply_);
    else reply(sid,seq,"ERR",cmd,"SEQ");
    return;
  }
  last_seq_=seq;strcpy(last_request_,request);
  const char* error=0;
  if (hello || (strcmp(cmd,"STATUS")==0 && count==4)) {
    // Read-only; never refresh a motion watchdog.
  } else if (strcmp(cmd,"ENC")==0 && count==4) {
    if (!sink_.reportEncoders()) error="UNBOUND";
    else {
      // A new sequence is required to sample again. An ACK alone is not replayable.
      cached_reply_[0]=0;
      reply(sid,seq,"ACK",cmd);
      return;
    }
  } else if (strcmp(cmd,"CLEAR")==0 && count==4) {
    if (hal_.estopInput()||!hal_.healthy()) error="INTERLOCK";
    else stop(DISARMED);
  } else if (strcmp(cmd,"ARM")==0 && count==4) {
    if (state_!=DISARMED) error="STATE";
    else if (!hal_.ready()) error="UNBOUND";
    else if (!hal_.healthy()||hal_.estopInput()) error="INTERLOCK";
    else if (!hal_.enable(true)) {stop(FAULT);error="HAL";}
    else {enabled_=true;state_=ARMED;lease_ms_=now;}
  } else if (strcmp(cmd,"KEEP")==0 && count==4) {
    if (state_==ARMED||state_==JOGGING||state_==PWM_TEST) lease_ms_=now;
    else error="STATE"; // KEEP must not prolong an old continuous velocity command.
  } else if (strcmp(cmd,"WHEELS")==0 && count==6) {
    int64_t left,right;
    if (!number(fields[4],-200,200,left)||!number(fields[5],-200,200,right)) error="RANGE";
    else if (!enabled_ || state_==JOGGING || state_==PWM_TEST) error="STATE";
    else if (!hal_.rates(static_cast<int32_t>(left),static_cast<int32_t>(right))) {stop(FAULT);error="HAL";}
    else {state_=(left||right)?RUNNING:ARMED;lease_ms_=now;}
  } else if (strcmp(cmd,"JOG")==0 && count==7) {
    int64_t axis,pulses,rate;
    if (!number(fields[4],0,1,axis)||!number(fields[5],-200,200,pulses)||pulses==0||
        !number(fields[6],1,200,rate)||((pulses<0?-pulses:pulses)*1000>rate*1500)) error="RANGE";
    else if (!enabled_ || state_!=ARMED || hal_.busy()) error="STATE";
    else if (!hal_.jog(static_cast<uint8_t>(axis),static_cast<int32_t>(pulses),static_cast<uint16_t>(rate))) {
      stop(FAULT);error="HAL";
    } else {state_=JOGGING;jog_start_ms_=lease_ms_=now;}
  } else if (strcmp(cmd,"PWM")==0 && count==7) {
    int64_t axis,duty,duration;
    if (!number(fields[4],0,3,axis)||!number(fields[5],-200,200,duty)||duty==0||
        !number(fields[6],1,400,duration)) error="RANGE";
    else if (!enabled_ || state_!=ARMED || hal_.busy()) error="STATE";
    else if (!hal_.pwm(static_cast<uint8_t>(axis),static_cast<int16_t>(duty),static_cast<uint16_t>(duration))) {
      stop(FAULT);error="HAL";
    } else {state_=PWM_TEST;pwm_timeout_ms_=500;jog_start_ms_=lease_ms_=now;}
  } else if (strcmp(cmd,"PWM_PAIR")==0 && count==7) {
    int64_t left,right,duration;
    if (!number(fields[4],-200,200,left)||!number(fields[5],-200,200,right)||(!left&&!right)||
        !number(fields[6],1,400,duration)) error="RANGE";
    else if (!enabled_ || state_!=ARMED || hal_.busy()) error="STATE";
    else if (!hal_.pwmPair(static_cast<int16_t>(left),static_cast<int16_t>(right),static_cast<uint16_t>(duration))) {
      stop(FAULT);error="HAL";
    } else {state_=PWM_TEST;pwm_timeout_ms_=500;jog_start_ms_=lease_ms_=now;}
  } else if (strcmp(cmd,"PWM_FOUR")==0 && count==9) {
    int64_t m1,m2,m3,m4,duration;
    if (!number(fields[4],-PWM_FOUR_MAX,PWM_FOUR_MAX,m1)||!number(fields[5],-PWM_FOUR_MAX,PWM_FOUR_MAX,m2)||
        !number(fields[6],-PWM_FOUR_MAX,PWM_FOUR_MAX,m3)||!number(fields[7],-PWM_FOUR_MAX,PWM_FOUR_MAX,m4)||(!m1&&!m2&&!m3&&!m4)||
        !number(fields[8],1,PWM_FOUR_DURATION_MAX,duration)) error="RANGE";
#ifdef J1_PWM_FOUR_PAIRED
    else if (m1!=m2 || m3!=m4) error="PAIR";
#endif
    else if (!enabled_ || state_!=ARMED || hal_.busy()) error="STATE";
    else if (!hal_.pwmFour(static_cast<int16_t>(m1),static_cast<int16_t>(m2),static_cast<int16_t>(m3),static_cast<int16_t>(m4),static_cast<uint16_t>(duration))) {
      stop(FAULT);error="HAL";
    } else {
      state_=PWM_TEST;
      pwm_timeout_ms_=duration>400 ? static_cast<uint16_t>(duration+100) : 500;
      jog_start_ms_=lease_ms_=now;
    }
  } else error="COMMAND";
  if (error) reply(sid,seq,"ERR",cmd,error,true);
  else reply(sid,seq,"ACK",cmd,0,true);
}
}
