# Implementation Plan: SaaS Licensing with Cloudflare Workers (KV)

This plan outlines the steps to transition `OdooPOSKitchenPrintDirect` to a SaaS model using a "License Check" architecture. The proxy server will require a valid API key to process print jobs. The central authority will be a free, highly scalable Cloudflare Worker backed by Cloudflare KV.

## User Review Required
> [!IMPORTANT]
> **API Key Storage Location:** 
> We have two choices on where to configure the API key. 
> **Option A (Recommended):** The user enters the API Key inside the Odoo POS Settings UI. Odoo passes this key to the proxy on every print job. This is the best user experience.
> **Option B:** The user manually types the API Key into the proxy's local setup (e.g. modifying a `config.json` on their Windows PC). This avoids modifying Odoo settings, but is harder for restaurant owners.
> 
> *I have planned for Option A below, as it provides a superior SaaS experience. Please confirm if this is acceptable.*

## Proposed Changes

We will implement this across three distinct components:

---

### 1. Cloudflare Worker (Central License Server)
We will provide you with a standalone `worker.js` script that you can upload to Cloudflare.
- **KV Store:** We will use a Cloudflare KV namespace called `ridhira_odoo_direct_kitchen_print_licenses` to store API keys and their expiration dates.
- **API Endpoint:** The worker will expose a secure HTTPS endpoint (e.g. `POST https://license.yourdomain.workers.dev/verify`).
- **Cryptographic Signature (JWT):** The worker will accept an `api_key`. If valid, it will construct a JSON Web Token (JWT) containing `{"status": "active", "expires_at": "..."}`. The worker will digitally sign this JWT using a private secret key. This prevents users from forging or extending their own licenses. It returns this signed token to the proxy.

---

### 2. Odoo Module (`ridhira_pos_kitchen_print_direct`)

#### [NEW] `models/pos_config.py` & `models/res_config_settings.py`
- We will add a new field `ridhira_kitchen_print_api_key` to the POS configuration.

#### [NEW] `views/res_config_settings_views.xml`
- We will expose this field in the Odoo POS Settings page so users can paste their API Key. We will add a button/link here pointing to your billing website (e.g., Stripe) so they can purchase the subscription.

#### [MODIFY] `static/src/js/pos_print_override.js`
- **Inject API Key:** We will modify `EpsonPrinter.prototype.printReceipt` and `HWPrinter.prototype.sendAction` to include the `ridhira_kitchen_print_api_key` in the JSON RPC payload sent to the proxy.
- **Error Handling:** We will update `sendAction` to catch specific "License Expired" errors returned by the proxy. When caught, we will use Odoo's UI framework to show a large red Error Popup: *"Kitchen Print Failed: Your Proxy Subscription has expired. Please visit billing.yourdomain.com."*

---

### 3. Local Proxy (`proxy/app.py`)

#### [MODIFY] `proxy/app.py`
- **Cache Table:** We will update `init_db()` to create a new `license_cache` table in the SQLite database to store the validation status.
- **Validation Logic:** We will intercept the `/hw_proxy/default_printer_action` and `/hw_proxy/open_cashbox` routes. 
    1. Extract the `api_key` from the Odoo request payload.
    2. Read the local `license.key` file (or `license_cache` table) where the signed JWT is stored.
    3. **Cryptographic Verification:** The proxy will mathematically verify the JWT's signature. If the signature is invalid (meaning the user tampered with the file to change the date to 2099), the license is rejected.
    4. **Offline Mode:** If the signature is valid and the current date is **before the exact `expires_at` date** inside the token, allow the print immediately. We will **never make a network request** as long as this local token is valid.
    5. **The Renewal:** If the cache is missing or the current date has passed the `expires_at` date, the proxy deletes the local token and makes a single HTTPS request to the Cloudflare Worker to fetch a new signed JWT for the next month.
    6. If the Cloudflare Worker says "Expired" (or the payment failed), we immediately reject the print job and return a custom JSON-RPC error back to Odoo.

## Verification Plan

### Manual Verification
1. **Cloudflare Simulation:** We will create a dummy HTTP server locally to simulate the Cloudflare Worker returning "active" and "expired" statuses.
2. **Odoo UI Testing:** We will enter a fake API key in Odoo settings, trigger a kitchen print, and verify that Odoo correctly routes the key to the proxy.
3. **Expiration Handling:** We will force the proxy to receive an "expired" response and verify that the Odoo UI displays the correct Error Popup to the cashier instead of silently failing.
4. **Offline Resilience:** We will disconnect the proxy from the internet (after initial validation) and verify that printing continues successfully using the local cache.
