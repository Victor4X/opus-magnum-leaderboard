use notify::{Config, Event, EventKind, RecommendedWatcher, RecursiveMode, Watcher};
use std::path::PathBuf;
use std::sync::mpsc;
use std::time::{Duration, Instant};
use tokio::sync::mpsc as tokio_mpsc;

pub fn start_watcher(
    dir: PathBuf,
    tx: tokio_mpsc::Sender<PathBuf>,
) -> anyhow::Result<RecommendedWatcher> {
    let (sync_tx, sync_rx) = mpsc::channel::<notify::Result<Event>>();

    let mut watcher = RecommendedWatcher::new(sync_tx, Config::default())?;
    watcher.watch(&dir, RecursiveMode::Recursive)?;

    // Spawn a thread to debounce and forward events
    std::thread::spawn(move || {
        // pending: path -> last_seen time
        let mut pending: std::collections::HashMap<PathBuf, Instant> = std::collections::HashMap::new();
        let debounce = Duration::from_millis(500);

        loop {
            // Drain available events with a short timeout
            let deadline = Instant::now() + Duration::from_millis(100);
            while Instant::now() < deadline {
                match sync_rx.recv_timeout(Duration::from_millis(50)) {
                    Ok(Ok(event)) => {
                        if matches!(
                            event.kind,
                            EventKind::Create(_) | EventKind::Modify(_)
                        ) {
                            for path in event.paths {
                                if path.extension().map_or(false, |e| e == "solution") {
                                    pending.insert(path, Instant::now());
                                }
                            }
                        }
                    }
                    Ok(Err(_)) | Err(mpsc::RecvTimeoutError::Timeout) => break,
                    Err(mpsc::RecvTimeoutError::Disconnected) => return,
                }
            }

            // Flush debounced paths
            let now = Instant::now();
            let ready: Vec<PathBuf> = pending
                .iter()
                .filter(|(_, t)| now.duration_since(**t) >= debounce)
                .map(|(p, _)| p.clone())
                .collect();
            for path in ready {
                pending.remove(&path);
                let _ = tx.blocking_send(path);
            }
        }
    });

    Ok(watcher)
}
