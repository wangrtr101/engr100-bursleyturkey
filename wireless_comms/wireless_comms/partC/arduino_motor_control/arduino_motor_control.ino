
int topspeed = 255;

// Manual input definitions
#define FORWARD w
#define LEFT a
#define BACK s
#define RIGHT d
#define STOP x

void Set_Speed(unsigned char Left,unsigned char Right)
{
  if (((int)Left)>topspeed) {Left = topspeed;}
  if (((int)Right)>topspeed) {Right = topspeed;}
  
  analogWrite(5,Left);    //Send a speed value (Left = 0-255) to Pin #5 for setting the rotation speed of the two left-side wheels.
  analogWrite(6,Right);   //Send a speed value (Right = 0-255) to Pin #6 for setting the rotation speed of the two right-side wheels.
}

void forward () {
  //go forward
 digitalWrite(7, HIGH);       //set Pin #7 to HIGH and set Pin #8 to LOW, making two left-side wheels rotate forward.
 digitalWrite(8, LOW);
 digitalWrite(9, LOW);        //set Pin #11 to HIGH and set Pin #9 to LOW, making two right-side wheels rotate forward.
 digitalWrite(11, HIGH);
}

void back () {
   //go backward
 digitalWrite(7, LOW);        //set Pin #7 to LOW and set Pin #8 to HIGH, making two left-side wheels rotate backward.
 digitalWrite(8, HIGH);
 digitalWrite(9, HIGH);       //set Pin #11 to LOW and set Pin #9 to HIGH, making two right-side wheels rotate backward.
 digitalWrite(11, LOW);
}

void left () {
  //turn left
 digitalWrite(7, LOW);        //set Pin #7 to LOW and set Pin #8 to HIGH, making two left-side wheels rotate backward.
 digitalWrite(8, HIGH);
 digitalWrite(9, LOW);        //set Pin #11 to HIGH and set Pin #9 to LOW, making two right-side wheels rotate forward.
 digitalWrite(11, HIGH);
}

void right () {
  //turn right
 digitalWrite(7, HIGH);       //set Pin #7 to HIGH and set Pin #8 to LOW, making two left-side wheels rotate forward.
 digitalWrite(8, LOW);
 digitalWrite(9, HIGH);       //set Pin #11 to LOW and set Pin #9 to HIGH, making two right-side wheels rotate backward.
 digitalWrite(11, LOW);
}

void stopcar () {
 //stop
 analogWrite (5, 0);          //set the rotation speed of left-side wheels to "0".
 analogWrite (6, 0);          //set the rotation speed of right-side wheels to "0".
}

void setup() {
  // put your setup code here, to run once:
  pinMode (5, OUTPUT);     //Pins #5, 7, 8 are used for controlling the two left-side wheels.
  pinMode (7, OUTPUT);
  pinMode (8, OUTPUT);

  pinMode (6, OUTPUT);    //Pins #6, 9, 11 are used for controlling the two right-side wheels
  pinMode (9, OUTPUT);
  pinMode (11, OUTPUT);

  Serial.begin(115200);
}

void process_input(char input) {
  switch(input) {
    case 'w':
      forward();
      Set_Speed(150, 150);
      break;

    case 'a':
      left();
      Set_Speed(150, 150);
      break;

    case 's':
      back();
      Set_Speed(150, 150);
      break;

    case 'd':
      right();
      Set_Speed(150, 150);
      break;

    case 'x':
      stopcar();
      break;
  }
}

void loop() {
  // put your main code here, to run repeatedly:
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    char cmd_char = command[0]; // Grab the first character, e.g. "w" in "w\n".
    // Process input, set motion according to WASD/X
    process_input(cmd_char);
  }
}
