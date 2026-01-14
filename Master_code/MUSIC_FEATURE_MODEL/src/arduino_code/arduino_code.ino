#include <ArduinoBLE.h>

BLEService encoderService("19B10000-E8F2-537E-4F6C-D104768A1214");
BLEStringCharacteristic encoderChar("19B10001-E8F2-537E-4F6C-D104768A1214", BLERead | BLENotify, 30);

const int encoderPinA = 6;
const int encoderPinB = 7;
const int switchPin = 2;  // Switch connected between D2 and GND
const int batteryPin = A0;

volatile long encoderPosCount = 0;
volatile int lastEncoded = 0;
long lastReportedPos = 0;

// Button debouncing
int lastButtonState = HIGH;
int buttonState = HIGH;
unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 50;

void setup() {
  Serial.begin(115200);
  
  // Setup encoder
  pinMode(encoderPinA, INPUT_PULLUP); 
  pinMode(encoderPinB, INPUT_PULLUP);
  
  // Setup switch
  pinMode(switchPin, INPUT_PULLUP);
  
  // Test encoder pins
  Serial.println("Testing encoder pins...");
  Serial.print("Pin A: ");
  Serial.println(digitalRead(encoderPinA));
  Serial.print("Pin B: ");
  Serial.println(digitalRead(encoderPinB));
  
  attachInterrupt(digitalPinToInterrupt(encoderPinA), updateEncoder, CHANGE);
  attachInterrupt(digitalPinToInterrupt(encoderPinB), updateEncoder, CHANGE);
  
  // Setup battery monitoring
  pinMode(batteryPin, INPUT);
  
  // BLE setup
  if (!BLE.begin()) {
    Serial.println("BLE failed!");
    while (1);
  }
  
  BLE.setLocalName("Nano_Encoder");
  BLE.setAdvertisedService(encoderService);
  encoderService.addCharacteristic(encoderChar);
  BLE.addService(encoderService);
  encoderChar.writeValue("Ready");
  BLE.advertise();
  
  Serial.println("System ready - Switch on D2");
}

void loop() {
  // Debug output every second
  static unsigned long lastDebug = 0;
  if (millis() - lastDebug > 1000) {
    Serial.print("Encoder: ");
    Serial.print(encoderPosCount);
    Serial.print("  Battery ADC: ");
    Serial.println(analogRead(batteryPin));
    lastDebug = millis();
  }
  
  BLEDevice central = BLE.central();
  
  if (central) {
    while (central.connected()) {
      
      // Check switch with debouncing
      int reading = digitalRead(switchPin);
      
      if (reading != lastButtonState) {
        lastDebounceTime = millis();
      }
      
      if ((millis() - lastDebounceTime) > debounceDelay) {
        if (reading != buttonState) {
          buttonState = reading;
          
          // Switch pressed (goes LOW when connected to GND)
          if (buttonState == LOW) {
            String msg = "SWITCH PRESSED";
            encoderChar.writeValue(msg);
            Serial.println(msg);
          }
        }
      }
      
      lastButtonState = reading;
      
      // Send encoder position
      if (encoderPosCount != lastReportedPos) {
        String msg = "Pos: " + String(encoderPosCount);
        encoderChar.writeValue(msg);
        Serial.println(msg);
        lastReportedPos = encoderPosCount;
      }
      
      delay(10);
    }
  }
}

void updateEncoder() {
  int MSB = digitalRead(encoderPinA);
  int LSB = digitalRead(encoderPinB);
  int encoded = (MSB << 1) | LSB;
  int sum = (lastEncoded << 2) | encoded;
  
  if(sum == 0b1101 || sum == 0b0100 || sum == 0b0010 || sum == 0b1011) encoderPosCount++;
  if(sum == 0b1110 || sum == 0b0111 || sum == 0b0001 || sum == 0b1000) encoderPosCount--;
  
  lastEncoded = encoded;
}
