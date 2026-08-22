# Linux Installation Guide for Print Proxy (`app_linux`)

This guide explains how to install and run the standalone Linux binary (`app_linux`) as a background service on a Linux machine using systemd.

## Prerequisites
- A Linux environment (Ubuntu, Debian, CentOS, etc.)
- The compiled `app_linux` executable
- `sudo` access to create a system service

## Step 1: Copy the Binary to the Linux Machine
Upload or copy the `app_linux` binary to your target Linux machine. For example, using SCP:
```bash
scp proxy/dist/app_linux username@linux-server-ip:/home/username/
```

## Step 2: Move the Binary to a Standard Directory
Connect to the Linux machine and move the binary to a directory like `/usr/local/bin` so it's accessible system-wide:
```bash
sudo mv /home/username/app_linux /usr/local/bin/app_linux
```

## Step 3: Make the Binary Executable
Ensure the file has the correct execution permissions:
```bash
sudo chmod +x /usr/local/bin/app_linux
```

## Step 4: Choose How to Run the Proxy

You can run the proxy either manually (for testing or ad-hoc usage) or as a background service (recommended for production).

### Option A: Running Manually

If you only need to run the proxy temporarily or want to see the live output:

1. **Foreground Execution:**
   Simply execute the binary in your terminal:
   ```bash
   /usr/local/bin/app_linux
   ```
   *Note: This will block your terminal, and closing the terminal will stop the proxy.*

2. **Detached Execution (nohup/tmux/screen):**
   If you want it to keep running after closing the terminal without setting up a full service, you can use `nohup`:
   ```bash
   nohup /usr/local/bin/app_linux > proxy.log 2>&1 &
   ```
   To stop it later, you will need to find its process ID (`ps aux | grep app_linux`) and kill it (`kill -9 PID`).

### Option B: Running as a Background Service (Recommended)

To run the proxy in the background and ensure it automatically starts on boot, create a systemd service.

1. Open a new service file using your preferred text editor (e.g., nano):
```bash
sudo nano /etc/systemd/system/kitchenprintproxy.service
```

2. Add the following configuration to the file:
```ini
[Unit]
Description=Odoo POS Kitchen Print Proxy
After=network.target

[Service]
Type=simple
# Change the User to whichever user you want to run the proxy as
User=root
# The command to execute the binary
ExecStart=/usr/local/bin/app_linux
# Automatically restart if it crashes
Restart=on-failure
RestartSec=5
# Set the working directory if your app requires relative files
WorkingDirectory=/usr/local/bin

[Install]
WantedBy=multi-user.target
```

3. Save and close the file.

4. Reload systemd and start the service:
```bash
# Reload the systemd manager configuration
sudo systemctl daemon-reload

# Start the proxy service
sudo systemctl start kitchenprintproxy

# Enable the service to start automatically on system boot
sudo systemctl enable kitchenprintproxy
```

5. Check the status of the service to make sure it's running without issues:
```bash
sudo systemctl status kitchenprintproxy
```

## Step 5: Verify the Installation
You can test the proxy by opening a web browser or using `curl` to access the dashboard:
```bash
curl http://localhost:9100/
```
*(Replace `localhost` with the server's IP address if accessing from a different machine.)*

## Troubleshooting / Logs
If you are running the proxy via systemd, you can view the logs using `journalctl`:
```bash
sudo journalctl -u kitchenprintproxy -f
```
If you ran it manually, check the terminal output or the `proxy.log` file if you used `nohup`.
