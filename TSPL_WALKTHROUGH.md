# TSPL Implementation Walkthrough

I have successfully updated the local proxy app to fully support TSPL thermal printers for label printing! Here is a summary of what was accomplished based on the approved implementation plan.

## Changes Made

### 1. TSPL Command Generation (`generate_tspl_commands`)
- Created a new generator function that converts the incoming `BOBA_LABEL_JSON:` payload directly into TSPL format text, completely bypassing the heavy Image raster generation.
- **Dynamic Sizing:** Implemented dynamic scaling that converts pixel sizes (`label_width`, `label_height`) into millimeters (assuming 203 DPI / 8 dots per mm) so that commands like `SIZE 50.0 mm,37.5 mm` are accurately passed to the printer hardware.
- Text, modifiers, sequence tags, and formatting were carefully mapped to standard TSPL `TEXT` parameters using the native printer font for crisp text.

### 2. Dual Connection Support (`print_to_tspl`)
- **Network Support:** The proxy will automatically use an IP network socket (default Port 9100) if an IP address is defined in the printer config.
- **USB / OS Spooler Support:** If the printer lacks an IP address but has a `system_name`, the proxy leverages OS-level queues. On Windows, it uses `win32print` raw data passing; on Mac/Linux, it invokes the standard `lp -o raw` command, bypassing driver image processing.

### 3. File Tracking & Deduplication Updates (`handle_default_printer_action`)
- When a `tspl` printer processes a boba sticker JSON payload, it now writes a lightweight `.json` file to the `print_images` folder instead of a `.png` file.
- The `_worker_loop` queue correctly detects this type and processes it sequentially.
- If a receipt image is sent to a TSPL printer by mistake, it is safely rejected to prevent garbled printouts.

## How to Test

You can begin testing this with your Xprinter XP-T202UA immediately:

1. **Assign the Printer**: Use the `/assign` API endpoint or edit `printers.json` to register the printer with `"type": "tspl"`.

   **Example `printers.json` (Network / Ethernet / Wi-Fi):**
   ```json
   {
       "Boba_Printer_IP": {
           "kitchen": true,
           "type": "tspl",
           "system_name": "Boba_Printer_IP",
           "ip": "192.168.1.100",
           "port": 9100
       }
   }
   ```

   **Example `printers.json` (USB):**
   ```json
   {
       "Boba_Printer_USB": {
           "kitchen": true,
           "type": "tspl",
           "system_name": "Xprinter XP-T202UA",
           "ip": "127.0.0.1",
           "port": 9100
       }
   }
   ```
   *(Note: For USB, ensure the `ip` is set to `127.0.0.1` or omitted so the proxy knows to use the `system_name` via the OS spooler instead of a direct socket).*
2. **Trigger a Print**: Send a boba label from the Odoo POS Kitchen printer module.
3. **Verify**: You should see the proxy terminal logs indicate:
   `[DEBUG] Printer type is TSPL, saving JSON directly...`
   and
   `🖨️ Sending TSPL to network printer [IP]` (or USB). 

The labels should now print significantly faster with sharper text native to the Xprinter hardware!
