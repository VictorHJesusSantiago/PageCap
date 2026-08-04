import { app, BrowserWindow, ipcMain, shell, dialog, Notification } from "electron";
import path from "path";
import { spawn, ChildProcess } from "child_process";
import crypto from "crypto";
import fs from "fs";

const isDev = process.env.NODE_ENV !== "production";
const API_PORT = 8765;

const API_TOKEN = crypto.randomBytes(32).toString("hex");

let mainWindow: BrowserWindow | null = null;
let apiProcess: ChildProcess | null = null;

function getEnginePath(): string {
  if (isDev) {
    return path.join(__dirname, "../../engine");
  }
  return path.join(process.resourcesPath, "engine");
}

function getUiPath(): string {
  if (isDev) {
    return "http://localhost:5173";
  }
  return `file://${path.join(__dirname, "../../ui/dist/index.html")}`;
}

async function startApiServer(): Promise<void> {
  const engineDir = getEnginePath();
  const apiScript = path.join(engineDir, "api.py");

  if (!fs.existsSync(apiScript)) {
    console.warn("API script not found at", apiScript);
    return;
  }

  const python = process.platform === "win32" ? "python" : "python3";

  apiProcess = spawn(
    python,
    ["-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", String(API_PORT)],
    {
      cwd: engineDir,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        PAGECAP_API_TOKEN: API_TOKEN,
        PAGECAP_ALLOW_NULL_ORIGIN: "1",
      },
    },
  );

  apiProcess.stdout?.on("data", (d: Buffer) => console.log("[API]", d.toString().trim()));
  apiProcess.stderr?.on("data", (d: Buffer) => console.error("[API]", d.toString().trim()));

  await waitForApi();
}

async function waitForApi(retries = 20, delay = 500): Promise<void> {
  for (let i = 0; i < retries; i++) {
    try {
      const { default: http } = await import("http");
      await new Promise<void>((resolve, reject) => {
        const req = http.get(`http://127.0.0.1:${API_PORT}/health`, (res) => {
          if (res.statusCode === 200) resolve();
          else reject(new Error(`status ${res.statusCode}`));
        });
        req.on("error", reject);
        req.setTimeout(400, () => req.destroy());
      });
      return;
    } catch {
      await new Promise((r) => setTimeout(r, delay));
    }
  }
  console.warn("API server did not start in time");
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 900,
    height: 700,
    minWidth: 680,
    minHeight: 500,
    title: "PageCap",
    backgroundColor: "#0f1117",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
  });

  mainWindow.webContents.on("did-finish-load", () => {
    mainWindow?.webContents.executeJavaScript(
      `window.__PAGECAP_API__ = "http://127.0.0.1:${API_PORT}";` +
        `window.__PAGECAP_TOKEN__ = ${JSON.stringify(API_TOKEN)};`,
    );
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    const allowed = isDev ? "http://localhost:5173" : "file://";
    if (!url.startsWith(allowed)) {
      event.preventDefault();
      if (/^https?:\/\//.test(url)) shell.openExternal(url);
    }
  });

  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    mainWindow.loadFile(path.join(__dirname, "../../ui/dist/index.html"));
  }

  mainWindow.on("closed", () => { mainWindow = null; });
}

ipcMain.handle("open-folder", async (_event, folderPath: string) => {
  if (typeof folderPath !== "string" || !fs.existsSync(folderPath)) return;
  if (!fs.statSync(folderPath).isDirectory()) return;
  await shell.openPath(path.resolve(folderPath));
});

ipcMain.handle("choose-directory", async () => {
  const result = await dialog.showOpenDialog({ properties: ["openDirectory"] });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle("notify", async (_event, title: string, body: string) => {
  if (Notification.isSupported()) {
    new Notification({ title, body }).show();
  }
});

app.whenReady().then(async () => {
  await startApiServer();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  apiProcess?.kill();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  apiProcess?.kill();
});
