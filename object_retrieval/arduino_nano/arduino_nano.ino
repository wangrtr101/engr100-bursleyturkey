#include "DFRobot_DF2301Q.h"
#include <Servo.h>

int topspeed = 255;

#define FORWARD 'w'
#define LEFT 'a'
#define RIGHT 'd'
#define BACK 's'
#define STOP 'x'
// Spin in place (wheels turn opposite ways). Separate from 'a'/'d' because the line-follow
// ESP32 sends 'a'/'d' during normal line following, and those must keep driving forward.
#define SPIN_LEFT 'q'
#define SPIN_RIGHT 'e'

// servo definitions
#define SERVO_PIN 3
#define SERVO_OPEN 0
#define SERVO_CLOSE 90


// Define voice recog
DFRobot_DF2301Q_I2C asr;

// Define claw servo
Servo main_servo;

void Set_Speed(int Left, int Right)
{
  if (((int)Left)>topspeed) {Left = topspeed;}
  if (((int)Right)>topspeed) {Right = topspeed;}
  
  analogWrite(5,Left);    // Send a speed value (Left = 0-255) to Pin #5 for setting the rotation speed of the two left-side wheels.
  analogWrite(6,Right);   // Send a speed value (Right = 0-255) to Pin #6 for setting the rotation speed of the two right-side wheels.
}

void back() {
  // Go forward
  digitalWrite(7, LOW);        // Set Pin #7 to LOW and set Pin #8 to HIGH, making two left-side wheels rotate forward.
  digitalWrite(8, HIGH);
  digitalWrite(9, HIGH);       // Set Pin #11 to LOW and set Pin #9 to HIGH, making two right-side wheels rotate forward.
  digitalWrite(11, LOW);
}

void forward() {
   // Go backward
  digitalWrite(7, HIGH);       // Set Pin #7 to HIGH and set Pin #8 to LOW, making two left-side wheels rotate backward.
  digitalWrite(8, LOW);
  digitalWrite(9, LOW);        // Set Pin #11 to HIGH and set Pin #9 to LOW, making two right-side wheels rotate backward.
  digitalWrite(11, HIGH);
}

void right() {
  // Turn right
  digitalWrite(7, HIGH);       // Set Pin #7 to HIGH and set Pin #8 to LOW, making two left-side wheels rotate backward.
  digitalWrite(8, LOW);
  digitalWrite(9, HIGH);       // Set Pin #11 to LOW and set Pin #9 to HIGH, making two right-side wheels rotate forward.
  digitalWrite(11, LOW);
}

void left() {
  // Turn left
  digitalWrite(7, LOW);        // Set Pin #7 to LOW and set Pin #8 to HIGH, making two left-side wheels rotate forward.
  digitalWrite(8, HIGH);
  digitalWrite(9, LOW);        // Set Pin #11 to HIGH and set Pin #9 to LOW, making two right-side wheels rotate backward.
  digitalWrite(11, HIGH);
}

void stopcar() {
  // Stop
  analogWrite (5, 0);          // Set the rotation speed of left-side wheels to "0".
  analogWrite (6, 0);          // Set the rotation speed of right-side wheels to "0".
}

void process_direction(char direction) {
  switch(direction) {
    case FORWARD: {
      forward();
      break;      
    }

    case LEFT: {
      left();
      break;
    }

    case RIGHT: {
      right();
      break;
    }

    case BACK: {
      back();
      break;
    }

    case STOP: {
      stopcar();
      break;
    }

    case SPIN_LEFT: {
      left();
      break;
    }

    case SPIN_RIGHT: {
      right();
      break;
    }
  }
}

void setup() {
  delay(4000);
  // Put your setup code here, to run once:

  // Voice Recognition Setup - Taken from DFRobot documentation
  Serial.begin(115200);

  // servo setup
  main_servo.attach(SERVO_PIN);
  main_servo.write(SERVO_CLOSE);

  // Serial prints probably get delayed here or don't work
  //  because message forwarding on the esp32 is only during loop 
  //  And theres probably some kind of desync between the esp and nano
  while (!(asr.begin())) {
    Serial.println("Communication with device failed, please check connection"); 
    delay(3000);
  }
  Serial.println("Begin ok!");

    /**
   * @brief Set voice volume
   * @param voc - Volume value(1~7)
   */
  asr.setVolume(6);

  /**
     @brief Set mute mode
     @param mode - Mute mode; set value 1: mute, 0: unmute
  */
  asr.setMuteMode(0);

  /**
     @brief Set wake-up duration
     @param wakeTime - Wake-up duration (0-255)
  */
  asr.setWakeTime(5);

  /**
     @brief Get wake-up duration
     @return The currently-set wake-up period
  */
  uint8_t wakeTime = 0;
  wakeTime = asr.getWakeTime();


  // asr.playByCMDID(1);   // Wake-up command

  /**
     @brief Play the corresponding reply audio according to the ID
     @param CMDID - command word ID
  */
  //asr.playByCMDID(23);  // Command word ID


  // Motor setup
  pinMode (5, OUTPUT);     // Pins #5, 7, 8 are used for controlling the two left-side wheels.
  pinMode (7, OUTPUT);
  pinMode (8, OUTPUT);

  pinMode (6, OUTPUT);    // Pins #6, 9, 11 are used for controlling the two right-side wheels
  pinMode (9, OUTPUT);
  pinMode (11, OUTPUT);

  stopcar();
}

void loop() {
  // Check to see if a voice recognition 
  uint8_t CMDID = asr.getCMDID();
  if (CMDID != 0) {
    switch (CMDID) {
      case 5: // Get me the cup
        Serial.println("cup");
        break;
      case 6: // Get me the banana
        Serial.println("banana");
        break;
      case 7: // Get me the teddy bear
        Serial.println("teddybear");
        break;
      
      case 2: // wake up command ID should be bypassed
        break;

      default: //defaults to cup
        Serial.println("cup");
        break;
    }
  }
  
  // Read motor and claw inputs
  while (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim(); // Remove "\n" endline character

    // TODO: parse servo command
    if (command == "CLOSE"){
      main_servo.write(SERVO_CLOSE);
      continue;
    }

    if (command == "OPEN"){
      main_servo.write(SERVO_OPEN);
      continue;
    }
    
    // If STOP received, then stop the car motors
    if (command == "STOP") {
      stopcar();
      continue;
    }

    // Parse into left/right speeds and direction
    int firstCommaIndex = command.indexOf(',');
    int secondCommaIndex = command.indexOf(',', firstCommaIndex + 1);

    // Process both motor direction and speed
    if (firstCommaIndex > 0 && secondCommaIndex > firstCommaIndex) {
      int leftSpeed = command.substring(0, firstCommaIndex).toInt();
      int rightSpeed = command.substring(firstCommaIndex + 1).toInt();
      char direction = command.substring(secondCommaIndex + 1)[0];

      // Process motor direction
      process_direction(direction);
      Set_Speed(leftSpeed, rightSpeed);
    }
  }
}
