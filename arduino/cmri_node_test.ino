void setup() {
  // put your setup code here, to run once:
  pinMode(13,OUTPUT);
  digitalWrite(13,HIGH);
  Serial.begin(9600);
  Serial1.begin(9600);
  while (!Serial);
}

const char SYN='\xff';
const char STX='\x2';
const char ETX='\x3';
const char DLE='\x10';
bool escaped = false;
bool cmd_complete = false;
char cmd[30];
byte pos = 0;
byte cmd_len = 0;
long unsigned last_input_ch = 0;
byte input = 0;

bool must_escape(char c)
{
  return (c==STX) || (c==ETX) || (c==DLE);
}

void send_input()
{
  char answer[]= {SYN,SYN,STX,'B','R','\0','\0','\0','\0','\0','\0','\0'};  // 2 more in case of DLE and null terminated
  byte pos = 5;
  Serial1.print("input=");
  Serial1.print(input);
  if (must_escape((char) input)) {
    answer[pos++]=DLE;
    //Serial1.print(" escaped!");
  }
  Serial1.println();
  answer[pos++]=(char) input;
  pos++; //leave a 0 byte (always 2-bytes anwser for the board inputs)
  //next IOX input byte
  if (must_escape((char) input)) {
    answer[pos++]=DLE;
    //Serial1.print(" escaped!");
  }
  answer[pos++]=(char) input;
  answer[pos++]=ETX;
  Serial1.print("sending: ");
  for (byte i=0;i<pos;i++) {
    Serial.write(answer[i]);
    Serial1.print((byte)(answer[i]),HEX);
    Serial1.print(" ");
  }
  Serial1.println();
  if (millis()>last_input_ch+5000) {
    last_input_ch = millis();
    input++;
  }
}

void show_transmit()
{
  Serial1.print("Transmit received:");
    for (byte i=0;i<cmd_len;i++) {
    Serial1.print((byte)(cmd[i]));
    Serial1.print(" ");
  }
  Serial1.println();
}

void process_cmd()
{
 
  byte add = cmd[0]-65;
  Serial1.print("command processed:");
  for (byte i=0;i<cmd_len;i++) {
    Serial1.print((byte)(cmd[i]));
    Serial1.print(" ");
  }
          Serial1.print("add= ");
          Serial1.println(add);
  if ((cmd_len>1) && (add>0)) {
    switch (cmd[1]) {
      case 'I':  //initialization
        Serial1.println("Initialization!");
        break;
      case 'P':  //poll request
        Serial1.println("Poll request");
        send_input();
        break;
      case 'T':  // Transmit
        show_transmit();
    }
  }
  cmd_complete = false;
  pos = 0;
  cmd_len=0;
}

long unsigned live=0;
// States
const byte  WAIT_FOR_SYNC=0,
            SYNCED=1,
            STARTED=2,
            COMPLETE=3;
            
byte cmd_state=WAIT_FOR_SYNC,nb_SYN=0;
bool cmd_started=false;
bool light=true;
void loop() {
  if (millis()>live+5000) {
 //   Serial1.println("live");
    live=millis();
    digitalWrite(13,light?HIGH:LOW);
    light = !light;
  }
  if (Serial.available()) {
    char c = Serial.read();
/*    Serial1.print("rcved:");
    Serial1.print(c);
    Serial1.print(" ");
    Serial1.println((byte)c);*/
    if (cmd_state==WAIT_FOR_SYNC) {
      if (c==SYN)
        nb_SYN++;
      if (nb_SYN==2) {
        cmd_state = SYNCED;
//        Serial1.println("SYNCED");
      }
      else if (nb_SYN>2)  // malformed go back to first cmd_state
      {
        cmd_state=WAIT_FOR_SYNC;
        nb_SYN = 0;
        Serial1.println("Malformed");
      }
      return;
    }
    if (cmd_state == SYNCED) {
      if (c!=STX) // Malformed
      {
        Serial1.println("Malformed");
        cmd_state=WAIT_FOR_SYNC;
        nb_SYN=0;
      } else {
 //       Serial1.println("STARTED");
        cmd_state = STARTED;
      }
      return;
    }
    if (cmd_state == STARTED) {
      switch (c) {
        case DLE:
          if (escaped) {
            cmd[pos++]=c;
            escaped = false;
          }
          else
            escaped = true;
          break;
        case ETX:
          if (!escaped) {
            cmd_state=COMPLETE;
            cmd_len = pos;
          }
          else {
            cmd[pos++]=ETX;
            escaped = false;
          }
          break;
        case STX:
          if (escaped) {
            cmd[pos++]=c;
            escaped = false;
          } else {//Malformed
            Serial1.println("Malformed");
            cmd_state=WAIT_FOR_SYNC;
            nb_SYN=0;
          }
          break;
        default:
          cmd[pos++]=c;
      }
    }
    if (cmd_state==COMPLETE) {
      process_cmd();
      cmd_state=WAIT_FOR_SYNC;
      nb_SYN=0;
    }
  }
}
