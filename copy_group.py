import os
import shutil
import hashlib
from datetime import datetime
import sys

# === CONFIGURATION ===
SDCARD_PATH = "/Volumes/SDCARD/DCIM/"      # Update to your SD card path
TARGET_BASE = "/Users/andy/Photos/"       # Destination folder

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

def count_files_to_copy(directory, target_base):
    """Count total number of files that will actually be copied (excluding duplicates)."""
    count = 0
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
            target_dir = os.path.join(target_base, date_folder)
            dst_path = os.path.join(target_dir, file)

            # Only count if file doesn't exist or is different
            if not os.path.exists(dst_path):
                count += 1
            else:
                # Check if it's a duplicate
                try:
                    src_stat = os.stat(src_path)
                    dst_stat = os.stat(dst_path)
                    
                    same_size = src_stat.st_size == dst_stat.st_size
                    same_mtime = int(src_stat.st_mtime) == int(dst_stat.st_mtime)
                    
                    if not (same_size and same_mtime):
                        count += 1
                    # If size and mtime match, we'll do MD5 check during copy, but count it for now
                    else:
                        count += 1
                except Exception:
                    count += 1
    return count

def copy_file_with_progress(src_path, dst_path, filename=""):
    """Copy a file while showing real-time progress."""
    try:
        src_size = os.path.getsize(src_path)
        if src_size == 0:
            print(f"\r📁 Copying: {filename} (0 bytes)", end='', flush=True)
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
                        edge_idx = int((copied / chunk_size) % len(edge_chars))
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
                    indicator_idx = int((copied / (chunk_size * 8)) % len(indicator_chars))
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

                    print(f"\r📀 Copying: [{bar}] {percentage_color}{percentage:.1f}%\033[0m ({copied_mb:.1f}MB/{src_size_mb:.1f}MB) - {filename} {indicator}", end='', flush=True)
        
        # Preserve metadata
        shutil.copystat(src_path, dst_path)
        
        # Clear the entire line and show red-themed completion
        print(f"\r\033[K\033[38;5;226m\033[1m✅ Copied: {filename} 100.0% ({src_size_mb:.1f}MB/{src_size_mb:.1f}MB)\033[0m")
        return True
        
    except Exception as e:
        print(f"\r❌ Error copying {filename}: {e}")
        return False

# === CREATE TARGET BASE IF NOT EXISTS ===
os.makedirs(TARGET_BASE, exist_ok=True)

try:
    # First, count total files for progress tracking
    print("🔍 Scanning files...")
    total_files = count_files_to_copy(SDCARD_PATH, TARGET_BASE)
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
            target_dir = os.path.join(TARGET_BASE, date_folder)
            os.makedirs(target_dir, exist_ok=True)

            dst_path = os.path.join(target_dir, file)

            # Skip if file already exists and is identical
            if os.path.exists(dst_path):
                src_stat = os.stat(src_path)
                dst_stat = os.stat(dst_path)

                same_size = src_stat.st_size == dst_stat.st_size
                same_mtime = int(src_stat.st_mtime) == int(dst_stat.st_mtime)
                same_checksum = get_md5(src_path) == get_md5(dst_path)

                if same_size and same_mtime and same_checksum:
                    print(f"\r⏩ Skipped (duplicate): {file}")
                    skipped_files += 1
                    continue

            # Copy the file with progress
            if copy_file_with_progress(src_path, dst_path, file):
                copied_files += 1
            else:
                print(f"\r❌ Failed to copy {file}")

    # Final summary
    print(f"\n🎉 Copy operation completed!")
    print(f"📈 Summary:")
    print(f"   • Files copied: {copied_files}")
    print(f"   • Files skipped (duplicates): {skipped_files}")

except KeyboardInterrupt:
    print("\n\n⛔️ Operation cancelled by user. Exiting cleanly.")
    sys.exit(0)
