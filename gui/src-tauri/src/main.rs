#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    fs,
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, Ordering},
        Mutex,
    },
};

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, RunEvent, WindowEvent,
};
#[cfg(not(all(windows, kokoromemo_embedded_backend)))]
use tauri_plugin_shell::process::CommandChild;
#[cfg(not(all(windows, kokoromemo_embedded_backend)))]
use tauri_plugin_shell::ShellExt;

enum BackendChild {
    #[cfg(not(all(windows, kokoromemo_embedded_backend)))]
    Sidecar(CommandChild),
    #[cfg(all(windows, kokoromemo_embedded_backend))]
    Embedded(std::process::Child),
}

impl BackendChild {
    fn kill(self) {
        match self {
            #[cfg(not(all(windows, kokoromemo_embedded_backend)))]
            Self::Sidecar(child) => {
                let _ = child.kill();
            }
            #[cfg(all(windows, kokoromemo_embedded_backend))]
            Self::Embedded(mut child) => {
                let _ = child.kill();
            }
        }
    }
}

struct AppState {
    backend_child: Mutex<Option<BackendChild>>,
    close_to_tray: AtomicBool,
    quitting: AtomicBool,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            backend_child: Mutex::new(None),
            close_to_tray: AtomicBool::new(true),
            quitting: AtomicBool::new(false),
        }
    }
}

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! KokoroMemo is running.", name)
}

#[tauri::command]
fn set_close_to_tray(enabled: bool, state: tauri::State<'_, AppState>) {
    state.close_to_tray.store(enabled, Ordering::Relaxed);
}

#[tauri::command]
fn get_close_to_tray(state: tauri::State<'_, AppState>) -> bool {
    state.close_to_tray.load(Ordering::Relaxed)
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn backend_work_dir(app: &tauri::AppHandle) -> PathBuf {
    let dir = app
        .path()
        .app_data_dir()
        .unwrap_or_else(|_| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
    let _ = fs::create_dir_all(&dir);
    dir
}

#[cfg(all(windows, kokoromemo_embedded_backend))]
const EMBEDDED_BACKEND: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/embedded-backend/kokoromemo-server.exe"
));

#[cfg(all(windows, kokoromemo_embedded_backend))]
fn embedded_backend_path(app: &tauri::AppHandle) -> std::io::Result<PathBuf> {
    let runtime_dir = backend_work_dir(app).join("runtime");
    fs::create_dir_all(&runtime_dir)?;
    let backend_path = runtime_dir.join("kokoromemo-server.exe");
    let should_write = fs::metadata(&backend_path)
        .map(|meta| meta.len() != EMBEDDED_BACKEND.len() as u64)
        .unwrap_or(true);
    if should_write {
        fs::write(&backend_path, EMBEDDED_BACKEND)?;
    }
    Ok(backend_path)
}

#[cfg(all(windows, kokoromemo_embedded_backend))]
fn spawn_embedded_backend(app: &tauri::AppHandle, work_dir: &PathBuf) -> std::io::Result<std::process::Child> {
    use std::os::windows::process::CommandExt;

    const CREATE_NO_WINDOW: u32 = 0x08000000;
    let backend_path = embedded_backend_path(app)?;
    std::process::Command::new(backend_path)
        .current_dir(work_dir)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .creation_flags(CREATE_NO_WINDOW)
        .spawn()
}

fn spawn_backend(app: tauri::AppHandle) {
    tauri::async_runtime::spawn(async move {
        let work_dir = backend_work_dir(&app);

        #[cfg(all(windows, kokoromemo_embedded_backend))]
        {
            match spawn_embedded_backend(&app, &work_dir) {
                Ok(child) => {
                    eprintln!("KokoroMemo embedded backend started, pid={}", child.id());
                    if let Some(state) = app.try_state::<AppState>() {
                        *state.backend_child.lock().expect("backend child lock poisoned") =
                            Some(BackendChild::Embedded(child));
                    }
                }
                Err(error) => eprintln!("failed to start embedded KokoroMemo backend: {error}"),
            }
        }

        #[cfg(not(all(windows, kokoromemo_embedded_backend)))]
        {
            let command = match app.shell().sidecar("kokoromemo-server") {
                Ok(command) => command.current_dir(&work_dir),
                Err(error) => {
                    #[cfg(debug_assertions)]
                    {
                        eprintln!("sidecar backend not found, falling back to python: {error}");
                        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
                        let project_root = manifest_dir
                            .parent()
                            .and_then(|path| path.parent())
                            .map(PathBuf::from)
                            .unwrap_or_else(|| work_dir.clone());
                        app.shell()
                            .command("python")
                            .args(["-m", "app.main"])
                            .current_dir(project_root)
                    }
                    #[cfg(not(debug_assertions))]
                    {
                        eprintln!("failed to resolve backend sidecar: {error}");
                        return;
                    }
                }
            };

            match command.spawn() {
                Ok((mut rx, child)) => {
                    eprintln!("KokoroMemo backend started, pid={}", child.pid());
                    if let Some(state) = app.try_state::<AppState>() {
                        *state.backend_child.lock().expect("backend child lock poisoned") =
                            Some(BackendChild::Sidecar(child));
                    }
                    while let Some(event) = rx.recv().await {
                        eprintln!("backend: {event:?}");
                    }
                    if let Some(state) = app.try_state::<AppState>() {
                        let _ = state.backend_child.lock().expect("backend child lock poisoned").take();
                    }
                }
                Err(error) => eprintln!("failed to start KokoroMemo backend: {error}"),
            }
        }
    });
}

fn kill_backend(app: &tauri::AppHandle) {
    if let Some(state) = app.try_state::<AppState>() {
        if let Some(child) = state
            .backend_child
            .lock()
            .expect("backend child lock poisoned")
            .take()
        {
            child.kill();
        }
    }
}

fn main() {
    let app = tauri::Builder::default()
        .manage(AppState::default())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            spawn_backend(app.handle().clone());

            let show = MenuItem::with_id(app, "show", "显示窗口", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "退出 KokoroMemo", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &quit])?;
            let mut tray = TrayIconBuilder::with_id("main")
                .tooltip("KokoroMemo")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_tray_icon_event(|tray, event| match event {
                    TrayIconEvent::DoubleClick { .. }
                    | TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } => show_main_window(tray.app_handle()),
                    _ => {}
                });
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }
            tray.build(app)?;

            Ok(())
        })
        .on_menu_event(|app, event| {
            if event.id() == "show" {
                show_main_window(app);
            } else if event.id() == "quit" {
                if let Some(state) = app.try_state::<AppState>() {
                    state.quitting.store(true, Ordering::Relaxed);
                }
                app.exit(0);
            }
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                if let Some(state) = window.try_state::<AppState>() {
                    if state.close_to_tray.load(Ordering::Relaxed)
                        && !state.quitting.load(Ordering::Relaxed)
                    {
                        api.prevent_close();
                        let _ = window.hide();
                    }
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            greet,
            set_close_to_tray,
            get_close_to_tray
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
            if let Some(state) = app_handle.try_state::<AppState>() {
                state.quitting.store(true, Ordering::Relaxed);
            }
            kill_backend(app_handle);
        }
    });
}
