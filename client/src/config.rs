use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    pub server_url: String,
    pub nickname: String,
    pub solution_dir: String,
    #[serde(default)]
    pub api_key: String,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            server_url: "http://localhost:8000".into(),
            nickname: String::new(),
            solution_dir: detect_solution_dir().unwrap_or_default(),
            api_key: String::new(),
        }
    }
}

fn config_path() -> Option<PathBuf> {
    let mut p = dirs::config_dir()?;
    p.push("om-leaderboard");
    p.push("config.toml");
    Some(p)
}

pub fn load() -> Config {
    let Some(path) = config_path() else {
        return Config::default();
    };
    let Ok(text) = std::fs::read_to_string(&path) else {
        return Config::default();
    };
    toml::from_str(&text).unwrap_or_default()
}

pub fn save(cfg: &Config) -> std::io::Result<()> {
    let Some(path) = config_path() else {
        return Ok(());
    };
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let text = toml::to_string_pretty(cfg).unwrap_or_default();
    std::fs::write(path, text)
}

fn detect_solution_dir() -> Option<String> {
    #[cfg(target_os = "linux")]
    {
        let base = dirs::data_local_dir()?;
        let om_dir = base.join("Opus Magnum");
        if let Ok(rd) = std::fs::read_dir(&om_dir) {
            for entry in rd.flatten() {
                if entry.path().is_dir() {
                    return Some(entry.path().to_string_lossy().into_owned());
                }
            }
        }
    }
    #[cfg(target_os = "macos")]
    {
        let base = dirs::data_dir()?; // ~/Library/Application Support
        let om_dir = base.join("Opus Magnum");
        if let Ok(mut rd) = std::fs::read_dir(&om_dir) {
            if let Some(Ok(entry)) = rd.next() {
                return Some(entry.path().to_string_lossy().into_owned());
            }
        }
    }
    #[cfg(target_os = "windows")]
    {
        for base in [dirs::document_dir(), dirs::home_dir()
            .map(|h| h.join("OneDrive").join("Documents"))]
            .into_iter()
            .flatten()
        {
            let om_dir = base.join("My Games").join("Opus Magnum");
            if let Ok(mut rd) = std::fs::read_dir(&om_dir) {
                if let Some(Ok(entry)) = rd.next() {
                    return Some(entry.path().to_string_lossy().into_owned());
                }
            }
        }
    }
    None
}
