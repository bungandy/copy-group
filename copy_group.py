import os
import shutil
import hashlib
from datetime import datetime
import sys

# === CONFIGURATION ===
SDCARD_PATH = "/Volumes/Untitled/DCIM/"      # Update to your SD card path
TARGET_BASE = "/Users/andy/TRANSIT_BLACKBOX/_SANDISK_128/"       # Destination folder

def get_md5(file_path, chunk_size=8192):
    """Calculate MD5 checksum of a file."""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"⚠️ Could not read {file_path}: {e}")
        return None


def get_file_creation_time(src_path):
    """Return the best available creation timestamp for a source file."""
    stat = os.stat(src_path)
    return stat.st_birthtime if hasattr(stat, "st_birthtime") else stat.st_ctime


def build_target_dir(target_base, creation_time, filename):
    """Build the destination directory for a file."""
    year_folder = datetime.fromtimestamp(creation_time).strftime("%Y")
    date_folder = datetime.fromtimestamp(creation_time).strftime("%Y%m%d")
    target_dir = os.path.join(target_base, year_folder, date_folder)

    if os.path.splitext(filename)[1].lower() == ".dng":
        target_dir = os.path.join(target_dir, "DNG")

    return target_dir


def shorten_text(text, max_len=24):
    """Shorten a label while keeping it readable."""
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[: max_len - 3] + "..."


def collect_files_to_copy(directory, target_base):
    """Collect source and destination paths in one pass."""
    files_to_copy = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.startswith("."):
                continue

            src_path = os.path.join(root, file)

            try:
                creation_time = get_file_creation_time(src_path)
            except Exception:
                continue

            target_dir = build_target_dir(target_base, creation_time, file)
            dst_path = os.path.join(target_dir, file)
            files_to_copy.append((src_path, dst_path, file))

    return files_to_copy

