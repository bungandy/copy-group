import os
import subprocess
import hashlib
from datetime import datetime
import sys
import tempfile
import json

# === CONFIGURATION ===
# Source path (SD card)
SDCARD_PATH = "/Volumes/Untitled/DCIM/"      # Your SD card path
# SDCARD_PATH = "/Users/andy/Documents/Scripts/copy-group/_test/"
# SDCARD_PATH = "/Users/andy/TRANSIT_BLACKBOX/_AWS/20250706 - Malaysia/"


# Update these values with your Synology NAS details

# Synology NAS connection details
SYNOLOGY_HOST = "192.168.1.123"     # Your Synology IP address
SYNOLOGY_USER = "andy"              # Your Synology username
SYNOLOGY_PORT = 22                  # SSH port (usually 22)

# Paths
SYNOLOGY_BASE_PATH = "/volume1/Photos/2025/" # Target path on Synology

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
        "-p", str(SYNOLOGY_PORT),
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-o", "ControlMaster=auto",
        "-o", "ControlPath=/tmp/ssh_mux_%h_%p_%r",
        "-o", "ControlPersist=5m",
        f"{SYNOLOGY_USER}@{SYNOLOGY_HOST}",
        command
    ]
    
    try:
        result = subprocess.run(ssh_cmd, capture_output=capture_output, text=True, timeout=30)
        return result
    except subprocess.TimeoutExpired:
        print(f"❌ SSH command timed out: {command}")
        return None
    except Exception as e:
        print(f"❌ SSH command failed: {e}")
        return None

def check_remote_file_exists(remote_path):
    """Check if a file exists on the remote Synology NAS."""
    command = f"test -f '{remote_path}' && echo 'exists' || echo 'not_exists'"
    result = run_ssh_command(command)
    if result and result.returncode == 0:
        return "exists" in result.stdout.strip()
    return False

def get_remote_file_info(remote_path):
    """Get file size and modification time from remote file."""
    command = f"stat -c '%s %Y' '{remote_path}' 2>/dev/null || echo '0 0'"
    result = run_ssh_command(command)
    if result and result.returncode == 0:
        try:
            size, mtime = result.stdout.strip().split()
            return int(size), int(mtime)
        except:
            pass
    return 0, 0

def count_files_to_copy(directory):
    """Count total number of files that will actually be copied (excluding duplicates)."""
    count = 0
    print("🔍 Scanning files and checking remote duplicates...")
    
    for root, _, files in os.walk(directory):
        for file in files:
            if file.startswith('.'):
                continue
                
            src_path = os.path.join(root, file)
            
            # Get creation time
            try:
                stat = os.stat(src_path)
                creation_time = stat.st_birthtime if hasattr(stat, "st_birthtime") else stat.st_ctime
            except Exception:
                continue

            # Format date folder
            date_folder = datetime.fromtimestamp(creation_time).strftime("%Y%m%d")
            remote_path = f"{SYNOLOGY_BASE_PATH}{date_folder}/{file}"
            
            # Check if remote file exists and is identical
            if check_remote_file_exists(remote_path):
                src_stat = os.stat(src_path)
                remote_size, remote_mtime = get_remote_file_info(remote_path)
                
                same_size = src_stat.st_size == remote_size
                same_mtime = int(src_stat.st_mtime) == remote_mtime
                
                if same_size and same_mtime:
                    # Files appear to be identical, skip
                    continue
            
            count += 1
    
    return count

