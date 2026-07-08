mod config;
mod parser;
mod uploader;
mod watcher;

use chrono::Local;
use eframe::egui;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use tokio::sync::mpsc;

#[derive(Clone)]
struct LogEntry {
    time: String,
    puzzle_id: String,
    status: String,
    cost: Option<i64>,
    cycles: Option<i64>,
    area: Option<i64>,
    instructions: Option<i64>,
}

struct App {
    config: config::Config,
    config_dirty: bool,

    // Status
    watching: bool,
    watch_error: Option<String>,
    connection_status: Arc<Mutex<Option<bool>>>, // None=checking, Some(true)=ok, Some(false)=fail

    // Upload log
    log: Arc<Mutex<Vec<LogEntry>>>,

    // Channel from watcher -> upload worker
    upload_tx: Option<mpsc::Sender<PathBuf>>,

    // Keep watcher alive
    _watcher: Option<notify::RecommendedWatcher>,

    // "Upload all" state: None = idle, Some(n) = n files queued
    upload_all_queued: Option<usize>,

    // Tokio runtime
    rt: tokio::runtime::Handle,
}

impl App {
    fn new(cc: &eframe::CreationContext<'_>, rt: tokio::runtime::Handle) -> Self {
        let _ = cc;
        let cfg = config::load();
        let log = Arc::new(Mutex::new(Vec::<LogEntry>::new()));
        let conn_status = Arc::new(Mutex::new(None::<bool>));

        // Ping server
        {
            let url = cfg.server_url.clone();
            let status = conn_status.clone();
            rt.spawn(async move {
                let ok = reqwest::get(format!("{}/api/leaderboard", url.trim_end_matches('/')))
                    .await
                    .map(|r| r.status().is_success())
                    .unwrap_or(false);
                *status.lock().unwrap() = Some(ok);
            });
        }

        let mut app = Self {
            config: cfg,
            config_dirty: false,
            watching: false,
            watch_error: None,
            connection_status: conn_status,
            log,
            upload_tx: None,
            _watcher: None,
            upload_all_queued: None,
            rt,
        };
        app.start_watching();
        app
    }

    fn start_watching(&mut self) {
        let dir = PathBuf::from(&self.config.solution_dir);
        if !dir.exists() {
            self.watch_error = Some(format!("Directory not found: {}", dir.display()));
            self.watching = false;
            return;
        }

        let (path_tx, mut path_rx) = mpsc::channel::<PathBuf>(64);
        let log = self.log.clone();
        let server_url = self.config.server_url.clone();
        let nickname = self.config.nickname.clone();

        self.rt.spawn(async move {
            while let Some(path) = path_rx.recv().await {
                let puzzle_id = {
                    let data = match tokio::fs::read(&path).await {
                        Ok(d) => d,
                        Err(_) => continue,
                    };
                    parser::extract_puzzle_id(&data).unwrap_or_else(|| "?".to_string())
                };

                let time = Local::now().format("%H:%M:%S").to_string();

                // Try upload, retry once on failure
                let result = match uploader::upload(&server_url, &nickname, &path).await {
                    Ok(r) => Ok(r),
                    Err(_) => uploader::upload(&server_url, &nickname, &path).await,
                };

                let entry = match result {
                    Ok(r) => LogEntry {
                        time,
                        puzzle_id: r.puzzle_id,
                        status: if r.accepted { "OK".into() } else { "no improvement".into() },
                        cost: r.cost,
                        cycles: r.cycles,
                        area: r.area,
                        instructions: r.instructions,
                    },
                    Err(e) => LogEntry {
                        time,
                        puzzle_id,
                        status: format!("ERR: {}", e),
                        cost: None,
                        cycles: None,
                        area: None,
                        instructions: None,
                    },
                };

                let mut log = log.lock().unwrap();
                log.insert(0, entry);
                log.truncate(20);
            }
        });

        match watcher::start_watcher(dir.clone(), path_tx.clone()) {
            Ok(w) => {
                self._watcher = Some(w);
                self.upload_tx = Some(path_tx);
                self.watching = true;
                self.watch_error = None;
            }
            Err(e) => {
                self.watch_error = Some(format!("Watcher error: {e}"));
                self.watching = false;
            }
        }
    }

    fn upload_all(&mut self) {
        let Some(tx) = self.upload_tx.clone() else { return };
        let dir = PathBuf::from(&self.config.solution_dir);

        let entries: Vec<PathBuf> = std::fs::read_dir(&dir)
            .into_iter()
            .flatten()
            .flatten()
            .map(|e| e.path())
            .filter(|p| p.extension().map_or(false, |e| e == "solution"))
            .collect();

        let count = entries.len();
        self.upload_all_queued = Some(count);

        self.rt.spawn(async move {
            for path in entries {
                let _ = tx.send(path).await;
            }
        });
    }

    fn ping_server(&self) {
        let url = self.config.server_url.clone();
        let status = self.connection_status.clone();
        *status.lock().unwrap() = None;
        self.rt.spawn(async move {
            let ok = reqwest::get(format!("{}/api/leaderboard", url.trim_end_matches('/')))
                .await
                .map(|r| r.status().is_success())
                .unwrap_or(false);
            *status.lock().unwrap() = Some(ok);
        });
    }
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        ctx.request_repaint_after(std::time::Duration::from_secs(2));

