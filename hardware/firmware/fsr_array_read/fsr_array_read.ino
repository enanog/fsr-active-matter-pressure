// ============================================================================
// PRUEBA SIMPLE DE SENSADO CON 1 CD4051 Y ADC ESTÁNDAR (10-BIT)
// ============================================================================

// --- CONFIGURACIÓN DE PINES ---
const int PIN_A = 11; // Dirección A (LSB)
const int PIN_B = 12; // Dirección B
const int PIN_C = 13; // Dirección C (MSB)

const int PIN_ADC = A0; // Entrada analógica común desde la salida del op-amp

// --- PARÁMETROS DEL CIRCUITO ---
const float V_REF = 5.0;            // Voltaje de referencia del Arduino (5.0V o 3.3V)
const float V_EXC = 0.88;           // Voltaje de excitación (Volts)
const float R_F   = 1000.0;         // Resistencia de realimentación Rf (Ohms)
const float ADC_MAX_SCALE = 1023.0; // Escala máxima ADC de 10 bits (2^10 - 1)

// Prototipos de funciones
void setMuxChannel(byte channel);
float calculateResistance(int rawADC);

void setup() {
  Serial.begin(9600);

  pinMode(PIN_A, OUTPUT);
  pinMode(PIN_B, OUTPUT);
  pinMode(PIN_C, OUTPUT);

  Serial.println("==============================================");
  Serial.println("  INICIANDO PRUEBA LENTA DE FSR (CD4051)     ");
  Serial.println("==============================================");
}

void loop() {
  Serial.println("\n--- NUEVA BARRIDA DE SENSORES (Canales 0 a 7) ---");

  // Recorremos los 8 canales del CD4051
  for (byte channel = 0; channel < 8; channel++) {

    // 1. Seleccionar el canal en el multiplexor
    setMuxChannel(channel);
    delay(50); // Tiempo de estabilización de la señal

    // 2. Leer ADC estándar (0 - 1023)
    int rawADC = analogRead(PIN_ADC);

    // 3. Convertir lectura a resistencia
    float resistencia = calculateResistance(rawADC);

    // 4. Imprimir lecturas en Serial
    Serial.print("Canal CH");
    Serial.print(channel);
    Serial.print(" | ADC: ");
    Serial.print(rawADC);
    Serial.print(" | ");

    if (resistencia >= 39000.0) {
      Serial.println("Estado: IDLE / SIN PRESIÓN");
    } else {
      Serial.print("Resistencia: ");
      Serial.print(resistencia, 0);
      Serial.println(" Ohms");
    }

    // Pausa de 1 segundo entre canales para medir tranquilamente
    delay(1000);
  }

  // Pausa de 3 segundos entre barridas completas
  delay(3000);
}

// Selecciona el canal activo (0 a 7) en los pines A, B, C del CD4051
void setMuxChannel(byte channel) {
  digitalWrite(PIN_A, bitRead(channel, 0)); // Bit 0
  digitalWrite(PIN_B, bitRead(channel, 1)); // Bit 1
  digitalWrite(PIN_C, bitRead(channel, 2)); // Bit 2
}

// Convierte la lectura directa del ADC de 10 bits a la resistencia del FSR
float calculateResistance(int rawADC) {
  // Convertir lectura digital a voltaje de salida (Vout)
  float vOut = (rawADC * V_REF) / ADC_MAX_SCALE;

  // Umbral para evitar división por cero o ruido de pin flotante
  if (vOut < 0.02) {
    return 40000.0; // Resistencia alta por defecto (sensor no presionado)
  }

  // Transferencia del amplificador inversor: Rsensor = (Vexc * Rf) / Vout
  return (V_EXC * R_F) / vOut;
}