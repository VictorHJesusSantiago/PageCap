/** Fires a desktop notification: native Electron Notification when running
 * inside the packaged app, falling back to the browser Notification API
 * (with a one-time permission prompt) when running as a plain web page. */
export async function notify(title: string, body: string): Promise<void> {
  const electronAPI = (window as any).electronAPI;
  if (electronAPI?.isElectron) {
    await electronAPI.notify(title, body);
    return;
  }

  if (typeof Notification === "undefined") return;
  if (Notification.permission === "granted") {
    new Notification(title, { body });
  } else if (Notification.permission !== "denied") {
    const permission = await Notification.requestPermission();
    if (permission === "granted") new Notification(title, { body });
  }
}
