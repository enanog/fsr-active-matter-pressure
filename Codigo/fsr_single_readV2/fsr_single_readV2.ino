// ============================================================================
// FSR RING - Oversampled ADC with noise/clipping diagnostics (ATmega328P)
// Free-running ADC in interrupt mode: sampling never stops while Serial prints.
// Streams mean ADC, in-window std, sample count, clip counters, G, R, envelope.
// ============================================================================

#include <math.h>

// --- PIN CONFIGURATION ---
const uint8_t PIN_SYNC_BTN = 2;    // pushbutton to GND, uses internal pull-up
const uint8_t PIN_SYNC_LED = 4;    // LED visible in frame
const uint8_t ADC_CHANNEL  = 0;    // A0

// --- FRONT-END PARAMETERS ---
const float V_REF      = 3.3f;       // external AREF
const float V_EXC      = 0.7534f;    // excitation voltage
const float R_FEEDBACK = 1000.0f;    // feedback resistor (use measured value)
const float ADC_FS     = 1023.0f;

const float K_G_US = (V_REF * 1.0e6f) / (ADC_FS * V_EXC * R_FEEDBACK);

// Pedestal conductance [uS] of a fixed resistor in parallel with the FSR.
// Set to the value MEASURED with the FSR disconnected; 0 if not installed.
const float G_PED_US = 0.0f;

// --- TIMING & FILTERING ---
const uint16_t WINDOW_MS = 50;       // 20 Hz output rate
const float ALPHA_ENV    = 0.0250f;
const float G_MIN_US     = 1.0e-3f;  // clamp before 1/G and log10

// --- SYNC ---
const uint16_t DEBOUNCE_MS   = 20;   // contact must be stable this long
const uint16_t SYNC_PULSE_MS = 5000;  // fixed LED pulse, independent of hold time

// --- ISR ACCUMULATORS ---
// sumSq headroom: 1023^2 * n < 2^32 holds up to n ~ 4100 samples (~425 ms)
volatile uint32_t isrSum   = 0;
volatile uint32_t isrSumSq = 0;
volatile uint16_t isrN     = 0;
volatile uint16_t isrN0    = 0;      // samples stuck at 0    -> front-end floor clipping
volatile uint16_t isrNSat  = 0;      // samples stuck at 1023 -> saturation

ISR(ADC_vect) {
  uint16_t v = ADC;
  isrSum   += v;
  isrSumSq += (uint32_t)v * v;
  isrN++;
  if (v == 0)          isrN0++;
  else if (v >= 1023)  isrNSat++;
}

// --- STATE ---
uint32_t windowStart = 0;
float    envG        = 0.0f;
bool     firstWindow  = true;

// Sync state
bool     btnStable    = HIGH;        // debounced level
bool     btnLastRaw   = HIGH;
uint32_t btnChangeT   = 0;
bool     ledOn        = false;
uint32_t ledOnT       = 0;
bool     ledInWindow  = false;       // LED was on at some point in this window

void adcStartFreeRunning() {
  // REFS1:0 = 00 -> external AREF. Never select AVcc/internal while AREF is driven.
  ADMUX  = (ADC_CHANNEL & 0x0F);
  ADCSRB = 0;                                   // free-running trigger source
  DIDR0  = (1 << ADC_CHANNEL);                  // disable digital buffer on analog pin
  ADCSRA = (1 << ADEN) | (1 << ADATE) | (1 << ADIE)
         | (1 << ADPS2) | (1 << ADPS1) | (1 << ADPS0);  // 125 kHz -> ~9.6 kS/s
  ADCSRA |= (1 << ADSC);
}

void printChannel(const __FlashStringHelper* name, uint32_t t, float value, uint8_t decimals) {
  Serial.print('>'); Serial.print(name); Serial.print(':');
  Serial.print(t); Serial.print(':');
  Serial.print(value, decimals); Serial.println(F("|g"));
}

void setup() {
  Serial.begin(115200);

  pinMode(PIN_SYNC_BTN, INPUT_PULLUP);
  pinMode(PIN_SYNC_LED, OUTPUT);
  digitalWrite(PIN_SYNC_LED, LOW);

  adcStartFreeRunning();
  windowStart = millis();
}

void loop() {
  // --- Sync: debounced press -> fixed-length LED pulse ---
  uint32_t tNow = millis();
  bool raw = digitalRead(PIN_SYNC_BTN);
  if (raw != btnLastRaw) { btnLastRaw = raw; btnChangeT = tNow; }
  if ((tNow - btnChangeT) >= DEBOUNCE_MS && raw != btnStable) {
    btnStable = raw;
    if (btnStable == LOW && !ledOn) {          // press edge (active LOW)
      ledOn = true;
      ledOnT = tNow;
      digitalWrite(PIN_SYNC_LED, HIGH);
      Serial.print(F(">SYNC:")); Serial.print(tNow); Serial.println(F(":1|np"));
    }
  }
  if (ledOn && (tNow - ledOnT) >= SYNC_PULSE_MS) {
    ledOn = false;
    digitalWrite(PIN_SYNC_LED, LOW);
  }
  if (ledOn) ledInWindow = true;

  uint32_t now = millis();
  if (now - windowStart < WINDOW_MS) return;
  windowStart += WINDOW_MS;                     // fixed grid, no cumulative drift

  // --- Atomic snapshot & reset of ISR accumulators ---
  noInterrupts();
  uint32_t sum   = isrSum;   isrSum   = 0;
  uint32_t sumSq = isrSumSq; isrSumSq = 0;
  uint16_t n     = isrN;     isrN     = 0;
  uint16_t n0    = isrN0;    isrN0    = 0;
  uint16_t nSat  = isrNSat;  isrNSat  = 0;
  interrupts();

  if (n == 0) return;
  if (firstWindow) { firstWindow = false; return; }   // discard settling window

  float mean = (float)sum / (float)n;

  // Exact integer variance: (n*sumSq - sum^2) / n^2, avoids float cancellation
  uint64_t num = (uint64_t)n * sumSq - (uint64_t)sum * sum;
  float stdAdc = sqrtf((float)num) / (float)n;

  float gs = mean * K_G_US - G_PED_US;
  envG += ALPHA_ENV * (fabs(gs) - envG);

  float gsClamped = (gs > G_MIN_US) ? gs : G_MIN_US;
  float rOhm   = 1.0f / (gsClamped * 1.0e-6f);
  float rLog10 = log10f(rOhm);

  // --- TELEPLOT OUTPUT ---
  printChannel(F("ADC_RAW"), now, mean,   4);
  printChannel(F("G"),       now, gs,     4);
  printChannel(F("R"),       now, rOhm,   1);
  printChannel(F("R_LOG"),   now, rLog10, 4);
  printChannel(F("ENV"),     now, envG,   3);
  printChannel(F("ADC_STD"), now, stdAdc, 3);
  printChannel(F("N"),       now, n,      0);
  printChannel(F("CLIP0"),   now, n0,     0);
  printChannel(F("CLIPSAT"), now, nSat,   0);
  printChannel(F("LED"),     now, ledInWindow ? 1 : 0, 0);
  ledInWindow = ledOn;                           // carry state into next window
}
