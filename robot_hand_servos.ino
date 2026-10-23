/*
  robot_hand_servos.ino  -  Controls 10 servos from Python gesture commands
  =========================================================================

  LIBRARY:  Servo (built into the Arduino IDE - nothing to install)
  BOARD:    Arduino Uno / Nano (the Servo library supports up to 12 servos on them)

  SERIAL PROTOCOL (9600 baud, one byte per command):
      'O'  -> open hand   (prints "Servos opening")
      'C'  -> close hand  (prints "Servos closing")

  WIRING
      Servo signal wires -> pins 2..11 (pins 0 and 1 are used by USB serial)
      Servo power (red)   -> EXTERNAL 5-6 V supply (NOT the Arduino 5V pin!)
      Servo ground        -> external supply GND  AND  Arduino GND (common ground)
      Tip: add a 470-1000 uF capacitor across the servo supply.
      Ten servos can draw several amps when moving - use a 5V supply of 5A or more.

  SMOOTH MOTION
      Servos don't jump to the target. Every UPDATE_INTERVAL_MS each servo moves a
      little toward its target with easing (fast in the middle, gentle at the end),
      and servos start one after another (STAGGER_MS) like fingers - this also
      avoids a big current spike from all 10 starting at once.

  ADDING A GESTURE
      1. Define a new pose array (10 angles) below.
      2. Add one line to GESTURES[] with its command letter and message.
      3. Map the same letter in mediator_bridge.py (GESTURE_COMMANDS).
*/

#include <Servo.h>

// ============================== SETTINGS ====================================
const unsigned long BAUD_RATE = 9600;          // must match mediator_bridge.py
const uint8_t NUM_SERVOS = 10;
const uint8_t SERVO_PINS[NUM_SERVOS] = {2, 3, 4, 5, 6, 7, 8, 9, 10, 11};

// Pulse range of your servos in microseconds (544-2400 suits most hobby servos)
const int SERVO_MIN_US = 544;
const int SERVO_MAX_US = 2400;

// Poses: target angle (0-180) for each of the 10 servos.
// If a servo is mounted mirrored, swap its two values (e.g. open=170, closed=10).
// Tune these so your fingers don't push against their mechanical limits.
const uint8_t POSE_OPEN  [NUM_SERVOS] = { 10,  10,  10,  10,  10,  10,  10,  10,  10,  10};
const uint8_t POSE_CLOSED[NUM_SERVOS] = {170, 170, 170, 170, 170, 170, 170, 170, 170, 170};

// Smoothness tuning
const unsigned long UPDATE_INTERVAL_MS = 15;   // motion update rate (~66 Hz)
const float EASE         = 0.10f;              // fraction of remaining distance per update
const float MAX_STEP_DEG = 3.0f;               // top speed: 3 deg / 15 ms = 200 deg/s
const float MIN_STEP_DEG = 0.35f;              // so motion always finishes
const unsigned long STAGGER_MS = 35;           // delay between each servo's start

// Gesture table: command letter -> pose -> message printed back to Python
struct Gesture {
  char cmd;
  const uint8_t* pose;
  const char* message;
};

const Gesture GESTURES[] = {
  {'O', POSE_OPEN,   "Servos opening"},
  {'C', POSE_CLOSED, "Servos closing"},
  // {'P', POSE_PEACE, "Servos peace sign"},   // <- example of a future gesture
};
const uint8_t NUM_GESTURES = sizeof(GESTURES) / sizeof(GESTURES[0]);

// ============================== STATE =======================================
Servo servos[NUM_SERVOS];
float currentAngle[NUM_SERVOS];
float targetAngle[NUM_SERVOS];
unsigned long startAtMs[NUM_SERVOS];

// ============================== HELPERS =====================================
int angleToMicroseconds(float angle) {
  angle = constrain(angle, 0.0f, 180.0f);
  return SERVO_MIN_US + (int)((angle / 180.0f) * (SERVO_MAX_US - SERVO_MIN_US));
}

// Start moving every servo toward a pose (staggered, like fingers)
void setPose(const uint8_t* pose, const char* message) {
  unsigned long now = millis();
  for (uint8_t i = 0; i < NUM_SERVOS; i++) {
    targetAngle[i] = pose[i];
    startAtMs[i] = now + (unsigned long)i * STAGGER_MS;
  }
  Serial.println(message);
}

// Called every loop(); moves servos a small eased step toward their targets
void updateServos() {
  static unsigned long lastUpdate = 0;
  unsigned long now = millis();
  if (now - lastUpdate < UPDATE_INTERVAL_MS) return;
  lastUpdate = now;

  for (uint8_t i = 0; i < NUM_SERVOS; i++) {
    if ((long)(now - startAtMs[i]) < 0) continue;       // still waiting for its stagger delay

    float diff = targetAngle[i] - currentAngle[i];
    float dist = fabs(diff);
    if (dist < 0.05f) continue;                         // already there

    float step = dist * EASE;
    if (step > MAX_STEP_DEG) step = MAX_STEP_DEG;
    if (step < MIN_STEP_DEG) step = MIN_STEP_DEG;
    if (step > dist) step = dist;                       // never overshoot

    currentAngle[i] += (diff > 0) ? step : -step;
    servos[i].writeMicroseconds(angleToMicroseconds(currentAngle[i]));
  }
}

// Reads incoming command bytes from Python
void handleSerial() {
  while (Serial.available() > 0) {
    char c = (char)toupper(Serial.read());
    if (c == '\n' || c == '\r' || c == ' ') continue;   // ignore whitespace

    bool known = false;
    for (uint8_t g = 0; g < NUM_GESTURES; g++) {
      if (c == GESTURES[g].cmd) {
        setPose(GESTURES[g].pose, GESTURES[g].message);
        known = true;
        break;
      }
    }
    if (!known) {
      Serial.print("Unknown command: ");
      Serial.println(c);
    }
  }
}

// ============================== ARDUINO =====================================
void setup() {
  Serial.begin(BAUD_RATE);

  // Attach one servo at a time so they don't all draw current at the same moment.
  // Start in the OPEN pose.
  for (uint8_t i = 0; i < NUM_SERVOS; i++) {
    currentAngle[i] = POSE_OPEN[i];
    targetAngle[i]  = POSE_OPEN[i];
    startAtMs[i]    = 0;
    servos[i].attach(SERVO_PINS[i], SERVO_MIN_US, SERVO_MAX_US);
    servos[i].writeMicroseconds(angleToMicroseconds(currentAngle[i]));
    delay(30);
  }

  Serial.println("Arduino ready: 'O' = open, 'C' = close");
}

void loop() {
  handleSerial();   // listen continuously for commands
  updateServos();   // non-blocking smooth motion (no delay() calls)
}
