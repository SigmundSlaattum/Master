/*
 * Arduino Nano 33 BLE - Rotary Encoder Remote Control
 *
 * Features:
 * - Power-optimized BLE communication (50ms update rate when connected)
 * - Battery voltage monitoring with low battery warning (< 7V)
 * - Voltage reporting every 20 seconds
 * - Rotary encoder position tracking
 * - Push button toggle
 *
 * Hardware:
 * - Rotary encoder on pins D6 (A) and D7 (B)
 * - Push button on D2 (active LOW)
 * - Battery voltage divider on A0
 *   (Use voltage divider: Battery+ -> 10kΩ -> A0 -> 4.7kΩ -> GND)
 *   (This scales ~12V down to ~3.3V max for ADC)
 */

#include <ArduinoBLE.h>

// BLE Service and Characteristics
BLEService encoderService("19B10000-E8F2-537E-4F6C-D104768A1214");
BLEStringCharacteristic encoderChar("19B10001-E8F2-537E-4F6C-D104768A1214", BLERead | BLENotify, 50);

// Pin definitions
const int encoderPinA = 6;
const int encoderPinB = 7;
const int switchPin = 2;
const int batteryPin = A0;

// Encoder state
volatile long encoderPosCount = 0;
volatile int lastEncoded = 0;
long lastReportedPos = 0;

// Button debouncing
int lastButtonState = HIGH;
int buttonState = HIGH;
unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 50;  // 50ms debounce

// Battery monitoring configuration
// Voltage divider: R1=10kΩ (high side), R2=4.7kΩ (low side)
// Scaling factor: (R1 + R2) / R2 = 14.7kΩ / 4.7kΩ = 3.128
// ADC reference: 3.3V, 10-bit resolution (0-1023)
const float VOLTAGE_DIVIDER_RATIO = 3.128;  // Adjust based on your actual resistors
const float ADC_REFERENCE_VOLTAGE = 3.3;
const float LOW_BATTERY_THRESHOLD = 7.0;    // Volts
const int ADC_SAMPLES = 10;                  // Number of samples to average

unsigned long lastBatteryCheck = 0;
const unsigned long BATTERY_CHECK_INTERVAL = 20000;  // 20 seconds
bool lowBatteryWarning = false;
float lastVoltage = 0.0;

// Power saving: slower update rate when connected
const unsigned long BLE_UPDATE_INTERVAL = 50;  // 50ms = 20Hz (reduced from ~10ms = 100Hz)
unsigned long lastBLEUpdate = 0;

void setup() {
  Serial.begin(115200);
  delay(1000);  // Wait for serial to stabilize

  Serial.println("=== Arduino Nano BLE Encoder Remote ===");
  Serial.println("Version: 2.0 (Power Optimized)");

  // Setup encoder
  pinMode(encoderPinA, INPUT_PULLUP);
  pinMode(encoderPinB, INPUT_PULLUP);

  // Setup switch
  pinMode(switchPin, INPUT_PULLUP);

  // Setup battery monitoring
  pinMode(batteryPin, INPUT);
  analogReference(AR_DEFAULT);  // 3.3V reference

  // Test encoder pins
  Serial.println("\n[Init] Testing encoder pins...");
  Serial.print("  Pin A (D6): ");
  Serial.println(digitalRead(encoderPinA) ? "HIGH" : "LOW");
  Serial.print("  Pin B (D7): ");
  Serial.println(digitalRead(encoderPinB) ? "HIGH" : "LOW");

  // Attach encoder interrupts
  attachInterrupt(digitalPinToInterrupt(encoderPinA), updateEncoder, CHANGE);
  attachInterrupt(digitalPinToInterrupt(encoderPinB), updateEncoder, CHANGE);

  // Initial battery check
  float voltage = readBatteryVoltage();
  Serial.print("\n[Battery] Initial voltage: ");
  Serial.print(voltage, 2);
  Serial.println("V");

  if (voltage < LOW_BATTERY_THRESHOLD) {
    Serial.println("[Battery] WARNING: Low battery detected!");
    lowBatteryWarning = true;
  }

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
      Serial.print("[Debug] Encoder: ");
      Serial.print(encoderPosCount);
      Serial.print(" | Battery: ");
      Serial.print(readBatteryVoltage(), 2);
      Serial.println("V");
    }
    lastDebug = millis();
  }

  BLEDevice central = BLE.central();

  if (central) {
    Serial.print("[BLE] Connected to: ");
    Serial.println(central.address());

    // Reset timing variables on new connection
    lastBLEUpdate = millis();
    lastBatteryCheck = millis();

    // Send initial battery status
    sendBatteryStatus();

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

      // Battery check every 20 seconds
      if (currentMillis - lastBatteryCheck >= BATTERY_CHECK_INTERVAL) {
        lastBatteryCheck = currentMillis;
        sendBatteryStatus();
      }

      // Small delay to prevent CPU spinning (power saving)
      delay(10);
    }

    Serial.println("[BLE] Disconnected");
  }
}

/**
 * Read battery voltage with averaging for stability
 */
float readBatteryVoltage() {
  long sum = 0;

  // Take multiple samples and average
  for (int i = 0; i < ADC_SAMPLES; i++) {
    sum += analogRead(batteryPin);
    delay(2);  // Small delay between samples
  }

  float avgADC = sum / (float)ADC_SAMPLES;

  // Convert ADC reading to voltage
  // ADC reading (0-1023) -> voltage at pin (0-3.3V) -> actual battery voltage
  float pinVoltage = (avgADC / 1023.0) * ADC_REFERENCE_VOLTAGE;
  float batteryVoltage = pinVoltage * VOLTAGE_DIVIDER_RATIO;

  return batteryVoltage;
}

/**
 * Send battery status via BLE
 */
void sendBatteryStatus() {
  float voltage = readBatteryVoltage();
  lastVoltage = voltage;

  // Check for low battery condition
  bool isLowBattery = (voltage < LOW_BATTERY_THRESHOLD);

  // Send battery warning if threshold crossed
  if (isLowBattery && !lowBatteryWarning) {
    lowBatteryWarning = true;
    String warningMsg = "BATTERY LOW: " + String(voltage, 2) + "V";
    encoderChar.writeValue(warningMsg);
    Serial.print("[Battery] WARNING - Low battery: ");
    Serial.print(voltage, 2);
    Serial.println("V");
  } else if (!isLowBattery && lowBatteryWarning) {
    lowBatteryWarning = false;
    Serial.println("[Battery] Battery level restored");
  }

  // Send regular voltage update
  String voltageMsg = "Battery: " + String(voltage, 2) + "V";
  encoderChar.writeValue(voltageMsg);

  Serial.print("[Battery] Voltage: ");
  Serial.print(voltage, 2);
  Serial.print("V (ADC: ");
  Serial.print(analogRead(batteryPin));
  Serial.println(")");
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
