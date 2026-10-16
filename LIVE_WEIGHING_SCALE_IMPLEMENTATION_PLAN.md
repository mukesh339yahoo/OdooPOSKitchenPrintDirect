# Live Weighing Scale Integration (RS-232 / USB) — Implementation Plan

## 1. Executive Summary & Customer Fulfillment

### Customer Requirements:
1. **Direct Cable Link (RS-232 / USB Virtual COM)**: Direct connection between counter scale and the POS terminal PC — **NO Odoo IoT Box required**.
2. **Instant Live Weight Calculation**: Place fruit on scale &rarr; POS reads live weight (kg/g) &rarr; price dynamically calculated &rarr; added to order line.
3. **Frictionless Workflow**: **Zero manual weight typing** and **NO sticker/barcode printing** (direct checkout counter scale).

### Why Our Module Architecture is the Perfect Fit:
The module already runs a local proxy (`app.py`) on the POS terminal machine. We leverage Python's battle-tested serial engine (`pyserial`) inside the proxy to communicate with the scale via COM port / USB, and hook directly into **Odoo 20's native `electronic_scales` registry**.

```mermaid
flowchart LR
    A["Counter Scale (RS-232 / USB)"] -- Serial Data --> B["Ridhira Local Proxy (app.py)"]
    B -- "HTTP / Live Weight API (Port 8068)" --> C["Odoo 20 POS Frontend (Browser)"]
    C -- "Auto-Calculate Price (Weight × $/kg)" --> D["POS Cart / Orderline"]
```

---

## 2. Hardware & Serial Communication Architecture

### Physical Connection:
* **RS-232 DB9 / USB Virtual COM Port** (e.g., FTDI, CH340, Prolific, or native USB serial from scales like CAS, Mettler Toledo, Avery Berkel, Dibal, Torrey, Brecknell, Adam Equipment).
* Supported Baud Rates: 9600 (standard default), 4800, 19200 (8 data bits, 1 stop bit, no/even parity).

### Scale Protocols Supported in Proxy:
1. **Continuous Streaming Mode** (Common in retail scales): Scale continuously emits weight frames (e.g., `ST,GS,+001.250kg\r\n` or `01.250\r\n`).
2. **Polling / Command Mode** (Toledo / NCI / Brecknell): Proxy sends `W\r` or `<ENQ>` inquiry and parses response.
3. **Auto-Detect / Generic ASCII**: Flexible regex parser extracting numeric values and unit identifiers (`kg`, `g`, `lb`).

---

## 3. Detailed Component Architecture

### Component 1: Proxy Scale Engine (`ridhira_pos_kitchen_print_direct/proxy/app.py`)

A non-blocking background daemon thread monitors the serial port and continuously updates the latest scale reading:

1. **`ScaleManager` Class**:
   - Manages connection lifecycle to serial ports (`serial.Serial`).
   - Auto-scans available COM ports using `serial.tools.list_ports`.
   - Parses incoming frames for:
     - `weight` (float, in kg or g)
     - `unit` (`kg`, `g`, `lb`)
     - `is_stable` (boolean: detects scale motion vs stable settle)
     - `is_over_capacity` / `is_under_zero`
     - `tare`
2. **REST Endpoints Exposed by Proxy**:
   * `GET /scale/weight`:
     ```json
     {
       "connected": true,
       "weight": 1.450,
       "unit": "kg",
       "is_stable": true,
       "raw": "ST,GS,+001.450kg",
       "timestamp": 1729051234.56
     }
     ```
   * `POST /scale/tare`: Sends Tare signal to scale or applies software tare.
   * `POST /scale/zero`: Sends Zero command to scale.
   * `GET /scale/status`: Lists connected scale port, baudrate, and signal health.
   * `POST /scale/config`: Saves configured COM port, baudrate, and protocol.

---

### Component 2: Odoo 20 Backend Models & Settings

Extend POS configuration and settings in Odoo 20:

#### 1. Models (`models/res_config_settings.py` & `models/pos_config.py`):
* `scale_enabled` (`fields.Boolean`, default=False): Enable Live Weighing Scale.
* `scale_proxy_url` (`fields.Char`, default='http://localhost:8068'): Local proxy URL.
* `scale_auto_confirm` (`fields.Boolean`, default=True): Auto-add to cart once weight stabilizes (zero-click weighing).
* `scale_polling_interval` (`fields.Integer`, default=200): Polling rate in milliseconds.

#### 2. Views (`views/res_config_settings_views.xml`):
Add a dedicated **"Direct Weighing Scale (No IoT Box)"** section under POS settings:
* Toggle enable/disable.
* Configure auto-confirm threshold on stable weight.
* Test connection button (pings proxy `/scale/status`).

---

### Component 3: Odoo 20 POS Frontend Integration

Odoo 20 has a native scale architecture in `@point_of_sale/app/utils/scale/scale_interface`.

#### 1. Implement `RidhiraProxyScaleInterface`:
Create `static/src/js/scale_proxy_interface.js` extending Odoo 20's `ScaleInterface`:

