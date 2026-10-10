// Part A: The goal of this section is to send a constant video stream from your ESP32 to your laptop.

#include "esp_camera.h"
#include <WiFi.h>

// Select camera model
#define CAMERA_MODEL_AI_THINKER // Has PSRAM
#include "camera_pins.h"
#define port 5005

const char *ssid_STA = "ENGR100-400"; // Enter the router name
const char *password_STA = "notapwd777"; // Enter the router password

IPAddress local_IP(192, 168, 50, /* TODO */); // Set the IP address of ESP32 itself
IPAddress gateway(192, 168, 50, 1); // Gateway for this device is the AP/Object Detection ESP32's IP Address
IPAddress subnet(255, 255, 255, 0);

WiFiServer server(port);

void startCameraServer();

void cameraServerSetup() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Use QVGA resolution for higher frame rate and lower memory usage
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 12;
  config.fb_count = 1;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;

  // Use PSRAM if available
  if (psramFound()) {
    config.fb_location = CAMERA_FB_IN_PSRAM;
  }
  else {
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

  // Camera init
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    return;
  }
  Serial.println("Camera initialized successfully.");

  // Drop down frame size for higher initial frame rate
  sensor_t * s = esp_camera_sensor_get();
  s->set_framesize(s, FRAMESIZE_QVGA);
  s->set_vflip(s, 0);        // 1-Upside down, 0-No operation
  s->set_hmirror(s, 0);      // 1-Reverse left and right, 0-No operation
}

void WiFiSetup() {
  Serial.println("Connecting as station with static IP...");
  WiFi.disconnect();
  WiFi.mode(WIFI_STA);
  Serial.println(WiFi.config(local_IP, gateway, subnet) ? "Ready" : "Failed!");
  WiFi.begin(ssid_STA, password_STA);

  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.println("WiFi connected.");

  Serial.print("Station IP address = ");
  Serial.println(WiFi.localIP());

  Serial.print("MAC address = ");
  Serial.println(WiFi.macAddress());

  server.begin(port);
  WiFi.setAutoReconnect(true);
}

void setup() {
  // Put your setup code here, to run once:
  Serial.begin(115200);

  // Initialize camera BEFORE WiFi
  cameraServerSetup();

  // Connect to WiFi after camera memory has been allocated
  WiFiSetup();

  // Start camera stream after WiFi is connected
  Serial.println("Starting camera server...");
  startCameraServer();
  Serial.println("Camera server started.");
}

void loop() {
  // Put your main code here, to run repeatedly:
  WiFiClient client = server.available();           // Listen for incoming clients
  if (client) {                                     // If you get a client,
    //Serial.println("Client connected.");
    while (client.connected()) {                    // Loop while the client's connected
      if (client.available()) {                     // If there's bytes to read from the client,
        char direction = client.read();             // Receive manual control character
        Serial.println(direction);
        //Serial.println(client.readStringUntil('%')); // Print it out the serial monitor
        //Serial.print(client.readStringUntil('%'));   // Print the signal stream to the serial port connecting to the microcontroller
        //while(client.read()>0);                      // Clear the wifi receive area cache
      }
    }
    client.stop();                                  // Stop the client connecting.
    Serial.println("Client Disconnected.");
  }
  //delay(10000);
}