        // Clear "queued" banner once all uploads have landed in the log
        if let Some(n) = self.upload_all_queued {
            if self.log.lock().unwrap().len() >= n.min(20) {
                self.upload_all_queued = None;
            }
        }

        egui::CentralPanel::default().show(ctx, |ui| {
            ui.heading("Opus Magnum Leaderboard Client");
            ui.add_space(8.0);

            // --- Settings ---
            egui::CollapsingHeader::new("Settings").default_open(true).show(ui, |ui| {
                egui::Grid::new("settings_grid").num_columns(2).spacing([8.0, 6.0]).show(ui, |ui| {
                    ui.label("Server URL:");
                    if ui.text_edit_singleline(&mut self.config.server_url).changed() {
                        self.config_dirty = true;
                    }
                    ui.end_row();

                    ui.label("Nickname:");
                    if ui.text_edit_singleline(&mut self.config.nickname).changed() {
                        self.config_dirty = true;
                    }
                    ui.end_row();

                    ui.label("Solution directory:");
                    if ui.text_edit_singleline(&mut self.config.solution_dir).changed() {
                        self.config_dirty = true;
                    }
                    ui.end_row();
                });

                ui.horizontal(|ui| {
                    if ui.button("Save & Restart Watcher").clicked() {
                        let _ = config::save(&self.config);
                        self.config_dirty = false;
                        self._watcher = None;
                        self.upload_tx = None;
                        self.start_watching();
                        self.ping_server();
                    }

                    if self.config_dirty {
                        ui.colored_label(egui::Color32::YELLOW, "Unsaved changes");
                    }

                    // Connection status
                    let status = *self.connection_status.lock().unwrap();
                    match status {
                        None => { ui.spinner(); ui.label("Connecting..."); }
                        Some(true) => { ui.colored_label(egui::Color32::GREEN, "Connected"); }
                        Some(false) => { ui.colored_label(egui::Color32::RED, "Server unreachable"); }
                    }
                });
            });

            ui.add_space(8.0);

            // --- Status ---
            ui.group(|ui| {
                if self.watching {
                    ui.colored_label(egui::Color32::GREEN, format!("Watching: {}", self.config.solution_dir));
                } else {
                    ui.colored_label(egui::Color32::RED, "Not watching");
                    if let Some(err) = &self.watch_error {
                        ui.label(err);
                    }
                }
            });

            ui.add_space(8.0);

            // --- Upload All ---
            ui.horizontal(|ui| {
                let can_upload = self.watching && !self.config.nickname.is_empty();
                if ui.add_enabled(can_upload, egui::Button::new("Upload All Solutions")).clicked() {
                    self.upload_all();
                }
                if let Some(n) = self.upload_all_queued {
                    ui.colored_label(egui::Color32::YELLOW, format!("Queued {n} solutions..."));
                }
            });

            ui.add_space(8.0);

            // --- Upload Log ---
            ui.label("Recent uploads:");
            egui::ScrollArea::vertical().max_height(400.0).show(ui, |ui| {
                let log = self.log.lock().unwrap().clone();
                if log.is_empty() {
                    ui.colored_label(egui::Color32::GRAY, "No uploads yet — modify a .solution file to trigger upload");
                } else {
                    egui::Grid::new("log_grid")
                        .num_columns(6)
                        .spacing([12.0, 4.0])
                        .striped(true)
                        .show(ui, |ui| {
                            ui.strong("Time");
                            ui.strong("Puzzle");
                            ui.strong("Cost");
                            ui.strong("Cycles");
                            ui.strong("Area");
                            ui.strong("Instructions / Status");
                            ui.end_row();

                            for entry in &log {
                                ui.label(&entry.time);
                                ui.label(&entry.puzzle_id);
                                if entry.status == "OK" {
                                    ui.label(entry.cost.map_or("—".into(), |v| v.to_string()));
                                    ui.label(entry.cycles.map_or("—".into(), |v| v.to_string()));
                                    ui.label(entry.area.map_or("—".into(), |v| v.to_string()));
                                    ui.label(entry.instructions.map_or("—".into(), |v| v.to_string()));
                                } else if entry.status == "no improvement" {
                                    ui.label(entry.cost.map_or("—".into(), |v| v.to_string()));
                                    ui.label(entry.cycles.map_or("—".into(), |v| v.to_string()));
                                    ui.label(entry.area.map_or("—".into(), |v| v.to_string()));
                                    ui.colored_label(egui::Color32::GRAY, "no improvement");
                                } else {
                                    ui.label("—");
                                    ui.label("—");
                                    ui.label("—");
                                    ui.colored_label(egui::Color32::RED, &entry.status);
                                }
                                ui.end_row();
                            }
                        });
                }
            });
        });
    }
}

fn main() {
    let rt = tokio::runtime::Runtime::new().expect("tokio runtime");
    let handle = rt.handle().clone();

    // Keep runtime alive in a background thread
    std::thread::spawn(move || {
        rt.block_on(std::future::pending::<()>());
    });

    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([700.0, 550.0])
            .with_title("Opus Magnum Leaderboard"),
        ..Default::default()
    };

    eframe::run_native(
        "om-leaderboard-client",
        options,
        Box::new(move |cc| Box::new(App::new(cc, handle))),
    )
    .expect("eframe run");
}
