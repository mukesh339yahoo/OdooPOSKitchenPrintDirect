# Device Binding Implementation Plan

## The Weaknesses of `uuid.getnode()` (MAC Address)

Yes, `uuid.getnode()` is built into Python and officially supports Windows, Mac, and Linux. However, you are very smart to ask about edge cases, because there are several scenarios where it can completely fail and break your licensing flow:

1. **Multiple Network Cards:** If a computer has both Wi-Fi and Ethernet (or a VPN installed), `uuid.getnode()` just grabs one of them. If the user disables their Wi-Fi or unplugs a USB network adapter, the MAC address Python sees might suddenly change. The customer would be locked out of their license just because they switched from Wi-Fi to an Ethernet cable.
2. **MAC Randomization:** Modern operating systems (especially Windows 11 and macOS) often randomize MAC addresses for privacy on public networks. 
3. **The Silent Random Fallback:** If a machine has its network adapters disabled, or if Python lacks the permission to read the network hardware, `uuid.getnode()` does not crash. Instead, it *quietly generates a random ID every single time the script runs*. This means the proxy's Device ID would change every time it restarts, permanently breaking their license!

## The Bulletproof Solution: OS Machine GUID

Because network MAC addresses are volatile, the industry standard for node-locking software is to read the **OS Machine GUID**. 
When Windows, Linux, or macOS is first installed on a computer, the operating system generates a deep, permanent unique identifier for that specific physical machine. 

**Why it's perfect:**
- It **never changes** when you switch networks, unplug Wi-Fi adapters, or reboot.
- It **cannot be copied** by simply zipping up the proxy folder (a pirate would have to clone the customer's entire hard drive).
- It is 100% native to the OS.

### How we read the Machine GUID in Python:
- **Windows:** We read it from the hidden Windows Registry (`HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography\MachineGuid`).
- **Linux:** We read the native `/etc/machine-id` file.
- **macOS:** We run the native Apple command `ioreg -rd1 -c IOPlatformExpertDevice`.

---

## The OS Machine-Locking Architecture

### 1. Add OS Machine ID Helper to `app.py`
We will add a secure helper function that detects the operating system and pulls the true Machine GUID.

```python
import platform
import subprocess

def get_machine_id():
    try:
        os_name = platform.system()
        if os_name == "Windows":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                return winreg.QueryValueEx(key, "MachineGuid")[0]
                
        elif os_name == "Linux":
            with open("/etc/machine-id", "r") as f:
                return f.read().strip()
                
        elif os_name == "Darwin": # macOS
            output = subprocess.check_output(['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice']).decode('utf-8')
            for line in output.split('\n'):
                if 'IOPlatformUUID' in line:
                    return line.split('=')[1].strip().strip('"')
    except Exception as e:
        # Extreme fallback if OS is unrecognizable or permissions fail
        pass
        
    return "UNKNOWN-DEVICE-ID"
```

### 2. The Cloudflare Worker Payload
Just like before, we don't need a hidden `.device_id` file. We just read the permanent OS ID on the fly.

```python
machine_id = get_machine_id()
response = requests.post(LICENSE_SERVER_URL, json={"api_key": api_key, "device_id": machine_id}, timeout=5)

if response.status_code == 200:
    data = response.json()
    if data.get('status') == 'active' and data.get('token'):
        # ... save token to sqlite cache ...
```

## User Review Required

> [!IMPORTANT]
> The OS Machine GUID is the absolute safest way to lock a license to a physical computer without relying on volatile network adapters or easily-copied hidden files. Do you approve of this final robust approach? If so, I will add this code to `app.py`!
