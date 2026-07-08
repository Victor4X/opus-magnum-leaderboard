/// Extract the puzzle ID from a .solution file's bytes.
/// Format: 4-byte LE version (7), then a C#-style 7-bit length-prefixed UTF-8 string.
pub fn extract_puzzle_id(data: &[u8]) -> Option<String> {
    if data.len() < 5 {
        return None;
    }
    let version = u32::from_le_bytes(data[0..4].try_into().ok()?);
    if version != 7 {
        return None;
    }
    let (length, idx) = read_varint(data, 4)?;
    let end = idx + length;
    if end > data.len() {
        return None;
    }
    String::from_utf8(data[idx..end].to_vec()).ok()
}

fn read_varint(data: &[u8], mut offset: usize) -> Option<(usize, usize)> {
    let mut result: usize = 0;
    let mut shift = 0;
    loop {
        if offset >= data.len() {
            return None;
        }
        let b = data[offset] as usize;
        offset += 1;
        result |= (b & 0x7F) << shift;
        if b & 0x80 == 0 {
            break;
        }
        shift += 7;
    }
    Some((result, offset))
}
