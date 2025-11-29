
#include <WiFi.h>  // Use <ESP8266WiFi.h> if using ESP8266
#include <HTTPClient.h>
#include <ArduinoOTA.h>

// Wi-Fi Credentials
const char* ssid = "zenxtox";
const char* password = "himanshu";

// Django Backend URL
const char* serverUrl = "http://10.151.27.167:8000/post-data/";

// Dummy data (temperature and humidity)
float temperature = 25.5;  // Dummy temperature value
float humidity = 60.0;     // Dummy humidity value

void setup() {
  Serial.begin(115200);
  delay(10);

  // Connect to Wi-Fi
  Serial.println("Connecting to Wi-Fi...");
  WiFi.begin(ssid, password);
  reconnectWiFi();

  // Initialize OTA
  ArduinoOTA.setHostname("ESP32-OTA-2");  // Set a unique hostname for OTA updates
  ArduinoOTA.onStart([]() {
    String type = ArduinoOTA.getCommand() == U_FLASH ? "sketch" : "filesystem";
    Serial.println("Start updating " + type);
  });
  ArduinoOTA.onEnd([]() {
    Serial.println("\nUpdate Complete!");
  });
  ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
    Serial.printf("Progress: %u%%\r", (progress * 100) / total);
  });
  ArduinoOTA.onError([](ota_error_t error) {
    Serial.printf("Error[%u]: ", error);
    if (error == OTA_AUTH_ERROR) Serial.println("Auth Failed");
    else if (error == OTA_BEGIN_ERROR) Serial.println("Begin Failed");
    else if (error == OTA_CONNECT_ERROR) Serial.println("Connect Failed");
    else if (error == OTA_RECEIVE_ERROR) Serial.println("Receive Failed");
    else if (error == OTA_END_ERROR) Serial.println("End Failed");
  });
  ArduinoOTA.begin();

  Serial.println("OTA Initialized");
  Serial.println("Ready for updates.");
  Serial.println("Device IP Address: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  // Handle OTA
  ArduinoOTA.handle();

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;

    // Prepare JSON payload with dummy data
    String jsonPayload = String("{\"device_id\": \"06\", \"temperature\": ") +
                         String(temperature) + String(", \"humidity\": ") +
                         String(humidity) + String("}");

    Serial.println("Sending data to server...");
    Serial.println("Payload: " + jsonPayload);  // Print the JSON payload to check for issues

    // Send data to the Django backend
    http.begin(serverUrl);  // Initialize HTTP connection
    http.addHeader("Content-Type", "application/json");  // Specify JSON content type

    int httpResponseCode = http.POST(jsonPayload);

    // Debugging: Print the HTTP response code
    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.println("Response Code: " + String(httpResponseCode));
      Serial.println("Response: " + response);
    } else {
      Serial.println("Error sending data: " + String(httpResponseCode));
    }

    http.end();  // End HTTP connection
  } else {
    Serial.println("Wi-Fi not connected. Attempting to reconnect...");
    reconnectWiFi();
  }

  delay(5000);  // Wait before sending the next data
}

// Function to reconnect Wi-Fi with more detailed output
void reconnectWiFi() {
  int maxRetries = 10;  // Set maximum number of retries
  int attempt = 0;

  while (WiFi.status() != WL_CONNECTED && attempt < maxRetries) {
    attempt++;
    delay(1000);  // Delay between each retry
    Serial.print(".");
    if (attempt == maxRetries) {
      Serial.println("\nFailed to connect to Wi-Fi after 10 attempts.");
    }
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nConnected to Wi-Fi");
    Serial.println("Device IP Address: ");
    Serial.println(WiFi.localIP());  // Print the IP address for diagnostics
  }
}
