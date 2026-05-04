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
#[cfg(not(debug_assertions))]
use tauri::path::BaseDirectory;
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
            close_to_tray: AtomicBool::new(false),
            quitting: AtomicBool::new(false),
        }
    }
}

#[tauri::command]
fn greet(name: &str) -> String {
    format!("你好，{}！KokoroMemo 正在运行。", name)
}

#[tauri::command]
fn set_close_to_tray(enabled: bool, state: tauri::State<'_, AppState>) {
    state.close_to_tray.store(enabled, Ordering::Relaxed);
}

#[tauri::command]
fn get_close_to_tray(state: tauri::State<'_, AppState>) -> bool {
    state.close_to_tray.load(Ordering::Relaxed)
}

#[tauri::command]
fn write_text_file(path: String, contents: String) -> Result<(), String> {
    let path = PathBuf::from(path);
    if path.is_dir() {
        return Err("目标路径是目录".to_string());
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(path, contents).map_err(|error| error.to_string())
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn backend_work_dir(_app: &tauri::AppHandle) -> PathBuf {
    #[cfg(debug_assertions)]
    {
        // 开发模式下，Python 后端从项目根目录启动。
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        manifest_dir
            .parent()
            .and_then(|path| path.parent())
            .map(PathBuf::from)
            .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")))
    }
    #[cfg(not(debug_assertions))]
    {
        let dir = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(PathBuf::from))
            .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
        let _ = fs::create_dir_all(&dir);
        dir
    }
}

fn web_dist_dir(_app: &tauri::AppHandle, _work_dir: &PathBuf) -> Option<PathBuf> {
    #[cfg(debug_assertions)]
    {
        let repo_dist = repo_root_dir()?.join("gui").join("dist");
        return repo_dist.is_dir().then_some(repo_dist);
    }

    #[cfg(not(debug_assertions))]
    {
        if let Ok(resource_dist) = _app.path().resolve("dist", BaseDirectory::Resource) {
            if resource_dist.is_dir() {
                return Some(resource_dist);
            }
        }
        let adjacent_dist = _work_dir.join("dist");
        if adjacent_dist.is_dir() {
            return Some(adjacent_dist);
        }
        let legacy_dist = _work_dir.join("gui").join("dist");
        legacy_dist.is_dir().then_some(legacy_dist)
    }
}

#[cfg(debug_assertions)]
fn repo_root_dir() -> Option<PathBuf> {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .parent()
        .and_then(|path| path.parent())
        .map(PathBuf::from)
}

fn config_dir(app: &tauri::AppHandle) -> PathBuf {
    #[cfg(debug_assertions)]
    {
        return repo_root_dir().unwrap_or_else(|| backend_work_dir(app));
    }
    #[cfg(not(debug_assertions))]
    {
        backend_work_dir(app)
    }
}

#[cfg(all(windows, kokoromemo_embedded_backend))]
const EMBEDDED_BACKEND: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/embedded-backend/kokoromemo-server.exe"
));

#[cfg(all(windows, kokoromemo_embedded_backend))]
fn embedded_backend_path(_app: &tauri::AppHandle) -> std::io::Result<PathBuf> {
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(PathBuf::from))
        .unwrap_or_else(|| PathBuf::from("."));
    let runtime_dir = exe_dir.join("runtime");
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
    let mut command = std::process::Command::new(backend_path);
    command
        .current_dir(work_dir)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .creation_flags(CREATE_NO_WINDOW);
    if let Some(dist_dir) = web_dist_dir(app, work_dir) {
        command.env("KOKOROMEMO_WEB_DIST", dist_dir);
    }
    command.spawn()
}

