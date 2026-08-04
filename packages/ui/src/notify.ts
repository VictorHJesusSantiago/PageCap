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
