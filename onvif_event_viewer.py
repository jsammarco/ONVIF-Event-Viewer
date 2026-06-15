#!/usr/bin/env python3
"""
Vanilla Python ONVIF live event viewer with GUI filtering.

No ONVIF libraries.
No third-party dependencies.
Uses only Python standard library.

Default camera:
  IP: 192.168.1.184
  User: onvif
  Pass: onvif
"""

import base64
import datetime as dt
import hashlib
import http.client
import os
import queue
import re
import socket
import threading
import time
import uuid
import urllib.parse
import xml.dom.minidom
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import ttk, messagebox


CAMERA_IP = "192.168.1.184"
ONVIF_USER = "onvif"
ONVIF_PASS = "onvif"

DEVICE_SERVICE_PATH = "/onvif/device_service"

SOAP_ENV = "http://www.w3.org/2003/05/soap-envelope"
WSA = "http://www.w3.org/2005/08/addressing"
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
TDS = "http://www.onvif.org/ver10/device/wsdl"
TEV = "http://www.onvif.org/ver10/events/wsdl"
TT = "http://www.onvif.org/ver10/schema"

DEFAULT_EXCLUDE_TOPICS = {
    "tnsaxis:AdaptiveAudioDetection/LevelData",
    "tnsaxis:SoundPressureLevel/Metrics",
}

ET.register_namespace("s", SOAP_ENV)
ET.register_namespace("wsa", WSA)
ET.register_namespace("wsse", WSSE)
ET.register_namespace("wsu", WSU)
ET.register_namespace("tds", TDS)
ET.register_namespace("tev", TEV)
ET.register_namespace("tt", TT)


def utc_timestamp():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def wsse_username_token(username, password):
    """
    ONVIF WS-Security UsernameToken PasswordDigest.

    PasswordDigest = Base64(SHA1(Nonce + Created + Password))
    """
    created = utc_timestamp()
    nonce = os.urandom(16)
    digest = hashlib.sha1(nonce + created.encode("utf-8") + password.encode("utf-8")).digest()

    return f"""
    <wsse:Security s:mustUnderstand="1">
      <wsse:UsernameToken>
        <wsse:Username>{xml_escape(username)}</wsse:Username>
        <wsse:Password
          Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{base64.b64encode(digest).decode()}</wsse:Password>
        <wsse:Nonce
          EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{base64.b64encode(nonce).decode()}</wsse:Nonce>
        <wsu:Created>{created}</wsu:Created>
      </wsse:UsernameToken>
    </wsse:Security>
    """


