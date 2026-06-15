# ONVIF Event Viewer

`ONVIF Event Viewer` is a small desktop GUI for monitoring live ONVIF events from a camera without any third-party dependencies. It uses only the Python standard library and connects directly to the camera's ONVIF SOAP endpoints.

<a href="https://github.com/jsammarco/ONVIF-Event-Viewer/blob/main/Screenshot1.jpg" target="_blank" rel="noopener noreferrer">
  <img src="https://github.com/jsammarco/ONVIF-Event-Viewer/blob/main/Screenshot1.jpg?raw=true" alt="ONVIF Event Viewer screenshot" width="900">
</a>

The app:

- Discovers the camera's ONVIF events service
- Creates a pull-point subscription
- Polls for live event notifications
- Displays incoming events in a filterable table
- Shows raw event XML in a readable detail panel

## Requirements

- Python 3.9 or newer recommended
- Network access to the target ONVIF camera
- Valid ONVIF username and password

No external Python packages are required.

## Project Files

- [onvif_event_viewer.py](/C:/Users/jasammarco.ENG/Projects/ONVIF-Event-Viewer/onvif_event_viewer.py) - main application script
- [LICENSE](/C:/Users/jasammarco.ENG/Projects/ONVIF-Event-Viewer/LICENSE) - GPL-3.0 license text

## Default Connection Settings

The script currently starts with these defaults near the top of the file:

- IP: `192.168.1.184`
- Username: `onvif`
- Password: `onvif`

Update those constants in [onvif_event_viewer.py](/C:/Users/jasammarco.ENG/Projects/ONVIF-Event-Viewer/onvif_event_viewer.py) if you want different startup values.

## Running The App

From the project folder:

```powershell
python .\onvif_event_viewer.py
```

## How To Use

1. Launch the application.
2. Enter the camera IP, ONVIF username, and password.
3. Click `Connect`.
4. Watch events appear in the top table.
5. Select any row to inspect the event details and formatted raw XML in the bottom panel.
6. Click `Disconnect` to stop polling.

## UI Features

### Event Table

The top panel shows:

- `Time`
- `Kind`
- `Topic`
- `Message`

### Filter Bar

Use the filter box to search across:

- event time
- event kind
- topic
- message text
- raw XML/details

Available options:

- `Regex` enables regular expression matching
- `Case-sensitive` makes plain-text or regex searches case-sensitive
- `Autoscroll` keeps the latest visible row in view
- `Hide audio metrics` suppresses noisy high-frequency Axis audio telemetry topics by default

### Detail Panel

The bottom panel displays:

- selected event metadata
- formatted raw XML when the payload is valid XML
- raw text fallback for non-XML messages such as status or error entries

## ONVIF Flow Implemented

The viewer uses this sequence:

1. `GetCapabilities` to discover the Events service endpoint
2. `GetEventProperties` to retrieve camera event metadata
3. `CreatePullPointSubscription` to open a subscription
4. `PullMessages` in a loop to fetch live notifications
5. `Unsubscribe` on shutdown when supported by the camera

If a camera does not implement `Unsubscribe`, the app logs that behavior and lets the subscription expire automatically.

## Notes And Limitations

- This is a polling-based pull-point viewer, not a persistent push receiver.
- Some cameras return vendor-specific topics or message layouts.
- The viewer includes a fallback events service URL of `http://<camera-ip>/onvif/events_service` if discovery does not provide a usable address.
- GUI logging, heartbeats, warnings, and errors are shown in the same event table as camera events.

## Troubleshooting

### No Events Appear

- Confirm the camera supports ONVIF Events and PullPoint subscriptions.
- Verify the IP address, username, and password.
- Check firewall and network routing between the workstation and camera.

### Connection Or SOAP Errors

- Make sure the ONVIF device service is reachable.
- Confirm the camera allows the provided ONVIF credentials.
- Review the detail panel for raw response text and SOAP fault content.

### High Event Volume

- Leave `Hide audio metrics` enabled to suppress noisy audio telemetry if applicable.
- Use plain-text or regex filters to narrow the event list.

## License

This project is licensed under GPL-3.0. See [LICENSE](/C:/Users/jasammarco.ENG/Projects/ONVIF-Event-Viewer/LICENSE).
