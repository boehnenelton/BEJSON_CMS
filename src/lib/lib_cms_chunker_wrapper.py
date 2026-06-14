import os
import sys
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Add Lib to path
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)

import lib_mfdb_chunker_v6 as ChunkerV6

class CMS_Chunker_Wrapper:
    def __init__(self, cms_manager):
        self.cms = cms_manager
        self.www_root = Path(cms_manager.www_root)
        self.backup_dir = Path(cms_manager.data_root) / "backups"
        if not self.backup_dir.exists():
            self.backup_dir.mkdir(parents=True)

    def backup_site(self, changelog: str = "Automated CMS Backup", tags: str = "backup,cms"):
        """Chunk the www_root and export as a zip."""
        try:
            # 1. Perform Chunking
            # Note: ChunkerV6 creates .mfdb/ folder inside target_dir
            result = ChunkerV6.do_chunk(str(self.www_root), changelog=changelog, tags=tags)
            if not result.get("ok"):
                return {"success": False, "error": result.get("message")}

            detail = result.get("detail", {})
            version = detail.get("version")
            manifest_path = detail.get("manifest")
            
            # 2. Export as Zip to backups folder
            timestamp = ChunkerV6.get_timestamp()
            zip_filename = f"site_backup_{version}_{timestamp}.zip"
            zip_path = self.backup_dir / zip_filename
            
            export_result = ChunkerV6.do_export(str(manifest_path), version, str(zip_path))
            if export_result.get("ok"):
                # 3. Automatic Bump for next backup
                ChunkerV6.do_bump(str(self.www_root), part="patch")
                return {"success": True, "zip_path": str(zip_path), "version": version, "message": "Site chunked and exported successfully."}
            else:
                return {"success": False, "error": export_result.get("message")}
                
        except Exception as e:
            return {"success": False, "error": str(e)}

    def restore_site(self, zip_filename: str):
        """Import a zip and unchunk to www_root."""
        try:
            zip_path = self.backup_dir / zip_filename
            if not zip_path.exists():
                return {"success": False, "error": f"Backup file not found: {zip_filename}"}

            # Create a clean temp workspace
            restore_workspace = self.www_root.parent / ".restore_workspace"
            if restore_workspace.exists(): shutil.rmtree(restore_workspace)
            restore_workspace.mkdir(parents=True)
            (restore_workspace / "data").mkdir()
            
            temp_manifest = restore_workspace / "104a.mfdb.bejson"
            
            # 1. Import Zip
            import_result = ChunkerV6.do_import(str(temp_manifest), str(zip_path), overwrite=True)
            if not import_result.get("ok"):
                return {"success": False, "error": import_result.get("message")}
            
            # 2. Get version from imported manifest
            versions = ChunkerV6.list_versions(str(temp_manifest))
            if not versions:
                return {"success": False, "error": "No versions found in backup zip."}
            
            target_version = versions[0]["version"] # Take latest/first
            
            # 3. Unchunk
            unchunk_result = ChunkerV6.do_unchunk(str(temp_manifest), target_version)
            if not unchunk_result.get("ok"):
                return {"success": False, "error": unchunk_result.get("message")}
            
            restored_files_dir = Path(unchunk_result.get("out_dir"))
            
            # 4. Swap www_root content
            for item in self.www_root.iterdir():
                if item.name == ".restore_workspace" or item.name == ".mfdb": continue
                if item.is_dir(): shutil.rmtree(item)
                else: item.unlink()
            
            for item in restored_files_dir.iterdir():
                shutil.move(str(item), str(self.www_root / item.name))
            
            # Cleanup
            shutil.rmtree(restore_workspace)
            
            return {"success": True, "message": f"Site restored to version {target_version}"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_backups(self):
        """List available zip backups in the backup folder."""
        if not self.backup_dir.exists():
            return []
        
        backups = []
        for f in self.backup_dir.glob("*.zip"):
            stats = f.stat()
            backups.append({
                "filename": f.name,
                "size_kb": round(stats.st_size / 1024, 2),
                "mtime": datetime.fromtimestamp(stats.st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M")
            })
        return sorted(backups, key=lambda x: x["mtime"], reverse=True)

