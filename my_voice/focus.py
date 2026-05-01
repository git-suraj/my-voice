from __future__ import annotations

try:
    from AppKit import NSApplicationActivateIgnoringOtherApps, NSRunningApplication, NSWorkspace
except Exception:  # pragma: no cover - AppKit is only available on macOS with PyObjC.
    NSApplicationActivateIgnoringOtherApps = None
    NSRunningApplication = None
    NSWorkspace = None


def frontmost_bundle_id() -> str:
    if NSWorkspace is None:
        return ""
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return ""
    bundle_id = app.bundleIdentifier()
    return str(bundle_id or "")


def activate_bundle_id(bundle_id: str) -> bool:
    if not bundle_id or NSRunningApplication is None or NSApplicationActivateIgnoringOtherApps is None:
        return False
    apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle_id)
    if not apps:
        return False
    app = apps[0]
    return bool(app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps))
