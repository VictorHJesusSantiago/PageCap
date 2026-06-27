import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("electronAPI", {
  openFolder: (path: string) => ipcRenderer.invoke("open-folder", path),
  chooseDirectory: () => ipcRenderer.invoke("choose-directory"),
  isElectron: true,
});
