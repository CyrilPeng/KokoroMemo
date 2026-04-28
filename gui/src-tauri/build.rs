use std::path::PathBuf;

fn main() {
    println!("cargo:rustc-check-cfg=cfg(kokoromemo_embedded_backend)");

    let embedded_backend = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap())
        .join("embedded-backend")
        .join("kokoromemo-server.exe");
    println!("cargo:rerun-if-changed={}", embedded_backend.display());
    if embedded_backend.exists() {
        println!("cargo:rustc-cfg=kokoromemo_embedded_backend");
    }

    tauri_build::build()
}
