import hashlib
import os
import re
import subprocess
import sys
from datetime import datetime

# === CONFIGURATION ===
# Source path (SD card)
# SDCARD_PATH = "/Volumes/Untitled/DCIM/"      # Your SD card path
SDCARD_PATH = "/Volumes/LEICA DSC/DCIM/"  # Your SD card path
# SDCARD_PATH = "/Users/andy/Documents/Scripts/copy-group/_test/"
# SDCARD_PATH = "/Users/andy/TRANSIT_BLACKBOX/_AWS/20250706 - Malaysia/"


# Update these values with your Synology NAS details

# Synology NAS connection details
SYNOLOGY_HOST = "192.168.1.123"  # Your Synology IP address
SYNOLOGY_USER = "andy"  # Your Synology username
SYNOLOGY_PORT = 22  # SSH port (usually 22)

# Paths
SYNOLOGY_BASE_PATH = "/volume1/Photos/"  # Target base path on Synology; files go into YYYY/YYYYMMDD folders


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


def run_ssh_command(command, capture_output=True):
    """Run a command on the Synology NAS via SSH."""
    ssh_cmd = [
        "ssh",
        "-p",
        str(SYNOLOGY_PORT),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ControlMaster=auto",
        "-o",
        "ControlPath=/tmp/ssh_mux_%h_%p_%r",
        "-o",
        "ControlPersist=5m",
        f"{SYNOLOGY_USER}@{SYNOLOGY_HOST}",
        command,
    ]

    try:
        result = subprocess.run(
            ssh_cmd, capture_output=capture_output, text=True, timeout=30
        )
        return result
    except subprocess.TimeoutExpired:
        print(f"❌ SSH command timed out: {command}")
        return None
    except Exception as e:
        print(f"❌ SSH command failed: {e}")
        return None


def get_file_creation_time(src_path):
    """Return the best available creation timestamp for a source file."""
    stat = os.stat(src_path)
    return stat.st_birthtime if hasattr(stat, "st_birthtime") else stat.st_ctime


def build_remote_target_dir(src_path):
    """Build the remote target directory for a source file."""
    creation_time = get_file_creation_time(src_path)
    year_folder = datetime.fromtimestamp(creation_time).strftime("%Y")
    date_folder = datetime.fromtimestamp(creation_time).strftime("%Y%m%d")
    extension = os.path.splitext(src_path)[1].lower()

    if extension == ".dng":
        return f"{SYNOLOGY_BASE_PATH}{year_folder}/{date_folder}/DNG"

    return f"{SYNOLOGY_BASE_PATH}{year_folder}/{date_folder}"


def shorten_text(text, max_len=24):
    """Shorten a label while keeping it readable."""
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[: max_len - 3] + "..."


def compact_path_label(path, max_len=24):
    """Show the most useful tail of a target path."""
    parts = [part for part in path.strip("/").split("/") if part]
    if not parts:
        return path

    tail = "/".join(parts[-3:])
    return shorten_text(tail, max_len)


