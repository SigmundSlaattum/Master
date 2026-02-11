/*
 * Arduino Nano 33 BLE - Rotary Encoder Remote Control
 * Power Optimized Version with Sleep Mode (No Battery Monitoring)
 *
 * Features:
 * - STOPS data transmission when not connected to BLE
 * - Reduced BLE advertising interval when idle (10x power saving)
 * - Power-efficient polling rate when connected (50ms = 20Hz)
 * - Activity detection via encoder/button interrupts
 * - Rotary encoder position tracking
 * - Push button toggle
 *
 * Power Consumption Estimates:
 * - Active BLE connected: ~7-10mA
 * - Advertising (not connected, active): ~3-5mA
 * - Advertising (not connected, idle): ~1-2mA (reduced interval)
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

// Power saving settings
const unsigned long BLE_UPDATE_INTERVAL = 50;  // 50ms = 20Hz when connected
unsigned long lastBLEUpdate = 0;

// Power saving: idle detection when not connected
const unsigned long IDLE_TIMEOUT = 30000;      // 30 seconds of no activity -> reduce advertising
unsigned long lastActivityTime = 0;
volatile bool activityDetected = false;        // Set by interrupts
bool isIdleMode = false;

// Advertising intervals (in 0.625ms units)
const int ADVERTISING_INTERVAL_ACTIVE = 160;   // 100ms - fast when activity detected
const int ADVERTISING_INTERVAL_IDLE = 1600;    // 1000ms - slow when idle (10x power saving)

void setup() {
  Serial.begin(115200);
  delay(1000);  // Wait for serial to stabilize

  Serial.println("=== Arduino Nano BLE Encoder Remote ===");
  Serial.println("Version: 3.0 (Power Optimized with Idle Mode)");

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
  attachInterrupt(digitalPinToInterrupt(encoderPinA), encoderInterrupt, CHANGE);
  attachInterrupt(digitalPinToInterrupt(encoderPinB), encoderInterrupt, CHANGE);

  // Attach button interrupt
  attachInterrupt(digitalPinToInterrupt(switchPin), buttonInterrupt, FALLING);

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

  // Set connection event handlers
  BLE.setEventHandler(BLEConnected, bleConnectHandler);
  BLE.setEventHandler(BLEDisconnected, bleDisconnectHandler);

  // Start with fast advertising
  setAdvertisingInterval(ADVERTISING_INTERVAL_ACTIVE);
  BLE.advertise();

  Serial.println("[BLE] Advertising as 'Nano_Encoder'");
  Serial.println("\n=== System Ready ===");
  Serial.println("Power saving features enabled:");
  Serial.println("  - No data transmission when not connected");
  Serial.println("  - Idle mode after 30s of no activity");
  Serial.println("  - Reduced advertising interval when idle");
  Serial.println("Waiting for connection...\n");

  lastActivityTime = millis();
}

void loop() {
  // Poll BLE events
  BLE.poll();

  BLEDevice central = BLE.central();

  if (central && central.connected()) {
    // ===== CONNECTED MODE =====
    // Full functionality, send data to central
    handleConnectedMode(central);
  } else {
    // ===== NOT CONNECTED MODE =====
    // Power saving: minimal activity, no data transmission
    handleDisconnectedMode();
  }
}

/**
 * Handle BLE connected state - full functionality
 */
void handleConnectedMode(BLEDevice& central) {
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

/**
 * Handle disconnected state - power saving mode
 * No data transmission, just advertising and waiting for connection
 */
void handleDisconnectedMode() {
  unsigned long currentMillis = millis();

  // Check for activity from interrupts
  if (activityDetected) {
    activityDetected = false;
    lastActivityTime = currentMillis;

    // If we were in idle mode, switch back to active advertising
    if (isIdleMode) {
      isIdleMode = false;
      setAdvertisingInterval(ADVERTISING_INTERVAL_ACTIVE);
      Serial.println("[Power] Activity detected - switching to fast advertising");
    }
  }

  // Check if we should enter idle mode (slow advertising)
  if (!isIdleMode && (currentMillis - lastActivityTime > IDLE_TIMEOUT)) {
    isIdleMode = true;
    setAdvertisingInterval(ADVERTISING_INTERVAL_IDLE);
    Serial.println("[Power] Idle timeout - switching to slow advertising (power save)");
  }

  // Debug output every 10 seconds when not connected
  static unsigned long lastDebug = 0;
  if (currentMillis - lastDebug > 10000) {
    Serial.print("[Status] Not connected | ");
    Serial.print(isIdleMode ? "Idle mode" : "Active mode");
    Serial.print(" | Encoder: ");
    Serial.println(encoderPosCount);
    lastDebug = currentMillis;
  }

  // Longer delay when not connected to save power
  // Interrupts will still trigger for encoder/button
  if (isIdleMode) {
    delay(100);  // 100ms delay in idle mode
  } else {
    delay(50);   // 50ms delay in active mode
  }
}

/**
 * Set BLE advertising interval
 * Lower intervals = faster discovery but more power
 */
void setAdvertisingInterval(int interval) {
  BLE.stopAdvertise();
  BLE.setAdvertisingInterval(interval);
  BLE.advertise();
}

/**
 * BLE connection event handler
 */
void bleConnectHandler(BLEDevice central) {
  Serial.print("[BLE] Connected to: ");
  Serial.println(central.address());

  // Reset to active state
  isIdleMode = false;
  lastActivityTime = millis();
  lastBLEUpdate = millis();
}

/**
 * BLE disconnection event handler
 */
void bleDisconnectHandler(BLEDevice central) {
  Serial.println("[BLE] Disconnected");

  // Reset activity timer
  lastActivityTime = millis();

  // Resume advertising with fast interval initially
  setAdvertisingInterval(ADVERTISING_INTERVAL_ACTIVE);
}

/**
 * Encoder interrupt handler
 * Also marks activity for power management
 */
void encoderInterrupt() {
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
  activityDetected = true;  // Mark activity for power management
}

/**
 * Button interrupt handler
 * Marks activity for power management
 */
void buttonInterrupt() {
  activityDetected = true;  // Mark activity for power management
}
