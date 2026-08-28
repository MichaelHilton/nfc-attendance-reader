# Using the reader's serial port from inside the dev container

The board's USB serial port (`/dev/cu.usbserial-*` on macOS, `/dev/ttyUSB*` on
Linux) belongs to the **host**. Docker Desktop on macOS/Windows runs the
container inside a Linux VM and does **not** forward USB devices, so there is no
`devcontainer.json` setting that makes the port appear inside the container.

Instead we bridge it over TCP with `socat`:

```
host machine                          dev container
-----------                          -------------
board  <--USB-->  serial_bridge_host.sh  <--TCP 9600-->  serial_bridge.sh  -->  ./reader-port (PTY)
                                                                                     |
                                                                          python3 sd_download.py --port ./reader-port
```

## One-time setup

- **Host:** install socat — macOS `brew install socat`, Debian/Ubuntu `sudo apt install socat`.
- **Container:** socat is installed by `postCreateCommand`. After pulling this
  change, run **Dev Containers: Rebuild Container** once. (Or just
  `sudo apt-get install -y socat` in the running container.)

## Each session

1. **On the host**, from `software/`:
   ```
   ./serial_bridge_host.sh                       # auto-detect port
   ./serial_bridge_host.sh /dev/cu.usbserial-XXXX 115200 9600
   ```
   Leave it running. Opening the port resets the ESP32 once — that's expected.
   Close the Arduino Serial Monitor first; only one program can hold the port.

2. **In the container**, from `software/`:
   ```
   ./serial_bridge.sh &                          # creates ./reader-port
   ```

3. **Run the tools**, always passing `--port` (auto-detect can't see the PTY):
   ```
   python3 sd_download.py --port ./reader-port --cmd roster
   python3 sd_upload.py roster.csv --port ./reader-port
   python3 reader_test.py --port ./reader-port
   ```

## Limitations

- **Firmware flashing does not work through this bridge.** `esptool` needs to
  toggle the DTR/RTS lines for the ESP32 boot sequence, and `socat` does not
  forward modem control lines. Flash `attendance_reader_PN532.ino` from the host
  (Arduino IDE / `arduino-cli`).
- If the container can't reach `host.docker.internal`, pass the host's LAN IP as
  the first argument to `serial_bridge.sh`.
