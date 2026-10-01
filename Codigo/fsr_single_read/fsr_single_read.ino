// ============================================================================
// FSR RING - AD_RAW, CONDUCTANCE & ENVELOPE (With Sync LED & Button)
// Streams raw average ADC, conductance, and envelope for Teleplot.
// ============================================================================

#include <math.h>

// --- PIN CONFIGURATION ---
const uint8_t PIN_ADC      = A0;
const uint8_t PIN_SYNC_BTN = 2;    // pushbutton to GND, uses internal pull-up
const uint8_t PIN_SYNC_LED = 4;    // LED visible in frame

// --- FRONT-END PARAMETERS ---
const float V_REF      = 3.3f;       // external AREF
const float V_EXC      = 0.7534f;    // excitation voltage
const float R_FEEDBACK = 10000.0f;   // feedback resistor
const float ADC_FS     = 1023.0f;

// Conductance in microsiemens directly from raw ADC average:
const float K_G_US = (V_REF * 1.0e6f) / (ADC_FS * V_EXC * R_FEEDBACK);

// --- TIMING & FILTERING ---
const uint16_t WINDOW_MS = 50;       // 20 Hz output rate
const float ALPHA_ENV    = 0.0250f;  // activity envelope tracking factor

// Minimum conductance clamp [uS] to avoid div-by-zero / log(0) on open circuit
const float G_MIN_US = 1.0e-3f;

// --- STATE: acquisition & envelope ---
uint32_t adcAccum = 0;
uint16_t adcCount = 0;
uint32_t windowStart = 0;
float envG = 0.0f;

// --- STATE: sync ---
bool lastBtnState = HIGH;

void setup() {
  Serial.begin(115200);

  pinMode(PIN_SYNC_BTN, INPUT_PULLUP);
  pinMode(PIN_SYNC_LED, OUTPUT);
  digitalWrite(PIN_SYNC_LED, LOW);

  analogReference(EXTERNAL);         // 3.3 V tied to AREF
  analogRead(PIN_ADC);               // discard first conversion after ref switch

  windowStart = millis();
}

void loop() {
  // --- Sync button: edge-triggered, active LOW ---
  bool btn = digitalRead(PIN_SYNC_BTN);
  if (btn == LOW && lastBtnState == HIGH) {
    digitalWrite(PIN_SYNC_LED, HIGH);
    uint32_t tSync = millis();
    Serial.print(F(">SYNC:")); Serial.print(tSync); Serial.println(F(":1|np"));
  }
  if (btn == HIGH && lastBtnState == LOW) {
    digitalWrite(PIN_SYNC_LED, LOW);   // Turn off LED on release
  }
  lastBtnState = btn;

  // --- Continuous free-running accumulation ---
  adcAccum += analogRead(PIN_ADC);
  adcCount++;

  uint32_t now = millis();
  if (now - windowStart < WINDOW_MS) return;

  float adcAvg = (float)adcAccum / (float)adcCount;
  adcAccum = 0;
  adcCount = 0;
  windowStart = now;

  // Conductance calculation [uS]
  float gs = adcAvg * K_G_US;

  // Envelope tracking
  envG += ALPHA_ENV * (fabs(gs) - envG);

  // Clamp conductance before inverting: avoids Inf/NaN on open circuit
  float gsClamped = (gs > G_MIN_US) ? gs : G_MIN_US;
  float rOhm   = 1.0f / (gsClamped * 1.0e-6f);
  float rLog10 = log10f(rOhm);   // R plotted as log10(ohms)

  // --- TELEPLOT OUTPUT ---
  Serial.print(F(">ADC_RAW:")); Serial.print(now); Serial.print(':');
  Serial.print(adcAvg, 2);      Serial.println(F("|g"));

  Serial.print(F(">G:"));       Serial.print(now); Serial.print(':');
  Serial.print(gs, 3);          Serial.println(F("|g"));

  Serial.print(F(">R:"));       Serial.print(now); Serial.print(':');
  Serial.print(rOhm, 3);        Serial.println(F("|g"));

  Serial.print(F(">R_LOG:"));   Serial.print(now); Serial.print(':');
  Serial.print(rLog10, 4);      Serial.println(F("|g"));

  Serial.print(F(">ENV:"));     Serial.print(now); Serial.print(':');
  Serial.print(envG, 3);        Serial.println(F("|g"));
}