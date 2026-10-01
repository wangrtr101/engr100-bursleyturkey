# This script takes in 2 numbers, sends them to the user's ESP32, and prints the result.
# Make sure that the ESP32 is running and flashed prior to running this script.
# Also make sure that your computer is connected to the router's WiFi access point prior to running this script.
import socket
import time

TCP_IP = "192.168.50.225" # Set the last three digits to your ESP32's assigned 3 digit code
TCP_PORT = 5005 # Keep this on port 5005.
TIMEOUT_S = 5 # Timeout is 5 seconds

# START: GSI DEFINED FUNCTIONS. DO NOT ALTER.
# Connect to ESP32 at IP and port. Return connected socket.
def wifi_setup():
    print(f"Connecting to ESP32 at {TCP_IP}:{TCP_PORT}")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT_S)
    s.connect((TCP_IP, TCP_PORT))
    print("Successfully connected to ESP32.")

    return s

def recv_line(sock):
    data = b""
    while True:
        chunk = sock.recv(1)
        if not chunk or chunk == b"\n":
            break
        data += chunk
    return data.decode().strip()

def encode_nums(n1, n2):
    return (f"{n1},{n2}\n").encode('utf-8')

# END: END OF GSI DEFINED FUNCTIONS. DO NOT ALTER.

def compute(sock):
    while True:
        # TODO: Take in two numbers via the command terminal
        n1 = float(input("Enter first number: "))
        n2 = float(input("Enter second number: "))
        # TODO: convert input numbers into a properly terminated string.
        # e.g. n1 = 2 and n2 = 5 becomes "2,5\n"
        # HINT: Are there any functions defined in this script we can use?
        data = encode_nums(n1, n2)
        # Send the data string over to the ESP32 over previously created socket
        print("Sending data: " + str(data))
        sock.sendall(data)

        # TODO: Receive the summed results from the ESP32.
        # HINT: Look at functions defined above. What function would be useful for receiving data?
        print("Results received from ESP32: " + recv_line(sock))

        time.sleep(0.1)

if __name__ == "__main__":
    esp32_sock = wifi_setup()
    compute(esp32_sock)