fn spawn_backend(app: tauri::AppHandle) {
    tauri::async_runtime::spawn(async move {
        let work_dir = backend_work_dir(&app);
        let web_dist = web_dist_dir(&app, &work_dir);
        // 清理旧端口文件，避免读取上一次启动留下的端口。
        let _ = fs::remove_file(work_dir.join(".port"));

        #[cfg(all(windows, kokoromemo_embedded_backend))]
        {
            match spawn_embedded_backend(&app, &work_dir) {
                Ok(child) => {
                    eprintln!("KokoroMemo 内置后端已启动，PID={}", child.id());
                    if let Some(state) = app.try_state::<AppState>() {
                        *state.backend_child.lock().expect("后端进程锁已损坏") =
                            Some(BackendChild::Embedded(child));
                    }
                }
                Err(error) => eprintln!("启动 KokoroMemo 内置后端失败：{error}"),
            }
        }

        #[cfg(not(all(windows, kokoromemo_embedded_backend)))]
        {
            #[cfg(debug_assertions)]
            let command = {
                let project_root = repo_root_dir().unwrap_or_else(|| work_dir.clone());
                app.shell()
                    .command("python")
                    .args(["-m", "app.main"])
                    .current_dir(project_root)
            };

            #[cfg(not(debug_assertions))]
            let command = match app.shell().sidecar("kokoromemo-server") {
                Ok(command) => command.current_dir(&work_dir),
                Err(error) => {
                    eprintln!("解析后端随附程序失败：{error}");
                    return;
                }
            };

            let command = if let Some(dist_dir) = web_dist {
                command.env("KOKOROMEMO_WEB_DIST", dist_dir)
            } else {
                command
            };

            match command.spawn() {
                Ok((mut rx, child)) => {
                    eprintln!("KokoroMemo 后端已启动，PID={}", child.pid());
                    if let Some(state) = app.try_state::<AppState>() {
                        *state.backend_child.lock().expect("后端进程锁已损坏") =
                            Some(BackendChild::Sidecar(child));
                    }
                    while let Some(event) = rx.recv().await {
                        eprintln!("后端输出：{event:?}");
                    }
                    if let Some(state) = app.try_state::<AppState>() {
                        let _ = state.backend_child.lock().expect("后端进程锁已损坏").take();
                    }
                }
                Err(error) => eprintln!("启动 KokoroMemo 后端失败：{error}"),
            }
        }
    });
}

fn kill_backend(app: &tauri::AppHandle) {
    if let Some(state) = app.try_state::<AppState>() {
        if let Some(child) = state
            .backend_child
            .lock()
            .expect("后端进程锁已损坏")
            .take()
        {
            child.kill();
        }
    }
}

#[tauri::command]
async fn restart_backend(app: tauri::AppHandle) -> Result<String, String> {
    kill_backend(&app);
    // 等待端口释放。
    tokio::time::sleep(std::time::Duration::from_millis(800)).await;
    spawn_backend(app.clone());
    Ok("后端正在重启".to_string())
}

#[tauri::command]
async fn get_backend_port(app: tauri::AppHandle) -> Result<u16, String> {
    let work_dir = backend_work_dir(&app);
    let config_dir = config_dir(&app);
    let port_files = [config_dir.join(".port"), work_dir.join(".port")];
    // 轮询端口文件，后端可能仍在启动中。
    for _ in 0..30 {
        for port_file in &port_files {
            if let Ok(content) = fs::read_to_string(port_file) {
                if let Ok(port) = content.trim().parse::<u16>() {
                    if port > 0 {
                        // 确认端口已经开始监听。
                        let addr: std::net::SocketAddr = format!("127.0.0.1:{}", port).parse().unwrap();
                        if std::net::TcpStream::connect_timeout(&addr, std::time::Duration::from_millis(500)).is_ok() {
                            return Ok(port);
                        }
                    }
                }
            }
        }
        tokio::time::sleep(std::time::Duration::from_millis(200)).await;
    }
    Err("6 秒内未找到后端端口文件，或端口尚未开始监听".to_string())
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
            get_close_to_tray,
            write_text_file,
            restart_backend,
            get_backend_port
        ])
        .build(tauri::generate_context!())
        .expect("构建 Tauri 应用失败");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
            if let Some(state) = app_handle.try_state::<AppState>() {
                state.quitting.store(true, Ordering::Relaxed);
            }
            kill_backend(app_handle);
        }
    });
}
