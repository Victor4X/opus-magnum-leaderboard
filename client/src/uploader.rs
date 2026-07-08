use std::path::PathBuf;

#[derive(Debug, Clone)]
pub struct UploadResult {
    pub puzzle_id: String,
    pub accepted: bool,
    pub cost: Option<i64>,
    pub cycles: Option<i64>,
    pub area: Option<i64>,
    pub instructions: Option<i64>,
}

pub async fn upload(server_url: &str, nickname: &str, api_key: &str, path: &PathBuf) -> anyhow::Result<UploadResult> {
    let data = tokio::fs::read(path).await?;
    let filename = path
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| "solution.solution".into());

    let client = reqwest::Client::new();
    let url = format!("{}/api/submit", server_url.trim_end_matches('/'));

    let part = reqwest::multipart::Part::bytes(data)
        .file_name(filename)
        .mime_str("application/octet-stream")?;
    let form = reqwest::multipart::Form::new()
        .part("file", part)
        .text("nickname", nickname.to_string());

    let resp = client.post(&url).header("X-Api-Key", api_key).multipart(form).send().await?;
    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        return Err(anyhow::anyhow!("Server error {}: {}", status, body));
    }

    let json: serde_json::Value = resp.json().await?;
    Ok(UploadResult {
        puzzle_id: json["puzzle_id"].as_str().unwrap_or("?").to_string(),
        accepted: json["accepted"].as_bool().unwrap_or(true),
        cost: json["cost"].as_i64(),
        cycles: json["cycles"].as_i64(),
        area: json["area"].as_i64(),
        instructions: json["instructions"].as_i64(),
    })
}