def build_progress_bar(percentage, bar_length=22):
    """Build a red-to-yellow progress bar for terminal output."""
    colors = [
        "\033[38;5;52m",  # Dark Red
        "\033[38;5;88m",  # Red
        "\033[38;5;124m",  # Medium Red
        "\033[38;5;160m",  # Bright Red
        "\033[38;5;196m",  # Vivid Red
        "\033[38;5;202m",  # Orange-Red
        "\033[38;5;208m",  # Orange
        "\033[38;5;214m",  # Yellow-Orange
        "\033[38;5;220m",  # Yellow
        "\033[38;5;226m",  # Bright Yellow
    ]

    filled_length = int(bar_length * percentage // 100)
    bar = ""

    for i in range(filled_length):
        color_idx = min(int((i / max(filled_length, 1)) * len(colors)), len(colors) - 1)
        bar += colors[color_idx] + "█"

    if 0 < filled_length < bar_length:
        edge_color = colors[
            min(int((percentage / 100) * (len(colors) - 1)), len(colors) - 1)
        ]
        edge_chars = ["▊", "▋", "▌", "▍", "▎", "▏"]
        edge_idx = min(int((percentage / 100) * len(edge_chars)), len(edge_chars) - 1)
        bar += edge_color + edge_chars[edge_idx]
        filled_length += 1

    remaining = bar_length - filled_length
    if remaining > 0:
        bar += "\033[38;5;240m" + "░" * remaining

    return bar + "\033[0m"


def render_progress_line(
    percentage, file_label, target_label, update_index, current_index, total_files
):
    """Render a colored progress line similar to the local copy path."""
    indicator_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    indicator = indicator_chars[update_index % len(indicator_chars)]
    progress_bar = build_progress_bar(percentage)
    display_name = shorten_text(file_label, 18)

    if percentage >= 100:
        percentage_color = "\033[38;5;226m\033[1m"
    elif percentage >= 75:
        percentage_color = "\033[38;5;220m\033[1m"
    elif percentage >= 50:
        percentage_color = "\033[38;5;208m\033[1m"
    else:
        percentage_color = "\033[38;5;196m\033[1m"

    print(
        f"\r\033[K{current_index:>3}/{total_files:<3} {display_name:<18} -> {target_label:<24} "
        f"[{progress_bar}] {percentage_color}{percentage:5.1f}%\033[0m {indicator}",
        end="",
        flush=True,
    )


def stream_rsync_output(process, target_label, total_files, start_index):
    """Stream rsync output and rewrite progress lines with color."""
    progress_pattern = re.compile(r"(?P<percent>\d{1,3}(?:\.\d+)?)%")
    buffer = ""
    saw_progress = False
    update_index = 0
    current_file = ""
    current_index = start_index

    def flush_buffer(line):
        nonlocal saw_progress, update_index, current_file, current_index

        text = line.strip()
        if not text:
            return

        match = progress_pattern.search(text)
        if match:
            percentage = min(float(match.group("percent")), 100.0)
            render_progress_line(
                percentage,
                current_file or "copying",
                target_label,
                update_index,
                current_index,
                total_files,
            )
            update_index += 1
            saw_progress = True
            return

        ignored_prefixes = (
            "sending incremental file list",
            "sent ",
            "total size is ",
            "created directory ",
            "receiving incremental file list",
            "building file list",
        )

        if any(text.startswith(prefix) for prefix in ignored_prefixes):
            if saw_progress:
                print()
                saw_progress = False
            print(text)
            return

        if text != current_file:
            current_file = os.path.basename(text.rstrip("/")) or text
            current_index += 1

        if saw_progress:
            print()
            saw_progress = False

    while True:
        char = process.stdout.read(1) if process.stdout else ""
        if char == "":
            break

        if char in "\r\n":
            flush_buffer(buffer)
            buffer = ""
        else:
            buffer += char

    flush_buffer(buffer)

    if saw_progress:
        print()


def collect_files_by_target_dir(directory):
    """Group non-hidden source files by their final remote target directory."""
    files_by_target_dir = {}
    print("🔍 Scanning files...")

    for root, _, files in os.walk(directory):
        for file in files:
            if file.startswith("."):
                continue

            src_path = os.path.join(root, file)

            try:
                target_dir = build_remote_target_dir(src_path)
            except Exception as e:
                print(f"\n⚠️ Skipping {src_path}: {e}")
                continue

            files_by_target_dir.setdefault(target_dir, []).append(src_path)

    return files_by_target_dir


def rsync_folder_batch(src_paths, target_dir, start_index, total_files):
    """Copy a batch of files to one Synology date folder using rsync."""
    try:
        remote_dir = f"{target_dir}/"

        mkdir_cmd = f"mkdir -p '{remote_dir}'"
        mkdir_result = run_ssh_command(mkdir_cmd, capture_output=False)
        if not mkdir_result or mkdir_result.returncode != 0:
            print(f"❌ Failed to create remote directory: {remote_dir}")
            return False

        rsync_cmd = [
            "rsync",
            "-av",  # archive, verbose; no compression for faster LAN photo/video copy
            "--progress",
            "--partial",
            "--inplace",
            "--timeout=30",
            "--ignore-existing",  # skip files already present remotely
            "-e",
            f"ssh -p {SYNOLOGY_PORT} -o StrictHostKeyChecking=no -o ControlMaster=auto -o ControlPath=/tmp/ssh_mux_%h_%p_%r -o ControlPersist=5m",
            *src_paths,
            f"{SYNOLOGY_USER}@{SYNOLOGY_HOST}:{remote_dir}",
        ]

        compact_label = compact_path_label(target_dir)
        print(f"📁 {compact_label} ({len(src_paths)} files)")

        # Run rsync with real-time output
        process = subprocess.Popen(
            rsync_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )

        stream_rsync_output(process, compact_label, total_files, start_index)
        process.wait()

        if process.returncode == 0:
            print(f"✅ {compact_label} done")
            return True

        print(f"❌ {compact_label} failed")
        return False

    except Exception as e:
        print(f"❌ {compact_path_label(target_dir)} error: {e}")
        return False


def test_ssh_connection():
    """Test SSH connection to Synology."""
    print("🔐 Authenticating SSH connection to Synology...")
    result = run_ssh_command("echo 'SSH connection successful'")
    if result and result.returncode == 0:
        print("✅ SSH connection successful!")
        return True
    else:
        print("❌ SSH connection failed!")
        print("Please check:")
        print(f"  • Synology IP: {SYNOLOGY_HOST}")
        print(f"  • Username: {SYNOLOGY_USER}")
        print(f"  • SSH port: {SYNOLOGY_PORT}")
        print("  • Password authentication is enabled")
        return False


def cleanup_ssh_connection():
    """Clean up SSH connection multiplexing."""
    try:
        # Close the SSH connection
        ssh_cmd = [
            "ssh",
            "-p",
            str(SYNOLOGY_PORT),
            "-o",
            "ControlMaster=auto",
            "-o",
            "ControlPath=/tmp/ssh_mux_%h_%p_%r",
            "-O",
            "exit",
            f"{SYNOLOGY_USER}@{SYNOLOGY_HOST}",
        ]
        subprocess.run(ssh_cmd, capture_output=True, timeout=10)
    except Exception:
        pass  # Ignore cleanup errors


try:
    # Test SSH connection first
    if not test_ssh_connection():
        sys.exit(1)

    # Check if source directory exists
    if not os.path.exists(SDCARD_PATH):
        print(f"❌ Source directory not found: {SDCARD_PATH}")
        print("Please check your SDCARD_PATH configuration.")
        sys.exit(1)

    # First, group files by target date folder
    files_by_target_dir = collect_files_by_target_dir(SDCARD_PATH)
    total_files = sum(len(files) for files in files_by_target_dir.values())
    total_folders = len(files_by_target_dir)

    print(f"Found {total_files} files to copy across {total_folders} target folder(s)")
    print()  # Add extra space above copying progress

    if total_files == 0:
        print("ℹ️ No files found to copy.")
        sys.exit(0)

    attempted_files = 0
    completed_folders = 0
    failed_folders = 0

    current_file_index = 0

    for folder_index, target_dir in enumerate(sorted(files_by_target_dir), start=1):
        src_paths = files_by_target_dir[target_dir]
        attempted_files += len(src_paths)

        print(f"[{folder_index:>3}/{total_folders:<3} folders] 📁", end=" ")

        if rsync_folder_batch(src_paths, target_dir, current_file_index, total_files):
            completed_folders += 1
        else:
            failed_folders += 1

        current_file_index += len(src_paths)

    # Final summary
    print(f"\n🎉 Copy operation completed!")
    print(f"📈 Summary:")
    print(f"   • Files attempted: {attempted_files}")
    print(f"   • Target folders completed: {completed_folders}")
    print(f"   • Target folders failed: {failed_folders}")
    print("   • Existing remote files skipped by rsync --ignore-existing")

    # Clean up SSH connection
    cleanup_ssh_connection()

except KeyboardInterrupt:
    print("\n\n⛔️ Operation cancelled by user. Exiting cleanly.")
    cleanup_ssh_connection()
    sys.exit(0)
except Exception as e:
    print(f"\n❌ Unexpected error: {e}")
    cleanup_ssh_connection()
    sys.exit(1)
