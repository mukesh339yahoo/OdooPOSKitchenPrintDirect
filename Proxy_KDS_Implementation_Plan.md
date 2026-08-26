# Proxy-Hosted Queue Display System (KDS) Implementation Plan

## Goal
Implement a cost-effective, simplified Queue Display System directly within the local Python proxy app (`app.py`). This bypasses the need for an expensive Enterprise KDS module or Odoo backend changes. The system will feature:
1. **Staff Screen**: A touch-friendly web page where staff can tap queue numbers to mark them as "Ready".
2. **Customer TV Screen**: A digital display with "Preparing" and "Please Collect" columns, complete with visual jumping animations and a "Ding-Dong" audio chime.

---

## Proposed Changes

### 1. Proxy App Backend (`proxy/app.py`)
We will extend the existing Flask app to act as the KDS server.

#### [MODIFY] `ridhira_pos_kitchen_print_direct/proxy/app.py`
- **Database Schema**: Add a `queue_display` table to `jobs.db` to store `queue_number`, `status` (Preparing/Ready), and `timestamp`.
- **Global Settings**: Update the proxy app's `settings.json` and the `/settings` dashboard to include a new setting: **"Auto-Clear Ready Orders (Minutes)"**. This will allow the user to control exactly how long a number stays in the "Please Collect" column before disappearing.
- **REST API Endpoints**:
  - `POST /api/kds/add`: Accepts a queue number from Odoo POS and inserts it as "Preparing".
  - `POST /api/kds/update`: Updates a queue number to "Ready".
  - `GET /api/kds/state`: Returns a JSON array of the current live queue, automatically filtering out "Ready" orders that have exceeded the auto-clear time limit.
- **UI Routes**:
  - `GET /staff`: Renders `staff.html`.
  - `GET /tv`: Renders `tv.html`.

### 2. Proxy App Frontend (HTML/JS UIs)
We will add two new HTML templates that the Flask proxy will serve over the local network.

#### [NEW] `ridhira_pos_kitchen_print_direct/proxy/templates/staff.html`
- A responsive grid layout for kitchen staff matching the proxy's dark aesthetic.
- Fetches "Preparing" orders via `/api/kds/state`.
- Displays massive, easy-to-tap buttons for each number.
- Tapping a button fires an AJAX request to `/api/kds/update` marking it "Ready".

#### [NEW] `ridhira_pos_kitchen_print_direct/proxy/templates/tv.html`
- **Design Theme**: The TV screen will strictly follow the main Print Proxy Dashboard's **Dark Theme** (`base.html`). It will feature a deep dark slate blue background (`#0f172a`), glassmorphic panels with blurred effects (`backdrop-filter: blur`), crisp white text (`#f8fafc`) for maximum readability from a distance, and vibrant blue/green accents.
- **Layout**: A split-screen UI: Left side "Preparing", Right side "Please Collect". 
- **Sorting**: The latest "Ready" numbers will always appear at the **top** of the "Please Collect" list.
- **Interactivity**: 
  - Uses Javascript polling (e.g., every 2 seconds) to fetch `/api/kds/state`.
  - Detects when a number moves from Preparing to Ready and triggers a CSS animation moving the number.
  - Triggers an embedded HTML5 `<audio>` tag to play a "Ding-Dong" chime when a new number becomes Ready. (Note: Staff will need to tap the screen once in the morning to bypass browser auto-play restrictions).
  - Automatically clears numbers from the screen based on the time limit configured in the proxy settings.

### 3. Odoo POS Integration
Odoo POS needs to secretly ping the Proxy App whenever an order is sent to the kitchen.

#### [MODIFY] `ridhira_pos_kitchen_print_direct/static/src/js/pos_order_patch.js`
- Intercept the `sendOrderInPreparation` function.
- After extracting the `daily_queue_number` (or `tracking_number`), identify the proxy server's IP address from the configured printers.
- Send a silent, asynchronous `fetch` request to `http://[proxy-ip]:9100/api/kds/add` with the order's queue number.
- If an order is voided/cancelled in the POS, send a request to remove it from the KDS.

---

## Verification Plan

### Manual Verification
1. **Proxy Settings Check**: Open the proxy dashboard `/settings` and verify the new "Auto-Clear Ready Orders" input field is present and saves correctly.
2. **Odoo Integration**: Open an Odoo POS session, create an order, and click "Order" (Send to kitchen). 
3. **Staff Screen**: Open `http://localhost:9100/staff` and verify the queue number instantly appears as a button.
4. **TV Screen**: Open `http://localhost:9100/tv`. Click anywhere to allow audio. Verify the rich dark theme and white text look correct.
5. **Workflow Test**: Tap the queue number on the Staff Screen. Verify that on the TV Screen, the number jumps to the "Please Collect" column, appears at the very top of the list, and the Ding-Dong sound plays. Wait for the auto-clear duration to verify the number is removed automatically.
