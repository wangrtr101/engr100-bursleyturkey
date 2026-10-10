// Part B: The goal of this code is to receive 2 numbers wirelessly, sum the result, and send the result back to the user's laptop via Wi-Fi.
#include <WiFi.h>

#define port 5005

const char *ssid_STA = "ENGR100-400"; //Enter the router name
const char *password_STA = "notapwd777"; //Enter the router password

IPAddress local_IP(192, 168, 50, 225);//Set the IP address of ESP32 itself
IPAddress gateway(192, 168, 50, 1);   //Set the gateway of the router
IPAddress subnet(255,255,255,0);  //Set the subnet mask for ESP32 itself

WiFiServer server(port);
WiFiClient client;

void WiFiSetup() {
  WiFi.disconnect();
  WiFi.mode(WIFI_STA);

  // Set static IP, gateway, and subnet BEFORE WiFi.begin()
  if (!WiFi.config(local_IP, gateway, subnet)) {
    Serial.println("STA Failed to configure");
  }

  WiFi.begin(ssid_STA, password_STA);

  Serial.print("Connecting to Wi-Fi...");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.println("WiFi connected.");
  Serial.print("ESP32 IP address: ");
  Serial.println(WiFi.localIP());

  server.begin(port);
  WiFi.setAutoReconnect(true);
}

void setup() {
  // put your setup code here, to run once:
  Serial.begin(115200);
  WiFiSetup();
}


void loop() {
  // Accept new clients if none connected
  if (!client || !client.connected()) {
    client = server.available();
    if (client) {
      Serial.println("New client connected!");
      Serial.println("ESP32 Calculator Ready. Send two numbers separated by a comma (e.g., '5,3')");
    }
  }

  // Process input if a client is connected
  if (client && client.connected() && client.available()) {
    /* TODO: Read in the raw input. */
    /* Example input string: 5,4\n */
    String input = client.readStringUntil('\n');
    // Serial.println("Received input: " + raw_input);

    /* TODO: Parse the raw input into 2 different numbers. */
    int commaIndex = input.indexOf(","); /* TODO: How do we find the comma delimiter in this string? */
    if (commaIndex > 0) {
      /* TODO: Convert the substrings into two separate integers. */
      int res = input.substring(0, commaIndex).toInt() + input.substring(commaIndex + 1).toInt();
      Serial.println("Res: " + String(res)); 

      client.println(res);  // Send back result
      client.flush();
    }
    else {
      Serial.println("ERROR: Invalid format. Use 'num1,num2'");
    }
  }
  
}
