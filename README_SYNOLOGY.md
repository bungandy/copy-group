# Synology Photo Backup Script

This script copies photos from an SD card to a Synology NAS using rsync over SSH, organizing files by date.

## Features

- ✅ **Secure SSH transfer** using rsync
- ✅ **Date-based organization** (YYYYMMDD folders)
- ✅ **Duplicate detection** (skips identical files)
- ✅ **Progress tracking** with rsync output
- ✅ **Resume capability** (partial transfers)
- ✅ **Compression** for faster transfers
- ✅ **Metadata preservation**

## Prerequisites

1. **Synology NAS with SSH enabled**
2. **SSH password authentication** enabled
3. **Python 3.6+** on your local machine
4. **rsync** installed on both local and remote machines

## Setup Instructions

### 1. Enable SSH on Synology NAS

1. Open **DSM** (Synology's web interface)
2. Go to **Control Panel** > **Terminal & SNMP**
3. Enable **SSH service**
4. Set port (default: 22)
5. Click **Apply**

### 2. Enable Password Authentication

1. In DSM, go to **Control Panel** > **Terminal & SNMP**
2. Make sure **SSH service** is enabled
3. Ensure **Password authentication** is allowed (default)

### 3. Test SSH Connection

```bash
ssh your_username@192.168.1.100
```

### 5. Configure the Script

Edit `synology_config.py` and update these values:

```python
# Your Synology NAS details
SYNOLOGY_HOST = "192.168.1.100"              # Your Synology IP
SYNOLOGY_USER = "your_username"              # Your username
SYNOLOGY_PORT = 22                           # SSH port

# Paths
SYNOLOGY_BASE_PATH = "/volume1/photo_backup/" # Target folder on Synology
SDCARD_PATH = "/Volumes/Untitled/DCIM/"      # Your SD card path
```

## Usage

1. **Insert your SD card** into your computer
2. **Mount the SD card** (it should appear as `/Volumes/Untitled/` on macOS)
3. **Run the script**:

```bash
python3 copy_group_synology.py
```

## What the Script Does

1. **Tests SSH connection** to your Synology NAS
2. **Scans your SD card** for photos and videos
3. **Checks for duplicates** on the remote NAS
4. **Organizes files by date** (YYYYMMDD folders)
5. **Copies files using rsync** with progress display
6. **Skips identical files** to save time and bandwidth

## File Organization

Files are organized on your Synology NAS like this:

```
/volume1/photo_backup/
├── 20241201/
│   ├── IMG_001.jpg
│   ├── IMG_002.jpg
│   └── VID_001.mp4
├── 20241202/
│   ├── IMG_003.jpg
│   └── VID_002.mp4
└── ...
```

## Troubleshooting

### SSH Connection Issues

- **Check IP address**: Ensure `SYNOLOGY_HOST` is correct
- **Verify SSH is enabled**: Check DSM Control Panel
- **Test manually**: Try `ssh your_username@192.168.1.100`
- **Check password**: Ensure your password is correct

### Permission Issues

- **Check user permissions**: Ensure your user has write access to the target folder
- **Create target folder**: Make sure `/volume1/photo_backup/` exists on Synology

### SD Card Not Found

- **Check mount point**: Update `SDCARD_PATH` to match your SD card location
- **Verify card is mounted**: Check `/Volumes/` directory

### rsync Not Found

- **Install rsync**: On macOS: `brew install rsync`
- **Check remote rsync**: Ensure rsync is available on Synology (usually pre-installed)

## Performance Tips

- **Use wired connection** for faster transfers
- **Close other applications** to free up bandwidth
- **Consider network speed** - large files may take time
- **Use compression** (already enabled with `-z` flag)

## Security Notes

- **Password authentication** is used for SSH access
- **Use a strong password** for your Synology account
- **Use a dedicated user account** on Synology for backups
- **Consider firewall rules** to restrict SSH access

## Example Output

```
🔐 Testing SSH connection to Synology...
✅ SSH connection successful!
🔍 Scanning files and checking remote duplicates...
Found 45 files to copy

📀 Copying: IMG_001.jpg
  IMG_001.jpg
     1,234,567 100%    2.34MB/s    0:00:01
✅ Copied: IMG_001.jpg

⏩ Skipped (duplicate): IMG_002.jpg

🎉 Copy operation completed!
📈 Summary:
   • Files copied: 42
   • Files skipped (duplicates): 3
``` 