def xml_escape(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def soap_envelope(username, password, to_url, action, body_xml, extra_header_xml=""):
    message_id = f"urn:uuid:{uuid.uuid4()}"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope
  xmlns:s="{SOAP_ENV}"
  xmlns:wsa="{WSA}"
  xmlns:wsse="{WSSE}"
  xmlns:wsu="{WSU}"
  xmlns:tds="{TDS}"
  xmlns:tev="{TEV}"
  xmlns:tt="{TT}">
  <s:Header>
    <wsa:Action s:mustUnderstand="1">{action}</wsa:Action>
    <wsa:MessageID>{message_id}</wsa:MessageID>
    <wsa:To s:mustUnderstand="1">{xml_escape(to_url)}</wsa:To>
    {extra_header_xml}
    {wsse_username_token(username, password)}
  </s:Header>
  <s:Body>
    {body_xml}
  </s:Body>
</s:Envelope>
"""


class OnvifSoapClient:
    def __init__(self, ip, username, password, timeout=10):
        self.ip = ip
        self.username = username
        self.password = password
        self.timeout = timeout

    def build_url(self, path):
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"http://{self.ip}{path}"

    def post(self, url, action, body_xml, extra_header_xml=""):
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        envelope = soap_envelope(
            username=self.username,
            password=self.password,
            to_url=url,
            action=action,
            body_xml=body_xml,
            extra_header_xml=extra_header_xml,
        )

        headers = {
            "Content-Type": 'application/soap+xml; charset=utf-8; action="' + action + '"',
            "Content-Length": str(len(envelope.encode("utf-8"))),
            "User-Agent": "VanillaPythonONVIFEventViewer/1.1",
            "Connection": "close",
        }

        if parsed.scheme == "https":
            conn = http.client.HTTPSConnection(host, port, timeout=self.timeout)
        else:
            conn = http.client.HTTPConnection(host, port, timeout=self.timeout)

        try:
            conn.request("POST", path, envelope.encode("utf-8"), headers)
            resp = conn.getresponse()
            data = resp.read()
            text = data.decode("utf-8", errors="replace")

            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status} {resp.reason}\n{text}")

            return text
        finally:
            conn.close()


class OnvifEventClient:
    def __init__(self, ip, username, password, log_callback):
        self.ip = ip
        self.username = username
        self.password = password
        self.log = log_callback
        self.soap = OnvifSoapClient(ip, username, password)
        self.device_url = self.soap.build_url(DEVICE_SERVICE_PATH)
        self.events_url = None
        self.subscription_reference_headers = ""
        self.unsubscribe_attempted = False
        self.stop_flag = threading.Event()

    def discover_events_service(self):
        body = """
        <tds:GetCapabilities>
          <tds:Category>Events</tds:Category>
        </tds:GetCapabilities>
        """

        action = "http://www.onvif.org/ver10/device/wsdl/GetCapabilities"
        xml = self.soap.post(self.device_url, action, body)

        root = ET.fromstring(xml)
        xaddrs = []

        for elem in root.iter():
            if elem.tag.endswith("XAddr") and elem.text:
                xaddrs.append(elem.text.strip())

        for xaddr in xaddrs:
            if "event" in xaddr.lower():
                self.events_url = xaddr
                break

        if not self.events_url and xaddrs:
            self.events_url = xaddrs[0]

        if not self.events_url:
            # Common fallback. Some cameras do not expose clean XAddr values.
            self.events_url = f"http://{self.ip}/onvif/events_service"

        self.log(f"Events service URL: {self.events_url}")
        return self.events_url

    def get_event_properties(self):
        body = """
        <tev:GetEventProperties/>
        """

        action = "http://www.onvif.org/ver10/events/wsdl/EventPortType/GetEventPropertiesRequest"
        return self.soap.post(self.events_url, action, body)

    def create_pullpoint_subscription(self):
        body = """
        <tev:CreatePullPointSubscription>
          <tev:InitialTerminationTime>PT2M</tev:InitialTerminationTime>
        </tev:CreatePullPointSubscription>
        """

        action = "http://www.onvif.org/ver10/events/wsdl/EventPortType/CreatePullPointSubscriptionRequest"
        xml = self.soap.post(self.events_url, action, body)

        root = ET.fromstring(xml)

        address = None
        reference_headers = []

        subscription_ref = None

        for elem in root.iter():
            if local_name(elem.tag) == "SubscriptionReference":
                subscription_ref = elem
                break

        if subscription_ref is not None:
            for child in list(subscription_ref):
                lname = local_name(child.tag)

                if lname == "Address" and child.text:
                    address = child.text.strip()

                elif lname == "ReferenceParameters":
                    # WS-Addressing rule:
                    # each child of ReferenceParameters must be copied into
                    # the SOAP Header of later PullMessages requests.
                    for ref_child in list(child):
                        reference_headers.append(
                            ET.tostring(ref_child, encoding="unicode", short_empty_elements=True)
                        )

        if not address:
            # Fallback to first absolute Address in the response.
            for elem in root.iter():
                if local_name(elem.tag) == "Address" and elem.text:
                    text = elem.text.strip()
                    if text.startswith("http://") or text.startswith("https://"):
                        address = text
                        break

        if not address:
            address = self.events_url

        self.subscription_url = address
        self.subscription_reference_headers = "\n".join(reference_headers)

        self.log(f"Subscription URL: {self.subscription_url}")

        if self.subscription_reference_headers:
            self.log(f"Captured subscription reference headers:\n{self.subscription_reference_headers}")
        else:
            self.log("No subscription reference headers found in CreatePullPointSubscription response.")

        return self.subscription_url

    def pull_messages_once(self):
        body = """
        <tev:PullMessages>
          <tev:Timeout>PT2S</tev:Timeout>
          <tev:MessageLimit>50</tev:MessageLimit>
        </tev:PullMessages>
        """

        action = "http://www.onvif.org/ver10/events/wsdl/PullPointSubscription/PullMessagesRequest"

        return self.soap.post(
            self.subscription_url,
            action,
            body,
            extra_header_xml=self.subscription_reference_headers,
        )

    def unsubscribe(self):
        if not self.subscription_url:
            return

        if self.unsubscribe_attempted:
            return

        self.unsubscribe_attempted = True

        body = """
        <tev:Unsubscribe/>
        """

        action = "http://www.onvif.org/ver10/events/wsdl/SubscriptionManager/UnsubscribeRequest"

        try:
            self.soap.post(
                self.subscription_url,
                action,
                body,
                extra_header_xml=self.subscription_reference_headers,
            )
            self.log("Unsubscribed.")

        except Exception as exc:
            text = str(exc)

            if (
                "ter:ActionNotSupported" in text
                or "Optional action not implemented" in text
                or "The requested action is optional and is not implemented" in text
            ):
                self.log(
                    "Camera does not implement ONVIF Unsubscribe; "
                    "subscription will expire automatically."
                )
                return

            self.log(f"Unsubscribe failed: {exc}")

    def run(self, event_queue):
        try:
            self.discover_events_service()

            try:
                props = self.get_event_properties()
                event_queue.put({
                    "kind": "system",
                    "text": "Fetched event properties.",
                    "raw": props,
                })
            except Exception as exc:
                event_queue.put({
                    "kind": "warning",
                    "text": f"GetEventProperties failed, continuing anyway: {exc}",
                    "raw": "",
                })

            self.create_pullpoint_subscription()

            while not self.stop_flag.is_set():
                try:
                    xml = self.pull_messages_once()
                    events = parse_notification_messages(xml)

                    if not events:
                        event_queue.put({
                            "kind": "heartbeat",
                            "text": "No event messages in this pull.",
                            "raw": xml,
                        })

                    for ev in events:
                        event_queue.put(ev)

                except socket.timeout:
                    event_queue.put({
                        "kind": "warning",
                        "text": "Socket timeout while pulling messages.",
                        "raw": "",
                    })
                except Exception as exc:
                    event_queue.put({
                        "kind": "error",
                        "text": f"PullMessages error: {exc}",
                        "raw": "",
                    })
                    time.sleep(2)

        finally:
            self.unsubscribe()


def local_name(tag):
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def elem_text(elem):
    return "".join(elem.itertext()).strip()


def tostring(elem):
    return ET.tostring(elem, encoding="unicode", short_empty_elements=True)


def format_xml_for_display(text):
    stripped = text.strip()
    if not stripped or not stripped.startswith("<"):
        return text

    try:
        pretty = xml.dom.minidom.parseString(stripped.encode("utf-8")).toprettyxml(indent="  ")
        return "\n".join(line for line in pretty.splitlines() if line.strip())
    except Exception:
        return text


def parse_notification_messages(xml):
    """
    Extract ONVIF NotificationMessage blocks from PullMessages response.

    Returns list of event dictionaries:
      {
        kind,
        time,
        topic,
        message,
        raw
      }
    """
    results = []

    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return [{
            "kind": "raw",
            "time": "",
            "topic": "",
            "message": "Could not parse XML response.",
            "raw": xml,
        }]

    for node in root.iter():
        if local_name(node.tag) != "NotificationMessage":
            continue

        topic = ""
        event_time = ""
        message_bits = []

        for child in node.iter():
            lname = local_name(child.tag)

            if lname == "Topic":
                topic = elem_text(child)

            elif lname == "UtcTime":
                event_time = child.attrib.get("UtcTime", "") or elem_text(child)

            elif lname in ("SimpleItem", "ElementItem"):
                name = child.attrib.get("Name", "")
                value = child.attrib.get("Value", "")
                if name or value:
                    message_bits.append(f"{name}={value}")

        raw = tostring(node)
        message = "; ".join(message_bits) if message_bits else elem_text(node)

        results.append({
            "kind": "event",
            "time": event_time,
            "topic": topic,
            "message": message,
            "raw": raw,
        })

    return results


class EventViewerGui:
    def __init__(self, root):
        self.root = root
        self.root.title("Vanilla Python ONVIF Live Event Viewer")
        self.root.geometry("1200x720")

        self.event_queue = queue.Queue()
        self.all_events = []
        self.client = None
        self.worker = None

        self.ip_var = tk.StringVar(value=CAMERA_IP)
        self.user_var = tk.StringVar(value=ONVIF_USER)
        self.pass_var = tk.StringVar(value=ONVIF_PASS)
        self.filter_var = tk.StringVar(value="")
        self.regex_var = tk.BooleanVar(value=False)
        self.case_var = tk.BooleanVar(value=False)
        self.autoscroll_var = tk.BooleanVar(value=True)
        self.exclude_noise_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Disconnected")

        self.build_gui()
        self.root.after(200, self.process_queue)

    def build_gui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top, text="IP").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.ip_var, width=18).pack(side=tk.LEFT, padx=(4, 10))

        ttk.Label(top, text="User").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.user_var, width=14).pack(side=tk.LEFT, padx=(4, 10))

        ttk.Label(top, text="Password").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.pass_var, width=14, show="*").pack(side=tk.LEFT, padx=(4, 10))

        self.connect_btn = ttk.Button(top, text="Connect", command=self.connect)
        self.connect_btn.pack(side=tk.LEFT, padx=4)

        self.disconnect_btn = ttk.Button(top, text="Disconnect", command=self.disconnect, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=4)

        ttk.Button(top, text="Clear", command=self.clear_events).pack(side=tk.LEFT, padx=4)

        ttk.Label(top, textvariable=self.status_var).pack(side=tk.RIGHT)

        filter_frame = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        filter_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(filter_frame, text="Filter").pack(side=tk.LEFT)
        filter_entry = ttk.Entry(filter_frame, textvariable=self.filter_var, width=60)
        filter_entry.pack(side=tk.LEFT, padx=(4, 10), fill=tk.X, expand=True)
        filter_entry.bind("<KeyRelease>", lambda _e: self.refresh_table())

        ttk.Checkbutton(filter_frame, text="Regex", variable=self.regex_var, command=self.refresh_table).pack(side=tk.LEFT)
        ttk.Checkbutton(filter_frame, text="Case-sensitive", variable=self.case_var, command=self.refresh_table).pack(side=tk.LEFT, padx=8)
        ttk.Checkbutton(filter_frame, text="Autoscroll", variable=self.autoscroll_var).pack(side=tk.LEFT)
        ttk.Checkbutton(
            filter_frame,
            text="Hide audio metrics",
            variable=self.exclude_noise_var,
            command=self.refresh_table,
        ).pack(side=tk.LEFT, padx=8)

        paned = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        table_frame = ttk.Frame(paned)
        detail_frame = ttk.Frame(paned)

        paned.add(table_frame, weight=3)
        paned.add(detail_frame, weight=2)

        columns = ("time", "kind", "topic", "message")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("time", text="Time")
        self.tree.heading("kind", text="Kind")
        self.tree.heading("topic", text="Topic")
        self.tree.heading("message", text="Message")

        self.tree.column("time", width=190, anchor=tk.W)
        self.tree.column("kind", width=90, anchor=tk.W)
        self.tree.column("topic", width=330, anchor=tk.W)
        self.tree.column("message", width=560, anchor=tk.W)

        yscroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        ttk.Label(detail_frame, text="Raw XML / Details").pack(anchor=tk.W, padx=8, pady=(8, 0))

        detail_container = ttk.Frame(detail_frame)
        detail_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.detail = tk.Text(detail_container, wrap=tk.NONE, height=12)
        detail_y = ttk.Scrollbar(detail_container, orient=tk.VERTICAL, command=self.detail.yview)
        detail_x = ttk.Scrollbar(detail_container, orient=tk.HORIZONTAL, command=self.detail.xview)
        self.detail.configure(yscrollcommand=detail_y.set, xscrollcommand=detail_x.set)

        self.detail.grid(row=0, column=0, sticky="nsew")
        detail_y.grid(row=0, column=1, sticky="ns")
        detail_x.grid(row=1, column=0, sticky="ew")

        detail_container.columnconfigure(0, weight=1)
        detail_container.rowconfigure(0, weight=1)

    def connect(self):
        if self.worker and self.worker.is_alive():
            return

        ip = self.ip_var.get().strip()
        username = self.user_var.get().strip()
        password = self.pass_var.get()

        if not ip or not username:
            messagebox.showerror("Missing details", "IP and username are required.")
            return

        self.client = OnvifEventClient(ip, username, password, self.log)
        self.client.stop_flag.clear()

        self.worker = threading.Thread(
            target=self.client.run,
            args=(self.event_queue,),
            daemon=True,
        )
        self.worker.start()

        self.status_var.set("Connected / listening")
        self.connect_btn.configure(state=tk.DISABLED)
        self.disconnect_btn.configure(state=tk.NORMAL)

    def disconnect(self):
        if self.client:
            self.client.stop_flag.set()

        self.status_var.set("Disconnecting...")
        self.root.after(1000, self.mark_disconnected)

    def mark_disconnected(self):
        self.status_var.set("Disconnected")
        self.connect_btn.configure(state=tk.NORMAL)
        self.disconnect_btn.configure(state=tk.DISABLED)

    def clear_events(self):
        self.all_events.clear()
        self.refresh_table()
        self.set_detail_text("")

    def log(self, text):
        self.event_queue.put({
            "kind": "system",
            "time": utc_timestamp(),
            "topic": "",
            "message": text,
            "raw": text,
        })

    def process_queue(self):
        changed = False

        while True:
            try:
                item = self.event_queue.get_nowait()
            except queue.Empty:
                break

            if "time" not in item:
                item["time"] = utc_timestamp()
            if "topic" not in item:
                item["topic"] = ""
            if "message" not in item:
                item["message"] = item.get("text", "")
            if "raw" not in item:
                item["raw"] = ""

            self.all_events.append(item)
            changed = True

        if changed:
            self.refresh_table()

        self.root.after(200, self.process_queue)

    def event_matches_filter(self, ev):
        topic = ev.get("topic", "")

        # Default noise suppression for high-frequency Axis audio telemetry.
        if self.exclude_noise_var.get() and topic in DEFAULT_EXCLUDE_TOPICS:
            return False

        pattern = self.filter_var.get()

        if not pattern:
            return True

        haystack = "\n".join([
            ev.get("time", ""),
            ev.get("kind", ""),
            ev.get("topic", ""),
            ev.get("message", ""),
            ev.get("raw", ""),
        ])

        if self.regex_var.get():
            flags = 0 if self.case_var.get() else re.IGNORECASE
            try:
                return re.search(pattern, haystack, flags) is not None
            except re.error:
                return False

        if self.case_var.get():
            return pattern in haystack

        return pattern.lower() in haystack.lower()

    def refresh_table(self):
        selected_raw = None
        selected = self.tree.selection()
        if selected:
            selected_raw = self.tree.item(selected[0], "values")

        self.tree.delete(*self.tree.get_children())

        for idx, ev in enumerate(self.all_events):
            if not self.event_matches_filter(ev):
                continue

            msg = ev.get("message", "")
            if len(msg) > 500:
                msg = msg[:500] + "..."

            self.tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(
                    ev.get("time", ""),
                    ev.get("kind", ""),
                    ev.get("topic", ""),
                    msg,
                )
            )

        if self.autoscroll_var.get():
            children = self.tree.get_children()
            if children:
                self.tree.see(children[-1])

    def on_select(self, _event):
        selected = self.tree.selection()
        if not selected:
            return

        idx = int(selected[0])
        ev = self.all_events[idx]

        raw = ev.get("raw", "")
        formatted_raw = format_xml_for_display(raw)

        text = (
            f"Time: {ev.get('time', '')}\n"
            f"Kind: {ev.get('kind', '')}\n"
            f"Topic: {ev.get('topic', '')}\n"
            f"Message: {ev.get('message', '')}\n\n"
            f"Raw XML / Details:\n{formatted_raw}"
        )

        self.set_detail_text(text)

    def set_detail_text(self, text):
        self.detail.delete("1.0", tk.END)
        self.detail.insert("1.0", text)


def main():
    root = tk.Tk()
    app = EventViewerGui(root)

    def on_close():
        if app.client:
            app.client.stop_flag.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
