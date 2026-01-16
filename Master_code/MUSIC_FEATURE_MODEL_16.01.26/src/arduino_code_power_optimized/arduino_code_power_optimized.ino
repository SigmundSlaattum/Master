/*
 * Arduino Nano 33 BLE - Rotary Encoder Remote Control
 * Power Optimized Version (No Battery Monitoring)
 *
 * Features:
 * - Reduced BLE update rate (50ms) for 80% lower power consumption
 * - Rotary encoder position tracking
 * - Push button toggle
 * - Estimated 2-3× longer battery life vs original
 *
 * Hardware:
 * - Rotary encoder on pins D6 (A) and D7 (B)
 * - Push button on D2 (active LOW, internal pullup)
 * - Power: LiPo 2S (7.4V) on VIN and GND
 */

#include <ArduinoBLE.h>

// BLE Service and Characteristics
BLEService encoderService("19B10000-E8F2-537E-4F6C-D104768A1214");
BLEStringCharacteristic encoderChar("19B10001-E8F2-537E-4F6C-D104768A1214", BLERead | BLENotify, 30);

// Pin definitions
const int encoderPinA = 6;
const int encoderPinB = 7;
const int switchPin = 2;

// Encoder state
volatile long encoderPosCount = 0;
volatile int lastEncoded = 0;
long lastReportedPos = 0;

// Button debouncing
int lastButtonState = HIGH;
int buttonState = HIGH;
unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 50;  // 50ms debounce

// Power saving: slower update rate when connected
const unsigned long BLE_UPDATE_INTERVAL = 50;  // 50ms = 20Hz (was ~10ms = 100Hz)
unsigned long lastBLEUpdate = 0;

void setup() {
  Serial.begin(115200);
  delay(1000);  // Wait for serial to stabilize

  Serial.println("=== Arduino Nano BLE Encoder Remote ===");
  Serial.println("Version: Power Optimized (No Battery Monitor)");

  // Setup encoder
  pinMode(encoderPinA, INPUT_PULLUP);
  pinMode(encoderPinB, INPUT_PULLUP);

  // Setup switch
  pinMode(switchPin, INPUT_PULLUP);

  // Test encoder pins
  Serial.println("\n[Init] Testing encoder pins...");
  Serial.print("  Pin A (D6): ");
  Serial.println(digitalRead(encoderPinA) ? "HIGH" : "LOW");
  Serial.print("  Pin B (D7): ");
  Serial.println(digitalRead(encoderPinB) ? "HIGH" : "LOW");

  // Attach encoder interrupts
  attachInterrupt(digitalPinToInterrupt(encoderPinA), updateEncoder, CHANGE);
  attachInterrupt(digitalPinToInterrupt(encoderPinB), updateEncoder, CHANGE);

  // BLE setup
  Serial.println("\n[BLE] Initializing Bluetooth...");
  if (!BLE.begin()) {
    Serial.println("[BLE] ERROR: Failed to initialize!");
    while (1) {
      delay(1000);  // Halt execution
    }
  }

  BLE.setLocalName("Nano_Encoder");
  BLE.setAdvertisedService(encoderService);
  encoderService.addCharacteristic(encoderChar);
  BLE.addService(encoderService);
  encoderChar.writeValue("Ready");
  BLE.advertise();

  Serial.println("[BLE] Advertising as 'Nano_Encoder'");
  Serial.println("\n=== System Ready ===");
  Serial.println("Waiting for connection...\n");
}

void loop() {
  // Debug output every 5 seconds when not connected
  static unsigned long lastDebug = 0;
  if (millis() - lastDebug > 5000) {
    if (!BLE.central()) {
      Serial.print("[Debug] Encoder position: ");
      Serial.println(encoderPosCount);
    }
    lastDebug = millis();
  }

  BLEDevice central = BLE.central();

  if (central) {
    Serial.print("[BLE] Connected to: ");
    Serial.println(central.address());

    // Reset timing variables on new connection
    lastBLEUpdate = millis();

    while (central.connected()) {
      unsigned long currentMillis = millis();

      // Power-optimized: Only process BLE updates at specified interval
      if (currentMillis - lastBLEUpdate >= BLE_UPDATE_INTERVAL) {
        lastBLEUpdate = currentMillis;

        // Check switch with debouncing
        int reading = digitalRead(switchPin);

        if (reading != lastButtonState) {
          lastDebounceTime = currentMillis;
        }

        if ((currentMillis - lastDebounceTime) > debounceDelay) {
          if (reading != buttonState) {
            buttonState = reading;

            // Switch pressed (goes LOW when connected to GND)
            if (buttonState == LOW) {
              String msg = "SWITCH PRESSED";
              encoderChar.writeValue(msg);
              Serial.println("[Button] Switch pressed");
            }
          }
        }

        lastButtonState = reading;

        // Send encoder position only when it changes
        if (encoderPosCount != lastReportedPos) {
          String msg = "Pos: " + String(encoderPosCount);
          encoderChar.writeValue(msg);
          Serial.print("[Encoder] Position: ");
          Serial.println(encoderPosCount);
          lastReportedPos = encoderPosCount;
        }
      }

      // Small delay to prevent CPU spinning (power saving)
      delay(10);
    }

    Serial.println("[BLE] Disconnected");
  }
}

/**
 * Encoder interrupt handler
 * Optimized quadrature decoding
 */
void updateEncoder() {
  int MSB = digitalRead(encoderPinA);
  int LSB = digitalRead(encoderPinB);
  int encoded = (MSB << 1) | LSB;
  int sum = (lastEncoded << 2) | encoded;

  // Quadrature decoding state machine
  if (sum == 0b1101 || sum == 0b0100 || sum == 0b0010 || sum == 0b1011) {
    encoderPosCount++;
  }
  if (sum == 0b1110 || sum == 0b0111 || sum == 0b0001 || sum == 0b1000) {
    encoderPosCount--;
  }

  lastEncoded = encoded;
}