def render_compact_progress(filename, dst_path, copied, src_size, current_index, total_files):
    """Render a compact progress line with numbering."""
    bar_length = 22
    percentage = (copied / src_size) * 100 if src_size else 100
    filled_length = int(bar_length * copied // src_size) if src_size else bar_length
    colors = [
        '\033[38;5;52m',
        '\033[38;5;88m',
        '\033[38;5;124m',
        '\033[38;5;160m',
        '\033[38;5;196m',
        '\033[38;5;202m',
        '\033[38;5;208m',
        '\033[38;5;214m',
        '\033[38;5;220m',
        '\033[38;5;226m',
    ]

    bar = ''
    for i in range(filled_length):
        color_idx = min(int((i / max(filled_length, 1)) * len(colors)), len(colors) - 1)
        bar += colors[color_idx] + '█'

    if 0 < filled_length < bar_length:
        edge_color = colors[min(int((percentage / 100) * (len(colors) - 1)), len(colors) - 1)]
        edge_chars = ['▊', '▋', '▌', '▍', '▎', '▏']
        edge_idx = min(int((percentage / 100) * len(edge_chars)), len(edge_chars) - 1)
        bar += edge_color + edge_chars[edge_idx]
        filled_length += 1

    remaining = bar_length - filled_length
    if remaining > 0:
        bar += '\033[38;5;240m' + '░' * remaining

    bar += '\033[0m'
    spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    spinner = spinner_chars[int((copied / (8192 * 8)) % len(spinner_chars))]

    if percentage >= 100:
        percentage_color = '\033[38;5;226m\033[1m'
    elif percentage >= 75:
        percentage_color = '\033[38;5;220m\033[1m'
    elif percentage >= 50:
        percentage_color = '\033[38;5;208m\033[1m'
    else:
        percentage_color = '\033[38;5;196m\033[1m'

    display_name = shorten_text(os.path.basename(filename), 20)
    target_path = os.path.relpath(os.path.dirname(dst_path), TARGET_BASE)
    if target_path == ".":
        target_path = os.path.basename(os.path.dirname(dst_path))

    print(
        f"\r\033[K{current_index:>3}/{total_files:<3} {display_name:<20} -> "
        f"{shorten_text(target_path, 24):<24} [{bar}] {percentage_color}{percentage:5.1f}%\033[0m {spinner}",
        end='',
        flush=True,
    )


def copy_file_with_progress(src_path, dst_path, filename="", current_index=1, total_files=1):
    """Copy a file while showing real-time progress."""
    try:
        src_size = os.path.getsize(src_path)
        if src_size == 0:
            render_compact_progress(filename, dst_path, 0, 0, current_index, total_files)
            shutil.copy2(src_path, dst_path)
            return True
            
        # Create destination directory if it doesn't exist
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        
        # Copy with progress monitoring
        with open(src_path, 'rb') as src_file:
            with open(dst_path, 'wb') as dst_file:
                copied = 0
                chunk_size = 8192  # 8KB chunks
                
                while True:
                    chunk = src_file.read(chunk_size)
                    if not chunk:
                        break
                    
                    dst_file.write(chunk)
                    copied += len(chunk)
                    
                    # Update progress
                    render_compact_progress(filename, dst_path, copied, src_size, current_index, total_files)
        
        # Preserve metadata
        shutil.copystat(src_path, dst_path)
        
        display_name = shorten_text(filename, 20)
        target_path = os.path.relpath(os.path.dirname(dst_path), TARGET_BASE)
        if target_path == ".":
            target_path = os.path.basename(os.path.dirname(dst_path))
        print(f"\r\033[K{current_index:>3}/{total_files:<3} {display_name:<20} -> {shorten_text(target_path, 24):<24} ✅ 100% ⠏")
        return True
        
    except Exception as e:
        print(f"\r❌ {current_index:>3}/{total_files:<3} {shorten_text(filename, 20)}: {e}")
        return False

# === CREATE TARGET BASE IF NOT EXISTS ===
os.makedirs(TARGET_BASE, exist_ok=True)

try:
    print("🔍 Scanning files...")
    files_to_copy = collect_files_to_copy(SDCARD_PATH, TARGET_BASE)
    total_files = len(files_to_copy)
    print(f"Found {total_files} files to copy")
    print()  # Add extra space above copying progress
    
    if total_files == 0:
        print("ℹ️ No files found to copy.")
        sys.exit(0)
    
    copied_files = 0
    skipped_files = 0
    
    for index, (src_path, dst_path, file) in enumerate(files_to_copy, start=1):
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)

        # Skip if file already exists and is identical
        if os.path.exists(dst_path):
            src_stat = os.stat(src_path)
            dst_stat = os.stat(dst_path)

            same_size = src_stat.st_size == dst_stat.st_size
            same_mtime = int(src_stat.st_mtime) == int(dst_stat.st_mtime)
            same_checksum = get_md5(src_path) == get_md5(dst_path)

            if same_size and same_mtime and same_checksum:
                rel_target = os.path.relpath(os.path.dirname(dst_path), TARGET_BASE)
                if rel_target == ".":
                    rel_target = os.path.basename(os.path.dirname(dst_path))
                print(f"\r⏩ {index:>3}/{total_files:<3} {shorten_text(file, 20)} -> {shorten_text(rel_target, 24)} skipped")
                skipped_files += 1
                continue

        if copy_file_with_progress(src_path, dst_path, file, index, total_files):
            copied_files += 1
        else:
            rel_target = os.path.relpath(os.path.dirname(dst_path), TARGET_BASE)
            if rel_target == ".":
                rel_target = os.path.basename(os.path.dirname(dst_path))
            print(f"\r❌ {index:>3}/{total_files:<3} {shorten_text(file, 20)} -> {shorten_text(rel_target, 24)} failed")

    # Final summary
    print(f"\n🎉 Copy operation completed!")
    print(f"📈 Summary:")
    print(f"   • Files copied: {copied_files}")
    print(f"   • Files skipped (duplicates): {skipped_files}")

except KeyboardInterrupt:
    print("\n\n⛔️ Operation cancelled by user. Exiting cleanly.")
    sys.exit(0)