def rsync_file_with_progress(src_path, date_folder, filename):
    """Copy a file to Synology using rsync with progress."""
    try:
        # Get source file size for progress calculation
        src_size = os.path.getsize(src_path)
        if src_size == 0:
            print(f"\r📁 Copying: {filename} (0 bytes)", end='', flush=True)
            # For zero-byte files, just create the remote directory and touch the file
            remote_dir = f"{SYNOLOGY_BASE_PATH}{date_folder}/"
            mkdir_cmd = f"mkdir -p '{remote_dir}'"
            mkdir_result = run_ssh_command(mkdir_cmd, capture_output=False)
            if mkdir_result and mkdir_result.returncode == 0:
                touch_cmd = f"touch '{remote_dir}{filename}'"
                touch_result = run_ssh_command(touch_cmd, capture_output=False)
                if touch_result and touch_result.returncode == 0:
                    print(f"\r\033[K\033[38;5;226m\033[1m✅ Copied: {filename} 100.0% (0 bytes)\033[0m")
                    return True
            return False
            
        # Create remote directory
        remote_dir = f"{SYNOLOGY_BASE_PATH}{date_folder}/"
        mkdir_cmd = f"mkdir -p '{remote_dir}'"
        mkdir_result = run_ssh_command(mkdir_cmd, capture_output=False)
        if mkdir_result and mkdir_result.returncode != 0:
            print(f"❌ Failed to create remote directory: {remote_dir}")
            return False
        
        # Build rsync command with progress parsing
        rsync_cmd = [
            "rsync",
            "-avz",                    # archive, verbose, compress
            "--progress",              # show progress
            "--partial",               # keep partial transfers
            "--inplace",               # update files in-place
            "--timeout=30",            # connection timeout
            "-e", f"ssh -p {SYNOLOGY_PORT} -o StrictHostKeyChecking=no -o ControlMaster=auto -o ControlPath=/tmp/ssh_mux_%h_%p_%r -o ControlPersist=5m",
            src_path,
            f"{SYNOLOGY_USER}@{SYNOLOGY_HOST}:{remote_dir}"
        ]
        
        # Show initial progress bar
        src_size_mb = src_size / (1024 * 1024)
        print(f"\r📀 Copying: [{'░' * 40}] 0.0% (0.0MB/{src_size_mb:.1f}MB) - {filename} ⠋", end='', flush=True)
        
        # Run rsync with real-time output
        process = subprocess.Popen(
            rsync_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # Monitor progress with fancy progress bar
        copied = 0
        last_percentage = 0
        
        if process.stdout:
            for line in process.stdout:
                line = line.strip()
                if line and not line.startswith('sending incremental file list'):
                    # Parse rsync progress output
                    if '%' in line:
                        # Extract percentage from rsync output
                        try:
                            # rsync format: "filename 1,234,567 100%    2.34MB/s    0:00:01"
                            # or: "1,234,567 100%    2.34MB/s    0:00:01"
                            parts = line.split()
                            for part in parts:
                                if '%' in part:
                                    percentage_str = part.replace('%', '')
                                    percentage = float(percentage_str)
                                    copied = int((percentage / 100) * src_size)
                                    break
                        except:
                            pass
                    
                    # Also try to parse bytes transferred from rsync output
                    if 'bytes sent' in line or 'bytes received' in line:
                        try:
                            # Look for patterns like "1,234,567 bytes sent" or "1,234,567 bytes received"
                            import re
                            match = re.search(r'(\d+(?:,\d+)*)\s+bytes', line)
                            if match:
                                bytes_str = match.group(1).replace(',', '')
                                copied = int(bytes_str)
                        except:
                            pass
                    
                    # Update progress bar (show even if copied is 0 to indicate start)
                    if copied >= 0:
                        # If we couldn't parse exact progress, show a moving indicator
                        if copied == 0:
                            # Show animated progress for small files or when parsing fails
                            import time
                            animated_progress = int((time.time() * 10) % 100)
                            percentage = min(animated_progress, 95)  # Don't show 100% until done
                            copied = int((percentage / 100) * src_size)
                        else:
                            percentage = (copied / src_size) * 100
                        bar_length = 40
                        filled_length = int(bar_length * copied // src_size)
                        
                        # Super fancy Grok-style progress bar with gradient colors
                        filled_blocks = filled_length
                        
                        # Red gradient color progression
                        colors = [
                            '\033[38;5;52m',   # Dark Red
                            '\033[38;5;88m',   # Red
                            '\033[38;5;124m',  # Medium Red
                            '\033[38;5;160m',  # Bright Red
                            '\033[38;5;196m',  # Vivid Red
                            '\033[38;5;202m',  # Orange-Red
                            '\033[38;5;208m',  # Orange
                            '\033[38;5;214m',  # Yellow-Orange
                            '\033[38;5;220m',  # Yellow
                            '\033[38;5;226m'   # Bright Yellow
                        ]
                        
                        # Build gradient bar
                        bar = ''
                        for i in range(filled_blocks):
                            color_idx = min(int((i / filled_blocks) * len(colors)), len(colors) - 1)
                            bar += colors[color_idx] + '█'
                        
                        # Add animated leading edge
                        if filled_blocks > 0:
                            edge_color = colors[min(int((filled_blocks / bar_length) * len(colors)), len(colors) - 1)]
                            edge_chars = ['▊', '▋', '▌', '▍', '▎', '▏']
                            edge_idx = int((copied / 8192) % len(edge_chars))
                            bar += edge_color + edge_chars[edge_idx]
                            filled_blocks += 1
                        
                        # Add remaining space with gradient fade
                        remaining = bar_length - filled_blocks
                        if remaining > 0:
                            bar += '\033[38;5;240m' + '░' * remaining
                        
                        # Reset color
                        bar += '\033[0m'
                        
                        # Add subtle animated indicator
                        indicator_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
                        indicator_idx = int((copied / (8192 * 8)) % len(indicator_chars))
                        indicator = indicator_chars[indicator_idx]
                        
                        # Format file size with fancy formatting
                        src_size_mb = src_size / (1024 * 1024)
                        copied_mb = copied / (1024 * 1024)
                        
                        # Add red-themed color to percentage
                        if percentage >= 100:
                            percentage_color = '\033[38;5;226m\033[1m'  # Bright yellow + bold
                        elif percentage >= 75:
                            percentage_color = '\033[38;5;220m\033[1m'  # Yellow + bold
                        elif percentage >= 50:
                            percentage_color = '\033[38;5;208m\033[1m'  # Orange + bold
                        else:
                            percentage_color = '\033[38;5;196m\033[1m'  # Vivid red + bold

                        print(f"\r📀 Copying: [{bar}] {percentage_color}{percentage:.1f}%\033[0m ({copied_mb:.1f}MB/{src_size_mb:.1f}MB) - {filename} {indicator}", end='\r', flush=True)
        
        process.wait()
        
        if process.returncode == 0:
            # Clear the entire line and show red-themed completion
            src_size_mb = src_size / (1024 * 1024)
            print(f"\r\033[K\033[38;5;226m\033[1m✅ Copied: {filename} 100.0% ({src_size_mb:.1f}MB/{src_size_mb:.1f}MB)\033[0m")
            return True
        else:
            print(f"\r❌ Failed to copy: {filename}")
            print()  # Print newline after each file
            return False
            
    except Exception as e:
        print(f"\r❌ Error copying {filename}: {e}")
        print() # Print newline after each file
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
            "-p", str(SYNOLOGY_PORT),
            "-o", "ControlMaster=auto",
            "-o", "ControlPath=/tmp/ssh_mux_%h_%p_%r",
            "-O", "exit",
            f"{SYNOLOGY_USER}@{SYNOLOGY_HOST}"
        ]
        subprocess.run(ssh_cmd, capture_output=True, timeout=10)
    except:
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
    
    # First, count total files for progress tracking
    total_files = count_files_to_copy(SDCARD_PATH)
    print(f"Found {total_files} files to copy")
    print()  # Add extra space above copying progress
    
    if total_files == 0:
        print("ℹ️ No files found to copy.")
        sys.exit(0)
    
    copied_files = 0
    skipped_files = 0
    
    for root, _, files in os.walk(SDCARD_PATH):
        for file in files:
            src_path = os.path.join(root, file)

            # Skip hidden files
            if file.startswith('.'):
                continue

            # Get creation time
            try:
                stat = os.stat(src_path)
                creation_time = stat.st_birthtime if hasattr(stat, "st_birthtime") else stat.st_ctime
            except Exception as e:
                print(f"\n⚠️ Skipping {src_path}: {e}")
                continue

            # Format date folder
            date_folder = datetime.fromtimestamp(creation_time).strftime("%Y%m%d")
            # date_folder = "20250706"
            remote_path = f"{SYNOLOGY_BASE_PATH}{date_folder}/{file}"

            # Skip if file already exists and is identical
            if check_remote_file_exists(remote_path):
                src_stat = os.stat(src_path)
                remote_size, remote_mtime = get_remote_file_info(remote_path)

                same_size = src_stat.st_size == remote_size
                same_mtime = int(src_stat.st_mtime) == remote_mtime
                
                # For efficiency, we'll skip MD5 check on remote files unless size/mtime differ
                if same_size and same_mtime:
                    print(f"⏩ Skipped (duplicate): {file}")
                    skipped_files += 1
                    continue

            # Copy the file with rsync
            if rsync_file_with_progress(src_path, date_folder, file):
                copied_files += 1
            else:
                print(f"❌ Failed to copy {file}")

    # Final summary
    print(f"\n🎉 Copy operation completed!")
    print(f"📈 Summary:")
    print(f"   • Files copied: {copied_files}")
    print(f"   • Files skipped (duplicates): {skipped_files}")

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