```javascript
import { ScaleInterface } from "@point_of_sale/app/utils/scale/scale_interface";
import { registry } from "@web/core/registry";

export class RidhiraProxyScaleInterface extends ScaleInterface {
    async connectToScale() {
        if (!this.pos.config.scale_enabled) {
            return false;
        }
        try {
            const res = await fetch(`${this.pos.config.scale_proxy_url}/scale/status`, { signal: AbortSignal.timeout(1500) });
            const data = await res.json();
            return Boolean(data.connected);
        } catch {
            return false;
        }
    }

    async _readWeight() {
        const res = await fetch(`${this.pos.config.scale_proxy_url}/scale/weight`);
        const data = await res.json();
        this.status = {
            SCALE_IN_MOTION: !data.is_stable,
            OVER_CAPACITY: data.is_over_capacity,
            UNDER_ZERO: data.is_under_zero,
        };
        return data.weight;
    }

    get isWeightValid() {
        return super.isWeightValid && !this.status.SCALE_IN_MOTION;
    }
}

// Register with high priority (sequence 10) so it takes precedence over cloud/IoT interfaces
registry.category("electronic_scales").add("ridhira_proxy_scale", RidhiraProxyScaleInterface, { sequence: 10 });
```

#### 2. Auto-Confirm on Stable Weight (Zero-Click Flow):
Patch `handleWeighableProduct` in POS store:
* When a product marked `to_weight = true` (e.g., Bananas) is selected:
  * If `scale_auto_confirm` is active and weight is stable & > 0:
    * It reads the stable weight immediately, sets `values.qty = weight`, and adds it to the cart with the calculated price without interrupting the cashier!
  * If the scale is empty (0.00 kg) or in motion:
    * Opens Odoo's native `ScaleScreen` dialog showing live gross weight, tare, price per kg, and dynamic total price until settled.

---

### Component 4: Proxy Management UI (`index.html`)

Add a dedicated **"Scale"** tab to the local proxy dashboard:
* Dropdown to select COM port (auto-populated with detected COM ports).
* Dropdown for Baudrate (9600, 4800, 19200).
* Dropdown for Protocol (Generic ASCII, CAS PD-II, Toledo/NCI, Avery Berkel).
* **Live Test Display**: Visual ticker showing live weight and `STABLE` / `MOTION` badge so technicians can test the cable connection without opening Odoo.

---

## 5. Cashier User Journey (Zero Sticker, Zero Manual Typing)

```
1. Customer brings 1.25 kg of Apples to checkout counter.
2. Cashier places Apples on the counter scale.
   ↳ Scale sends weight (1.250 kg) to Proxy.
3. Cashier taps [Apples] on Odoo 20 POS screen:
   ↳ POS detects product has `to_weight = true`.
   ↳ POS instantly queries proxy: Weight = 1.250 kg (Status: STABLE).
   ↳ POS calculates: 1.250 kg × $3.00/kg = $3.75.
   ↳ Orderline is created with quantity 1.250 and total $3.75 automatically.
4. Cashier proceeds to payment or weighs next item.
```

---

## 6. File Changes & Implementation Roadmap

| Step | File | Purpose |
| :--- | :--- | :--- |
| **Step 1** | `proxy/app.py` | Add `ScaleManager` thread, serial reader, protocol decoders, and REST endpoints (`/scale/weight`, `/scale/tare`, etc.). |
| **Step 2** | `proxy/templates/index.html` | Add "Weighing Scale" tab with COM port selector, protocol picker, and live weight preview gauge. |
| **Step 3** | `models/pos_config.py` & `res_config_settings.py` | Add fields: `scale_enabled`, `scale_auto_confirm`, `scale_proxy_url`. |
| **Step 4** | `views/res_config_settings_views.xml` | Add configuration UI in POS settings. |
| **Step 5** | `static/src/js/scale_proxy_interface.js` | Implement `RidhiraProxyScaleInterface` registered into `electronic_scales`. |
| **Step 6** | `static/src/js/scale_auto_confirm_patch.js` | Patch weighable product flow for instant one-touch checkout. |
| **Step 7** | `__manifest__.py` | Add new JS files to `point_of_sale._assets_pos`. |
| **Step 8** | `docker_test/` | Test end-to-end in Odoo 20 Docker container with simulated serial scale feed. |

---

## 7. Verification & Test Plan

1. **Virtual Serial Port Testing**:
   - Use `com0com` (Windows) or `socat` (Linux) to create a virtual loopback COM pair (e.g., COM4 <-> COM5).
   - Run a test script emitting realistic CAS/Toledo data streams.
2. **Live Weighing Screen**:
   - Open Odoo POS session in Docker container.
   - Click weighable product &rarr; verify live weight updates in real time.
3. **Price Calculation**:
   - Verify unit price × weight calculates correct decimals according to Odoo currency precision.
4. **Auto-Confirm Mode**:
   - Place weight &rarr; click product &rarr; confirm it enters cart without requiring extra confirmation clicks.
5. **Tare & Zero**:
   - Test tare button adjusts net weight properly while retaining gross weight.
