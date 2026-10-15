
int topspeed = 255;

#define FORWARD 'w'
#define LEFT 'a'
#define RIGHT 'd'
#define BACK 's'
#define STOP 'x'

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

void setup() {
  // Put your setup code here, to run once:
  pinMode (5, OUTPUT);     // Pins #5, 7, 8 are used for controlling the two left-side wheels.
  pinMode (7, OUTPUT);
  pinMode (8, OUTPUT);

  pinMode (6, OUTPUT);    // Pins #6, 9, 11 are used for controlling the two right-side wheels
  pinMode (9, OUTPUT);
  pinMode (11, OUTPUT);

  Serial.begin(115200);

  stopcar();
}

void process_direction(char direction) {
  switch(direction) {
    case FORWARD: {
      forward();
      break;      
    }

    case LEFT: {
      forward();
      break;
    }

    case RIGHT: {
      forward();
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
  }
}

void loop() {
  // Put your main code here, to run repeatedly:
  while (Serial.available()) {
    String pid_command = Serial.readStringUntil('\n');
    pid_command.trim(); // Remove "\n" endline character

    // If STOP received, then stop the car motors
    if (pid_command == "STOP") {
      stopcar();
      continue;
    }

    // Parse into left/right speeds and direction
    int firstCommaIndex = pid_command.indexOf(',');
    int secondCommaIndex = pid_command.indexOf(',', firstCommaIndex + 1);

    // Process both motor direction and speed
    if (firstCommaIndex > 0 && secondCommaIndex > firstCommaIndex) {
      int leftSpeed = pid_command.substring(0, firstCommaIndex).toInt();
      int rightSpeed = pid_command.substring(firstCommaIndex + 1).toInt();
      char direction = pid_command.substring(secondCommaIndex + 1)[0];

      // Process motor direction
      process_direction(direction);
      Set_Speed(leftSpeed, rightSpeed);
    }
  }
}
