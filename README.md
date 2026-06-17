# ONVIF Event Viewer

`ONVIF Event Viewer` is a small desktop GUI for monitoring live ONVIF events from a camera without any third-party dependencies. It uses only the Python standard library and connects directly to the camera's ONVIF SOAP endpoints.

Download the pre-built Windows EXE from the [Release page](https://github.com/jsammarco/ONVIF-Event-Viewer/releases/tag/Release).

<a href="https://github.com/jsammarco/ONVIF-Event-Viewer/blob/main/Screenshot_Dark.jpg" target="_blank" rel="noopener noreferrer">
  <img src="https://github.com/jsammarco/ONVIF-Event-Viewer/blob/main/Screenshot_Dark.jpg?raw=true" alt="ONVIF Event Viewer dark mode screenshot" width="900">
</a>

<a href="https://github.com/jsammarco/ONVIF-Event-Viewer/blob/main/Screenshot.jpg" target="_blank" rel="noopener noreferrer">
  <img src="https://github.com/jsammarco/ONVIF-Event-Viewer/blob/main/Screenshot.jpg?raw=true" alt="ONVIF Event Viewer screenshot" width="900">
</a>

The app:

- Discovers the camera's ONVIF events service
- Creates a pull-point subscription
- Polls for live event notifications
- Displays incoming events in a filterable table
- Shows raw event XML in a readable detail panel with XML syntax coloring
- Remembers the last-used connection settings between launches
- Supports light and dark viewing modes
- Includes menu actions for importing/exporting all events and exporting a selected event's XML

## Requirements

- Python 3.9 or newer recommended
- Network access to the target ONVIF camera
- Valid ONVIF username and password

No external Python packages are required.

## Project Files

- [onvif_event_viewer.py](/C:/Users/jasammarco.ENG/Projects/ONVIF-Event-Viewer/onvif_event_viewer.py) - main application script
- [onvif_event_viewer_settings.json](/C:/Users/jasammarco.ENG/Projects/ONVIF-Event-Viewer/onvif_event_viewer_settings.json) - auto-saved local settings file created after first run/connect
- [LICENSE](/C:/Users/jasammarco.ENG/Projects/ONVIF-Event-Viewer/LICENSE) - GPL-3.0 license text

## Saved Connection Settings

The app starts with built-in defaults:

- IP: `192.168.1.184`
- Username: `onvif`
- Password: `onvif`

After you change any of those settings, the viewer saves them automatically to `onvif_event_viewer_settings.json` next to the script and reloads them automatically on the next launch.

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

## Menu Bar

### File

- `Import All Events...` loads a full event list from a JSON export
- `Export All Events...` writes the current event list to a JSON file
- `Export Selected Event XML...` saves the selected event's XML to an `.xml` file
- `Exit` closes the application

### View

- `Hide XML Preview` collapses the bottom raw XML/details pane
- `Show XML Preview` restores the bottom raw XML/details pane
- `Light Mode` switches the viewer to the light theme
- `Dark Mode` switches the viewer to the dark theme

### Help

- `Web Help` opens the project page at [jsammarco/ONVIF-Event-Viewer](https://github.com/jsammarco/ONVIF-Event-Viewer)
- `About` shows the author/contact card for Consulting Joe

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
- XML syntax coloring for tags, attributes, values, comments, and declarations
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

### Settings Questions

- The app automatically saves connection settings and common UI options as you change them.
- Delete `onvif_event_viewer_settings.json` if you want to reset the remembered connection values.

### Event Export And Import

- Use `File` -> `Export All Events...` to save the current event list to JSON.
- Use `File` -> `Import All Events...` to load a previously exported event list.
- Use `File` -> `Export Selected Event XML...` to save just the selected event's XML payload.

### High Event Volume

- Leave `Hide audio metrics` enabled to suppress noisy audio telemetry if applicable.
- Use plain-text or regex filters to narrow the event list.

## License

This project is licensed under GPL-3.0. See [LICENSE](/C:/Users/jasammarco.ENG/Projects/ONVIF-Event-Viewer/LICENSE).
