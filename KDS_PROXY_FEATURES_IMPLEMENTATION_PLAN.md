# KDS Proxy App Features Implementation Plan

This plan outlines the changes to implement the requested KDS features in the Ridhira Printer Proxy app.

## Proposed Changes

### Proxy App Configuration (`app.py`)
- **[MODIFY]** `app.py`
  - Add `audio_alert_minutes` to the default settings (default to 3 minutes).
  - Add `audio_alert_repeat_seconds` to the default settings (default to 60 seconds).
  - Expose `audio_alert_minutes` and `audio_alert_repeat_seconds` in the `/settings` HTML form to allow users to configure them.
  - Read both settings and pass them to the TV screen template in the `/tv` route.

### Staff Screen (`templates/staff.html`)
- **[MODIFY]** `templates/staff.html`
  - Split the staff screen into two columns:
    1. **Preparing:** Tap to mark as "Ready".
    2. **Ready (Pending Collection):** Tap to mark as "Collected" (this will update the order status to 'Collected').
  - The API call will update the status to 'Collected', which will automatically hide it from both the Staff and TV screens (since both screens only display Preparing/Ready statuses).

### TV Screen (`templates/tv.html`)
- **[MODIFY]** `templates/tv.html`
  - Inject the configured `audio_alert_minutes` and `audio_alert_repeat_seconds` from settings.
  - During the polling interval, check all orders in the "Ready" column.
  - Track when the alert last played for an uncollected order.
  - If `time_elapsed >= audio_alert_minutes`, play the audio alert (using `/static/ding.ogg`).
  - Continue playing the audio alert periodically every `audio_alert_repeat_seconds` as long as the order remains uncollected.

## Verification Plan
- Launch the proxy app locally.
- Adjust the `audio_alert_minutes` to 1 minute in the settings.
- Push an order to "Ready" via the Staff screen.
- Wait 1 minute and verify the TV screen plays the audio alert.
- Click "Collected" on the Staff screen and verify it disappears from both KDS screens.
